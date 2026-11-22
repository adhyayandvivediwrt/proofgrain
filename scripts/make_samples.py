"""Generate sample grain photos (with ground truth) into samples/ and web/samples/.

Usage: python scripts/make_samples.py
"""
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from proofgrain import synth  # noqa: E402

CASES = [
    ("rice_sample", "rice", 0.04, 0.01, 0),
    ("rice_gradeB", "rice", 0.11, 0.03, 1),
    ("rice_poor", "rice", 0.30, 0.10, 4),
    ("wheat_sample", "wheat", 0.02, 0.01, 0),
    ("wheat_gradeC", "wheat", 0.08, 0.04, 2),
]


def main():
    out = os.path.join(ROOT, "samples")
    web = os.path.join(ROOT, "web", "samples")
    os.makedirs(out, exist_ok=True)
    os.makedirs(web, exist_ok=True)
    truth = {}
    for i, (name, crop, br, dc, st) in enumerate(CASES):
        img, t = synth.generate(crop, n=160, broken_frac=br, discoloured_frac=dc, stones=st, seed=100 + i)
        Image.fromarray(img).save(os.path.join(out, f"{name}.png"))
        if name.endswith("_sample"):
            Image.fromarray(img).save(os.path.join(web, f"{name}.png"))
        truth[name] = {"crop": crop, **t}
        print(name, t)
    with open(os.path.join(out, "ground_truth.json"), "w") as f:
        json.dump(truth, f, indent=2)


if __name__ == "__main__":
    main()
