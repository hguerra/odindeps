# Git subtree

The subtree strategy imports dependency history into the consuming repository.
It intentionally creates commits and requires `git subtree` plus a completely
clean worktree and index.

## 1. Prepare a clean consuming repository

```sh
mkdir odindeps-subtree-example
cd odindeps-subtree-example
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
          "strategy": "subtree",
          "subtree": {
            "squash": true
          }
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
git log --oneline -- third_party/slog
```

Unlike clone and submodule strategies, `git subtree add` creates a consuming
repository commit. Squash mode is enabled by default.

## 3. Update

Change `rev`, commit the manifest so the worktree is clean, and request a
managed subtree pull:

```sh
git add odindeps.json
git commit -m "Update slog revision"
odindeps sync --force
git log --oneline -- third_party/slog
```

Set `git.subtree.squash` to `false` only when importing the dependency's
unsquashed history is intentional.

## 4. Clean up

Subtree cleanup is a history-changing project operation. Remove the directory
in an explicit commit, or revert the subtree-add commit when that matches the
repository's history policy:

```sh
git rm -r third_party/slog
git commit -m "Remove slog subtree"
```
