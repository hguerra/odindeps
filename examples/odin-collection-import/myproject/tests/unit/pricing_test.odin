package unit

import myproject "../../src/myproject"
import "core:testing"

@(test)
discounted_order_returns_6750_cents :: proc(t: ^testing.T) {
	total, ok := myproject.calculate_total(
		myproject.Order{unit_price_cents = 2_500, quantity = 3, discount_percent = 10},
	)

	testing.expect(t, ok)
	testing.expect_value(t, total, u64(6_750))
}

@(test)
zero_discount_preserves_the_subtotal :: proc(t: ^testing.T) {
	total, ok := myproject.calculate_total(myproject.Order{unit_price_cents = 1_250, quantity = 4})

	testing.expect(t, ok)
	testing.expect_value(t, total, u64(5_000))
}

@(test)
zero_quantity_returns_zero :: proc(t: ^testing.T) {
	total, ok := myproject.calculate_total(
		myproject.Order{unit_price_cents = 2_500, quantity = 0, discount_percent = 10},
	)

	testing.expect(t, ok)
	testing.expect_value(t, total, u64(0))
}

@(test)
full_discount_returns_zero :: proc(t: ^testing.T) {
	total, ok := myproject.calculate_total(
		myproject.Order{unit_price_cents = 2_500, quantity = 3, discount_percent = 100},
	)

	testing.expect(t, ok)
	testing.expect_value(t, total, u64(0))
}

@(test)
discount_above_100_is_invalid :: proc(t: ^testing.T) {
	total, ok := myproject.calculate_total(
		myproject.Order{unit_price_cents = 2_500, quantity = 3, discount_percent = 101},
	)

	testing.expect(t, !ok)
	testing.expect_value(t, total, u64(0))
}

@(test)
maximum_u32_values_do_not_overflow_subtotal_or_discount :: proc(t: ^testing.T) {
	max_u32 := u32(0xffff_ffff)
	subtotal := u64(max_u32) * u64(max_u32)
	expected := subtotal / 100
	if subtotal % 100 != 0 {
		expected += 1
	}

	total, ok := myproject.calculate_total(
		myproject.Order{unit_price_cents = max_u32, quantity = max_u32, discount_percent = 99},
	)

	testing.expect(t, ok)
	testing.expect_value(t, total, expected)
}
