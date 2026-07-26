# Contributing

Install the pinned tools with `mise install`, then run `mise run check`. Use TDD: add a failing focused test, implement the smallest change, and rerun the affected suite before the complete check. Keep runtime dependencies in the Python standard library and verify macOS, Linux, and native Windows impact.

Pull requests explain observable behavior, tests, platform and security impact, and whether `CHANGELOG.md` changes. Keep commits scoped and documentation in English.

## Release version contract

Before a human-created `vX.Y.Z` tag is published, verify that all four version sources agree: `odindeps --version`, `pyproject.toml`, `CHANGELOG.md`, and the tag itself. The release workflow rejects a mismatch and publishes the executable with its SHA-256 checksum.
