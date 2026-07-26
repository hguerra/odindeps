#+vet explicit-allocators
package slog

// Hand-rolled streaming JSON encoder shared by the generic, GCP, and AWS
// handlers. It writes directly into a per-call strings.Builder (no intermediate
// core:encoding/json value/map), because key ordering matters for the special
// GCP/AWS fields and an intermediate map would allocate and reorder.
//
// Correctness rules (SPEC "JSON encoding"):
//   - escape exactly RFC 8259's required set; valid UTF-8 above U+001F passes
//     through unescaped (no per-byte \uXXXX that would corrupt multibyte runes);
//   - numbers via core:strconv; non-finite f64 (NaN, ±Inf) → null;
//   - the nil Value variant → null; empty groups are elided;
//   - timestamps are UTC with a trailing Z.

import "core:fmt"
import "core:io"
import "core:math"
import "core:mem"
import "core:strconv"
import "core:strings"
import "core:time"
import "core:unicode/utf8"

@(private = "file")
hex_digit :: proc(nibble: byte) -> byte {
	return nibble < 10 ? '0' + nibble : 'a' + (nibble - 10)
}

// json_write_escaped writes the RFC-8259-escaped contents of s (without the
// surrounding quotes). Only the required set is escaped; a valid multibyte
// UTF-8 rune is written verbatim. Odin `string`s are byte spans, not
// guaranteed-valid UTF-8 — a byte >= 0x80 that does not start (or complete) a
// well-formed rune is replaced with U+FFFD (the Unicode replacement
// character) rather than passed through raw, so the output is always valid
// UTF-8 inside a JSON string even if the input wasn't.
@(private)
json_write_escaped :: proc(b: ^strings.Builder, s: string) {
	i := 0
	for i < len(s) {
		c := s[i]
		if c < 0x80 {
			switch c {
			case '"':
				strings.write_string(b, "\\\"")
			case '\\':
				strings.write_string(b, "\\\\")
			case '\n':
				strings.write_string(b, "\\n")
			case '\t':
				strings.write_string(b, "\\t")
			case '\r':
				strings.write_string(b, "\\r")
			case '\b':
				strings.write_string(b, "\\b")
			case '\f':
				strings.write_string(b, "\\f")
			case:
				if c < 0x20 {
					strings.write_string(b, "\\u00")
					strings.write_byte(b, hex_digit(c >> 4))
					strings.write_byte(b, hex_digit(c & 0xf))
				} else {
					strings.write_byte(b, c)
				}
			}
			i += 1
		} else {
			r, size := utf8.decode_rune(s[i:])
			if r == utf8.RUNE_ERROR && size <= 1 {
				strings.write_rune(b, utf8.RUNE_ERROR) // malformed byte sequence
			} else {
				strings.write_string(b, s[i:i + size])
			}
			i += size
		}
	}
}

// json_write_quoted writes s as a quoted, escaped JSON string.
@(private)
json_write_quoted :: proc(b: ^strings.Builder, s: string) {
	strings.write_byte(b, '"')
	json_write_escaped(b, s)
	strings.write_byte(b, '"')
}

// format_any renders an arbitrary value as a string via %v. It is the single
// routine used both by the emit path (the `any` Value variant) and by `with`
// when it snapshots a bound `any`, so both paths render identically.
@(private)
format_any :: proc(v: any, allocator: mem.Allocator) -> string {
	return fmt.aprintf("%v", v, allocator = allocator)
}

// write_number writes the i64/u64/f64 variants bare (unquoted). Non-finite
// floats (NaN, ±Inf) become null, and the '+' sign strconv emits for positive
// floats is stripped (JSON permits '-' only). Shared by the JSON and text
// handlers so their numeric formatting can never diverge.
@(private)
write_number :: proc(b: ^strings.Builder, v: Value) {
	#partial switch val in v {
	case i64:
		buf: [32]byte
		strings.write_string(b, strconv.write_int(buf[:], val, 10))
	case u64:
		buf: [32]byte
		strings.write_string(b, strconv.write_uint(buf[:], val, 10))
	case f64:
		if math.is_nan(val) || math.is_inf(val) {
			strings.write_string(b, "null")
		} else {
			buf: [40]byte
			s := strconv.write_float(buf[:], val, 'g', -1, 64)
			if len(s) > 0 && s[0] == '+' {
				s = s[1:]
			}
			strings.write_string(b, s)
		}
	}
}

