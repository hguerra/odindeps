package myproject

Order :: struct {
	unit_price_cents: u32,
	quantity:         u32,
	discount_percent: u8,
}

// calculate_total calculates integer cents without floating-point arithmetic.
// Monetary division rounds down. Splitting the discount into quotient and
// remainder terms avoids overflowing u64 at the u32 multiplication limits.
calculate_total :: proc(order: Order) -> (total_cents: u64, ok: bool) {
	if order.discount_percent > 100 {
		return 0, false
	}

	subtotal := u64(order.unit_price_cents) * u64(order.quantity)
	percent := u64(order.discount_percent)
	discount := subtotal / 100 * percent + subtotal % 100 * percent / 100
	return subtotal - discount, true
}
