"""Time-series worker. Statistical, not deep.

Default anomaly detector: a joblib-serialized sklearn IsolationForest at
$ARIKIZU_MODELS_DIR/anomaly_iforest.joblib (produced by
scripts/download-default-models.sh --tier minimum).

Weekend 8 wires WavqWise for N-HiTS / N-BEATS style neural forecasting.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from pathlib import Path
from typing import Any

from arikizu_worker import Worker
from arikizu_worker import backend as bk

MODELS_DIR = os.environ.get("ARIKIZU_MODELS_DIR", "./models")
ANOMALY_MODEL = os.environ.get("ARIKIZU_ANOMALY_MODEL") or f"{MODELS_DIR}/anomaly_iforest.joblib"


def _naive_forecast(series: list[float], horizon: int) -> list[float]:
    """Exponential smoothing with alpha=0.3; good enough baseline."""
    if not series:
        return [0.0] * horizon
    alpha = 0.3
    level = series[0]
    for v in series[1:]:
        level = alpha * v + (1 - alpha) * level
    # Project forward with small momentum from the last diff.
    diff = (series[-1] - series[-min(len(series), 5)]) / min(len(series), 5) if len(series) > 1 else 0.0
    return [level + diff * (i + 1) for i in range(horizon)]


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("timeseries")

    # Try to load the joblib Isolation Forest. If joblib / sklearn isn't
    # installed, fall back to a z-score threshold.
    anomaly_handle = None
    if Path(ANOMALY_MODEL).exists():
        try:
            anomaly_handle = bk.load_model(ANOMALY_MODEL)
            logger.info("loaded anomaly model: %s (%s)", ANOMALY_MODEL, anomaly_handle.meta)
        except bk.BackendUnavailable as e:
            logger.warning("anomaly model load failed: %s; falling back to z-score", e)
    else:
        logger.info("no anomaly model at %s; using z-score fallback", ANOMALY_MODEL)

    worker = Worker("timeseries")

    @worker.handler("timeseries.forecast")
    def forecast(series: list[float] | None = None, horizon: int = 24) -> dict[str, Any]:
        s = series or []
        return {
            "forecast": _naive_forecast(s, horizon),
            "horizon": horizon,
            "method": "exponential_smoothing",
            "note": "statistical baseline; WavqWise neural forecaster lands Weekend 8",
        }

    @worker.handler("timeseries.detect_anomaly")
    def detect_anomaly(series: list[float] | None = None, threshold: float = 3.0) -> dict[str, Any]:
        s = series or []
        if not s:
            return {"anomalies": [], "method": "none", "note": "empty series"}

        if anomaly_handle is not None:
            # IsolationForest expects 2D X; we feed a sliding window of 1.
            import numpy as np
            X = np.asarray(s, dtype=float).reshape(-1, 1)
            try:
                out = anomaly_handle.infer({"X": X})
                scores = out.get("score_samples", None)
                preds = out.get("predict", None)
                anomalies: list[dict[str, Any]] = []
                if preds is not None:
                    for i, p in enumerate(preds):
                        if int(p) == -1:
                            anomalies.append({"index": int(i), "value": float(s[i])})
                return {
                    "anomalies": anomalies,
                    "method": "isolation_forest",
                    "backend": anomaly_handle.backend.value,
                }
            except Exception as e:
                logger.warning("isolation forest failed: %s; falling back", e)

        # z-score fallback (no deps)
        n = len(s)
        mean = sum(s) / n
        var = sum((v - mean) ** 2 for v in s) / n
        sd = math.sqrt(var) if var > 0 else 1e-9
        anomalies_fb = [
            {"index": i, "value": v, "z": (v - mean) / sd}
            for i, v in enumerate(s) if abs((v - mean) / sd) > threshold
        ]
        return {"anomalies": anomalies_fb, "method": "zscore", "threshold": threshold}

    @worker.handler("timeseries.backends")
    def backends() -> dict[str, Any]:
        """Diagnostic. Reports what sklearn/numpy/joblib is doing."""
        return {
            **bk.summarize(),
            "model_path": ANOMALY_MODEL,
            "model_loaded": anomaly_handle is not None,
            "picked_backend": anomaly_handle.backend.value if anomaly_handle else None,
            "models_dir": MODELS_DIR,
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
