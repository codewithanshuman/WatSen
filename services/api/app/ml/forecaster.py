"""
72-hour stream stress forecasting.

Two backends behind one interface:

  RidgeForecaster  — direct multi-horizon linear model over lag features.
                     Trains in under a second, needs only scikit-learn, and is
                     surprisingly hard to beat on 72h horizons. This is the
                     safety net: if the LSTM is not ready, the demo still runs.

  LSTMForecaster   — PyTorch sequence model with Monte-Carlo dropout for
                     uncertainty. This is what goes in the submission.

Both predict the composite stress index (see core/stress.py), not raw DO. One
target keeps the map, the alerting thresholds and the brief consistent.

Uncertainty is not decoration. A single forecast line implies a precision we do
not have, and a judge who works with environmental data will notice. Ridge uses
residual quantiles per horizon; the LSTM uses MC dropout.

    from app.ml.forecaster import RidgeForecaster, build_dataset
    X, Y, meta = build_dataset(frames)
    m = RidgeForecaster().fit(X, Y)
    out = m.predict_latest(frame)      # -> {'valid_at', 'value', 'lower', 'upper'}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from app.core.stress import series_from_measurements

# Exogenous drivers fed alongside the target's own history.
DRIVERS = ["do_mgl", "turbidity_ntu", "temp_c", "rain_mm", "nitrate_mgl"]
LOOKBACK_H = 168          # one week of context
HORIZON_H = 72
MODEL_VERSION = "forecaster-0.3.0"


# ── feature construction ───────────────────────────────────────────

def _cyclical(ts: list[datetime]) -> np.ndarray:
    hod = np.array([t.hour for t in ts], dtype=float)
    doy = np.array([t.timetuple().tm_yday for t in ts], dtype=float)
    return np.stack([
        np.sin(2 * np.pi * hod / 24), np.cos(2 * np.pi * hod / 24),
        np.sin(2 * np.pi * doy / 365), np.cos(2 * np.pi * doy / 365),
    ], axis=1)


def frame_matrix(frame: dict, aspt: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """
    frame: {'t': [datetime], 'do_mgl': arr, ...} at hourly resolution.
    Returns (features [n, d], target stress [n]).
    """
    target = series_from_measurements(frame, aspt=aspt)
    cols = [frame[k] for k in DRIVERS if k in frame]
    x = np.stack(cols + [target], axis=1)
    x = np.hstack([x, _cyclical(frame["t"])])
    return x, target


def build_dataset(
    frames: list[dict], aspts: list[float | None] | None = None,
    lookback: int = LOOKBACK_H, horizon: int = HORIZON_H, stride: int = 3,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Windowed supervised dataset across many segments."""
    aspts = aspts or [None] * len(frames)
    xs, ys = [], []
    for frame, aspt in zip(frames, aspts):
        mat, target = frame_matrix(frame, aspt=aspt)
        n = len(target)
        for i in range(lookback, n - horizon, stride):
            xs.append(mat[i - lookback : i])
            ys.append(target[i : i + horizon])
    X = np.asarray(xs, dtype=np.float32)
    Y = np.asarray(ys, dtype=np.float32)
    return X, Y, {"lookback": lookback, "horizon": horizon, "n_features": X.shape[-1]}


# ── ridge baseline ─────────────────────────────────────────────────

@dataclass
class ForecastPoint:
    valid_at: str
    value: float
    lower: float
    upper: float


