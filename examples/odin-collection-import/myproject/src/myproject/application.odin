package myproject

import "core:io"
import "third_party:slog"

run :: proc(writer: io.Writer, order: Order) -> bool {
	handler := slog.create_gcp_handler(writer, level = slog.LEVEL_INFO)
	defer slog.destroy_handler(handler)
	logger := slog.create_logger(handler)
	defer slog.destroy_logger(&logger)

	total_cents, ok := calculate_total(order)
	if !ok {
		slog.error(
			&logger,
			"invalid order",
			slog.attr("unit_price_cents", order.unit_price_cents),
			slog.attr("quantity", order.quantity),
			slog.attr("discount_percent", order.discount_percent),
		)
		return false
	}

	slog.info(
		&logger,
		"order total calculated",
		slog.attr("unit_price_cents", order.unit_price_cents),
		slog.attr("quantity", order.quantity),
		slog.attr("discount_percent", order.discount_percent),
		slog.attr("total_cents", total_cents),
	)
	return true
}
