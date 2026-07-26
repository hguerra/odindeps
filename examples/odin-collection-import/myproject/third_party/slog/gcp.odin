#+vet explicit-allocators
package slog

// Google Cloud Logging handler. It specializes the shared streaming JSON encoder
// with GCP field names (severity, message, time, sourceLocation) and routes the
// explicit gcp_* correlation fields to the top level, never nested.
//
// Correlation is produced only by the gcp_* helpers, whose keys are already the
// final `logging.googleapis.com/*` (or top-level) field names. The handler emits
// any attr whose key is on the allow-list at top level and hoists it out of any
// open group, so correlation still routes even when a with_group is open. It
// never reinterprets a user attr by short name.

import "core:fmt"
import "core:io"
import "core:mem"
import "core:strconv"
import "core:strings"

@(private = "file")
GCP_SPECIAL_PREFIX :: "logging.googleapis.com/"

@(private = "file")
GCP_HTTP_REQUEST_KEY :: "httpRequest"

// ---- correlation helpers (keys are the final provider fields) ----

// gcp_trace binds `logging.googleapis.com/trace` = projects/<p>/traces/<t>. Like
// `group`, it defaults to the temp allocator: the composed value is a borrow for
// the call, and `with` re-clones it into the logger allocator when bound.
gcp_trace :: proc(project_id, trace_id: string, allocator := context.temp_allocator) -> Attr {
	value := fmt.aprintf("projects/%s/traces/%s", project_id, trace_id, allocator = allocator)
	return Attr{key = GCP_SPECIAL_PREFIX + "trace", value = value}
}

gcp_span :: proc(span_id: string) -> Attr {
	return Attr{key = GCP_SPECIAL_PREFIX + "spanId", value = span_id}
}

gcp_trace_sampled :: proc(sampled: bool) -> Attr {
	return Attr{key = GCP_SPECIAL_PREFIX + "trace_sampled", value = sampled}
}

gcp_insert_id :: proc(id: string) -> Attr {
	return Attr{key = GCP_SPECIAL_PREFIX + "insertId", value = id}
}

// gcp_labels builds the `logging.googleapis.com/labels` string->string object.
gcp_labels :: proc(pairs: ..[2]string, allocator := context.temp_allocator) -> Attr {
	labels := make([]Attr, len(pairs), allocator)
	for pair, i in pairs {
		labels[i] = Attr {
			key   = pair[0],
			value = pair[1],
		}
	}
	return Attr{key = GCP_SPECIAL_PREFIX + "labels", value = labels}
}

// gcp_operation builds the `logging.googleapis.com/operation` object.
gcp_operation :: proc(
	id, producer: string,
	first := false,
	last := false,
	allocator := context.temp_allocator,
) -> Attr {
	fields := make([]Attr, 4, allocator)
	fields[0] = Attr {
		key   = "id",
		value = id,
	}
	fields[1] = Attr {
		key   = "producer",
		value = producer,
	}
	fields[2] = Attr {
		key   = "first",
		value = first,
	}
	fields[3] = Attr {
		key   = "last",
		value = last,
	}
	return Attr{key = GCP_SPECIAL_PREFIX + "operation", value = fields}
}

// gcp_http_request builds the top-level `httpRequest` object with typed fields.
// requestMethod/status are always present; the rest are optional (empty
// string / negative int = omitted) since GCP's schema has more fields than any
// caller typically has on hand. `latency` is a caller-formatted duration string
// (GCP's own textual form, e.g. "3.5s").
gcp_http_request :: proc(
	method: string,
	status: int,
	latency := "",
	request_url := "",
	user_agent := "",
	remote_ip := "",
	response_size := -1,
	allocator := context.temp_allocator,
) -> Attr {
	fields := make([dynamic]Attr, 0, 7, allocator)
	append(&fields, Attr{key = "requestMethod", value = method})
	append(&fields, Attr{key = "status", value = i64(status)})
	if latency != "" {
		append(&fields, Attr{key = "latency", value = latency})
	}
	if request_url != "" {
		append(&fields, Attr{key = "requestUrl", value = request_url})
	}
	if user_agent != "" {
		append(&fields, Attr{key = "userAgent", value = user_agent})
	}
	if remote_ip != "" {
		append(&fields, Attr{key = "remoteIp", value = remote_ip})
	}
	if response_size >= 0 {
		append(&fields, Attr{key = "responseSize", value = i64(response_size)})
	}
	return Attr{key = GCP_HTTP_REQUEST_KEY, value = fields[:]}
}

