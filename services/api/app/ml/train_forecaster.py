"""
Pre-train the stress forecaster.  [Person 1 — run this on day 2]

Why day 2 and not day 6: the LSTM needs hours of wall-clock training and the
first run always surfaces a shape bug. Getting a trained artefact on disk early
means integration never waits on training, and the ridge model gives the team a
working forecast endpoint from the first hour.

    # fast baseline, seconds, no torch needed
    python -m app.ml.train_forecaster --backend ridge --out ../../models/forecaster.pkl

    # the real one
    python -m app.ml.train_forecaster --backend lstm --epochs 60 --days 400

Data source order of preference:
  1. real measurements exported from the DB  (--from-db)
  2. Open-Meteo / ERA5 backfill via app.ingest  (--from-json data/ingested.json)
  3. the synthetic catchment  (default)

Always report skill against persistence. A model that cannot beat "tomorrow is
the same as today" is not a model, and a judge who works with time series will
ask this exact question.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.core.synthetic import SEGMENTS, generate_series
from app.ml.forecaster import (
    LSTMForecaster, RidgeForecaster, build_dataset, evaluate, frame_matrix,
)
from app.store import ASPT


def frames_from_synthetic(days: int) -> tuple[list[dict], list[float]]:
    frames = [generate_series(s, hours=24 * days) for s in SEGMENTS]
    for frame, segment in zip(frames, SEGMENTS):
        frame["_segment_code"] = segment.code
    return frames, [ASPT.get(s.code) for s in SEGMENTS]


def frames_from_json(path: str) -> tuple[list[dict], list[float]]:
    """Rows in the `measurement` schema -> per-segment hourly frames."""
    import pandas as pd

    rows = json.loads(Path(path).read_text())
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit(f"{path} has no rows — run `make ingest` first")
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    frames, aspts = [], []
    for code, grp in df.groupby("segment_code"):
        if "quality" in grp:
            grp = grp[grp["quality"].fillna(0) >= 0.5]
        wide = (grp.pivot_table(index="observed_at", columns="variable",
                                values="value", aggfunc="mean")
                   .resample("1h").mean().interpolate(limit=6))
        required = {"do_mgl", "turbidity_ntu", "temp_c", "rain_mm", "nitrate_mgl"}
        missing = required - set(wide.columns)
        if missing:
            print(f"  skipping {code}: missing required aquatic variables {sorted(missing)}")
            continue
        wide = wide.dropna(subset=sorted(required))
        if len(wide) < 24 * 21:
            print(f"  skipping {code}: only {len(wide)}h of usable data")
            continue
        frame = {"t": list(wide.index.to_pydatetime())}
        frame["_segment_code"] = str(code)
        for var in ("do_mgl", "turbidity_ntu", "temp_c", "rain_mm", "nitrate_mgl"):
            frame[var] = wide[var].to_numpy()
        frame["ph"] = wide["ph"].to_numpy() if "ph" in wide else np.full(len(wide), np.nan)
        frames.append(frame)
        aspts.append(ASPT.get(code))
    if not frames:
        raise SystemExit("no segment had enough history; fall back to --synthetic")
    return frames, aspts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["ridge", "lstm"], default="ridge")
    ap.add_argument("--from-json", default=None, help="ingested measurements")
    ap.add_argument("--days", type=int, default=300, help="synthetic history length")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--out", default="models/forecaster.pkl")
    args = ap.parse_args()

    if args.from_json:
        print(f"loading measurements from {args.from_json}")
        frames, aspts = frames_from_json(args.from_json)
    else:
        print(f"generating {args.days} days of synthetic history for {len(SEGMENTS)} segments")
        frames, aspts = frames_from_synthetic(args.days)

    # Split time inside every reach before combining. Concatenating reaches and
    # then cutting once is a hidden site split, not a chronological split.
    train_x, train_y, test_x, test_y = [], [], [], []
    meta = None
    for frame, aspt in zip(frames, aspts):
        x_site, y_site, meta = build_dataset([frame], [aspt], stride=args.stride)
        cut = int(len(x_site) * .8)
        train_x.append(x_site[:cut]); train_y.append(y_site[:cut])
        test_x.append(x_site[cut:]); test_y.append(y_site[cut:])
    Xtr, Ytr = np.concatenate(train_x), np.concatenate(train_y)
    Xte, Yte = np.concatenate(test_x), np.concatenate(test_y)
    X = np.concatenate([Xtr, Xte]); Y = np.concatenate([Ytr, Yte])
    print(f"dataset {X.shape} -> {Y.shape}  ({meta})")

    if args.backend == "ridge":
        fit_x, fit_y, calibration_x, calibration_y = [], [], [], []
        for site_x, site_y in zip(train_x, train_y):
            calibration_cut = max(1, int(len(site_x) * .8))
            fit_x.append(site_x[:calibration_cut]); fit_y.append(site_y[:calibration_cut])
            calibration_x.append(site_x[calibration_cut:]); calibration_y.append(site_y[calibration_cut:])
        model = RidgeForecaster().fit(
            np.concatenate(fit_x), np.concatenate(fit_y),
            X_cal=np.concatenate(calibration_x), Y_cal=np.concatenate(calibration_y),
        )
    else:
        model = LSTMForecaster(n_features=X.shape[-1]).fit(Xtr, Ytr, epochs=args.epochs)
        model.predict = lambda Z: np.stack([  # batch predict for evaluate()
            [p.value for p in model.forecast(w, datetime.now(timezone.utc), n_samples=8)]
            for w in Z
        ])

    metrics = evaluate(model, Xte, Yte)
    print("\nheld-out performance (stress index units, 0-100):")
    for band in ("0-24h", "24-48h", "48-72h"):
        m = metrics[band]
        verdict = "beats persistence" if m["skill"] > 0 else "WORSE than persistence"
        print(f"  {band:8s} MAE {m['mae']:6.3f}   persistence {m['persistence_mae']:6.3f}"
              f"   skill {m['skill']:+.3f}  {verdict}")
    print(f"  overall  MAE {metrics['overall_mae']:.3f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.save(out)
    (out.parent / "forecaster_metrics.json").write_text(json.dumps({
        "backend": args.backend, "version": model.version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_windows": int(len(X)), "metrics": metrics,
    }, indent=1))
    print(f"\nsaved {out}  (+ forecaster_metrics.json — put these numbers in the README)")


if __name__ == "__main__":
    main()