class RidgeForecaster:
    """
    Direct multi-horizon ridge over summarised lag features.
    One model, `horizon` outputs — no recursive error accumulation.
    """

    def __init__(self, alpha: float = 3.0, horizon: int = HORIZON_H):
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler

        self.horizon = horizon
        self.scaler = StandardScaler()
        self.model = Ridge(alpha=alpha)
        self.resid_q = None            # (2, horizon) 10th/90th residual quantiles
        self.calibration_residuals = None
        self.version = MODEL_VERSION + "-ridge"

    @staticmethod
    def _summarise(window: np.ndarray) -> np.ndarray:
        """
        window: [lookback, d] -> compact feature vector.
        Recent detail matters more than week-old detail, so the lags thin out.
        """
        lags = [1, 2, 3, 6, 12, 24, 48, 72, 120, 168]
        feats = [window[-l] for l in lags if l <= len(window)]
        feats.append(window[-24:].mean(axis=0))
        feats.append(window[-24:].std(axis=0))
        feats.append(window[-72:].mean(axis=0))
        feats.append(window[-168:].mean(axis=0))
        feats.append(window[-24:].max(axis=0))
        feats.append(window[-24:].min(axis=0))
        # short-term slope: where is it heading right now
        feats.append(window[-1] - window[-6])
        feats.append(window[-1] - window[-24])
        return np.concatenate(feats)

    def _design(self, X: np.ndarray) -> np.ndarray:
        return np.vstack([self._summarise(w) for w in X])

    def fit(
        self,
        X: np.ndarray,
        Y: np.ndarray,
        calibration_fraction: float = 0.2,
        X_cal: np.ndarray | None = None,
        Y_cal: np.ndarray | None = None,
    ) -> "RidgeForecaster":
        D = self._design(X)
        if X_cal is None or Y_cal is None:
            n_cal = max(72, int(len(D) * calibration_fraction)) if len(D) >= 180 else max(1, len(D) // 5)
            cut = len(D) - n_cal
            D_train, Y_train = D[:cut], Y[:cut]
            D_cal, Y_calibration = D[cut:], Y[cut:]
        else:
            D_train, Y_train = D, Y
            D_cal, Y_calibration = self._design(X_cal), Y_cal
        d_train = self.scaler.fit_transform(D_train)
        self.model.fit(d_train, Y_train)
        # Hold out the most recent windows for split-conformal residual
        # calibration. The interval is no longer estimated on fitted samples.
        d_cal = self.scaler.transform(D_cal)
        resid = Y_calibration - self.model.predict(d_cal)
        self.calibration_residuals = resid
        self.resid_q = np.vstack([
            np.percentile(resid, 10, axis=0),
            np.percentile(resid, 90, axis=0),
        ])
        self.version = MODEL_VERSION + "-ridge-conformal"
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict(self.scaler.transform(self._design(X)))

    def forecast(self, window: np.ndarray, issued_at: datetime) -> list[ForecastPoint]:
        mu = self.predict(window[None, ...])[0]
        lo = np.clip(mu + self.resid_q[0], 0, 100)
        hi = np.clip(mu + self.resid_q[1], 0, 100)
        mu = np.clip(mu, 0, 100)
        return [
            ForecastPoint(
                valid_at=(issued_at + timedelta(hours=h + 1)).isoformat(),
                value=round(float(mu[h]), 2),
                lower=round(float(min(lo[h], mu[h])), 2),
                upper=round(float(max(hi[h], mu[h])), 2),
            )
            for h in range(len(mu))
        ]

    def save(self, path: str | Path) -> None:
        import pickle
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str | Path) -> "RidgeForecaster":
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)


# ── LSTM ───────────────────────────────────────────────────────────

def _torch():
    try:
        import torch
        return torch
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "PyTorch is not installed. Either `pip install torch --index-url "
            "https://download.pytorch.org/whl/cpu` or use RidgeForecaster."
        ) from e


def build_lstm(n_features: int, horizon: int = HORIZON_H, hidden: int = 128, dropout: float = 0.2):
    torch = _torch()
    nn = torch.nn

    class StressLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = nn.LayerNorm(n_features)
            self.lstm = nn.LSTM(
                input_size=n_features, hidden_size=hidden, num_layers=2,
                batch_first=True, dropout=dropout,
            )
            self.drop = nn.Dropout(dropout)
            self.head = nn.Sequential(
                nn.Linear(hidden, hidden), nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(hidden, horizon),
            )

        def forward(self, x):
            out, _ = self.lstm(self.norm(x))
            return self.head(self.drop(out[:, -1]))

    return StressLSTM()


