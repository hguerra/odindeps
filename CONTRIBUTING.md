# Contributing

Install the pinned tools with `mise install`, then run `mise run check`. The
check runs Ruff linting and formatting validation, the complete standard-library
test suite, and bytecode compilation. Use `mise run format` to format the
extensionless runtime and Python tests. Use TDD: add a failing focused test,
implement the smallest change, and rerun the affected suite before the complete
check. Keep runtime dependencies in the Python standard library and verify
macOS, Linux, and native Windows impact.

Pull requests explain observable behavior, tests, platform and security impact, and whether `CHANGELOG.md` changes. Keep commits scoped and documentation in English.

## Release version contract

Before a human-created `vX.Y.Z` tag is published, verify that all four version sources agree: `odindeps --version`, `pyproject.toml`, `CHANGELOG.md`, and the tag itself. The release workflow rejects a mismatch and publishes the executable with its SHA-256 checksum.

Move the intended entries from `Unreleased` into the matching dated version
section before creating the tag. Push the reviewed commit to `main`, wait for
CI, then create and push an annotated tag. The release workflow creates or
resumes a draft, verifies its downloaded assets, and publishes it only after
the checks pass. A failed draft may be rerun with the same tag; a published
immutable release is never modified. Correct a published release with a new
patch version instead of replacing its assets or moving its tag.