// json_write_value writes a single Value. Transient allocations (formatting an
// `any`) use temp.
@(private)
json_write_value :: proc(b: ^strings.Builder, v: Value, temp: mem.Allocator) {
	switch val in v {
	case string:
		json_write_quoted(b, val)
	case i64, u64, f64:
		write_number(b, v)
	case bool:
		strings.write_string(b, val ? "true" : "false")
	case time.Time:
		strings.write_byte(b, '"')
		format_rfc3339(b, val)
		strings.write_byte(b, '"')
	case time.Duration:
		buf: [32]byte
		strings.write_string(b, strconv.write_int(buf[:], i64(val), 10))
	case []Attr:
		json_write_group(b, val, temp)
	case any:
		s := format_any(val, temp)
		json_write_quoted(b, s)
	case:
		strings.write_string(b, "null") // nil variant
	}
}

// attr_is_empty_group reports whether an attr is a group with no non-elided
// members (so it should be elided entirely, matching Go's slog). The check is
// recursive: a group whose members are all empty groups is itself empty.
@(private)
attr_is_empty_group :: proc(a: Attr) -> bool {
	members, is_group := a.value.([]Attr)
	if !is_group {
		return false
	}
	for m in members {
		if !attr_is_empty_group(m) {
			return false
		}
	}
	return true
}

// json_write_attr_comma writes `,"key":value` for one attr, assuming a field
// already precedes it. Empty groups are elided (nothing is written). This is the
// single choke point every handler routes user attrs through.
@(private)
json_write_attr_comma :: proc(b: ^strings.Builder, a: Attr, temp: mem.Allocator) {
	if attr_is_empty_group(a) {
		return
	}
	strings.write_byte(b, ',')
	json_write_quoted(b, a.key)
	strings.write_byte(b, ':')
	json_write_value(b, a.value, temp)
}

// json_write_group writes attrs as a JSON object, eliding empty groups.
@(private)
json_write_group :: proc(b: ^strings.Builder, attrs: []Attr, temp: mem.Allocator) {
	strings.write_byte(b, '{')
	first := true
	for a in attrs {
		if attr_is_empty_group(a) {
			continue
		}
		if !first {
			strings.write_byte(b, ',')
		}
		first = false
		json_write_quoted(b, a.key)
		strings.write_byte(b, ':')
		json_write_value(b, a.value, temp)
	}
	strings.write_byte(b, '}')
}

// write_pad_int writes an integer left-padded with zeros to width. The month/
// day/hour/minute/second/millisecond fields time.date/time.clock_from_time
// produce are always non-negative, but the year is not for a Time constructed
// from a large enough negative nanosecond count (a pre-epoch, pre-year-1
// timestamp); a bare `strconv.write_int` would place the zero padding before
// the sign (e.g. "00-1"), so the sign is written first and the magnitude
// padded separately.
@(private = "file")
write_pad_int :: proc(b: ^strings.Builder, value, width: int) {
	v := value
	if v < 0 {
		strings.write_byte(b, '-')
		v = -v
	}
	buf: [20]byte
	s := strconv.write_int(buf[:], i64(v), 10)
	for _ in len(s) ..< width {
		strings.write_byte(b, '0')
	}
	strings.write_string(b, s)
}

// write_utc_date_time writes YYYY-MM-DDTHH:MM:SS from a UTC Time. Odin's
// time.date/clock compute calendar fields directly from the absolute unix
// instant, i.e. already in UTC, so no timezone conversion is needed.
@(private = "file")
write_utc_date_time :: proc(b: ^strings.Builder, t: time.Time) {
	year, month, day := time.date(t)
	hour, min, sec := time.clock_from_time(t)
	write_pad_int(b, year, 4)
	strings.write_byte(b, '-')
	write_pad_int(b, int(month), 2)
	strings.write_byte(b, '-')
	write_pad_int(b, day, 2)
	strings.write_byte(b, 'T')
	write_pad_int(b, hour, 2)
	strings.write_byte(b, ':')
	write_pad_int(b, min, 2)
	strings.write_byte(b, ':')
	write_pad_int(b, sec, 2)
}