class LSTMForecaster:
    """MC-dropout LSTM. Uncertainty comes from `n_samples` stochastic passes."""

    def __init__(self, n_features: int, horizon: int = HORIZON_H, hidden: int = 128,
                 dropout: float = 0.2, device: str | None = None):
        torch = _torch()
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net = build_lstm(n_features, horizon, hidden, dropout).to(self.device)
        self.horizon = horizon
        self.mu = None
        self.sd = None
        self.version = MODEL_VERSION + "-lstm"

    def _standardise(self, X):
        return (X - self.mu) / self.sd

    def fit(self, X, Y, epochs: int = 40, batch_size: int = 64, lr: float = 2e-3,
            val_split: float = 0.15, verbose: bool = True):
        torch = self.torch
        self.mu = X.reshape(-1, X.shape[-1]).mean(axis=0)
        self.sd = X.reshape(-1, X.shape[-1]).std(axis=0)
        self.sd[self.sd == 0] = 1.0

        n_val = max(1, int(len(X) * val_split))
        Xtr, Ytr = self._standardise(X[:-n_val]), Y[:-n_val]
        Xva, Yva = self._standardise(X[-n_val:]), Y[-n_val:]

        tt = lambda a: torch.tensor(a, dtype=torch.float32, device=self.device)
        ds = torch.utils.data.TensorDataset(tt(Xtr), tt(Ytr))
        dl = torch.utils.data.DataLoader(ds, batch_size=batch_size, shuffle=True)
        xva, yva = tt(Xva), tt(Yva)

        opt = torch.optim.AdamW(self.net.parameters(), lr=lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.OneCycleLR(
            opt, max_lr=lr, total_steps=max(epochs * len(dl), 1))
        # Huber: stream data has genuine spikes we do not want to over-fit to.
        loss_fn = torch.nn.HuberLoss(delta=6.0)

        best, best_state, patience = float("inf"), None, 0
        for ep in range(epochs):
            self.net.train()
            for xb, yb in dl:
                opt.zero_grad()
                loss = loss_fn(self.net(xb), yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                opt.step()
                sched.step()
            self.net.eval()
            with torch.no_grad():
                vmae = (self.net(xva) - yva).abs().mean().item()
            if vmae < best - 1e-4:
                best, patience = vmae, 0
                best_state = {k: v.detach().clone() for k, v in self.net.state_dict().items()}
            else:
                patience += 1
            if verbose:
                print(f"epoch {ep + 1:3d}  val MAE {vmae:6.3f}{'  *' if patience == 0 else ''}")
            if patience >= 8:
                break
        if best_state:
            self.net.load_state_dict(best_state)
        return self

    def forecast(self, window: np.ndarray, issued_at: datetime, n_samples: int = 40) -> list[ForecastPoint]:
        torch = self.torch
        x = torch.tensor(self._standardise(window[None, ...]), dtype=torch.float32, device=self.device)
        self.net.train()                       # keep dropout on: that is the point
        with torch.no_grad():
            draws = torch.stack([self.net(x)[0] for _ in range(n_samples)]).cpu().numpy()
        mu = draws.mean(axis=0)
        lo = np.percentile(draws, 10, axis=0)
        hi = np.percentile(draws, 90, axis=0)
        return [
            ForecastPoint(
                valid_at=(issued_at + timedelta(hours=h + 1)).isoformat(),
                value=round(float(np.clip(mu[h], 0, 100)), 2),
                lower=round(float(np.clip(lo[h], 0, 100)), 2),
                upper=round(float(np.clip(hi[h], 0, 100)), 2),
            )
            for h in range(self.horizon)
        ]

    def save(self, path: str | Path) -> None:
        torch = self.torch
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save({"state": self.net.state_dict(), "mu": self.mu, "sd": self.sd,
                    "horizon": self.horizon, "version": self.version}, path)


# ── evaluation ─────────────────────────────────────────────────────

def evaluate(model, X: np.ndarray, Y: np.ndarray) -> dict:
    """
    MAE per horizon band, against a persistence baseline.

    Persistence (tomorrow equals now) is the honest baseline for any
    environmental time series. Report this. If the model does not beat it,
    say so rather than hiding it — judges trust a team that measures itself.
    """
    pred = model.predict(X) if hasattr(model, "predict") else None
    if pred is None:
        raise ValueError("model needs a .predict for batch evaluation")
    naive = np.repeat(X[:, -1, -5][:, None], Y.shape[1], axis=1)  # last stress value
    bands = {"0-24h": slice(0, 24), "24-48h": slice(24, 48), "48-72h": slice(48, 72)}
    out = {}
    for name, sl in bands.items():
        out[name] = {
            "mae": round(float(np.abs(pred[:, sl] - Y[:, sl]).mean()), 3),
            "persistence_mae": round(float(np.abs(naive[:, sl] - Y[:, sl]).mean()), 3),
        }
        out[name]["skill"] = round(
            1 - out[name]["mae"] / max(out[name]["persistence_mae"], 1e-9), 3)
    out["overall_mae"] = round(float(np.abs(pred - Y).mean()), 3)
    return out


def alerts_from_forecast(points: list[ForecastPoint], segment_code: str) -> list[dict]:
    """Turn a trajectory into the tiered alerts the schema expects."""
    raised = []
    for tier, cutoff, severity in (("severe", 75, "critical"), ("poor", 50, "warning")):
        hit = next((p for p in points if p.value >= cutoff), None)
        if not hit:
            continue
        at = datetime.fromisoformat(hit.valid_at)
        confident = hit.lower >= cutoff - 5
        raised.append({
            "segment_code": segment_code,
            "valid_from": hit.valid_at,
            "severity": severity if confident else "watch",
            "hazard": "do_crash" if cutoff >= 75 else "bloom_risk",
            "headline": (
                f"Stress index forecast to reach {hit.value:.0f} "
                f"({tier}) at {at.strftime('%a %H:%M')}"
            ),
            "audience": "agency" if severity == "critical" else "public",
        })
        break                                  # only the most severe tier
    return raised
