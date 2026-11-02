# Python app examples

If you prefer Python over HTML/JS for building UIs, use whatever
framework you like — Arikizu's HTTP API is framework-agnostic.

| File | Framework | Run |
|------|-----------|-----|
| `streamlit_app.py` | Streamlit | `pip install streamlit requests` then `streamlit run streamlit_app.py` |
| `gradio_app.py` | Gradio | `pip install gradio requests` then `python gradio_app.py` |

Both call Arikizu capabilities through one function:

```python
def call_cap(cap: str, payload: dict) -> dict:
    r = requests.post(
        f"http://127.0.0.1:7000/api/v1/call/{cap.replace('.', '/')}",
        json={"payload": payload},
    )
    return r.json()
```

That is the whole integration surface. The same pattern works for:

- **Flask / FastAPI** — build a REST wrapper or your own frontend
- **Dash / Panel / Reflex** — Python dashboard frameworks
- **Jupyter notebook** — interactive exploration
- **React / Vue / Svelte** — any JS framework can `fetch` the same URL
- **curl / Postman** — manual testing from the command line

## Why there is no "Streamlit mode" in Arikizu itself

Arikizu is deliberately a capability layer, not a UI framework. If
Arikizu shipped a Streamlit clone, you would be locked into one
layout style. The HTTP boundary lets you pick whichever UI tool fits
your users — a quick Streamlit tool for an internal team, a polished
React app for customers, a Dash dashboard for operators, all talking
to the same local capability set.

The HTML demo pages under `demo/web/` are the reference frontend.
Copy `demo/web/user/hello.html` or either of these Python examples
to start your own.
