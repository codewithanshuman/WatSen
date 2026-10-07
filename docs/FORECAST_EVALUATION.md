# WatForecast evaluation

Generated: `2026-10-07T14:26:34+00:00`

Model: `forecaster-0.3.0-ridge-conformal`

Dataset: **Deterministic mechanistic synthetic development dataset**

> This is reproducible engineering evidence on deterministic synthetic development data. It is not field validation, clinical evidence, or regulatory certification.

## Chronological holdout

Per-site chronological 80/20 test split; the newest 20% of each site's training partition is reserved for conformal calibration.

| Horizon | MAE | RMSE | Persistence MAE | 24h seasonal MAE | Skill vs persistence |
|---|---:|---:|---:|---:|---:|
| 0-24h | 1.200 | 2.082 | 2.001 | 3.458 | +0.400 |
| 24-48h | 3.390 | 4.960 | 4.166 | 4.582 | +0.186 |
| 48-72h | 3.762 | 5.437 | 4.635 | 4.663 | +0.188 |

Overall MAE is **2.784** stress points. The nominal 80% interval covers **81.5%** of held-out targets with a mean width of **8.102** points.

## Operational event detection

Window-level precision/recall asks whether each issued 72-hour forecast correctly identifies at least one threshold event. Brier score is calculated over every forecasted point using probabilities derived only from held-out calibration residuals.

| Stress event | Precision | Recall | Brier | Median notice (h) | TP/FP/FN | Status |
|---|---:|---:|---:|---:|---:|---|
| >= 50 | 1.000 | 1.000 | 0.001 | 1.0 | 4/0/0 | evaluated |
| >= 75 | n/a | n/a | 0.000 | n/a | 0/0/0 | not_evaluable_no_positive_windows |

## Unseen-reach generalization

Train on every other reach and evaluate on one entirely unseen reach.

| Held-out reach | City | MAE | Skill vs persistence |
|---|---|---:|---:|
| PT-CBR-01 | Coimbra | 2.933 | +0.314 |
| PT-CBR-02 | Coimbra | 2.317 | +0.295 |
| IT-BLG-01 | Bologna | 2.860 | +0.286 |
| RO-BUC-01 | Bucharest | 2.580 | +0.317 |
| ES-VLC-01 | Valencia | 2.700 | +0.262 |
| NL-UTR-01 | Utrecht | 1.979 | +0.155 |

Macro-average MAE: **2.562 ± 0.328**.

## Unseen-city generalization

Hold out every reach in one city, then train and calibrate only on other cities.

| Held-out city | Reaches | MAE | Skill vs persistence |
|---|---|---:|---:|
| Coimbra | PT-CBR-01, PT-CBR-02 | 2.629 | +0.305 |
| Bologna | IT-BLG-01 | 2.860 | +0.286 |
| Bucharest | RO-BUC-01 | 2.580 | +0.317 |
| Valencia | ES-VLC-01 | 2.700 | +0.262 |
| Utrecht | NL-UTR-01 | 1.979 | +0.155 |

Macro-average city MAE: **2.550 ± 0.300**.

## Reproduce

```bash
cd services/api
python -m app.ml.evaluate_forecaster --days 180 --stride 12
```

The machine-readable result is in `reports/forecast_evaluation.json`. Replace `--synthetic` inputs with harmonized observations before claiming real-world accuracy.
