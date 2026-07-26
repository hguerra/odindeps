#+vet explicit-allocators
package slog

import "core:io"
import "core:mem"
import "core:sync"
import "core:time"

// A handler is a struct of {procedure, data, level, level_ptr, error_count_ptr},
// the same base shape as core:log.Logger plus level_ptr/error_count_ptr. The
// procedure formats+writes one Record; data is the handler-specific backing
// (opaque — never reinterpreted by this package outside the handler that
// created it); level is the minimum level (records below it are dropped by
// the emit path before any formatting).
//
// level_ptr and error_count_ptr, when non-nil, are the ONLY way runtime state
// (the live level, the write-error counter) is exposed for a Handler: every
// create_*_handler in this package points both at cells inside its own
// Handler_State, so set_handler_level/handler_error_count can observe and
// change that state at runtime, and have every Logger derived from this
// Handler (each holds its own COPY of this struct, hence the indirection)
// see it immediately. Neither ever reinterprets `data` — a hand-built Handler
// with `data` pointing at a caller-defined type (a supported pattern; `data`
// is documented as opaque) is safe to pass to either accessor even with
// level_ptr/error_count_ptr left nil, which is simply a no-op/zero read
// rather than a crash.
Handler :: struct {
	procedure:       Handler_Proc,
	data:            rawptr,
	level:           Level,
	level_ptr:       ^Level,
	error_count_ptr: ^u64,
}

// handler_level returns the handler's current minimum level: the live value
// behind level_ptr if set (read with an atomic load, since set_handler_level
// may run concurrently from another thread), otherwise the fixed by-value
// level.
handler_level :: proc(h: Handler) -> Level {
	if h.level_ptr != nil {
		return sync.atomic_load(h.level_ptr)
	}
	return h.level
}

// set_handler_level changes a handler's minimum level at runtime — e.g.
// enabling debug logging without a redeploy. It only has an effect when the
// Handler carries a level_ptr (every create_*_handler in this package sets
// one); on a hand-built Handler with level_ptr == nil this is a silent no-op,
// since there is no shared cell for every derived Logger's copy to observe.
set_handler_level :: proc(h: Handler, level: Level) {
	if h.level_ptr != nil {
		sync.atomic_store(h.level_ptr, level)
	}
}

Handler_Proc :: #type proc(data: rawptr, record: Record, temp: mem.Allocator)

// Handler_Options has a useful zero value: source included, color off, no
// replace_attr, no on_error. omit_source flips source off; replace_attr
// renames/redacts/drops attrs (nil means identity); on_error is called after
// the handler mutex is released whenever a full-line write fails or is short
// (nil means the failure is silently counted only, see handler_error_count).
// on_error_data is passed through to on_error unchanged — a caller-owned
// pointer (a metrics counter, an alert channel, ...), so on_error need not
// resort to a package-level global to carry state, mirroring Handler_Proc's
// own `data: rawptr` convention.
Handler_Options :: struct {
	omit_source:   bool, // zero = include the #caller_location source
	color:         bool, // text handler only
	replace_attr:  proc(groups: []string, a: Attr) -> (Attr, bool),
	on_error:      proc(err: io.Error, data: rawptr),
	on_error_data: rawptr,
}

// Record is built by the logger and formatted by the handler. attrs is the
// resolved set: the logger's bound attrs plus the call-site attrs, under the
// logger's group stack.
Record :: struct {
	time:    time.Time,
	level:   Level,
	message: string,
	source:  Source,
	attrs:   []Attr,
}

// Handler_State is the shared backing every encoding handler allocates. It holds
// the caller's writer (never owned or closed here), a mutex guarding the single
// full-line write so concurrent records never interleave, the options, a
// counter of failed/short writes readable via handler_error_count, and the
// live level cell every derived Logger's Handler.level_ptr points at.
@(private)
Handler_State :: struct {
	writer:       io.Writer,
	mutex:        sync.Mutex,
	options:      Handler_Options,
	write_errors: u64,
	level:        Level,
}

// MAX_ZERO_PROGRESS_WRITES bounds write_full_bounded's retry loop: a Writer
// that returns (0, nil) — a legal-shaped but degenerate response some
// non-blocking implementations (sockets in particular) can produce — would
// otherwise spin io.write_full forever with the handler mutex held, taking
// down every thread's logging through this handler. This cap turns that
// livelock into a bounded busy-wait that gives up and reports a No_Progress
// error instead.
@(private)
MAX_ZERO_PROGRESS_WRITES :: 1024

// write_full_bounded is io.write_full's loop (write until len(buf) lands or
// an error occurs) with one addition: it counts consecutive zero-byte,
// no-error writes and bails out with .No_Progress once MAX_ZERO_PROGRESS_
// WRITES is hit, rather than looping unboundedly. A single short write (some
// bytes landed) resets the counter — only true no-progress is bounded.
@(private)
write_full_bounded :: proc(w: io.Writer, buf: []byte) -> (n: int, err: io.Error) {
	zero_progress := 0
	for n < len(buf) {
		nn: int
		nn, err = io.write(w, buf[n:])
		if err != nil {
			return
		}
		if nn == 0 {
			zero_progress += 1
			if zero_progress >= MAX_ZERO_PROGRESS_WRITES {
				return n, .No_Progress
			}
			continue
		}
		zero_progress = 0
		n += nn
	}
	return
}

