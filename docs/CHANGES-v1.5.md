# Arikizu v1.5

## v1.5.20 (docs extraction via SLM, not regex)

Rewrote the docs worker to use the small language model instead of
regex rules. The flow is now:

1. docs.extract reads the file text and the schema.
2. Builds a prompt asking the LLM to return a JSON object with the
   requested fields.
3. Posts to the local /api/v1/call/reasoning/answer endpoint, which
   routes to llama-cpp with the SmolLM2 GGUF.
4. Parses the LLM's JSON reply and returns the fields.
5. Falls back to regex only when the LLM is not available (e.g. the
   GGUF file is missing). The response note tells you so.

The backend field in the response now says "slm:local-gguf" when the
real LLM extracted the fields. Document intelligence is actual LLM
work, not regex pattern matching.

Also confirmed: greeting on the dashboard home page is time-of-day
aware using the browser's local time (works correctly in IST).

## v1.5.19 (live dashboard + visible backend)
## v1.5.18 (removed Vellex)
## v1.5.17 (small LLM bundled by default)
## v1.5.16 .. v1.5 (prior history)
