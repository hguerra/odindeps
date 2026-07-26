# Changelog

## [Unreleased]

## [0.1.0] - 2026-07-26

- Initial portable `odindeps` release.
- **Breaking:** Change the built-in `destination_root` from `src/third_party`
  to `third_party`. To preserve the old layout, declare
  `"destination_root": "src/third_party"` in manifest `defaults`. To adopt the
  new default, clean up or move the previous materialization according to the
  project's chosen strategy, then run `odindeps sync`.
- Adopt the pre-release manifest vocabulary `dependencies`, `defaults`,
  `git`, `path`, and `destination_root`, and publish `odindeps.schema.json`.
- Provide a three-command installation path in the README and move platform,
  upgrade, source-checkout, and removal details into `docs/installation.md`.
- Use `hguerra/odin-slog` as the canonical public Git dependency example.
- Replace the pre-release clone `files` filter with composable `includes` and
  `excludes` filters.
- Reject non-portable clone globs and filtered snapshots that leave dangling
  symbolic links.
- Add collection and relative-import Odin projects with integer-safe pricing,
  deterministic tests, a checksum-verified formatter bootstrap, and CI smoke
  coverage.
- Preserve Git subtree ownership across unrelated commits and reject forced
  updates of destinations without subtree ownership trailers.
- Add locked Ruff linting and formatting to the Python development checks.
- Provide checksum-verified GitHub release assets and a native-Windows command
  wrapper.
- Keep Python CI portable on Windows and run the POSIX Odin harness on macOS
  and Linux, its supported platforms.
- Support native-Windows local path name inference, normalized containment
  checks, read-only Git metadata cleanup, and portable offline Git fixtures.
