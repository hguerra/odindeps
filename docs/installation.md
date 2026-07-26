# Installation

`odindeps` is a standalone Python script. It requires Python 3.11 or newer.
Git is required when a manifest declares Git dependencies.

## macOS and Linux

The shortest installation uses the latest GitHub release:

```sh
mkdir -p "$HOME/.local/bin"
curl -fsSL https://github.com/hguerra/odindeps/releases/latest/download/odindeps -o "$HOME/.local/bin/odindeps"
chmod +x "$HOME/.local/bin/odindeps"
```

Add the directory to `PATH` if it is not already present:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Add that export to the appropriate shell startup file to make it persistent.
Run `odindeps --version` to confirm the installation.

To install a specific version, replace `latest` in the URL with the release
path:

```text
https://github.com/hguerra/odindeps/releases/download/v0.1.0/odindeps
```

Repeat the installation commands to upgrade.

## Windows

Native Windows uses the Python script plus the release's command wrapper:

```powershell
$InstallDirectory = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force $InstallDirectory | Out-Null
Invoke-WebRequest "https://github.com/hguerra/odindeps/releases/latest/download/odindeps" -OutFile (Join-Path $InstallDirectory "odindeps")
Invoke-WebRequest "https://github.com/hguerra/odindeps/releases/latest/download/odindeps.cmd" -OutFile (Join-Path $InstallDirectory "odindeps.cmd")
```

Add `$InstallDirectory` to the user `PATH`, open a new terminal, and run
`odindeps --version`. Repeat the downloads to upgrade.

## Install from a source checkout

On macOS or Linux, run this from the repository root:

```sh
mkdir -p "$HOME/.local/bin"
cp ./odindeps "$HOME/.local/bin/odindeps"
chmod +x "$HOME/.local/bin/odindeps"
```

On Windows:

```powershell
$InstallDirectory = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force $InstallDirectory | Out-Null
Copy-Item .\odindeps, .\odindeps.cmd $InstallDirectory -Force
```

## Remove

On macOS or Linux:

```sh
rm "$HOME/.local/bin/odindeps"
```

On Windows:

```powershell
Remove-Item (Join-Path $HOME ".local\bin\odindeps")
Remove-Item (Join-Path $HOME ".local\bin\odindeps.cmd")
```

Removing the executable does not remove project materializations or shared
cache entries. Before removing `$HOME/.cache/odindeps`, confirm that no project
still uses a cache-backed dependency symlink.
