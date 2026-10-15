# ant-ipc

Length-prefixed MessagePack over Unix domain sockets. The control plane only; large tensors travel via shared memory handles added in Weekend 5.

## Wire format

Every frame is laid out as:

```
+----+----+----+----+---------------------------+
|   big-endian u32  |   MessagePack bytes        |
|   payload length  |   (<=100 MiB)             |
+----+----+----+----+---------------------------+
```

A frame larger than 100 MiB is refused on the read side with `ArikizuError::Ipc`.

## Frame kinds

| Kind         | Direction          | Fields                                                 |
| ------------ | ------------------ | ------------------------------------------------------ |
| `hello`      | worker → runtime   | worker, version, capabilities                          |
| `call`       | runtime → worker   | id, capability, payload                                |
| `reply`      | worker → runtime   | id, result                                             |
| `error`      | worker → runtime   | id, error                                              |
| `heartbeat`  | either             | memory_rss_mb, queue_depth, in_flight, resident_models |
| `event`      | worker → runtime   | subject, payload                                       |

Protocol version is `1`. Bump `PROTOCOL_VERSION` in both this crate and `arikizu_worker/__init__.py` when the wire changes; the supervisor refuses a `hello` with a mismatched version.

## API

```rust
use ant_ipc::{bind_supervisor, read_frame, write_frame, Frame, PROTOCOL_VERSION};

let listener = bind_supervisor(&socket_path).await?;
let (mut stream, _addr) = listener.accept().await?;
let frame = read_frame(&mut stream).await?;
write_frame(&mut stream, &Frame::Reply { id, result }).await?;
```

The supervisor splits one `UnixStream` into read/write halves and spawns two tasks; see `ant-supervisor/src/lib.rs`.

## Tests

```
cargo test -p ant-ipc
```

Covers: hello round-trip, call+reply round-trip, oversized frame rejection.
