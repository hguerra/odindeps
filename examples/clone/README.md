# Clone snapshot

The default Git strategy publishes a detached source snapshot without its
`.git` directory. It is suitable when the dependency should be ordinary
project content rather than part of the consuming repository's Git topology.

## 1. Create the project

```sh
mkdir odindeps-clone-example
cd odindeps-clone-example
```

Create `odindeps.json`:

```json
{
  "schema_version": 1,
  "dependencies": {
    "slog": {
      "git": "github.com/hguerra/odin-slog",
      "rev": "v0.0.1"
    }
  }
}
```

## 2. Synchronize

```sh
odindeps sync
```

The dependency is available at `src/third_party/slog`. Confirm that the
snapshot contains metadata but no Git repository:

```sh
test -f src/third_party/slog/.odindeps-meta.json
test ! -e src/third_party/slog/.git
```

Running `odindeps sync` again is a no-op while the managed metadata matches.

## 3. Update

Change `rev` to another tag or commit, then refresh the owned snapshot:

```sh
odindeps sync --force
```

`--force` refuses to replace a directory that does not contain matching
`odindeps` ownership metadata.

## 4. Clean up

Remove the materialized snapshot and, if desired, the example project:

```sh
rm -rf src/third_party/slog
```
