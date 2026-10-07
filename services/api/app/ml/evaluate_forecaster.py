"""Reproducible, leakage-aware WatForecast evaluation.

The default dataset is deterministic synthetic development data. Results must
therefore be presented as engineering evidence, never as field validation.

Run from ``services/api``::

    python -m app.ml.evaluate_forecaster --days 90 --stride 6
"""
from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn

from app.core.synthetic import SEGMENTS
from app.ml.forecaster import RidgeForecaster, build_dataset
from app.ml.train_forecaster import frames_from_json, frames_from_synthetic


BANDS = {"0-24h": slice(0, 24), "24-48h": slice(24, 48), "48-72h": slice(48, 72)}
THRESHOLDS = (50, 75)


def _round(value: float) -> float:
    return round(float(value), 4)


def _baselines(X: np.ndarray, horizon: int) -> dict[str, np.ndarray]:
    # Stress is the last physical feature; four cyclical features follow it.
    stress = X[:, :, -5]
    persistence = np.repeat(stress[:, -1, None], horizon, axis=1)
    daily_pattern = stress[:, -24:]
    seasonal = np.tile(daily_pattern, (1, int(np.ceil(horizon / 24))))[:, :horizon]
    return {"persistence": persistence, "seasonal_24h": seasonal}


def _probability_above(model: RidgeForecaster, pred: np.ndarray, threshold: float) -> np.ndarray:
    """P(target >= threshold) from the held-out conformal residual distribution."""
    residuals = np.asarray(model.calibration_residuals)
    probabilities = np.empty_like(pred, dtype=float)
    for horizon in range(pred.shape[1]):
        ordered = np.sort(residuals[:, horizon])
        cutoffs = threshold - pred[:, horizon]
        indices = np.searchsorted(ordered, cutoffs, side="left")
        probabilities[:, horizon] = (len(ordered) - indices) / len(ordered)
    return probabilities


def _event_metrics(model: RidgeForecaster, pred: np.ndarray, truth: np.ndarray, threshold: int) -> dict:
    predicted_event = pred.max(axis=1) >= threshold
    actual_event = truth.max(axis=1) >= threshold
    tp = int(np.sum(predicted_event & actual_event))
    fp = int(np.sum(predicted_event & ~actual_event))
    fn = int(np.sum(~predicted_event & actual_event))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None

    probabilities = _probability_above(model, pred, threshold)
    brier = np.mean((probabilities - (truth >= threshold)) ** 2)
    notice = []
    for row in np.flatnonzero(predicted_event & actual_event):
        notice.append(int(np.argmax(truth[row] >= threshold)) + 1)
    return {
        "threshold": threshold,
        "status": "evaluated" if np.any(actual_event) else "not_evaluable_no_positive_windows",
        "window_prevalence": _round(np.mean(actual_event)),
        "point_prevalence": _round(np.mean(truth >= threshold)),
        "window_precision": _round(precision) if precision is not None else None,
        "window_recall": _round(recall) if recall is not None else None,
        "point_brier_score": _round(brier),
        "true_positive_windows": tp,
        "false_positive_windows": fp,
        "false_negative_windows": fn,
        "median_notice_hours": _round(np.median(notice)) if notice else None,
    }


