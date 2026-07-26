#+vet explicit-allocators
package slog

import "base:runtime"
import "core:mem"
import "core:strings"
import "core:time"

// Logger accumulates bound attrs and a group stack and resolves them into a
// Record before calling the handler. The root logger owns nothing (attrs and
// groups are nil). The handler MUST outlive every logger derived from it.
//
// Concurrency: only the Handler is safe for concurrent use across threads (the
// write path is mutex-guarded). A Logger value itself is NOT internally
// synchronized: `with`/`with_group` read it, and `destroy_logger` mutates it,
// with no locking. Do not derive from, log through, or destroy the same Logger
// (or an ancestor a derived Logger still reads through) concurrently from more
// than one thread without your own external synchronization — e.g. give each
// thread its own child Logger via `with` instead of sharing one. Emitting
// records (`log`/`info`/`warn`/...) through independent Logger values that
// share only the Handler is safe and is the pattern the concurrency test
// exercises.
Logger :: struct {
	handler:   Handler,
	attrs:     []Attr, // already-nested resolved tree owned by this logger (root: nil)
	groups:    []string, // still-open group path applied to call-site attrs (root: nil)
	allocator: mem.Allocator, // the allocator attrs were cloned with; destroy_logger frees with it
}

// create_logger returns a root logger over a handler. It allocates nothing; the
// root owns no bound attrs.
create_logger :: proc(h: Handler, allocator := context.allocator) -> Logger {
	return Logger{handler = h, allocator = allocator}
}

// with derives a child logger with additional bound attrs. The new attrs are
// folded under the currently-open group path, merged onto the parent's bound
// tree (last-wins), and the whole result is deep-cloned into `allocator`, which
// is recorded on the child so destroy_logger frees with the same allocator. Each
// child owns a self-contained tree; the parent is untouched.
//
// `allocator` defaults to the zero Allocator (procedure == nil), which means
// "inherit logger.allocator" — Odin default-parameter expressions cannot refer
// to another parameter, so this sentinel is the only way to make the child
// default to its parent's allocator rather than silently falling through to
// context.allocator regardless of what the parent was built with. Passing
// context.temp_allocator explicitly is a use-after-free: the DEFAULT_TEMP_
// ALLOCATOR_TEMP_GUARD below rewinds (and zeroes) everything allocated after
// its mark, including this call's own clone, before with returns.
with :: proc(logger: ^Logger, args: ..Attr, allocator := mem.Allocator{}) -> Logger {
	runtime.DEFAULT_TEMP_ALLOCATOR_TEMP_GUARD()
	temp := context.temp_allocator
	alloc := allocator.procedure != nil ? allocator : logger.allocator
	folded := fold_under_path(args, logger.groups, temp)
	merged := merge_attrs(logger.attrs, folded, temp)
	return Logger {
		handler = logger.handler,
		attrs = clone_attrs(merged, alloc),
		groups = clone_strings(logger.groups, alloc),
		allocator = alloc,
	}
}

// with_group derives a child logger with `name` pushed onto the still-open group
// path. Subsequent call-site (and bound) attrs on the child nest under it. The
// parent's bound tree is deep-cloned so the child owns a self-contained copy.
//
// `allocator` defaults to inheriting logger.allocator; see `with`'s doc comment
// for why a zero-Allocator sentinel is used instead of a direct default.
with_group :: proc(logger: ^Logger, name: string, allocator := mem.Allocator{}) -> Logger {
	alloc := allocator.procedure != nil ? allocator : logger.allocator
	groups := make([]string, len(logger.groups) + 1, alloc)
	for g, i in logger.groups {
		groups[i] = strings.clone(g, alloc)
	}
	groups[len(logger.groups)] = strings.clone(name, alloc)
	return Logger {
		handler = logger.handler,
		attrs = clone_attrs(logger.attrs, alloc),
		groups = groups,
		allocator = alloc,
	}
}

// destroy_logger frees the attr tree and group path this logger owns, using the
// allocator they were cloned with. The root logger owns nothing, so this is a
// no-op there; a child never frees its parent's attrs.
destroy_logger :: proc(logger: ^Logger) {
	free_attrs(logger.attrs, logger.allocator)
	free_strings(logger.groups, logger.allocator)
	logger.attrs = nil
	logger.groups = nil
}

// log emits at an explicit level. Records below the handler level are dropped
// before any record building or allocation. A zero-valued Handler (procedure
// == nil — e.g. an unset field in a config struct, or a constructor whose
// error path was ignored) is also a silent no-op rather than a crash.
log :: proc(logger: ^Logger, level: Level, msg: string, args: ..Attr, loc := #caller_location) {
	if logger.handler.procedure == nil {
		return
	}
	if level < handler_level(logger.handler) {
		return
	}
	runtime.DEFAULT_TEMP_ALLOCATOR_TEMP_GUARD()
	temp := context.temp_allocator
	record := build_record(logger, level, msg, args, loc, temp)
	logger.handler.procedure(logger.handler.data, record, temp)
}

