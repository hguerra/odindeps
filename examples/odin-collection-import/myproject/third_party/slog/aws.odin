#+vet explicit-allocators
package slog

// AWS CloudWatch Logs handler. It emits the timestamp/level/message/requestId
// JSON shape that managed Lambda runtimes parse; its honest value on Odin's
// custom runtime (provided.al2*) is CloudWatch Logs Insights-queryable JSON. The
// app must read the request id itself from the Runtime API header and pass it in
// via aws_request_id — Lambda does not inject it on a custom runtime.

import "core:io"
import "core:mem"
import "core:strings"

// aws_request_id binds the app-supplied `requestId` field.
aws_request_id :: proc(id: string) -> Attr {
	return Attr{key = "requestId", value = id}
}

create_aws_handler :: proc(
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
		procedure = aws_handler_proc,
		data = state,
		level = level,
		level_ptr = &state.level,
		error_count_ptr = &state.write_errors,
	}
}

// aws_is_special identifies attrs produced by the aws_* helpers (currently just
// aws_request_id), so hoist_specials can pull them to the top level regardless
// of nesting depth — e.g. bound via `with` while a with_group is open.
//
// Unlike GCP's httpRequest (see gcp_is_special), this has no shape check: an
// ordinary attr a caller happens to name "requestId" is indistinguishable from
// the helper's own output — aws_request_id produces a scalar string, exactly
// what a hand-written attr("requestId", "...") would also produce, so there is
// no structural signal to tell them apart. This is an accepted, inherent
// limitation of AWS's single-scalar-field design, not an oversight.
@(private = "file")
aws_is_special :: proc(key: string, value: Value) -> bool {
	return key == "requestId"
}

// aws_level_name maps a Level to AWS's ladder. AWS has no CRITICAL/ALERT; any
// level >= CRITICAL renders "FATAL". NOTICE folds into INFO.
@(private = "file")
aws_level_name :: proc(l: Level) -> string {
	switch {
	case l >= LEVEL_CRITICAL:
		return "FATAL"
	case l >= LEVEL_ERROR:
		return "ERROR"
	case l >= LEVEL_WARN:
		return "WARN"
	case l >= LEVEL_INFO:
		return "INFO"
	case l >= LEVEL_DEBUG:
		return "DEBUG"
	case:
		return "TRACE"
	}
}

@(private = "file")
aws_handler_proc :: proc(data: rawptr, record: Record, temp: mem.Allocator) {
	state := cast(^Handler_State)data
	b: strings.Builder
	strings.builder_init(&b, temp)

	strings.write_byte(&b, '{')
	json_write_quoted(&b, "timestamp")
	strings.write_byte(&b, ':')
	strings.write_byte(&b, '"')
	format_iso8601_ms(&b, record.time)
	strings.write_byte(&b, '"')

	strings.write_byte(&b, ',')
	json_write_quoted(&b, "level")
	strings.write_byte(&b, ':')
	json_write_quoted(&b, aws_level_name(record.level))

	strings.write_byte(&b, ',')
	json_write_quoted(&b, "message")
	strings.write_byte(&b, ':')
	json_write_quoted(&b, record.message)

	// apply_replace_attr runs first: replace_attr is a caller-supplied hook that
	// can rename an attr's key to anything, including a reserved name, so
	// filter_reserved runs LAST — after the hook — to catch a collision it
	// introduces, not just one the caller wrote directly. Running it first only
	// would let a replace_attr hook reintroduce this exact spoof one layer up.
	attrs := apply_replace_attr(record.attrs, nil, state.options.replace_attr, temp)
	attrs = filter_reserved(attrs, {"timestamp", "level", "message"}, temp)
	specials := make([dynamic]Attr, 0, len(attrs), temp)
	regular := hoist_specials(attrs, aws_is_special, &specials, temp)
	for a in regular {
		json_write_attr_comma(&b, a, temp)
	}
	for a in specials {
		json_write_attr_comma(&b, a, temp)
	}

	strings.write_byte(&b, '}')
	strings.write_byte(&b, '\n')
	handler_write_line(state, strings.to_string(b))
}
