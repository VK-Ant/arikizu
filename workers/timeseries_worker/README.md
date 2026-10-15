# timeseries_worker

Wraps WavqWise. Forecasting and anomaly detection over numeric series (sensor readings, EEG, prices). Weekend 8 wires the real backend.

## Capabilities

| Capability                     | Payload                                     | Result                                   |
| ------------------------------ | ------------------------------------------- | ---------------------------------------- |
| `timeseries.forecast`          | `{ series: [float], horizon: int }`         | `{ forecast: [float], horizon: int }`    |
| `timeseries.detect_anomaly`    | `{ series: [float], threshold: float }`     | `{ anomalies: [{ index, value, z }] }`  |

## Wiring (Weekend 8)

```python
from wavqwise import Forecaster, AnomalyDetector

forecaster = Forecaster.load("nhits-small")
detector = AnomalyDetector.default()

@worker.handler("timeseries.forecast")
def forecast(series: list[float] | None = None, horizon: int = 24) -> dict:
    y = forecaster(series or [], horizon=horizon)
    return {"forecast": list(y), "horizon": horizon}
```

## Series format

Pass a flat `[float]`. For irregular time series, resample upstream (e.g. in the pipeline stage before this one) and pass evenly spaced samples. The eval worker's `golden_run` can benchmark forecaster accuracy on a reference set.
