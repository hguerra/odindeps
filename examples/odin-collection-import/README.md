# Odin collection import

This complete example materializes
[`hguerra/odin-slog` v0.0.1](https://github.com/hguerra/odin-slog/releases/tag/v0.0.1)
at the project root and exposes it to Odin as the `third_party` collection.
The sample application calculates an order total in integer cents and writes a
structured JSON log record.

From this directory:

```sh
cd myproject
mise run install
mise run sync
mise run verify
mise run dev
mise run build
```

The final command emits one JSON object with the message
`order total calculated` and `total_cents` equal to `6750`.

`odindeps.json` keeps the shared clone filters in `defaults`: only Odin source
and the exact `LICENSE` filename are included, while upstream tests and examples
are excluded. The generated `myproject/third_party/` directory is ignored and
can always be recreated with `mise run sync`.

The harness is POSIX-only and supports macOS and Linux. It requires `curl`,
`unzip`, Python 3, and Git in addition to mise. `mise run install` downloads the
`odinfmt` binary from the pinned OLS `dev-2026-06` release into the ignored
`.bin/` directory and verifies its platform-specific SHA-256 digest;
verification never downloads tools or dependencies implicitly. `mise run test`
is defined locally and runs this Odin project's checks, even when the example
is opened from a parent repository with its own mise tasks.

On native Windows, invoke the portable application and test commands directly
after installing Odin and `odinfmt`; the shell harness itself is not supported:

```powershell
python ../../../odindeps sync
odin test tests -all-packages -vet -strict-style -vet-tabs -disallow-do -warnings-as-errors -define:ODIN_TEST_RANDOM_SEED=12345 -define:ODIN_TEST_FAIL_ON_BAD_MEMORY=true -collection:third_party=third_party
odin run src -vet -strict-style -vet-tabs -disallow-do -warnings-as-errors -collection:third_party=third_party
```

Every build maps the dependency root with:

```text
-collection:third_party=third_party
```

That makes `import "third_party:slog"` independent of the importing source
file's depth. Run `mise tasks` to see the individual formatting, checking,
testing, smoke, and synchronization commands.
