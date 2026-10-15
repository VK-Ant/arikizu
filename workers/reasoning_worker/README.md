# reasoning_worker

Local LLM. Talks to an Ollama server (or any Ollama-compatible endpoint). This one is **live** in v0.1, not a placeholder.

## Capabilities

| Capability             | Payload                                                        | Result                        |
| ---------------------- | -------------------------------------------------------------- | ----------------------------- |
| `reasoning.answer`     | `{ question: str, context: str, max_tokens: int }`             | `{ answer: str, model: str }` |
| `reasoning.summarize`  | `{ text: str, template?: str, max_tokens: int }`               | `{ summary: str, model: str }` |
| `reasoning.complete`   | `{ prompt: str, max_tokens: int }`                             | `{ completion: str, model: str }` |

A `template` string supports a single `{text}` placeholder; the worker substitutes the input text into it.

## Prereqs

```
# One-time, outside Arikizu
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b-instruct-q4_K_M       # ~2 GB, Jetson-friendly
```

Running the Ollama server:

```
ollama serve                                  # 127.0.0.1:11434
```

## Config

| Env var                       | Default                                      |
| ----------------------------- | -------------------------------------------- |
| `ARIKIZU_OLLAMA_ENDPOINT`     | `http://127.0.0.1:11434`                     |
| `ARIKIZU_REASONING_MODEL`     | `qwen2.5:3b-instruct-q4_K_M`                 |
| `ARIKIZU_API_KEY`             | (unset)                                      |

Set these in `arikizu.yaml` under the worker's `env:` block.

### Three endpoint patterns

The worker auto-detects which API shape to use from the URL (Ollama's
native `/api/generate` or an OpenAI-compatible `/v1/chat/completions`):

**Device-only** (Ollama on this Pi):

```yaml
env:
  ARIKIZU_OLLAMA_ENDPOINT: http://127.0.0.1:11434
  ARIKIZU_REASONING_MODEL: qwen2.5:1.5b-instruct-q4_K_M
```

**LAN gateway** (big machine on your LAN):

```yaml
env:
  ARIKIZU_OLLAMA_ENDPOINT: http://192.168.1.50:11434
  ARIKIZU_REASONING_MODEL: qwen2.5:7b-instruct-q4_K_M
```

**Cloud (OpenAI-compatible)** — Groq, OpenAI, Together, Deepinfra:

```yaml
env:
  ARIKIZU_OLLAMA_ENDPOINT: https://api.groq.com/openai
  ARIKIZU_REASONING_MODEL: llama-3.1-70b-versatile
  ARIKIZU_API_KEY: your_key_here
```

See [`docs/MODEL_STRATEGY.md`](../../docs/MODEL_STRATEGY.md) for the full
device-to-model matrix and the decision tree.

## Try it

```
arikizu call reasoning.summarize '{"text":"The quick brown fox jumps over the lazy dog. The dog was not amused.","max_tokens":80}'
```

## Model choices for Jetson Orin Nano 8 GB

| Model                                | VRAM target | Quality | Latency |
| ------------------------------------ | ----------- | ------- | ------- |
| `qwen2.5:3b-instruct-q4_K_M`         | ~2 GB       | Good    | Fast    |
| `phi-3.5-mini-instruct:q4_K_M`       | ~2.5 GB     | Good    | Fast    |
| `llama3.1:8b-instruct-q4_K_M`        | ~4.8 GB     | Better  | Slower  |

Pick based on how much memory the vision and audio workers want.
