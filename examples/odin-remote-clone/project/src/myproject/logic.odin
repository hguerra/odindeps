package myproject

import "deps:slog"

log_startup :: proc(logger: ^slog.Logger) {
    slog.info(logger, "remote dependency materialized", slog.attr("example", "odindeps"))
}
