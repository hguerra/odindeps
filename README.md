**odindeps is not a package manager. It does not resolve transitive dependencies, generate an Odin dependency lockfile, validate dependency checksums, or provide a package registry. It only materializes explicitly declared sources.**

# odindeps

`odindeps` is a portable, dependency-free Python 3 helper for materializing
direct Git and local path dependencies in Odin projects. The executable is one
extensionless file and requires Python 3.11 or newer plus Git for Git
dependencies.

<details>
<summary><strong>Install odindeps</strong></summary>

Release downloads are the recommended installation method after the first
GitHub release is published. Until then, install from an existing source
checkout as shown below.

### macOS and Linux

Download the latest release, verify the published SHA-256 checksum, and install
the executable under `$HOME/.local/bin`:

```sh
install_directory="$HOME/.local/bin"
download_directory="$(mktemp -d)"

mkdir -p "$install_directory"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$download_directory/odindeps" \
  https://github.com/hguerra/odindeps/releases/latest/download/odindeps
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "$download_directory/odindeps.sha256" \
  https://github.com/hguerra/odindeps/releases/latest/download/odindeps.sha256

expected_checksum="$(awk '{print $1}' "$download_directory/odindeps.sha256")"
if command -v sha256sum >/dev/null 2>&1; then
  actual_checksum="$(sha256sum "$download_directory/odindeps" | awk '{print $1}')"
else
  actual_checksum="$(shasum -a 256 "$download_directory/odindeps" | awk '{print $1}')"
fi
test "$actual_checksum" = "$expected_checksum"

install -m 0755 "$download_directory/odindeps" "$install_directory/odindeps"
rm -rf "$download_directory"
"$install_directory/odindeps" --version
```

Ensure the installation directory is on `PATH`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Add that export to the appropriate shell startup file if it should persist
across terminal sessions.

### Native Windows

Download the same extensionless release asset, verify it, and invoke it
explicitly through Python:

```powershell
$InstallDirectory = Join-Path $HOME ".local\bin"
$DownloadDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("odindeps-" + [System.Guid]::NewGuid())
$DownloadPath = Join-Path $DownloadDirectory "odindeps"
$ChecksumPath = Join-Path $DownloadDirectory "odindeps.sha256"

New-Item -ItemType Directory -Force $InstallDirectory | Out-Null
New-Item -ItemType Directory -Force $DownloadDirectory | Out-Null
Invoke-WebRequest `
  https://github.com/hguerra/odindeps/releases/latest/download/odindeps `
  -OutFile $DownloadPath
Invoke-WebRequest `
  https://github.com/hguerra/odindeps/releases/latest/download/odindeps.sha256 `
  -OutFile $ChecksumPath

$ExpectedChecksum = ((Get-Content $ChecksumPath -Raw).Trim() -split "\s+")[0]
$ActualChecksum = (Get-FileHash $DownloadPath -Algorithm SHA256).Hash
if ($ActualChecksum -ne $ExpectedChecksum) {
  throw "odindeps checksum verification failed"
}

Move-Item $DownloadPath (Join-Path $InstallDirectory "odindeps") -Force
Remove-Item $DownloadDirectory -Recurse -Force
python (Join-Path $InstallDirectory "odindeps") --version
```

The first release does not provide a Windows executable wrapper.

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
python (Join-Path $InstallDirectory "odindeps") --version
```

</details>

<details>
<summary><strong>Remove odindeps</strong></summary>

On macOS or Linux, remove only the installed executable:

```sh
rm "$HOME/.local/bin/odindeps"
```

On native Windows:

```powershell
Remove-Item (Join-Path $HOME ".local\bin\odindeps")
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

By default, the dependency is materialized at
`src/third_party/slog`.

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
    "destination_root": "src/third_party"
  }
}
```

Configuration is merged from built-ins, manifest `defaults`, then
per-dependency `options`. The checked-in `odindeps.schema.json` describes the
manifest using JSON Schema Draft 2020-12.

## Strategy guides

| Strategy | Guide | Important effect |
| --- | --- | --- |
| Clone snapshot | [Clone example](examples/clone/README.md) | Publishes source without `.git`. |
| Local copy or symlink | [Local example](examples/local/README.md) | Copies everywhere; symlinks only on POSIX. |
| Cached clone symlink | [Cache example](examples/cache-symlink/README.md) | Creates a machine-local permanent symlink. |
| Git submodule | [Submodule example](examples/submodule/README.md) | Stages `.gitmodules` and a gitlink. |
| Git subtree | [Subtree example](examples/subtree/README.md) | Creates commits in the consuming repository. |

## Limits and exit codes

Git clone, submodule, subtree, and local copy are supported on macOS, Linux,
and native Windows when the required Git capability exists. Local and cache
symlinks are unsupported on native Windows.

Exit codes are `2` for validation, `3` for unsafe conflicts, `4` for Git
failures, and `5` for filesystem failures. `uv.lock` belongs only to the Python
development environment; it neither locks Odin dependencies nor provides
dependency checksums.
