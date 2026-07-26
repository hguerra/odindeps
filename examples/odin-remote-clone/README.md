# Odin remote clone run

This complete example uses `odindeps` to clone the pinned remote
[`hguerra/odin-slog` v0.0.1](https://github.com/hguerra/odin-slog/releases/tag/v0.0.1),
then runs an Odin application that imports the materialized package.

From this directory, synchronize the dependency and execute the app:

```sh
cd project
../../../odindeps sync
odin run src -collection:deps=src/third_party
```

Expected output is one structured JSON log record whose `message` is
`remote dependency materialized`.

`project/odindeps.json` pins the source tag and materializes it at
`project/src/third_party/slog`. The `-collection:deps=src/third_party` flag
maps Odin's `import "deps:slog"` to that snapshot. The clone strategy intentionally omits the
dependency's `.git` directory. Its `includes` filter retains `.odin` source
files, while `excludes` removes upstream test and example sources (plus odindeps ownership metadata). The
application's domain logic lives in `project/src/myproject/logic.odin`; the
main package only creates the logger and invokes that logic. To recreate the snapshot, delete
`project/src/third_party/slog` and run `odindeps sync` again.
