"""
Macroinvertebrate family classifier.  [Person 1]

Target: BMWP *family*, not species. This is the single most important design
decision in the vision pipeline and you should say it out loud in the demo:

  - The biotic index only needs family level. Species adds nothing to the score.
  - Family-level identification from a phone photo is achievable. Species-level
    is not, and claiming it invites a reviewer to disprove you live.
  - Published citizen-science validation work says volunteers are reliable at
    family level and unreliable below it. Matching the model to the index and to
    the human protocol is defensible; overreaching is not.

Confidence must be calibrated. A raw softmax from a fine-tuned CNN is badly
overconfident, and the whole human-in-the-loop story depends on the threshold
meaning something. Temperature scaling on a validation split is ~20 lines and
fixes most of it — `fit_temperature` below.

Grad-CAM, not SHAP, for images. KernelSHAP on a CNN is minutes per image and
the result is noisier than a gradient map. Use SHAP for the tabular anomaly
model where it is cheap and exact. Saying "we used the right explainer for each
modality" is a stronger answer than "we used SHAP everywhere".

Expected layout for training data:

    data/macroinvertebrates/
        train/Baetidae/*.jpg
        train/Chironomidae/*.jpg
        val/Baetidae/*.jpg
        ...
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

IMG_SIZE = 300              # EfficientNet-B3 native
MODEL_VERSION = "classifier-0.2.0-effnetb3"

# Start here. Every one of these is a BMWP scoring family with enough
# iNaturalist research-grade images to fine-tune on, and together they span
# the full sensitivity range from 10 (Perlidae) to 1 (Oligochaeta).
DEFAULT_CLASSES = [
    "Perlidae", "Heptageniidae", "Ephemerellidae", "Leuctridae", "Rhyacophilidae",
    "Limnephilidae", "Hydropsychidae", "Gammaridae", "Elminthidae", "Baetidae",
    "Asellidae", "Chironomidae", "Erpobdellidae", "Physidae", "Oligochaeta",
]


def _torch():
    try:
        import torch
        return torch
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "PyTorch not installed. `pip install torch torchvision "
            "--index-url https://download.pytorch.org/whl/cpu`"
        ) from e


@dataclass
class Prediction:
    taxon: str
    confidence: float
    top_k: list[tuple[str, float]]
    bmwp: int | None
    saliency: np.ndarray | None = None

    def to_dict(self) -> dict:
        return {
            "predicted_taxon": self.taxon,
            "taxon_confidence": round(self.confidence, 4),
            "top_k": [(t, round(p, 4)) for t, p in self.top_k],
            "bmwp_contribution": self.bmwp,
        }


def build_model(n_classes: int, dropout: float = 0.3, pretrained: bool = True):
    """EfficientNet-B3 with a fresh head."""
    torch = _torch()
    from torchvision import models

    weights = models.EfficientNet_B3_Weights.IMAGENET1K_V1 if pretrained else None
    net = models.efficientnet_b3(weights=weights)
    in_f = net.classifier[1].in_features
    net.classifier = torch.nn.Sequential(
        torch.nn.Dropout(dropout),
        torch.nn.Linear(in_f, n_classes),
    )
    return net


def build_transforms(train: bool):
    """
    Augmentation tuned to the actual failure modes of this data:
      - photos arrive at any rotation (phone held over a tray)
      - white balance varies wildly between sunlight and a shaded bank
      - specimens are often partly occluded by grit or another animal
    No horizontal-flip-only: these animals have no canonical orientation.
    """
    from torchvision import transforms as T

    if train:
        return T.Compose([
            T.RandomResizedCrop(IMG_SIZE, scale=(0.55, 1.0), ratio=(0.8, 1.25)),
            T.RandomHorizontalFlip(),
            T.RandomVerticalFlip(),
            T.RandomApply([T.RandomRotation(35)], p=0.7),
            T.ColorJitter(brightness=0.35, contrast=0.3, saturation=0.35, hue=0.06),
            T.RandomApply([T.GaussianBlur(5, (0.1, 1.8))], p=0.25),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            T.RandomErasing(p=0.25, scale=(0.02, 0.12)),
        ])
    return T.Compose([
        T.Resize(int(IMG_SIZE * 1.14)),
        T.CenterCrop(IMG_SIZE),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


class TaxonClassifier:
    def __init__(self, classes: list[str] | None = None, device: str | None = None):
        torch = _torch()
        self.torch = torch
        self.classes = classes or DEFAULT_CLASSES
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net = build_model(len(self.classes)).to(self.device)
        self.temperature = 1.0
        self.version = MODEL_VERSION

    # ── training ───────────────────────────────────────────────────
    def fit(self, data_dir: str | Path, epochs: int = 12, batch_size: int = 16,
            lr: float = 3e-4, freeze_backbone_epochs: int = 2, workers: int = 2):
        torch = self.torch
        from torchvision.datasets import ImageFolder

        data_dir = Path(data_dir)
        train_ds = ImageFolder(data_dir / "train", transform=build_transforms(True))
        val_ds = ImageFolder(data_dir / "val", transform=build_transforms(False))
        self.classes = train_ds.classes
        # head must match the folders actually present
        self.net = build_model(len(self.classes)).to(self.device)

        # class imbalance is guaranteed here: Chironomidae are everywhere,
        # Perlidae are rare. Weighted sampling beats weighted loss for CNNs.
        counts = np.bincount([y for _, y in train_ds.samples], minlength=len(self.classes))
        weights = 1.0 / np.maximum(counts, 1)
        sample_w = [weights[y] for _, y in train_ds.samples]
        sampler = torch.utils.data.WeightedRandomSampler(sample_w, len(sample_w), replacement=True)

        train_dl = torch.utils.data.DataLoader(
            train_ds, batch_size=batch_size, sampler=sampler, num_workers=workers)
        val_dl = torch.utils.data.DataLoader(
            val_ds, batch_size=batch_size, shuffle=False, num_workers=workers)

        opt = torch.optim.AdamW(self.net.parameters(), lr=lr, weight_decay=1e-4)
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
        loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.05)

        best_acc, best_state = 0.0, None
        for ep in range(epochs):
            # warm up the head before disturbing pretrained features
            freeze = ep < freeze_backbone_epochs
            for p in self.net.features.parameters():
                p.requires_grad = not freeze

            self.net.train()
            for xb, yb in train_dl:
                xb, yb = xb.to(self.device), yb.to(self.device)
                opt.zero_grad()
                loss = loss_fn(self.net(xb), yb)
                loss.backward()
                opt.step()
            sched.step()

            acc, _, _ = self.evaluate(val_dl)
            print(f"epoch {ep+1:2d}  val acc {acc:.4f}{'  (head only)' if freeze else ''}")
            if acc > best_acc:
                best_acc = acc
                best_state = {k: v.detach().clone() for k, v in self.net.state_dict().items()}

        if best_state:
            self.net.load_state_dict(best_state)
        self.fit_temperature(val_dl)
        print(f"best val acc {best_acc:.4f}  temperature {self.temperature:.3f}")
        return self

    def evaluate(self, dl):
        torch = self.torch
        self.net.eval()
        logits_all, y_all = [], []
        with torch.no_grad():
            for xb, yb in dl:
                logits_all.append(self.net(xb.to(self.device)).cpu())
                y_all.append(yb)
        logits = torch.cat(logits_all)
        y = torch.cat(y_all)
        acc = (logits.argmax(1) == y).float().mean().item()
        return acc, logits, y

    def fit_temperature(self, val_dl):
        """
        Temperature scaling (Guo et al. 2017). One parameter, fitted on the
        validation split, that makes the confidence number honest.
        """
        torch = self.torch
        _, logits, y = self.evaluate(val_dl)
        log_t = torch.zeros(1, requires_grad=True)
        opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=60)
        nll = torch.nn.CrossEntropyLoss()

        def closure():
            opt.zero_grad()
            loss = nll(logits / log_t.exp(), y)
            loss.backward()
            return loss

        opt.step(closure)
        self.temperature = float(log_t.exp().item())
        return self.temperature

    # ── inference ──────────────────────────────────────────────────
    def predict(self, image, top_k: int = 3, saliency: bool = False) -> Prediction:
        from PIL import Image
        from app.core.stress import BMWP_FAMILY

        torch = self.torch
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")
        x = build_transforms(False)(image).unsqueeze(0).to(self.device)

        self.net.eval()
        with torch.no_grad():
            logits = self.net(x) / self.temperature
            probs = torch.softmax(logits, dim=1)[0].cpu().numpy()

        order = probs.argsort()[::-1]
        top = [(self.classes[i], float(probs[i])) for i in order[:top_k]]
        taxon = top[0][0]
        cam = self.grad_cam(x, int(order[0])) if saliency else None
        return Prediction(
            taxon=taxon, confidence=top[0][1], top_k=top,
            bmwp=BMWP_FAMILY.get(taxon), saliency=cam,
        )

    def grad_cam(self, x, class_idx: int) -> np.ndarray:
        """Grad-CAM over the last conv block. Returns a 0..1 map at input size."""
        torch = self.torch
        acts, grads = {}, {}
        target = self.net.features[-1]

        h1 = target.register_forward_hook(lambda m, i, o: acts.setdefault("v", o))
        h2 = target.register_full_backward_hook(lambda m, gi, go: grads.setdefault("v", go[0]))
        try:
            self.net.zero_grad()
            out = self.net(x)
            out[0, class_idx].backward()
            a, g = acts["v"], grads["v"]
            w = g.mean(dim=(2, 3), keepdim=True)
            cam = torch.relu((w * a).sum(dim=1, keepdim=True))
            cam = torch.nn.functional.interpolate(
                cam, size=x.shape[-2:], mode="bilinear", align_corners=False)
            cam = cam[0, 0].detach().cpu().numpy()
        finally:
            h1.remove()
            h2.remove()
        rng = cam.max() - cam.min()
        return (cam - cam.min()) / rng if rng > 1e-8 else np.zeros_like(cam)

    # ── persistence ────────────────────────────────────────────────
    def save(self, path: str | Path):
        torch = self.torch
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            "state": self.net.state_dict(), "classes": self.classes,
            "temperature": self.temperature, "version": self.version,
        }, path)
        path.with_suffix(".classes.json").write_text(json.dumps(self.classes, indent=1))

    @classmethod
    def load(cls, path: str | Path, device: str | None = None) -> "TaxonClassifier":
        torch = _torch()
        blob = torch.load(path, map_location=device or "cpu")
        obj = cls(classes=blob["classes"], device=device)
        obj.net.load_state_dict(blob["state"])
        obj.temperature = blob.get("temperature", 1.0)
        obj.version = blob.get("version", MODEL_VERSION)
        obj.net.eval()
        return obj

    def export_onnx(self, path: str | Path):
        """ONNX keeps the API container off the torch dependency."""
        torch = self.torch
        dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE, device=self.device)
        torch.onnx.export(
            self.net, dummy, str(path),
            input_names=["image"], output_names=["logits"],
            dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=17,
        )


def overlay_saliency(image, cam: np.ndarray, alpha: float = 0.45):
    """Grad-CAM heatmap composited over the original. Returns a PIL image."""
    from PIL import Image
    import matplotlib.cm as cm

    if isinstance(image, (str, Path)):
        image = Image.open(image).convert("RGB")
    image = image.resize((cam.shape[1], cam.shape[0]))
    heat = (cm.get_cmap("inferno")(cam)[:, :, :3] * 255).astype(np.uint8)
    return Image.blend(image, Image.fromarray(heat), alpha)


def main() -> None:
    """Train, calibrate and export the classifier used by the API runtime."""
    import argparse

    parser = argparse.ArgumentParser(description="Train the WatSen BMWP family classifier")
    parser.add_argument("--data", required=True, help="directory containing train/ and val/")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--out", default="../../models/taxon_classifier.pt")
    parser.add_argument("--onnx", default="../../models/taxon_classifier.onnx")
    args = parser.parse_args()
    data = Path(args.data)
    if not (data / "train").exists() or not (data / "val").exists():
        raise SystemExit(f"{data} must contain train/ and val/ class folders")
    model = TaxonClassifier().fit(data, epochs=args.epochs, batch_size=args.batch_size)
    model.save(args.out)
    model.export_onnx(args.onnx)
    Path(args.onnx).with_suffix(".classes.json").write_text(json.dumps(model.classes, indent=1))
    print(f"saved {args.out} and {args.onnx}")


if __name__ == "__main__":
    main()
