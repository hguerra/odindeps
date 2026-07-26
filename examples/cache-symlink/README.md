# Cached clone symlink

Cache mode stores an immutable clone snapshot in a shared machine-local cache
and creates a permanent project symlink to it. It is available on macOS and
Linux only.

## 1. Create the project

```sh
mkdir odindeps-cache-example
cd odindeps-cache-example
```

Create `odindeps.json`:

```json
{
  "schema_version": 1,
  "dependencies": {
    "slog": {
      "git": "github.com/hguerra/odin-slog",
      "rev": "v0.0.1",
      "options": {
        "cache": {
          "mode": "symlink",
          "directory": "~/.cache/odindeps"
        }
      }
    }
  }
}
```

Ignore the generated project link:

```sh
printf '/src/third_party/slog\n' >> .gitignore
```

## 2. Synchronize and inspect

```sh
odindeps sync
test -L src/third_party/slog
readlink src/third_party/slog
```

The cache key includes the normalized Git locator, resolved commit, and clone
file filters. Identical inputs reuse the same entry. Cache hashes address
content but do not provide dependency-integrity guarantees.

## 3. Update

After changing `rev`, relink to the newly selected immutable entry:

```sh
odindeps sync --force
```

The previous cache entry is retained. `odindeps` does not perform cache garbage
collection.

## 4. Clean up

Remove the project symlink first:

```sh
rm src/third_party/slog
```

Uninstalling `odindeps` does not remove shared cache entries. Delete
`$HOME/.cache/odindeps` only after confirming that no other project symlink
uses it.
