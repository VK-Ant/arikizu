"""Gradio app that talks to a running Arikizu instance.

Same pattern as streamlit_app.py — single `requests.post` per
capability. Gradio is better than Streamlit when you want a quick ML
demo UI with components wired directly to a function.

Run:
    pip install gradio requests
    python examples/python-apps/gradio_app.py

Needs Arikizu already running on http://127.0.0.1:7000.
"""
from __future__ import annotations

import base64
import io

import gradio as gr
import requests

ARIKIZU = "http://127.0.0.1:7000/api/v1"


def call_cap(cap: str, payload: dict) -> dict:
    r = requests.post(
        f"{ARIKIZU}/call/{cap.replace('.', '/')}",
        json={"payload": payload}, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def ask(question: str, max_tokens: int) -> str:
    try:
        r = call_cap("reasoning.answer", {"question": question, "max_tokens": max_tokens})
        return r.get("answer", "(no answer)")
    except Exception as e:
        return f"error: {e}"


def detect(image_bytes, confidence: float):
    if image_bytes is None:
        return "pick an image first"
    import io as _io
    buf = _io.BytesIO()
    image_bytes.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    r = call_cap("vision.detect", {"image_base64": b64, "confidence": confidence})
    lines = [f"{r.get('count', 0)} objects:"]
    for d in r.get("detections", []):
        lines.append(f"- {d.get('class')} ({d.get('confidence', 0):.2f})")
    return "\n".join(lines)


with gr.Blocks(title="Arikizu + Gradio") as app:
    gr.Markdown("# Arikizu + Gradio\nOne function per capability, wired into Gradio widgets.")

    with gr.Tab("Ask"):
        q = gr.Textbox(label="Question", value="What is edge AI?")
        tokens = gr.Slider(32, 512, value=128, step=16, label="Max tokens")
        a_out = gr.Textbox(label="Answer", lines=5)
        gr.Button("Answer").click(ask, inputs=[q, tokens], outputs=a_out)

    with gr.Tab("Detect"):
        img = gr.Image(type="pil", label="Image")
        conf = gr.Slider(0.1, 0.95, value=0.5, step=0.05, label="Confidence floor")
        d_out = gr.Textbox(label="Detections", lines=10)
        gr.Button("Detect").click(detect, inputs=[img, conf], outputs=d_out)


if __name__ == "__main__":
    app.launch()
