package main

import "core:os"
import "deps:slog"
import "./myproject"

main :: proc() {
    handler := slog.create_gcp_handler(os.to_writer(os.stdout), level = slog.LEVEL_INFO)
    defer slog.destroy_handler(handler)

    logger := slog.create_logger(handler)
    myproject.log_startup(&logger)
}
