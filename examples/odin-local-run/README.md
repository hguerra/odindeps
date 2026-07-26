# Odin local dependency run

This complete, offline example materializes an Odin package with `odindeps`
and runs an application that imports it. It deliberately uses a local
dependency so it is reproducible without network access.

From this directory, synchronize the declared dependency and execute the app:

```sh
cd project
../../../odindeps sync
odin run src -collection:third_party=src/third_party
```

Expected output:

```text
Hello, Odin dependency!
```

`project/odindeps.json` maps `../shared/greeting` into
`project/src/third_party/greeting`. The application imports that materialized
package through Odin's `third_party` collection. Delete
`project/src/third_party/greeting` and run `odindeps sync` again to recreate
the snapshot.
