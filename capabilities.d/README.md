# Plug-in capability registry

Drop `*.toml` files here to register your own capabilities. The main
`capabilities.toml` stays untouched.

Each file is a map of capability blocks:

```toml
[my_calculate]
name = "my.calculate"
worker = "custom"
input = { a = "number", b = "number" }
output = "object"
timeout_ms = 5000
```

| Field | Meaning |
|-------|---------|
| `name` | Dotted capability name used in the URL and in pipelines |
| `worker` | Which worker handles it. For user-written capabilities this is almost always `custom`. |
| `input` | Expected input schema (hint for the UI; not enforced strictly) |
| `output` | `"string"`, `"object"`, `"array"`, or `"binary"` |
| `timeout_ms` | How long to wait before returning an error |
| `priority` | Optional. 0 = normal, higher = may preempt lower |

Files whose names start with `.` or `_` are skipped (use that for drafts).

The paired Python handlers live in `../custom/`. See
`../custom/README.md` for the two-file pattern.
