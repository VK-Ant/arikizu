# Arikizu v1.5

## v1.5.26 (fix demo gaps + audio keyword spot)

Three real fixes:

1. **Demo hub labels corrected.** Reasoning no longer says "needs
   Ollama" (it has not for 10 releases). Audio and Docs no longer
   say "partial". New tags: "live LLM", "live mic", "upload+QA".

2. **Golden set shipped and eval_worker fixed.**
   `golden/default.jsonl` now ships with 5 example rows. The eval
   worker's golden_run handler now actually runs the evaluation:
   returns per-row scores, pass/fail per row, overall pass rate, and
   mean Jaccard. "golden set not found" error is gone (unless you
   name a set that doesn't exist).

3. **Audio keyword spotter added.**
   New `audio.keyword_spot` capability + UI field for comma-separated
   keywords. While the mic is on, every chunk is sent through the
   keyword spotter (VAD segments mapped to each requested keyword).
   Mic indicator shows "KW: help, stop" when a keyword is flagged.
   Phonetic matching is pending (needs ASR; weekend 6).

Also added: a note on the audio page explaining why the shipped
sample.wav gives 0 speech segments (it is a 440Hz sine tone, not
speech). The microphone path works correctly.

## v1.5.25 (no more Ollama 404 noise)
## v1.5.24 (real-time audio + simpler documents)
## v1.5.23 .. v1.5 (prior history)
