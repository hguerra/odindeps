# Git submodule

The submodule strategy preserves independent dependency history and records the
selected commit as a gitlink in the consuming repository.

## 1. Prepare a clean consuming repository

```sh
mkdir odindeps-submodule-example
cd odindeps-submodule-example
git init
git config user.name "Example"
git config user.email "example@example.invalid"
```

Create and commit `odindeps.json`:

```json
{
  "schema_version": 1,
  "dependencies": {
    "slog": {
      "git": "github.com/hguerra/odin-slog",
      "rev": "v0.0.1",
      "options": {
        "git": {
          "strategy": "submodule"
        }
      }
    }
  }
}
```

```sh
git add odindeps.json
git commit -m "Declare Odin dependencies"
```

## 2. Synchronize and inspect

```sh
odindeps sync
git status --short
git submodule status
git -C third_party/slog rev-parse HEAD
```

The command stages `.gitmodules` and the `third_party/slog` gitlink. It does
not create a consuming-repository commit:

```sh
git commit -m "Materialize slog submodule"
```

## 3. Update

Change `rev`, commit the manifest change so the consuming repository is clean,
then refresh and commit the staged gitlink:

```sh
git add odindeps.json
git commit -m "Update slog revision"
odindeps sync --force
git commit -m "Refresh slog submodule"
```

Dirty or unowned submodules are rejected even with `--force`.

## 4. Clean up

```sh
git submodule deinit -f -- third_party/slog
git rm -f -- third_party/slog
rm -rf .git/modules/slog
git commit -m "Remove slog submodule"
```