def score(model: RidgeForecaster, X: np.ndarray, Y: np.ndarray) -> dict:
    pred = np.clip(model.predict(X), 0, 100)
    baselines = _baselines(X, Y.shape[1])
    lower = np.clip(pred + model.resid_q[0], 0, 100)
    upper = np.clip(pred + model.resid_q[1], 0, 100)
    result: dict = {
        "n_windows": int(len(X)),
        "overall": {
            "mae": _round(np.mean(np.abs(pred - Y))),
            "rmse": _round(np.sqrt(np.mean((pred - Y) ** 2))),
            "persistence_mae": _round(np.mean(np.abs(baselines["persistence"] - Y))),
            "seasonal_24h_mae": _round(np.mean(np.abs(baselines["seasonal_24h"] - Y))),
            "interval_80_coverage": _round(np.mean((Y >= lower) & (Y <= upper))),
            "interval_mean_width": _round(np.mean(upper - lower)),
        },
        "horizon_bands": {},
        "events": {},
    }
    overall = result["overall"]
    overall["interval_80_coverage_error"] = _round(
        abs(overall["interval_80_coverage"] - 0.8)
    )
    overall["skill_vs_persistence"] = _round(
        1 - overall["mae"] / max(overall["persistence_mae"], 1e-9)
    )
    overall["skill_vs_seasonal_24h"] = _round(
        1 - overall["mae"] / max(overall["seasonal_24h_mae"], 1e-9)
    )
    for name, band in BANDS.items():
        mae = np.mean(np.abs(pred[:, band] - Y[:, band]))
        persistence_mae = np.mean(np.abs(baselines["persistence"][:, band] - Y[:, band]))
        seasonal_mae = np.mean(np.abs(baselines["seasonal_24h"][:, band] - Y[:, band]))
        result["horizon_bands"][name] = {
            "mae": _round(mae),
            "rmse": _round(np.sqrt(np.mean((pred[:, band] - Y[:, band]) ** 2))),
            "persistence_mae": _round(persistence_mae),
            "seasonal_24h_mae": _round(seasonal_mae),
            "skill_vs_persistence": _round(1 - mae / max(persistence_mae, 1e-9)),
            "skill_vs_seasonal_24h": _round(1 - mae / max(seasonal_mae, 1e-9)),
        }
    for threshold in THRESHOLDS:
        result["events"][str(threshold)] = _event_metrics(model, pred, Y, threshold)
    return result


def _site_windows(frames: list[dict], aspts: list[float], stride: int) -> list[tuple[np.ndarray, np.ndarray]]:
    return [build_dataset([frame], [aspt], stride=stride)[:2] for frame, aspt in zip(frames, aspts)]


def _fit_with_site_calibration(training_sites: list[tuple[np.ndarray, np.ndarray]]) -> RidgeForecaster:
    fit_x, fit_y, calibration_x, calibration_y = [], [], [], []
    for X, Y in training_sites:
        cut = max(1, int(len(X) * 0.8))
        fit_x.append(X[:cut]); fit_y.append(Y[:cut])
        calibration_x.append(X[cut:]); calibration_y.append(Y[cut:])
    return RidgeForecaster().fit(
        np.concatenate(fit_x),
        np.concatenate(fit_y),
        X_cal=np.concatenate(calibration_x),
        Y_cal=np.concatenate(calibration_y),
    )


def evaluate_chronological(sites: list[tuple[np.ndarray, np.ndarray]]) -> dict:
    training_sites, testing_x, testing_y = [], [], []
    for X, Y in sites:
        cut = int(len(X) * 0.8)
        training_sites.append((X[:cut], Y[:cut]))
        testing_x.append(X[cut:]); testing_y.append(Y[cut:])
    X_test, Y_test = np.concatenate(testing_x), np.concatenate(testing_y)
    model = _fit_with_site_calibration(training_sites)
    return {
        "protocol": "Per-site chronological 80/20 test split; the newest 20% of each site's training partition is reserved for conformal calibration.",
        "n_training_windows": int(sum(len(X) for X, _ in training_sites)),
        **score(model, X_test, Y_test),
    }


def evaluate_leave_one_site_out(sites: list[tuple[np.ndarray, np.ndarray]], labels: list[dict]) -> dict:
    folds = []
    for held_index, ((X_test, Y_test), label) in enumerate(zip(sites, labels)):
        training_sites = [site for index, site in enumerate(sites) if index != held_index]
        model = _fit_with_site_calibration(training_sites)
        metrics = score(model, X_test, Y_test)
        folds.append({**label, **metrics})
    maes = [fold["overall"]["mae"] for fold in folds]
    skills = [fold["overall"]["skill_vs_persistence"] for fold in folds]
    return {
        "protocol": "Train on every other reach and evaluate on one entirely unseen reach.",
        "macro_average": {
            "mae": _round(np.mean(maes)),
            "mae_std": _round(np.std(maes)),
            "skill_vs_persistence": _round(np.mean(skills)),
        },
        "folds": folds,
    }


