package main

import "./third_party/slog"
import "core:os"

main :: proc() {
	handler := slog.create_gcp_handler(os.to_writer(os.stdout), level = slog.LEVEL_INFO)
	defer slog.destroy_handler(handler)
	logger := slog.create_logger(handler)
	defer slog.destroy_logger(&logger)

	slog.info(
		&logger,
		"relative dependency imported",
		slog.attr("example", "odin-relative-import"),
	)
}
