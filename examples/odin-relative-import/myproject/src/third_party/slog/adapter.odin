#+vet explicit-allocators
package slog

// core:log interop. as_log_logger wraps a slog Logger as a core:log.Logger so
// code that logs through context.logger (message-only) lands in a slog handler.
// core:log's Logger_Proc receives a flat text string — no structured attrs — so
// this bridge carries only the message and the mapped level.
//
// The returned core:log.Logger borrows the slog Logger by pointer: the backing
// slog Logger MUST stay pinned/alive for as long as the adapter is installed.

import corelog "core:log"

// as_log_logger returns a core:log.Logger that routes through `logger`'s handler.
// `lowest` (a slog Level) sets the core:log gate; it is mapped to the nearest
// core:log level.
as_log_logger :: proc(logger: ^Logger, lowest := LEVEL_DEBUG) -> corelog.Logger {
	return corelog.Logger {
		procedure = log_adapter_proc,
		data = logger,
		lowest_level = slog_to_core_level(lowest),
		options = {},
	}
}

@(private = "file")
log_adapter_proc :: proc(
	data: rawptr,
	level: corelog.Level,
	text: string,
	options: corelog.Options,
	location := #caller_location,
) {
	logger := cast(^Logger)data
	log(logger, core_to_slog_level(level), text, loc = location)
}

// core_to_slog_level maps a core:log level to a slog Level (Warning↔Warn,
// Fatal↔Critical).
@(private = "file")
core_to_slog_level :: proc(l: corelog.Level) -> Level {
	switch l {
	case .Debug:
		return LEVEL_DEBUG
	case .Info:
		return LEVEL_INFO
	case .Warning:
		return LEVEL_WARN
	case .Error:
		return LEVEL_ERROR
	case .Fatal:
		return LEVEL_CRITICAL
	case:
		return LEVEL_INFO
	}
}

// slog_to_core_level maps a slog Level to the nearest core:log level; any level
// at or above CRITICAL (incl. ALERT/EMERGENCY) maps to Fatal.
@(private = "file")
slog_to_core_level :: proc(l: Level) -> corelog.Level {
	switch {
	case l >= LEVEL_CRITICAL:
		return .Fatal
	case l >= LEVEL_ERROR:
		return .Error
	case l >= LEVEL_WARN:
		return .Warning
	case l >= LEVEL_INFO:
		return .Info
	case:
		return .Debug
	}
}