// ---- handler ----

create_gcp_handler :: proc(
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
		procedure = gcp_handler_proc,
		data = state,
		level = level,
		level_ptr = &state.level,
		error_count_ptr = &state.write_errors,
	}
}

// gcp_is_special identifies attrs produced by the gcp_* helpers, so
// hoist_specials can pull them to the top level regardless of nesting depth.
// httpRequest additionally requires a group (object) value: the gcp_http_request
// helper always emits a structured object, so a scalar attr a caller happens to
// name "httpRequest" (an accidental collision) is never treated as special and
// stays an ordinary payload field. The `logging.googleapis.com/*` keys are not
// shape-checked — that namespace is reserved for the gcp_* helpers — EXCEPT
// sourceLocation, which is excluded here: no gcp_* helper ever produces that
// key (the handler writes it directly, unconditionally, from record.source),
// so it must never be eligible for hoisting. Without this exclusion, a nested
// attr renamed to that exact key by a replace_attr hook — filter_reserved only
// inspects top-level keys, and hoist_specials runs after it — would still be
// pulled to the top level and collide with the handler's own sourceLocation.
@(private = "file")
gcp_is_special :: proc(key: string, value: Value) -> bool {
	if key == GCP_SPECIAL_PREFIX + "sourceLocation" {
		return false
	}
	if key == GCP_HTTP_REQUEST_KEY {
		_, is_group := value.([]Attr)
		return is_group
	}
	return strings.has_prefix(key, GCP_SPECIAL_PREFIX)
}

@(private = "file")
gcp_write_source :: proc(b: ^strings.Builder, s: Source) {
	strings.write_byte(b, '{')
	json_write_quoted(b, "file")
	strings.write_byte(b, ':')
	json_write_quoted(b, s.file)
	strings.write_byte(b, ',')
	json_write_quoted(b, "line")
	strings.write_byte(b, ':')
	buf: [32]byte
	json_write_quoted(b, strconv.write_int(buf[:], i64(s.line), 10)) // line quoted per GCP
	strings.write_byte(b, ',')
	json_write_quoted(b, "function")
	strings.write_byte(b, ':')
	json_write_quoted(b, s.procedure)
	strings.write_byte(b, '}')
}

@(private = "file")
gcp_handler_proc :: proc(data: rawptr, record: Record, temp: mem.Allocator) {
	state := cast(^Handler_State)data
	b: strings.Builder
	strings.builder_init(&b, temp)

	strings.write_byte(&b, '{')
	json_write_quoted(&b, "severity")
	strings.write_byte(&b, ':')
	json_write_quoted(&b, level_severity(record.level))

	strings.write_byte(&b, ',')
	json_write_quoted(&b, "message")
	strings.write_byte(&b, ':')
	json_write_quoted(&b, record.message)

	strings.write_byte(&b, ',')
	json_write_quoted(&b, "time")
	strings.write_byte(&b, ':')
	strings.write_byte(&b, '"')
	format_rfc3339(&b, record.time)
	strings.write_byte(&b, '"')

	if !state.options.omit_source {
		strings.write_byte(&b, ',')
		json_write_quoted(&b, GCP_SPECIAL_PREFIX + "sourceLocation")
		strings.write_byte(&b, ':')
		gcp_write_source(&b, record.source)
	}

	// apply_replace_attr runs first: replace_attr is a caller-supplied hook that
	// can rename an attr's key to anything, including a reserved name, so
	// filter_reserved runs LAST — after the hook — to catch a collision it
	// introduces, not just one the caller wrote directly. Running it first only
	// would let a replace_attr hook reintroduce this exact spoof one layer up.
	attrs := apply_replace_attr(record.attrs, nil, state.options.replace_attr, temp)
	attrs = filter_reserved(
		attrs,
		{"severity", "message", "time", GCP_SPECIAL_PREFIX + "sourceLocation"},
		temp,
	)
	specials := make([dynamic]Attr, 0, len(attrs), temp)
	regular := hoist_specials(attrs, gcp_is_special, &specials, temp)
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
