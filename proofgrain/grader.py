"""Computer-vision grain grading.

Pipeline: colour-correct -> segment kernels from the grading mat -> measure
each object (area, length, width, colour) -> classify as whole / broken /
discoloured / foreign -> compute count- and area-weighted percentages ->
map to a grade using configurable per-crop specifications.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import asdict, dataclass, field

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from . import color
from .synth import CARD_BOX, MAT

# Illustrative grade specifications (max % by area-weight). Tune per mandi / buyer contract.
GRADE_SPECS = {
    "rice": [("A", {"broken": 5, "discoloured": 2, "foreign": 0.5}),
             ("B", {"broken": 15, "discoloured": 5, "foreign": 1.0}),
             ("C", {"broken": 25, "discoloured": 8, "foreign": 2.0})],
    "wheat": [("A", {"broken": 3, "discoloured": 2, "foreign": 0.75}),
              ("B", {"broken": 6, "discoloured": 4, "foreign": 1.5}),
              ("C", {"broken": 10, "discoloured": 6, "foreign": 3.0})],
}
DISCOLOUR_RULE = {"rice": lambda r, g, b: (r - b) > 85, "wheat": lambda r, g, b: (r + g + b) / 3 < 110 and (r - b) > 40}
MIN_AREA = 35
MIN_KERNELS_FOR_CONFIDENCE = 100


@dataclass
class Kernel:
    label: str
    area: int
    length: float
    width: float
    rgb: tuple
    bbox: tuple


@dataclass
class GradeReport:
    crop: str
    grade: str
    kernels: int
    counts: dict
    percent_by_count: dict
    percent_by_area: dict
    confidence: float
    colour_residual: float
    image_sha256: str
    notes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def segment(img: np.ndarray):
    dist = np.linalg.norm(img - MAT, axis=2)
    mask = dist > 55
    x0, y0, x1, y1 = CARD_BOX
    mask[y0:y1, x0:x1] = False
    mask = ndimage.binary_opening(mask, iterations=1)
    lab, n = ndimage.label(mask)
    return lab, n


def measure(img, lab, n):
    objs = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        m = lab[sl] == i
        area = int(m.sum())
        if area < MIN_AREA:
            continue
        ys, xs = np.nonzero(m)
        cov = np.cov(np.vstack([xs, ys])) if area > 2 else np.eye(2)
        ev = np.sort(np.linalg.eigvalsh(cov))[::-1]
        length, width = 4 * np.sqrt(max(ev[0], 1e-6)), 4 * np.sqrt(max(ev[1], 1e-6))
        rgb = tuple(float(v) for v in img[sl][m].mean(axis=0))
        objs.append(dict(area=area, length=length, width=width, rgb=rgb,
                         bbox=(sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)))
    return objs


def classify(objs, crop):
    kernels = []
    is_disc = DISCOLOUR_RULE[crop]
    candidates = []
    for o in objs:
        r, g, b = o["rgb"]
        bright = (r + g + b) / 3
        sat = max(r, g, b) - min(r, g, b)
        if bright < 125 and sat < 35:
            kernels.append(Kernel("foreign", o["area"], o["length"], o["width"], o["rgb"], o["bbox"]))
        else:
            candidates.append(o)
    if candidates:
        ref_len = np.percentile([o["length"] for o in candidates], 85)
    for o in candidates:
        r, g, b = o["rgb"]
        if is_disc(r, g, b):
            lbl = "discoloured"
        elif o["length"] < 0.72 * ref_len:
            lbl = "broken"
        else:
            lbl = "whole"
        kernels.append(Kernel(lbl, o["area"], o["length"], o["width"], o["rgb"], o["bbox"]))
    return kernels


def assign_grade(crop, pct):
    for grade, limits in GRADE_SPECS[crop]:
        if all(pct.get(k, 0) <= v for k, v in limits.items()):
            return grade
    return "Below grade"


def grade_image(img: np.ndarray, crop: str = "rice", raw_bytes: bytes | None = None):
    if crop not in GRADE_SPECS:
        raise ValueError(f"unsupported crop {crop}")
    img = np.asarray(img)[..., :3]
    sha = hashlib.sha256(raw_bytes if raw_bytes is not None else img.tobytes()).hexdigest()
    corrected, residual = color.correct(img.astype(float))
    lab, n = segment(corrected)
    kernels = classify(measure(corrected, lab, n), crop)

    cats = ["whole", "broken", "discoloured", "foreign"]
    counts = {c: sum(k.label == c for k in kernels) for c in cats}
    total = max(len(kernels), 1)
    total_area = max(sum(k.area for k in kernels), 1)
    pct_c = {c: round(100 * counts[c] / total, 2) for c in cats}
    pct_a = {c: round(100 * sum(k.area for k in kernels if k.label == c) / total_area, 2) for c in cats}

    notes = []
    conf = 1.0
    if len(kernels) < MIN_KERNELS_FOR_CONFIDENCE:
        conf *= len(kernels) / MIN_KERNELS_FOR_CONFIDENCE
        notes.append(f"Only {len(kernels)} kernels detected - spread at least {MIN_KERNELS_FOR_CONFIDENCE} for a reliable grade")
    if residual > 12:
        conf *= max(0.2, 1 - (residual - 12) / 40)
        notes.append("Reference card not clearly visible - check lighting and card position")
    big = [k for k in kernels if k.label != "foreign" and k.area > 2.2 * np.median([q.area for q in kernels] or [1])]
    if big:
        notes.append(f"{len(big)} clumps of touching kernels - spread grains apart")
        conf *= max(0.5, 1 - len(big) / total)

    report = GradeReport(crop, assign_grade(crop, pct_a), len(kernels), counts, pct_c, pct_a,
                         round(conf, 3), round(residual, 2), sha, notes)
    return report, kernels, corrected


COLORS = {"whole": (80, 220, 120), "broken": (255, 200, 0), "discoloured": (255, 120, 40), "foreign": (255, 40, 40)}


def annotate(img: np.ndarray, kernels) -> bytes:
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for k in kernels:
        d.rectangle(k.bbox, outline=COLORS[k.label], width=2)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def load_image(data: bytes) -> np.ndarray:
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if im.size != (900, 640):
        im = im.resize((900, 640))
    return np.asarray(im)
