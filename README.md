**odindeps is not a package manager. It does not resolve transitive dependencies, generate an Odin dependency lockfile, validate dependency checksums, or provide a package registry. It only materializes explicitly declared sources.**

# odindeps

`odindeps` is a portable, dependency-free Python 3 helper for materializing
direct Git and local path dependencies in Odin projects. The executable is one
extensionless file and requires Python 3.11 or newer plus Git for Git
dependencies.

## Install

GitHub Releases are the recommended installation method. Each release contains
the standalone Python script, a native-Windows command wrapper, and their
SHA-256 checksums. Python 3.11 or newer is required; Git is required when a
manifest contains Git dependencies.

### macOS and Linux

Download a specific release, verify it, and atomically place it under
`$HOME/.local/bin`:

```sh
version="v0.1.0"
install_directory="$HOME/.local/bin"
mkdir -p "$install_directory"
staging_directory="$(mktemp -d "$install_directory/.odindeps-install.XXXXXX")"
staged_executable="$staging_directory/odindeps"
trap 'rm -rf "$staging_directory"' EXIT INT TERM

base_url="https://github.com/hguerra/odindeps/releases/download/$version"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$staged_executable" "$base_url/odindeps"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$staging_directory/odindeps.sha256" "$base_url/odindeps.sha256"

expected_checksum="$(awk '$2 == "odindeps" {print $1}' "$staging_directory/odindeps.sha256")"
if command -v sha256sum >/dev/null 2>&1; then
  actual_checksum="$(sha256sum "$staged_executable" | awk '{print $1}')"
else
  actual_checksum="$(shasum -a 256 "$staged_executable" | awk '{print $1}')"
fi
test "$actual_checksum" = "$expected_checksum"

chmod 0755 "$staged_executable"
"$staged_executable" --version
mv "$staged_executable" "$install_directory/odindeps"
"$install_directory/odindeps" --version
```

Ensure the installation directory is on `PATH`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Add that export to the appropriate shell startup file if it should persist
across terminal sessions. To upgrade, repeat the same procedure with a newer
`version`.

For convenience, GitHub also exposes the moving URLs
`https://github.com/hguerra/odindeps/releases/latest/download/odindeps` and
`https://github.com/hguerra/odindeps/releases/latest/download/odindeps.sha256`.
Use the versioned URLs above for reproducible installation. A checksum obtained
from the same release detects corruption or mismatched downloads; release
immutability protects published assets from later replacement.

### Native Windows

Download the script and its `.cmd` wrapper into the installation directory:

```powershell
$Version = "v0.1.0"
$InstallDirectory = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force $InstallDirectory | Out-Null
$StagingDirectory = Join-Path $InstallDirectory (".odindeps-install-" + [System.Guid]::NewGuid())
New-Item -ItemType Directory $StagingDirectory | Out-Null
$BaseUrl = "https://github.com/hguerra/odindeps/releases/download/$Version"

foreach ($Asset in @("odindeps", "odindeps.cmd", "odindeps.sha256")) {
  Invoke-WebRequest "$BaseUrl/$Asset" -OutFile (Join-Path $StagingDirectory $Asset)
}
$PublishedChecksums = @{}
Get-Content (Join-Path $StagingDirectory "odindeps.sha256") | ForEach-Object {
  $Hash, $Name = $_ -split "\s+", 2
  $PublishedChecksums[$Name.TrimStart("*")] = $Hash
}
foreach ($Asset in @("odindeps", "odindeps.cmd")) {
  $ActualChecksum = (Get-FileHash (Join-Path $StagingDirectory $Asset) -Algorithm SHA256).Hash
  if ($ActualChecksum -ne $PublishedChecksums[$Asset]) {
    throw "odindeps checksum verification failed for $Asset"
  }
}

python (Join-Path $StagingDirectory "odindeps") --version
Move-Item (Join-Path $StagingDirectory "odindeps") (Join-Path $InstallDirectory "odindeps") -Force
Move-Item (Join-Path $StagingDirectory "odindeps.cmd") (Join-Path $InstallDirectory "odindeps.cmd") -Force
Remove-Item $StagingDirectory -Recurse -Force
& (Join-Path $InstallDirectory "odindeps.cmd") --version
```

Add `$InstallDirectory` to the user `PATH` to invoke `odindeps` directly from a
new terminal. Upgrades repeat the procedure with a newer `$Version`.

### Existing source checkout

On macOS or Linux, run this from the repository root:

```sh
install_directory="$HOME/.local/bin"
mkdir -p "$install_directory"
install -m 0755 ./odindeps "$install_directory/odindeps"
"$install_directory/odindeps" --version
```

On native Windows:

```powershell
$InstallDirectory = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force $InstallDirectory | Out-Null
Copy-Item .\odindeps (Join-Path $InstallDirectory "odindeps") -Force
Copy-Item .\odindeps.cmd (Join-Path $InstallDirectory "odindeps.cmd") -Force
& (Join-Path $InstallDirectory "odindeps.cmd") --version
```

<details>
<summary><strong>Remove odindeps</strong></summary>

On macOS or Linux, remove only the installed executable:

```sh
rm "$HOME/.local/bin/odindeps"
```

On native Windows:

```powershell
Remove-Item (Join-Path $HOME ".local\bin\odindeps")
Remove-Item (Join-Path $HOME ".local\bin\odindeps.cmd")
```

Uninstalling does not remove project dependencies or shared cache entries.
Remove project materializations using the cleanup instructions in the relevant
strategy guide. Before deleting `$HOME/.cache/odindeps`, confirm that no
cache-backed project symlink still points into it.

</details>

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
