package main

import "core:os"
import "deps:slog"

main :: proc() {
    handler := slog.create_gcp_handler(os.to_writer(os.stdout), level = slog.LEVEL_INFO)
    defer slog.destroy_handler(handler)

    logger := slog.create_logger(handler)
    slog.info(&logger, "remote dependency materialized", slog.attr("example", "odindeps"))
}
