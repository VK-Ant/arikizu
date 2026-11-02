# Your custom capabilities

**This is where you drop your own logic.** Any Python file you add
here becomes an Arikizu capability without touching the main code.

## Two files per capability

### 1. Your Python handler — in this folder

```python
# custom/my_math.py
from arikizu_worker import Worker
worker = Worker.current()

@worker.handler("my.add")
def add(a: float, b: float) -> dict:
    """Add two numbers."""
    return {"result": a + b}

@worker.handler("my.multiply")
def multiply(a: float, b: float) -> dict:
    return {"result": a * b}
```

Rules:
- One `Worker.current()` call per file (gets the shared custom-worker instance)
- `@worker.handler("your.name")` decorator per capability
- Each handler returns a dict (serialized to JSON for the caller)
- Async handlers work too: `async def handler(...)`
- Any `.py` file whose name doesn't start with `_` or `.` is auto-loaded

### 2. The registry entry — in `../capabilities.d/`

```toml
# capabilities.d/my_math.toml
[my_add]
name = "my.add"
worker = "custom"
input = { a = "number", b = "number" }
output = "object"
timeout_ms = 5000

[my_multiply]
name = "my.multiply"
worker = "custom"
input = { a = "number", b = "number" }
output = "object"
timeout_ms = 5000
```

Every capability needs this block. The router uses it for routing,
timeouts and policy. The main `capabilities.toml` is untouched —
`capabilities.d/*.toml` files are merged in automatically.

## Hot reload — just save the file

The custom worker watches this folder. Save your `.py` file and the
new handlers are live in ~1 second. **No restart needed.** You will
see this log line in the worker:

    custom_worker reloaded: 1 file(s), 3 capabilit(ies): ['hello.add', 'hello.greet', 'hello.timestamp']

Your capability is live at `POST /api/v1/call/my/add`. The main
Arikizu runtime does not need a restart either.

New capability `.toml` files in `capabilities.d/` are NOT hot-reloaded —
the router loads those at startup. If you add a new TOML entry, run
`arikizu reload` (or restart the main process). Editing existing Python
handlers for already-registered capabilities is instant.

Hot reload is on by default. To disable it, set `ARIKIZU_CUSTOM_NO_WATCH=1`
in the environment for the custom worker (useful in production).

## Call it from anywhere

The capability behaves identically to the built-in ones:
- HTTP: `curl -X POST http://127.0.0.1:7000/api/v1/call/my/add -d '{"payload": {"a": 2, "b": 3}}'`
- From an agent: list `my.add` under the agent's policy
- From a pipeline: `capability: my.add` as a stage
- From an external MCP client: add `my.add` to `MCP_ALLOWED_CAPABILITIES`

Policy, audit logging and the approval queue apply the same way.

## Example

`hello.py` + `../capabilities.d/hello.toml` ship as a working example.
Copy them, rename, change the code. Delete them when you don't need
the demo.
