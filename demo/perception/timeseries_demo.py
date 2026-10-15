#!/usr/bin/env python3
"""Timeseries worker demo. WavqWise wrapper.

v0.1: placeholder (WAIT) until Weekend 8.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    fixture = os.path.join(os.path.dirname(__file__), "..", "fixtures", "series.json")
    if not os.path.exists(fixture):
        print("series.json not found; run: python3 demo/fixtures/make_fixtures.py")
        return 2
    data = json.load(open(fixture))
    series: list[float] = data["series"]
    anomaly_index: int = data["anomaly_index"]

    banner(f"Timeseries worker  —  {len(series)} points, injected anomaly at {anomaly_index}")

    print_result(
        "timeseries.forecast  horizon=12",
        call("timeseries.forecast", {"series": series, "horizon": 12}),
        show_body=True,
    )
    print_result(
        "timeseries.detect_anomaly  threshold=3.0",
        call("timeseries.detect_anomaly", {"series": series, "threshold": 3.0}),
        show_body=True,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
