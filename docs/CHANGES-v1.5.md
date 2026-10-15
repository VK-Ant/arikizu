# Arikizu v1.5

## v1.5.25 (no more 404 noise from Ollama probe)

The reasoning worker was logging 404s like:
    POST http://127.0.0.1:11434/api/generate "HTTP/1.1 404 Not Found"

That happens when the local GGUF path returns None for any reason
(empty text, generation error, etc.) and the worker tries the HTTP
fallback. The default endpoint was 127.0.0.1:11434, which usually
has nothing on it, so curl got 404 from whatever random port handler.

Fixed:
1. HTTP fallback is now OPT-IN. Env var renamed to
   ARIKIZU_HTTP_LLM_ENDPOINT. If unset, zero HTTP calls happen.
2. The legacy ARIKIZU_OLLAMA_ENDPOINT is still honored for people
   who had it set to a non-default value (actual LAN gateway).
   The default 127.0.0.1:11434 is treated as "disabled".
3. arikizu.yaml.example no longer defaults to 11434. The HTTP
   fallback is commented out with instructions.

Result: with no Ollama installed, logs are clean. Only the local
GGUF (SmolLM2) and built-in KB are tried. No noisy 404 lines.

## v1.5.24 (real-time audio + simpler documents)
## v1.5.23 (fix LLM output + real VAD + vision defaults)
## v1.5.22 .. v1.5 (prior history)