def evaluate_leave_one_city_out(sites: list[tuple[np.ndarray, np.ndarray]], labels: list[dict]) -> dict:
    folds = []
    for city in dict.fromkeys(label["city"] for label in labels):
        held_indices = [index for index, label in enumerate(labels) if label["city"] == city]
        training_sites = [site for index, site in enumerate(sites) if index not in held_indices]
        X_test = np.concatenate([sites[index][0] for index in held_indices])
        Y_test = np.concatenate([sites[index][1] for index in held_indices])
        model = _fit_with_site_calibration(training_sites)
        folds.append({
            "city": city,
            "codes": [labels[index]["code"] for index in held_indices],
            **score(model, X_test, Y_test),
        })
    maes = [fold["overall"]["mae"] for fold in folds]
    skills = [fold["overall"]["skill_vs_persistence"] for fold in folds]
    return {
        "protocol": "Hold out every reach in one city, then train and calibrate only on other cities.",
        "macro_average": {
            "mae": _round(np.mean(maes)),
            "mae_std": _round(np.std(maes)),
            "skill_vs_persistence": _round(np.mean(skills)),
        },
        "folds": folds,
    }


def _markdown(report: dict) -> str:
    chronological = report["chronological_holdout"]
    overall = chronological["overall"]
    rows = []
    for band, metrics in chronological["horizon_bands"].items():
        rows.append(
            f"| {band} | {metrics['mae']:.3f} | {metrics['rmse']:.3f} | "
            f"{metrics['persistence_mae']:.3f} | {metrics['seasonal_24h_mae']:.3f} | "
            f"{metrics['skill_vs_persistence']:+.3f} |"
        )
    event_rows = []
    for threshold, metrics in chronological["events"].items():
        notice = metrics["median_notice_hours"]
        precision = metrics["window_precision"]
        recall = metrics["window_recall"]
        event_rows.append(
            f"| >= {threshold} | {f'{precision:.3f}' if precision is not None else 'n/a'} | "
            f"{f'{recall:.3f}' if recall is not None else 'n/a'} | {metrics['point_brier_score']:.3f} | "
            f"{notice if notice is not None else 'n/a'} | "
            f"{metrics['true_positive_windows']}/{metrics['false_positive_windows']}/{metrics['false_negative_windows']} | "
            f"{metrics['status']} |"
        )
    fold_rows = []
    for fold in report["leave_one_site_out"]["folds"]:
        fold_rows.append(
            f"| {fold['code']} | {fold['city']} | {fold['overall']['mae']:.3f} | "
            f"{fold['overall']['skill_vs_persistence']:+.3f} |"
        )
    city_rows = []
    for fold in report["leave_one_city_out"]["folds"]:
        city_rows.append(
            f"| {fold['city']} | {', '.join(fold['codes'])} | {fold['overall']['mae']:.3f} | "
            f"{fold['overall']['skill_vs_persistence']:+.3f} |"
        )
    return f"""# WatForecast evaluation

Generated: `{report['generated_at']}`

Model: `{report['model']['version']}`

Dataset: **{report['dataset']['label']}**

> This is reproducible engineering evidence on deterministic synthetic development data. It is not field validation, clinical evidence, or regulatory certification.

## Chronological holdout

{chronological['protocol']}

| Horizon | MAE | RMSE | Persistence MAE | 24h seasonal MAE | Skill vs persistence |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Overall MAE is **{overall['mae']:.3f}** stress points. The nominal 80% interval covers **{overall['interval_80_coverage'] * 100:.1f}%** of held-out targets with a mean width of **{overall['interval_mean_width']:.3f}** points.

## Operational event detection

Window-level precision/recall asks whether each issued 72-hour forecast correctly identifies at least one threshold event. Brier score is calculated over every forecasted point using probabilities derived only from held-out calibration residuals.

| Stress event | Precision | Recall | Brier | Median notice (h) | TP/FP/FN | Status |
|---|---:|---:|---:|---:|---:|---|
{chr(10).join(event_rows)}

## Unseen-reach generalization

{report['leave_one_site_out']['protocol']}

| Held-out reach | City | MAE | Skill vs persistence |
|---|---|---:|---:|
{chr(10).join(fold_rows)}

Macro-average MAE: **{report['leave_one_site_out']['macro_average']['mae']:.3f} ± {report['leave_one_site_out']['macro_average']['mae_std']:.3f}**.

## Unseen-city generalization

{report['leave_one_city_out']['protocol']}

| Held-out city | Reaches | MAE | Skill vs persistence |
|---|---|---:|---:|
{chr(10).join(city_rows)}

Macro-average city MAE: **{report['leave_one_city_out']['macro_average']['mae']:.3f} ± {report['leave_one_city_out']['macro_average']['mae_std']:.3f}**.

## Reproduce

```bash
cd services/api
python -m app.ml.evaluate_forecaster --days {report['dataset']['days']} --stride {report['dataset']['stride']}
```

The machine-readable result is in `reports/forecast_evaluation.json`. Replace `--synthetic` inputs with harmonized observations before claiming real-world accuracy.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-json", help="Harmonized measurement export; synthetic data is used when omitted.")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--json-out", default="../../reports/forecast_evaluation.json")
    parser.add_argument("--markdown-out", default="../../docs/FORECAST_EVALUATION.md")
    parser.add_argument("--runtime-out", default="app/evidence/forecast_evaluation.json")
    args = parser.parse_args()

    if args.from_json:
        frames, aspts = frames_from_json(args.from_json)
        labels = [{"code": frame.get("_segment_code", f"SITE-{i + 1}"), "city": "unknown"}
                  for i, frame in enumerate(frames)]
        dataset_label = "User-supplied harmonized observations"
        source_kind = "observed"
    else:
        frames, aspts = frames_from_synthetic(args.days)
        labels = [{"code": segment.code, "city": segment.city} for segment in SEGMENTS]
        dataset_label = "Deterministic mechanistic synthetic development dataset"
        source_kind = "synthetic-development"

    sites = _site_windows(frames, aspts, args.stride)
    if any(len(X) < 10 for X, _ in sites):
        raise SystemExit("Each site needs at least 10 forecast windows for evaluation.")
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model": {"name": "WatForecast Ridge", "version": RidgeForecaster().version},
        "dataset": {
            "label": dataset_label,
            "source_kind": source_kind,
            "days": args.days if not args.from_json else None,
            "stride": args.stride,
            "sites": labels,
        },
        "protocol_notes": [
            "All splits are made at complete forecast-window boundaries.",
            "Conformal residuals are never estimated from an evaluation partition.",
            "Overlapping windows are retained and explicitly reported through stride.",
            "Synthetic results are not evidence of field performance.",
        ],
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "chronological_holdout": evaluate_chronological(sites),
        "leave_one_site_out": evaluate_leave_one_site_out(sites, labels),
        "leave_one_city_out": evaluate_leave_one_city_out(sites, labels),
    }
    # Report the version after fitting because the conformal suffix is assigned in fit().
    report["model"]["version"] = "forecaster-0.3.0-ridge-conformal"

    json_path = Path(args.json_out)
    markdown_path = Path(args.markdown_out)
    runtime_path = Path(args.runtime_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2) + "\n"
    json_path.write_text(serialized, encoding="utf-8")
    runtime_path.write_text(serialized, encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(f"wrote {json_path}, {runtime_path} and {markdown_path}")
    print(json.dumps(report["chronological_holdout"]["overall"], indent=2))


if __name__ == "__main__":
    main()
