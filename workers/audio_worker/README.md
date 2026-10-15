# audio_worker

Wraps Sonarwise. Transcription, VAD, keyword spotting. Weekend 6 wires the real backend; v0.1 ships placeholders.

## Capabilities

| Capability             | Payload                                          | Result                           |
| ---------------------- | ------------------------------------------------ | -------------------------------- |
| `audio.transcribe`     | `{ audio_path: str, lang: str }`                 | `{ text: str, lang: str }`       |
| `audio.vad`            | `{ audio_path: str, threshold: float }`          | `{ segments: [...] }`            |
| `audio.keyword_spot`   | `{ audio_path: str, keywords: [str] }`           | `{ spotted: [...] }`             |

## Wiring Sonarwise (Weekend 6)

```python
from sonarwise import Transcriber, VAD, KeywordSpotter

transcriber = Transcriber.load("whisper-small-int8", backend="onnx_cpu")
vad = VAD.silero_v4()
kws = KeywordSpotter.light()

@worker.handler("audio.transcribe")
def transcribe(audio_path: str = "", lang: str = "en") -> dict:
    text = transcriber(audio_path, lang=lang)
    return {"audio": audio_path, "text": text, "lang": lang}
```

## Streaming note

v0.1 keeps the API batch (one file in, one text out). Streaming mic input via the device bus lands with the pipeline refactor in Weekend 11.
