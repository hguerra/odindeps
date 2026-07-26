**odindeps is not a package manager. It does not resolve transitive dependencies, generate an Odin dependency lockfile, validate dependency checksums, or provide a package registry. It only materializes explicitly declared sources.**

# odindeps

`odindeps` is a portable, dependency-free Python 3 helper for materializing
direct Git and local path dependencies in Odin projects. The executable is one
extensionless file and requires Python 3.11 or newer plus Git for Git
dependencies.

## Install

Install the latest release on macOS or Linux:

```sh
mkdir -p "$HOME/.local/bin"
curl -fsSL https://github.com/hguerra/odindeps/releases/latest/download/odindeps -o "$HOME/.local/bin/odindeps"
chmod +x "$HOME/.local/bin/odindeps"
```

Python 3.11 or newer is required. Git is also required for Git dependencies.
See [Installation details](docs/installation.md) for `PATH`, Windows, upgrades,
version-pinned downloads, source checkouts, and removal.

## Quick start

Create a project manifest:

```sh
mkdir example-project
cd example-project
odindeps init
```

Add a pinned Git dependency:

```sh
odindeps add \
  --git github.com/hguerra/odin-slog \
  --rev v0.0.1 \
  --name slog
```

`add` updates the manifest and materializes that dependency. After cloning a
project whose manifest already exists, materialize all declared dependencies
with `odindeps sync`.

Before publishing snapshots, `sync` validates every local source and probes
every declared Git remote and revision. Git submodule and subtree strategies
also modify the consuming repository; keep it clean and review their staged or
committed changes as part of the normal Git workflow.

`sync` is not a multi-dependency transaction: if a later filesystem or Git
action fails, prior successful actions remain in place. Resolve those changes
with the consuming repository's normal Git workflow before retrying.

The resulting manifest is:

```json
{
  "dependencies": {
    "slog": {
      "git": "github.com/hguerra/odin-slog",
      "rev": "v0.0.1"
    }
  },
  "schema_version": 1
}
```

By default, dependencies are materialized at `third_party/<name>`, so this
dependency is available at `third_party/slog`.

## Commands

| Command | Purpose |
| --- | --- |
| `odindeps init` | Create the minimal `odindeps.json`. |
| `odindeps add --git LOCATOR --rev REV [--name NAME]` | Add and materialize one Git dependency. |
| `odindeps add --path DIRECTORY [--name NAME]` | Add and materialize one local path dependency. |
| `odindeps sync` | Materialize every missing dependency without replacement. |
| `odindeps sync --force` | Refresh only destinations proven to be managed by `odindeps`. |

## Manifest

`dependencies` distinguishes Git locators from local filesystem paths:

```json
{
  "schema_version": 1,
  "dependencies": {
    "slog": {
      "git": "github.com/hguerra/odin-slog",
      "rev": "v0.0.1"
    },
    "shared": {
      "path": "../shared"
    }
  },
  "defaults": {
    "destination_root": "third_party"
  }
}
```

Configuration is merged from built-ins, manifest `defaults`, then
per-dependency `options`. The checked-in `odindeps.schema.json` describes the
manifest using JSON Schema Draft 2020-12. Nested objects merge recursively;
scalars and lists replace inherited values, so `includes` and `excludes` are
never concatenated across scopes.

For clone snapshots, `options.git.clone.includes` selects relative POSIX globs
and `excludes` removes matches after inclusion. When `includes` is omitted all
regular files are candidates; a configured filter set must leave at least one
file. Patterns match relative POSIX paths: `LICENSE` selects that exact name,
not `LICENSE.md` or another variant. The legacy `files` field is not accepted.

Root-level dependencies work naturally as an external Odin collection:

```text
import "third_party:slog"
odin run src -collection:third_party=third_party
```

Projects that explicitly set `"destination_root": "src/third_party"` can
instead import from a source package with a relative path such as
`import "./third_party/slog"` and build without `-collection`. Collections keep
imports stable across nested packages; relative imports keep the build command
short but couple imports to the source tree's physical layout.

## Strategy guides

Start with the
[complete collection-import example](https://github.com/hguerra/odindeps/tree/main/examples/odin-collection-import)
for a realistic Odin project with formatting, tests, and smoke checks.

| Strategy | Guide | Important effect |
| --- | --- | --- |
| Odin collection import | [Complete Odin project](examples/odin-collection-import/README.md) | Uses root-level `third_party:slog` with a deterministic POSIX harness. |
| Odin relative import | [Compact Odin project](examples/odin-relative-import/README.md) | Overrides the destination into `src` and needs no collection flag. |
| Clone snapshot | [Clone example](examples/clone/README.md) | Publishes source without `.git`. |
| Local copy or symlink | [Local example](examples/local/README.md) | Copies everywhere; symlinks only on POSIX. |
| Cached clone symlink | [Cache example](examples/cache-symlink/README.md) | Creates a machine-local permanent symlink. |
| Git submodule | [Submodule example](examples/submodule/README.md) | Stages `.gitmodules` and a gitlink. |
| Git subtree | [Subtree example](examples/subtree/README.md) | Creates commits in the consuming repository. |

## Limits and exit codes

Git clone, submodule, subtree, and local copy are supported on macOS, Linux,
and native Windows when the required Git capability exists. Local and cache
symlinks are unsupported on native Windows. The complete Odin example's shell
harness supports macOS and Linux; its README provides direct native-Windows
commands for the portable source project.

Exit codes are `2` for validation, `3` for unsafe conflicts, `4` for Git
failures, and `5` for filesystem failures. `uv.lock` belongs only to the Python
development environment; it neither locks Odin dependencies nor provides
dependency checksums.
