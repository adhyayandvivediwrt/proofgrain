"""Grading accuracy vs ground truth over many synthetic photos.

Usage: python scripts/evaluate.py [n_images]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proofgrain import grader, synth  # noqa: E402


def main(n=40):
    rng = np.random.default_rng(0)
    errs = {k: [] for k in ["whole", "broken", "discoloured", "foreign"]}
    for i in range(n):
        crop = "rice" if i % 2 else "wheat"
        img, t = synth.generate(crop, n=int(rng.integers(110, 200)), broken_frac=rng.uniform(0, .3),
                                discoloured_frac=rng.uniform(0, .1), stones=int(rng.integers(0, 4)), seed=i)
        r, _, _ = grader.grade_image(img, crop)
        for k in errs:
            errs[k].append(abs(r.counts[k] - t[k]))
    for k, v in errs.items():
        print(f"{k:12s} mean abs count error {np.mean(v):.2f}   max {max(v)}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
