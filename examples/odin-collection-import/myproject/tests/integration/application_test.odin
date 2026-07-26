package integration

import myproject "../../src/myproject"
import "core:encoding/json"
import "core:strings"
import "core:testing"

@(private = "file")
parse_log :: proc(t: ^testing.T, line: string) -> json.Object {
	value, err := json.parse_string(
		line,
		spec = json.Specification.JSON,
		parse_integers = true,
		allocator = context.temp_allocator,
	)
	testing.expectf(t, err == nil, "log must be valid JSON: %q (%v)", line, err)
	object, ok := value.(json.Object)
	testing.expect(t, ok, "log must be a JSON object")
	return object
}

@(test)
valid_order_writes_an_info_log_with_the_total :: proc(t: ^testing.T) {
	builder: strings.Builder
	strings.builder_init(&builder, context.allocator)
	defer strings.builder_destroy(&builder)

	ok := myproject.run(
		strings.to_writer(&builder),
		myproject.Order{unit_price_cents = 2_500, quantity = 3, discount_percent = 10},
	)

	testing.expect(t, ok)
	object := parse_log(t, strings.to_string(builder))
	severity, _ := object["severity"].(json.String)
	message, _ := object["message"].(json.String)
	total, total_ok := object["total_cents"].(json.Integer)
	testing.expect_value(t, string(severity), "INFO")
	testing.expect_value(t, string(message), "order total calculated")
	testing.expect(t, total_ok, "total_cents must be an integer")
	testing.expect_value(t, i64(total), i64(6_750))
}

@(test)
invalid_order_writes_an_error_log_and_returns_false :: proc(t: ^testing.T) {
	builder: strings.Builder
	strings.builder_init(&builder, context.allocator)
	defer strings.builder_destroy(&builder)

	ok := myproject.run(
		strings.to_writer(&builder),
		myproject.Order{unit_price_cents = 2_500, quantity = 3, discount_percent = 101},
	)

	testing.expect(t, !ok)
	object := parse_log(t, strings.to_string(builder))
	severity, _ := object["severity"].(json.String)
	message, _ := object["message"].(json.String)
	testing.expect_value(t, string(severity), "ERROR")
	testing.expect_value(t, string(message), "invalid order")
}
