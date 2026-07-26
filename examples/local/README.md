# Local path dependency

Local dependencies support independent copies on every platform and relative
directory symlinks on macOS and Linux.

## 1. Prepare a source and project

```sh
mkdir -p local-workspace/shared local-workspace/project
printf 'package shared\n' > local-workspace/shared/shared.odin
cd local-workspace/project
```

Create `odindeps.json`:

```json
{
  "schema_version": 1,
  "dependencies": {
    "shared": {
      "path": "../shared"
    }
  }
}
```

## 2. Copy the source

```sh
odindeps sync
```

The independent snapshot is at `src/third_party/shared`. Later source changes
are applied only when explicitly refreshed:

```sh
odindeps sync --force
```

## 3. Choose a symlink instead

On macOS or Linux, select the symlink strategy before the first sync:

```json
{
  "schema_version": 1,
  "dependencies": {
    "shared": {
      "path": "../shared",
      "options": {
        "local": {
          "strategy": "symlink"
        }
      }
    }
  }
}
```

```sh
odindeps sync
readlink src/third_party/shared
```

The link is relative when possible. Native Windows rejects this strategy
during validation and never falls back to copying.

## 4. Clean up

Remove only the project entry. This does not modify the original source:

```sh
if test -L src/third_party/shared; then
  rm src/third_party/shared
else
  rm -rf src/third_party/shared
fi
```
