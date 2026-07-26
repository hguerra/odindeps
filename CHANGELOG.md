# Changelog

## [Unreleased]

- Adopt the pre-release manifest vocabulary `dependencies`, `defaults`,
  `git`, `path`, and `destination_root`, and publish `odindeps.schema.json`.
- Document checksum-verified installation, removal, and step-by-step workflows
  for every supported materialization strategy.
- Use `hguerra/odin-slog` as the canonical public Git dependency example.
- Replace the pre-release clone `files` filter with composable `includes` and
  `excludes` filters.
- Reject non-portable clone globs and filtered snapshots that leave dangling
  symbolic links.

## [0.1.0] - 2026-07-25

- Initial portable `odindeps` release.