// format_rfc3339 writes an RFC-3339 UTC timestamp with a trailing Z (GCP `time`).
@(private)
format_rfc3339 :: proc(b: ^strings.Builder, t: time.Time) {
	write_utc_date_time(b, t)
	strings.write_byte(b, 'Z')
}

// format_iso8601_ms writes an ISO-8601 UTC timestamp with exactly three
// fractional (millisecond) digits and a trailing Z (AWS `timestamp`).
@(private)
format_iso8601_ms :: proc(b: ^strings.Builder, t: time.Time) {
	write_utc_date_time(b, t)
	_, _, _, nanos := time.precise_clock_from_time(t)
	strings.write_byte(b, '.')
	write_pad_int(b, nanos / 1_000_000, 3)
	strings.write_byte(b, 'Z')
}

// ---- generic JSON handler ----

// create_json_handler builds a handler that formats each record as one JSON
// line: {time, level, message, source?, <attrs>}. It never owns the writer.
create_json_handler :: proc(
	w: io.Writer,
	level := LEVEL_INFO,
	opts := Handler_Options{},
	allocator := context.allocator,
) -> Handler {
	state := new(Handler_State, allocator)
	state.writer = w
	state.options = opts
	state.level = level
	return Handler {
		procedure = json_handler_proc,
		data = state,
		level = level,
		level_ptr = &state.level,
		error_count_ptr = &state.write_errors,
	}
}

@(private)
json_handler_proc :: proc(data: rawptr, record: Record, temp: mem.Allocator) {
	state := cast(^Handler_State)data
	b: strings.Builder
	strings.builder_init(&b, temp)
	json_write_record(&b, record, state.options, temp)
	handler_write_line(state, strings.to_string(b))
}

// json_write_record writes the full record object plus a trailing newline. The
// fixed fields (time, level, message, source) precede the user attrs.
@(private)
json_write_record :: proc(
	b: ^strings.Builder,
	record: Record,
	opts: Handler_Options,
	temp: mem.Allocator,
) {
	strings.write_byte(b, '{')

	json_write_quoted(b, "time")
	strings.write_byte(b, ':')
	strings.write_byte(b, '"')
	format_rfc3339(b, record.time)
	strings.write_byte(b, '"')

	strings.write_byte(b, ',')
	json_write_quoted(b, "level")
	strings.write_byte(b, ':')
	json_write_quoted(b, level_name(record.level))

	strings.write_byte(b, ',')
	json_write_quoted(b, "message")
	strings.write_byte(b, ':')
	json_write_quoted(b, record.message)

	if !opts.omit_source {
		strings.write_byte(b, ',')
		json_write_quoted(b, "source")
		strings.write_byte(b, ':')
		json_write_source(b, record.source)
	}

	// apply_replace_attr runs first: replace_attr is a caller-supplied hook that
	// can rename an attr's key to anything, including a reserved name, so
	// filter_reserved runs LAST — after the hook — to catch a collision it
	// introduces, not just one the caller wrote directly. Running it first only
	// would let a replace_attr hook reintroduce this exact spoof one layer up.
	attrs := apply_replace_attr(record.attrs, nil, opts.replace_attr, temp)
	attrs = filter_reserved(attrs, {"time", "level", "message", "source"}, temp)
	for a in attrs {
		json_write_attr_comma(b, a, temp)
	}

	strings.write_byte(b, '}')
	strings.write_byte(b, '\n')
}

// json_write_source writes the generic source object {file, line, procedure};
// the generic handler emits line as a JSON number (GCP quotes it separately).
@(private)
json_write_source :: proc(b: ^strings.Builder, s: Source) {
	strings.write_byte(b, '{')
	json_write_quoted(b, "file")
	strings.write_byte(b, ':')
	json_write_quoted(b, s.file)
	strings.write_byte(b, ',')
	json_write_quoted(b, "line")
	strings.write_byte(b, ':')
	buf: [32]byte
	strings.write_string(b, strconv.write_int(buf[:], i64(s.line), 10))
	strings.write_byte(b, ',')
	json_write_quoted(b, "procedure")
	strings.write_byte(b, ':')
	json_write_quoted(b, s.procedure)
	strings.write_byte(b, '}')
}
