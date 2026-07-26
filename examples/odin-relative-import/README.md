# Odin relative import

This compact example overrides the public `third_party` default so the
dependency is materialized beside the importing package. From this directory:

```sh
cd myproject
../../../odindeps sync
odin run src
```

On native Windows, invoke the extensionless Python script explicitly:

```powershell
cd myproject
python ../../../odindeps sync
odin run src
```

`src/main.odin` imports `slog` with:

```odin
import "./third_party/slog"
```

This keeps the build command short because it needs no `-collection` flag. The
tradeoff is that the import is coupled to the source file's physical location:
a package nested one directory deeper would need a path such as
`import "../third_party/slog"`.

The explicit `"destination_root": "src/third_party"` setting preserves this
layout; removing that override adopts the public root-level `third_party`
default instead. The exact `LICENSE` filename and Odin sources are retained,
while upstream tests and examples are excluded.