// handler_write_line takes the handler mutex and writes the full line via
// write_full_bounded, which loops until every byte lands, an error occurs, or
// the writer makes no progress for too long (see MAX_ZERO_PROGRESS_WRITES) —
// a bare io.write issues exactly one syscall and can silently truncate on a
// short write. On failure the mutex is released BEFORE options.on_error runs,
// so a hook that itself logs cannot deadlock on this same handler's mutex.
@(private)
handler_write_line :: proc(state: ^Handler_State, line: string) {
	sync.mutex_lock(&state.mutex)
	_, err := write_full_bounded(state.writer, transmute([]byte)line)
	sync.mutex_unlock(&state.mutex)

	if err != nil {
		sync.atomic_add(&state.write_errors, 1)
		if state.options.on_error != nil {
			state.options.on_error(err, state.options.on_error_data)
		}
	}
}

// handler_error_count returns the number of failed or short writes this
// handler has recorded so far. It reads through error_count_ptr — the same
// safe, opaque-data-independent indirection set_handler_level/handler_level
// use for level — so it returns 0 rather than reinterpreting `data` on a
// hand-built Handler that never set error_count_ptr.
handler_error_count :: proc(h: Handler) -> u64 {
	if h.error_count_ptr == nil {
		return 0
	}
	return sync.atomic_load(h.error_count_ptr)
}

// destroy_handler frees the handler's backing. It never touches the caller's
// writer (the caller owns the file/stream). Call it only after every logger
// derived from the handler has been destroyed.
destroy_handler :: proc(h: Handler, allocator := context.allocator) {
	free(h.data, allocator)
}

// apply_replace_attr transforms the user attr tree through the Handler_Options
// replace_attr hook before formatting, so every handler (JSON/GCP/AWS/text)
// shares one rename/redact/drop path. Leaf attrs are passed to the hook with
// their group path; returning `false` drops the attr; groups recurse with the
// path extended by the group key. A nil hook is identity (no allocation).
//
// By design, the hook only ever sees leaf (non-group) attrs — a whole group is
// never passed to it as a unit; only its members are. This mirrors Go's slog
// (ReplaceAttr never receives a Group value) and keeps rename/redact/drop
// decisions per-field rather than per-subtree.
@(private)
apply_replace_attr :: proc(
	attrs: []Attr,
	groups: []string,
	replace: proc(groups: []string, a: Attr) -> (Attr, bool),
	allocator: mem.Allocator,
) -> []Attr {
	if replace == nil {
		return attrs
	}
	out := make([dynamic]Attr, 0, len(attrs), allocator)
	for a in attrs {
		if group, ok := a.value.([]Attr); ok {
			child_path := make([]string, len(groups) + 1, allocator)
			copy(child_path, groups)
			child_path[len(groups)] = a.key
			filtered := apply_replace_attr(group, child_path, replace, allocator)
			append(&out, Attr{key = a.key, value = filtered})
		} else {
			replaced, keep := replace(groups, a)
			if keep {
				append(&out, replaced)
			}
		}
	}
	return out[:]
}

// filter_reserved drops any top-level attr whose key collides with one of a
// handler's fixed record fields (e.g. "time"/"level"/"message"), so a user
// attr can never spoof the record's own values via duplicate-key last-wins
// JSON resolution. Only top-level keys are filtered — a nested group's keys
// are namespaced by the group and cannot collide with the fixed fields.
@(private)
filter_reserved :: proc(attrs: []Attr, reserved: []string, allocator: mem.Allocator) -> []Attr {
	out := make([dynamic]Attr, 0, len(attrs), allocator)
	outer: for a in attrs {
		for r in reserved {
			if a.key == r {
				continue outer
			}
		}
		append(&out, a)
	}
	return out[:]
}

// hoist_specials splits attrs into (regular tree, hoisted specials): any attr
// matched by `is_special` (given its key and value, so a predicate can require
// a specific shape) is pulled to the top level from any depth and deduplicated
// by key — the last binding wins, matching the record's own last-wins merge
// semantics. A group that loses all its members to hoisting becomes empty and
// is elided by the encoder like any other empty group.
@(private)
hoist_specials :: proc(
	attrs: []Attr,
	is_special: proc(key: string, value: Value) -> bool,
	specials: ^[dynamic]Attr,
	allocator: mem.Allocator,
) -> []Attr {
	regular := make([dynamic]Attr, 0, len(attrs), allocator)
	for a in attrs {
		if is_special(a.key, a.value) {
			hoist_special_one(specials, a)
			continue
		}
		if group, ok := a.value.([]Attr); ok {
			append(
				&regular,
				Attr{key = a.key, value = hoist_specials(group, is_special, specials, allocator)},
			)
		} else {
			append(&regular, a)
		}
	}
	return regular[:]
}

@(private = "file")
hoist_special_one :: proc(specials: ^[dynamic]Attr, incoming: Attr) {
	for &existing in specials {
		if existing.key == incoming.key {
			existing.value = incoming.value // last-wins
			return
		}
	}
	append(specials, incoming)
}

// level_name renders a Level as a short name (Go slog style) for the generic
// JSON and text handlers, banding custom in-between values to the nearest named
// level. (GCP uses the severity ladder via level_severity instead.)
@(private)
level_name :: proc(l: Level) -> string {
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
		return "WARN"
	case l >= LEVEL_NOTICE:
		return "NOTICE"
	case l >= LEVEL_INFO:
		return "INFO"
	case:
		return "DEBUG"
	}
}
