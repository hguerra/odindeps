#+vet explicit-allocators
package slog

// Text/console handler for local development. Each record is one line:
//   TIME LEVEL msg key=value key2=value2 …
// Groups flatten to dotted keys (g.h.key=value), consistent with the JSON
// handler's nesting. When Handler_Options.color is set, the level header is
// wrapped in an ANSI color per level, mirroring core:log's console logger.

import "core:io"
import "core:mem"
import "core:strconv"
import "core:strings"
import "core:time"

@(private = "file")
ANSI_RESET :: "\x1b[0m"

create_text_handler :: proc(
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
		procedure = text_handler_proc,
		data = state,
		level = level,
		level_ptr = &state.level,
		error_count_ptr = &state.write_errors,
	}
}

@(private = "file")
text_level_color :: proc(l: Level) -> string {
	switch {
	case l >= LEVEL_ERROR:
		return "\x1b[31m" // red
	case l >= LEVEL_WARN:
		return "\x1b[33m" // yellow
	case l >= LEVEL_INFO:
		return "\x1b[32m" // green
	case:
		return "\x1b[90m" // bright black (debug)
	}
}

// text_write_value writes a value in bare (unquoted) text form.
@(private = "file")
text_write_value :: proc(b: ^strings.Builder, v: Value, temp: mem.Allocator) {
	switch val in v {
	case string:
		strings.write_string(b, val)
	case i64, u64, f64:
		write_number(b, v)
	case bool:
		strings.write_string(b, val ? "true" : "false")
	case time.Time:
		format_rfc3339(b, val)
	case time.Duration:
		buf: [32]byte
		strings.write_string(b, strconv.write_int(buf[:], i64(val), 10))
	case any:
		strings.write_string(b, format_any(val, temp))
	case []Attr:
	// groups are flattened by text_write_attrs; never reached here
	case:
		strings.write_string(b, "null") // nil variant
	}
}

// text_write_attrs flattens attrs into space-separated key=value tokens, groups
// contributing a dotted prefix. Empty groups are elided.
@(private = "file")
text_write_attrs :: proc(b: ^strings.Builder, attrs: []Attr, prefix: string, temp: mem.Allocator) {
	for a in attrs {
		if attr_is_empty_group(a) {
			continue
		}
		if group, ok := a.value.([]Attr); ok {
			sub := strings.concatenate({prefix, a.key, "."}, temp)
			text_write_attrs(b, group, sub, temp)
		} else {
			strings.write_byte(b, ' ')
			strings.write_string(b, prefix)
			strings.write_string(b, a.key)
			strings.write_byte(b, '=')
			text_write_value(b, a.value, temp)
		}
	}
}

@(private = "file")
text_handler_proc :: proc(data: rawptr, record: Record, temp: mem.Allocator) {
	state := cast(^Handler_State)data
	b: strings.Builder
	strings.builder_init(&b, temp)

	format_rfc3339(&b, record.time)
	strings.write_byte(&b, ' ')

	if state.options.color {
		strings.write_string(&b, text_level_color(record.level))
		strings.write_string(&b, level_name(record.level))
		strings.write_string(&b, ANSI_RESET)
	} else {
		strings.write_string(&b, level_name(record.level))
	}

	strings.write_byte(&b, ' ')
	strings.write_string(&b, record.message)

	attrs := apply_replace_attr(record.attrs, nil, state.options.replace_attr, temp)
	text_write_attrs(&b, attrs, "", temp)

	strings.write_byte(&b, '\n')
	handler_write_line(state, strings.to_string(b))
}