debug :: proc(logger: ^Logger, msg: string, args: ..Attr, loc := #caller_location) {
	log(logger, LEVEL_DEBUG, msg, ..args, loc = loc)
}

info :: proc(logger: ^Logger, msg: string, args: ..Attr, loc := #caller_location) {
	log(logger, LEVEL_INFO, msg, ..args, loc = loc)
}

warn :: proc(logger: ^Logger, msg: string, args: ..Attr, loc := #caller_location) {
	log(logger, LEVEL_WARN, msg, ..args, loc = loc)
}

error :: proc(logger: ^Logger, msg: string, args: ..Attr, loc := #caller_location) {
	log(logger, LEVEL_ERROR, msg, ..args, loc = loc)
}

// build_record assembles the Record. Call-site args are folded under the
// logger's open group path and merged onto its bound tree (last-wins), all in
// `temp` — the emit path's temp guard reclaims it after the handler formats.
@(private)
build_record :: proc(
	logger: ^Logger,
	level: Level,
	msg: string,
	args: []Attr,
	loc: runtime.Source_Code_Location,
	temp: mem.Allocator,
) -> Record {
	folded := fold_under_path(args, logger.groups, temp)
	resolved := merge_attrs(logger.attrs, folded, temp)
	return Record {
		time = time.now(),
		level = level,
		message = msg,
		source = Source{file = loc.file_path, line = loc.line, procedure = loc.procedure},
		attrs = resolved,
	}
}

// fold_under_path wraps attrs in a nested group per path element, innermost
// first, so [g, h] yields [g: [h: attrs]]. An empty path returns attrs as-is.
@(private)
fold_under_path :: proc(attrs: []Attr, path: []string, allocator: mem.Allocator) -> []Attr {
	result := attrs
	#reverse for name in path {
		wrapped := make([]Attr, 1, allocator)
		wrapped[0] = Attr {
			key   = name,
			value = result,
		}
		result = wrapped
	}
	return result
}

// merge_attrs unions base and extra into a fresh slice: keys appear once in
// first-seen order, later values win, and two attrs sharing a key that are both
// groups merge recursively. Members are shallow — the caller either uses the
// result transiently or deep-clones it.
@(private)
merge_attrs :: proc(base: []Attr, extra: []Attr, allocator: mem.Allocator) -> []Attr {
	result := make([dynamic]Attr, 0, len(base) + len(extra), allocator)
	for a in base {
		merge_one(&result, a, allocator)
	}
	for e in extra {
		merge_one(&result, e, allocator)
	}
	return result[:]
}

@(private)
merge_one :: proc(result: ^[dynamic]Attr, incoming: Attr, allocator: mem.Allocator) {
	for &existing in result {
		if existing.key == incoming.key {
			existing_group, x_is_group := existing.value.([]Attr)
			incoming_group, i_is_group := incoming.value.([]Attr)
			if x_is_group && i_is_group {
				existing.value = merge_attrs(existing_group, incoming_group, allocator)
			} else {
				existing.value = incoming.value // last-wins
			}
			return
		}
	}
	append(result, incoming)
}

// clone_attrs deep-clones an attr tree into `allocator`: every key and string
// value is cloned, groups recurse, an `any` is snapshotted to a cloned string
// via the shared format_any (so bound and call-site `any` render identically),
// and scalar/time values are copied by value.
@(private)
clone_attrs :: proc(attrs: []Attr, allocator: mem.Allocator) -> []Attr {
	if len(attrs) == 0 {
		return nil
	}
	out := make([]Attr, len(attrs), allocator)
	for a, i in attrs {
		out[i] = Attr {
			key   = strings.clone(a.key, allocator),
			value = clone_value(a.value, allocator),
		}
	}
	return out
}

@(private)
clone_value :: proc(v: Value, allocator: mem.Allocator) -> Value {
	switch val in v {
	case string:
		return strings.clone(val, allocator)
	case []Attr:
		return clone_attrs(val, allocator)
	case any:
		return format_any(val, allocator) // snapshot to a stable cloned string
	case i64, u64, f64, bool, time.Time, time.Duration:
		return v
	case:
		return nil // nil variant
	}
}

// free_attrs frees an attr tree cloned by clone_attrs, using the same allocator.
// (A snapshotted `any` is a plain string by this point, freed by the string arm.)
@(private)
free_attrs :: proc(attrs: []Attr, allocator: mem.Allocator) {
	for a in attrs {
		delete(a.key, allocator)
		#partial switch val in a.value {
		case string:
			delete(val, allocator)
		case []Attr:
			free_attrs(val, allocator)
		}
	}
	delete(attrs, allocator)
}

@(private)
clone_strings :: proc(s: []string, allocator: mem.Allocator) -> []string {
	if len(s) == 0 {
		return nil
	}
	out := make([]string, len(s), allocator)
	for str, i in s {
		out[i] = strings.clone(str, allocator)
	}
	return out
}

@(private)
free_strings :: proc(s: []string, allocator: mem.Allocator) {
	for str in s {
		delete(str, allocator)
	}
	delete(s, allocator)
}
