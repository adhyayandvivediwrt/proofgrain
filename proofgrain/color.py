"""Colour correction using the printed reference card.

Phone cameras apply unknown white balance, exposure and tone mapping. The
6-patch card has known sRGB values; we fit an affine 3x4 transform from the
observed patch means to the reference values by least squares and apply it to
the whole image, so colour-based grading rules stay stable across phones and
light.
"""
from __future__ import annotations

import numpy as np

from .synth import REF_PATCHES, patch_boxes


def fit(img: np.ndarray, inset: int = 8):
    obs = []
    for x0, y0, x1, y1 in patch_boxes():
        region = img[y0 + inset:y1 - inset, x0 + inset:x1 - inset].reshape(-1, 3).astype(float)
        obs.append(np.median(region, axis=0))
    obs = np.array(obs)
    A = np.hstack([obs, np.ones((len(obs), 1))])
    T, *_ = np.linalg.lstsq(A, REF_PATCHES, rcond=None)      # (4,3)
    pred = A @ T
    residual = float(np.sqrt(np.mean((pred - REF_PATCHES) ** 2)))
    return T, residual


def apply(img: np.ndarray, T: np.ndarray) -> np.ndarray:
    flat = img.reshape(-1, 3).astype(float)
    out = np.hstack([flat, np.ones((len(flat), 1))]) @ T
    return np.clip(out, 0, 255).reshape(img.shape)


def correct(img: np.ndarray):
    T, residual = fit(img)
    return apply(img, T), residual
