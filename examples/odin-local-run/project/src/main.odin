package main

import "core:fmt"
import greeting "third_party:greeting"

main :: proc() {
    fmt.println(greeting.message())
}
