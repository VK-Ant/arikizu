"""Streamlit app that talks to a running Arikizu instance.

Shows that Arikizu's HTTP API is framework-agnostic: anything that
speaks HTTP works. Streamlit is one example; the same pattern applies
to Gradio, Flask, FastAPI, Dash, Panel, Reflex, a plain Jupyter
notebook, or your own React/Vue app.

Run:
    pip install streamlit requests
    streamlit run examples/python-apps/streamlit_app.py

Needs Arikizu already running on http://127.0.0.1:7000
(see QUICKSTART.md).
"""
from __future__ import annotations

import base64
import io

import requests
import streamlit as st

ARIKIZU = "http://127.0.0.1:7000/api/v1"


def call_cap(cap: str, payload: dict) -> dict:
    """One function - every Arikizu capability goes through this."""
    r = requests.post(
        f"{ARIKIZU}/call/{cap.replace('.', '/')}",
        json={"payload": payload},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Arikizu + Streamlit", page_icon="orange_circle")
st.title("Arikizu + Streamlit")
st.caption(
    "A ~90 line Streamlit app that calls Arikizu capabilities over HTTP. "
    "Use this as a starting point for your own tool."
)

# Health check
try:
    status = requests.get(f"{ARIKIZU}/status", timeout=5).json()
    ready = sum(1 for w in status.get("workers", []) if w.get("state") == "Ready")
    total = len(status.get("workers", []))
    st.success(
        f"Connected. {ready}/{total} workers Ready, "
        f"{status.get('capability_count', 0)} capabilities, "
        f"uptime {status.get('uptime_s', 0):.0f}s"
    )
except Exception as e:
    st.error(f"Arikizu not reachable at {ARIKIZU}: {e}")
    st.stop()


tab_ask, tab_vision, tab_time = st.tabs(["Ask the local LLM", "Detect in an image", "Forecast a signal"])


# ---------- Ask ----------
with tab_ask:
    q = st.text_input("Question", "What is edge AI?")
    tokens = st.slider("Max tokens", 32, 512, 128)
    if st.button("Answer", key="ask"):
        with st.spinner("thinking..."):
            r = call_cap("reasoning.answer", {"question": q, "max_tokens": tokens})
        st.write(r.get("answer", "(no answer)"))
        st.caption(f"{r.get('ms', 0)} ms  ·  backend: {r.get('backend', 'unknown')}")


# ---------- Vision ----------
with tab_vision:
    uploaded = st.file_uploader("Pick an image", type=["jpg", "jpeg", "png"])
    conf = st.slider("Confidence floor", 0.1, 0.95, 0.5, 0.05)
    if uploaded and st.button("Detect", key="det"):
        b64 = base64.b64encode(uploaded.read()).decode("ascii")
        with st.spinner("detecting..."):
            r = call_cap("vision.detect", {"image_base64": b64, "confidence": conf})
        st.image(uploaded, caption=f"{r.get('count', 0)} objects")
        for d in r.get("detections", []):
            st.write(f"- **{d.get('class')}** ({d.get('confidence', 0):.2f})")


# ---------- Timeseries ----------
with tab_time:
    uploaded_csv = st.file_uploader(
        "Pick a CSV with one numeric column", type=["csv"], key="ts_csv"
    )
    horizon = st.slider("Forecast horizon (steps)", 10, 200, 30)
    if uploaded_csv and st.button("Forecast", key="fc"):
        import csv

        rows = list(csv.reader(io.StringIO(uploaded_csv.read().decode("utf-8"))))
        values = []
        for row in rows[1:]:
            try:
                values.append(float(row[-1]))
            except Exception:
                continue
        with st.spinner("forecasting..."):
            r = call_cap("timeseries.forecast", {"series": values, "horizon": horizon})
        if "forecast" in r:
            import pandas as pd

            df = pd.DataFrame(
                {"value": values + r["forecast"],
                 "kind": ["history"] * len(values) + ["forecast"] * len(r["forecast"])}
            )
            st.line_chart(df.pivot(columns="kind", values="value"))
        else:
            st.json(r)


st.divider()
st.caption(
    "This whole file is ~130 lines. Any Python UI framework works the same way: "
    "one `requests.post` per capability. Gradio, Dash, Panel, Reflex, FastAPI + "
    "your own frontend. The HTTP API is the contract."
)
