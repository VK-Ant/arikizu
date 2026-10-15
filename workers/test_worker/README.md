# test_worker

Reference worker. Proves the IPC path end-to-end before any real library is wired. CI uses this for the Rust `--test integration` run.

## Capabilities

| Capability   | Payload                   | Result                 |
| ------------ | ------------------------- | ---------------------- |
| `test.echo`  | `{ message: str }`        | `{ echo: <message> }`  |
| `test.add`   | `{ a: int, b: int }`      | `{ sum: <a+b> }`       |
| `test.slow`  | `{ seconds: float }`      | `{ slept: <seconds> }` |

## Try it

```
# Terminal 1
arikizu run

# Terminal 2
arikizu call test.echo '{"message":"hi"}'          # -> {"echo":"hi"}
arikizu call test.add '{"a":2,"b":40}'              # -> {"sum":42}
arikizu call test.slow '{"seconds":1.5}'            # -> {"slept":1.5} after a 1.5s wait
```
