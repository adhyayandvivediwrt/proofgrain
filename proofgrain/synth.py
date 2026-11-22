"""Synthetic grain-sample photo generator (for development and tests).

Layout the mobile app enforces with an on-screen guide:
  * the sample is spread on a dark-blue grading mat,
  * the printed 6-patch reference card sits inside the top-left guide box.

The generator draws whole, broken and discoloured kernels plus foreign matter
(stones), then applies a random affine colour cast to mimic phone cameras and
lighting, and Gaussian sensor noise. Ground-truth counts are returned.
"""
from __future__ import annotations

import numpy as np

W, H = 900, 640
MAT = np.array([35, 55, 110], float)
CARD_BOX = (0, 0, 300, 104)            # x0, y0, x1, y1 region reserved for the card
PATCH_W, PATCH_H, PATCH_X0, PATCH_Y0 = 40, 60, 24, 22
REF_PATCHES = np.array([
    [245, 245, 245], [160, 160, 160], [40, 40, 40],
    [200, 40, 40], [40, 160, 60], [40, 60, 190]], float)

CROPS = {
    "rice": {"whole_len": (34, 40), "width": (10, 13), "color": (236, 226, 200)},
    "wheat": {"whole_len": (24, 28), "width": (13, 16), "color": (205, 160, 95)},
}
DISCOLOURED = {"rice": (200, 160, 70), "wheat": (120, 80, 45)}
STONE = (100, 95, 88)


def patch_boxes():
    return [(PATCH_X0 + i * (PATCH_W + 4), PATCH_Y0, PATCH_X0 + i * (PATCH_W + 4) + PATCH_W, PATCH_Y0 + PATCH_H)
            for i in range(len(REF_PATCHES))]


def _draw_ellipse(img, cx, cy, a, b, theta, color, rng):
    r = int(max(a, b)) + 2
    y0, y1 = max(int(cy) - r, 0), min(int(cy) + r, H)
    x0, x1 = max(int(cx) - r, 0), min(int(cx) + r, W)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dx, dy = xx - cx, yy - cy
    c, s = np.cos(theta), np.sin(theta)
    u, v = dx * c + dy * s, -dx * s + dy * c
    d = (u / a) ** 2 + (v / b) ** 2
    m = d <= 1
    shade = (1.0 - 0.18 * d[m])[:, None]
    jitter = rng.normal(0, 4, 3)
    img[y0:y1, x0:x1][m] = np.clip((np.array(color) + jitter) * shade, 0, 255)


def _draw_stone(img, cx, cy, r, rng):
    y0, y1 = max(int(cy - r * 1.6), 0), min(int(cy + r * 1.6), H)
    x0, x1 = max(int(cx - r * 1.6), 0), min(int(cx + r * 1.6), W)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    ang = np.arctan2(yy - cy, xx - cx)
    rad = r * (1 + 0.25 * np.sin(3 * ang + rng.uniform(0, 6)) + 0.1 * np.sin(5 * ang))
    m = np.hypot(yy - cy, xx - cx) <= rad
    img[y0:y1, x0:x1][m] = np.clip(np.array(STONE) + rng.normal(0, 6, (m.sum(), 3)), 0, 255)


def generate(crop: str = "rice", n: int = 160, broken_frac: float = 0.08, discoloured_frac: float = 0.03,
             stones: int = 1, seed: int | None = None, cast: bool = True):
    rng = np.random.default_rng(seed)
    spec = CROPS[crop]
    img = np.tile(MAT, (H, W, 1)) + rng.normal(0, 3, (H, W, 3))
    # reference card
    x0, y0, x1, y1 = CARD_BOX
    img[y0 + 10:y1 - 10, x0 + 10:x1 - 10] = 250
    for (px0, py0, px1, py1), col in zip(patch_boxes(), REF_PATCHES):
        img[py0:py1, px0:px1] = col

    placed: list[tuple[float, float, float]] = []
    truth = {"whole": 0, "broken": 0, "discoloured": 0, "foreign": 0}
    kinds = (["broken"] * int(round(n * broken_frac)) + ["discoloured"] * int(round(n * discoloured_frac)))
    kinds += ["whole"] * (n - len(kinds)) + ["foreign"] * stones
    rng.shuffle(kinds)
    for kind in kinds:
        L = rng.uniform(*spec["whole_len"]) / 2
        if kind == "broken":
            L *= rng.uniform(0.35, 0.6)
        b = rng.uniform(*spec["width"]) / 2
        rad = max(L, b) + 5
        for _ in range(400):
            cx, cy = rng.uniform(rad + 4, W - rad - 4), rng.uniform(CARD_BOX[3] + rad + 6, H - rad - 4)
            if all((cx - px) ** 2 + (cy - py) ** 2 > (rad + pr) ** 2 for px, py, pr in placed):
                break
        else:
            continue
        placed.append((cx, cy, rad))
        if kind == "foreign":
            _draw_stone(img, cx, cy, rng.uniform(6, 9), rng)
        else:
            color = DISCOLOURED[crop] if kind == "discoloured" else spec["color"]
            _draw_ellipse(img, cx, cy, L, b, rng.uniform(0, np.pi), color, rng)
        truth[kind] += 1

    if cast:
        M = np.eye(3) + rng.normal(0, 0.06, (3, 3))
        M *= rng.uniform(0.8, 1.05)
        off = rng.normal(0, 8, 3)
        img = img @ M.T + off
    img = np.clip(img + rng.normal(0, 2.5, img.shape), 0, 255).astype(np.uint8)
    return img, truth
