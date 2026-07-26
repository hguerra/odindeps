#+vet explicit-allocators
package slog

import "base:intrinsics"
import "core:mem"
import "core:time"

// ---- levels ----

// Level is a `distinct i32` (not a closed enum) so custom intermediate levels
// are legal and the full GCP severity ladder is reachable, exactly like Go's
// `slog.Level` (a named int).
Level :: distinct i32

LEVEL_DEBUG :: Level(-4) // Go slog values; gaps allow custom intermediate levels
LEVEL_INFO :: Level(0)
LEVEL_NOTICE :: Level(2) // GCP NOTICE
LEVEL_WARN :: Level(4)
LEVEL_ERROR :: Level(8)
LEVEL_CRITICAL :: Level(12) // GCP CRITICAL
LEVEL_ALERT :: Level(16) // GCP ALERT
LEVEL_EMERGENCY :: Level(20) // GCP EMERGENCY

// level_severity maps a Level to the nearest GCP severity band, so a custom
// value such as Level(2) still resolves to a valid severity string.
level_severity :: proc(l: Level) -> string {
	switch {
	case l >= LEVEL_EMERGENCY:
		return "EMERGENCY"
	case l >= LEVEL_ALERT:
		return "ALERT"
	case l >= LEVEL_CRITICAL:
		return "CRITICAL"
	case l >= LEVEL_ERROR:
		return "ERROR"
	case l >= LEVEL_WARN:
		return "WARNING"
	case l >= LEVEL_NOTICE:
		return "NOTICE"
	case l >= LEVEL_INFO:
		return "INFO"
	case:
		return "DEBUG"
	}
}

// ---- values, attributes ----

// Value is a tagged union mirroring Go's slog.Value. The []Attr variant is a
// group (nested object); a slice keeps the union representable without a
// self-referential by-value member. The nil variant (a zero Value) renders as
// JSON `null`.
Value :: union {
	string, // borrowed at call sites; cloned by `with`
	i64,
	u64, // large IDs > 2^63 must not wrap negative
	f64,
	bool,
	time.Time,
	time.Duration,
	[]Attr, // a group (nested object)
	any, // escape hatch: formatted via reflection at emit time
}

// Attr is the unit of structured data. A zero value (the nil variant) renders
// as JSON `null` (never a bare `"key":`).
Attr :: struct {
	key:   string,
	value: Value,
}

// Source is the call-site location captured from #caller_location.
Source :: struct {
	file:      string,
	line:      i32,
	procedure: string,
}

attr_string :: proc(key: string, val: string) -> Attr {
	return Attr{key = key, value = val}
}

// attr_num widens any integer to i64/u64 and any float to f64. A single generic
// numeric constructor keeps the `attr` proc group unambiguous and ensures large
// unsigned IDs (> 2^63) are stored as u64 rather than wrapping to a negative i64.
// time.Duration is a `distinct i64` (hence numeric) but is excluded here so the
// concrete attr_duration wins in the proc group and keeps its dedicated variant.
attr_num :: proc(key: string, val: $T) -> Attr where intrinsics.type_is_numeric(T),
	T != time.Duration {
	when intrinsics.type_is_integer(T) {
		when intrinsics.type_is_unsigned(T) {
			return Attr{key = key, value = u64(val)}
		} else {
			return Attr{key = key, value = i64(val)}
		}
	} else when intrinsics.type_is_float(T) {
		return Attr{key = key, value = f64(val)}
	} else {
		#panic("attr_num supports only integer and float types")
	}
}

attr_bool :: proc(key: string, val: bool) -> Attr {
	return Attr{key = key, value = val}
}

attr_time :: proc(key: string, val: time.Time) -> Attr {
	return Attr{key = key, value = val}
}

attr_duration :: proc(key: string, val: time.Duration) -> Attr {
	return Attr{key = key, value = val}
}

// attr_any is the reflection escape hatch; it renders as a JSON string via `%v`.
// It is intentionally excluded from the `attr` proc group — numeric intent uses
// attr_num, not any.
attr_any :: proc(key: string, val: any) -> Attr {
	return Attr{key = key, value = val}
}

// attr resolves unambiguously across string/numeric/bool/time/duration: the
// concrete-typed members win over the polymorphic attr_num, so time values do
// not collide with numeric widening.
attr :: proc {
	attr_string,
	attr_num,
	attr_bool,
	attr_time,
	attr_duration,
}

// group builds a nested-object attr. Call-site groups default to the temp
// allocator (freed at the call boundary); `with` re-clones into the logger
// allocator. Members sharing a key are last-wins deduplicated (mirroring the
// encoder's own duplicate-key rule) and copied into a stable slice owned by
// the returned Attr, rather than borrowing the call's temporary storage.
//
// Deduplication here is flat, not recursive: if two args share a key and are
// both groups, the LAST one wins whole — its members are not merged with the
// first's. This deliberately differs from the recursive group-merge
// `merge_attrs` performs internally for logger record resolution, which is
// only safe there because that merge always runs under one temp-scoped
// allocator reclaimed as a unit. `group()`'s allocator is caller-overridable
// to a persistent one, where a recursive merge would allocate a third array
// and orphan both original groups' backing arrays; flat replacement allocates
// no third array, so it orphans at most the ONE superseded value.
//
// Value has no ownership metadata, so `group()` cannot free that superseded
// value itself — under the default temp allocator this is always moot
// (everything is reclaimed at the call boundary regardless); it only matters
// if you override `allocator` to a persistent one AND pass two args that are
// THEMSELVES separately-allocated groups sharing a key, a narrow, deliberately
// constructed scenario. The common case this fixes — duplicate SCALAR keys,
// e.g. `group("g", attr("x",1), attr("x",2))` — has no leak risk under any
// allocator, since a discarded scalar was always a caller-owned borrow, never
// something `group()` itself allocated.
group :: proc(key: string, args: ..Attr, allocator := context.temp_allocator) -> Attr {
	return Attr{key = key, value = dedupe_flat_last_wins(args, allocator)}
}

// dedupe_flat_last_wins keeps, for each key, only the last occurrence in
// attrs (at its first-seen position), without recursively merging duplicate
// group values. See `group`'s doc comment for why this is not `merge_attrs`.
@(private = "file")
dedupe_flat_last_wins :: proc(attrs: []Attr, allocator: mem.Allocator) -> []Attr {
	out := make([dynamic]Attr, 0, len(attrs), allocator)
	outer: for a in attrs {
		for &existing in out {
			if existing.key == a.key {
				existing.value = a.value // last-wins, no recursive merge
				continue outer
			}
		}
		append(&out, a)
	}
	return out[:]
}
