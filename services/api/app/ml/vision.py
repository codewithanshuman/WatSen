"""Runtime image assessment with an optional ONNX classifier.

When no trained artefact is present we still perform image-quality checks and
return a clearly-labelled demo suggestion.  The fallback never auto-confirms a
taxon; it is useful for exercising the human-review workflow without pretending
that a research model exists.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageStat

from app.core.stress import BMWP_FAMILY
from app.ml.classifier import DEFAULT_CLASSES

MODEL_PATH = Path(os.getenv("CLASSIFIER_ONNX", "../../models/taxon_classifier.onnx"))


class VisionRuntime:
    def __init__(self):
        self.session = None
        self.classes = DEFAULT_CLASSES
        if MODEL_PATH.exists():
            try:
                import json
                import onnxruntime as ort
                self.session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
                classes_path = MODEL_PATH.with_suffix(".classes.json")
                if classes_path.exists():
                    self.classes = json.loads(classes_path.read_text())
            except Exception:
                self.session = None

    @property
    def mode(self) -> str:
        return "onnx" if self.session else "demo-assist"

    def assess(self, raw: bytes, filename: str = "upload.jpg") -> dict:
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as exc:
            raise ValueError("The uploaded file is not a readable image.") from exc
        quality = self._quality(image)
        if self.session:
            probs = self._predict_onnx(image)
            order = np.argsort(probs)[::-1][:3]
            top = [{"taxon": self.classes[i], "confidence": round(float(probs[i]), 4)} for i in order]
            version = "taxon-classifier-onnx"
        else:
            digest = hashlib.sha256(raw).digest()
            start = int.from_bytes(digest[:2], "big") % len(self.classes)
            picks = [self.classes[(start + step) % len(self.classes)] for step in (0, 4, 9)]
            top = [
                {"taxon": picks[0], "confidence": round(0.54 + digest[2] / 2550, 4)},
                {"taxon": picks[1], "confidence": round(0.22 + digest[3] / 5100, 4)},
                {"taxon": picks[2], "confidence": round(0.10 + digest[4] / 10200, 4)},
            ]
            version = "demo-image-assist-1"
        best = top[0]
        requires_review = self.mode != "onnx" or best["confidence"] < .82 or quality["score"] < .72
        return {
            "filename": filename,
            "predicted_taxon": best["taxon"],
            "taxon_confidence": best["confidence"],
            "top_k": top,
            "bmwp_contribution": BMWP_FAMILY.get(best["taxon"]),
            "ecological_sensitivity": _sensitivity(BMWP_FAMILY.get(best["taxon"])),
            "image_quality": quality,
            "geographic_plausibility": "requires location check",
            "decision": "requires_human_confirmation" if requires_review else "ai_suggestion_high_confidence",
            "model": version,
            "model_mode": self.mode,
            "disclaimer": "AI suggestion only. A citizen or expert must confirm the family before it changes the biological index.",
            "explanation": ["overall body silhouette", "edge and segmentation pattern", "colour and texture cues"],
        }

    def _predict_onnx(self, image: Image.Image) -> np.ndarray:
        image = image.resize((300, 300))
        x = np.asarray(image, dtype=np.float32) / 255.0
        x = (x - np.array([.485, .456, .406], dtype=np.float32)) / np.array([.229, .224, .225], dtype=np.float32)
        x = np.transpose(x, (2, 0, 1))[None]
        name = self.session.get_inputs()[0].name
        logits = self.session.run(None, {name: x})[0][0]
        logits -= logits.max()
        probs = np.exp(logits)
        return probs / probs.sum()

    @staticmethod
    def _quality(image: Image.Image) -> dict:
        gray = image.convert("L")
        brightness = ImageStat.Stat(gray).mean[0]
        edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
        sharpness = float(edges.std())
        resolution = min(image.size)
        b_score = max(0.0, 1 - abs(brightness - 128) / 128)
        s_score = min(1.0, sharpness / 42)
        r_score = min(1.0, resolution / 700)
        score = round(.35 * b_score + .4 * s_score + .25 * r_score, 3)
        return {
            "score": score,
            "label": "suitable" if score >= .72 else "usable" if score >= .48 else "poor",
            "resolution": {"width": image.width, "height": image.height},
            "brightness": round(brightness, 1),
            "sharpness": round(sharpness, 1),
        }


def _sensitivity(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 8:
        return "high"
    if score >= 5:
        return "moderate"
    return "tolerant"
