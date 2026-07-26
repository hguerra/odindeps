package main

import "./myproject"
import "core:os"

main :: proc() {
	order := myproject.Order {
		unit_price_cents = 2_500,
		quantity         = 3,
		discount_percent = 10,
	}
	if !myproject.run(os.to_writer(os.stdout), order) {
		os.exit(1)
	}
}
