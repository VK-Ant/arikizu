# eval_worker

Wraps LLMEvalKit. Score, compare, and run golden-set evaluations. v0.1 ships exact-match and Jaccard; Weekend 12 wires the full LLMEvalKit metric suite.

## Capabilities

| Capability          | Payload                                              | Result                                 |
| ------------------- | ---------------------------------------------------- | -------------------------------------- |
| `eval.score`        | `{ predicted: str, expected: str, metrics?: [str] }` | `{ scores: { exact: 0..1, ... } }`     |
| `eval.compare`      | `{ a: str, b: str }`                                 | `{ a_len, b_len, equal }`              |
| `eval.golden_run`   | `{ set_name: str }`                                  | `{ set: str, size: int }`              |

## Golden set format

Each line in `golden/<set_name>.jsonl`:

```jsonl
{"id":"q-001","input":{"image_path":"golden/img/a.jpg"},"expected":{"detections":[...]}}
```

The eval runner iterates lines, invokes the capability under test, and scores the result. v0.1 scaffold just counts lines; Weekend 12 adds the real runner.

## Env var

| Env var                | Default    |
| ---------------------- | ---------- |
| `ARIKIZU_GOLDEN_DIR`   | `./golden` |

## Try it

```
arikizu call eval.score '{"predicted":"the cat sat","expected":"the cat sat","metrics":["exact","jaccard"]}'
# -> {"scores":{"exact":1.0,"jaccard":1.0}}

arikizu call eval.score '{"predicted":"the cat sat","expected":"the cats sat","metrics":["exact","jaccard"]}'
# -> {"scores":{"exact":0.0,"jaccard":0.5}}
```

## When to use

- CI: nightly golden-set run gates the next release
- Review queue: an operator rating a response can trigger a `memory.reward` _and_ an `eval.score` to track drift
- Model manager: Weekend 15 compares a new model's `golden_run` score to the current one before swapping
