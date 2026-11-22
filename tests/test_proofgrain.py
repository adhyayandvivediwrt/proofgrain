import io
import os
import sys

import numpy as np
import pytest
from PIL import Image

os.environ["PROOFGRAIN_NO_AUTOAPP"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient  # noqa: E402

from proofgrain import color, grader, synth  # noqa: E402
from proofgrain.api import create_app  # noqa: E402


def png(img):
    b = io.BytesIO()
    Image.fromarray(img).save(b, format="PNG")
    return b.getvalue()


def test_colour_correction_recovers_reference():
    img, _ = synth.generate("rice", n=10, seed=3)
    _, residual = color.correct(img.astype(float))
    assert residual < 5


@pytest.mark.parametrize("crop", ["rice", "wheat"])
def test_grader_counts_close_to_truth(crop):
    img, truth = synth.generate(crop, n=150, broken_frac=0.12, discoloured_frac=0.04, stones=2, seed=8)
    r, _, _ = grader.grade_image(img, crop)
    for k in truth:
        assert abs(r.counts[k] - truth[k]) <= 2, (k, r.counts, truth)


def test_grade_ordering():
    good, _ = synth.generate("rice", n=160, broken_frac=0.01, discoloured_frac=0.0, stones=0, seed=1)
    bad, _ = synth.generate("rice", n=160, broken_frac=0.35, discoloured_frac=0.12, stones=5, seed=1)
    assert grader.grade_image(good, "rice")[0].grade == "A"
    assert grader.grade_image(bad, "rice")[0].grade == "Below grade"


def test_low_kernel_count_lowers_confidence():
    img, _ = synth.generate("rice", n=30, seed=2)
    r, _, _ = grader.grade_image(img, "rice")
    assert r.confidence < 0.5 and r.notes


@pytest.fixture()
def env(tmp_path):
    c = TestClient(create_app(str(tmp_path / "pg.db")))
    tok = lambda role: {"Authorization": "Bearer " + c.post("/api/users", json={"name": role, "role": role}).json()["token"]}
    return c, tok("farmer"), tok("buyer"), tok("assessor")


def test_end_to_end_trade_and_dispute(env):
    c, F, B, A = env
    bid_ = c.post("/api/batches", json={"crop": "rice", "weight_kg": 1200}, headers=F).json()["id"]
    img, _ = synth.generate("rice", n=160, broken_frac=0.03, discoloured_frac=0.01, stones=0, seed=5)
    g = c.post(f"/api/batches/{bid_}/grade", files={"file": ("a.png", png(img))}, headers=F).json()
    assert g["report"]["grade"] == "A" and g["suggested_price"]["price"] > 0
    lst = c.post(f"/api/batches/{bid_}/list", json={}, headers=F).json()
    # buyers cannot list, farmers cannot bid
    assert c.post(f"/api/listings/{lst['listing_id']}/bids", json={"price_per_quintal": 1}, headers=F).status_code == 403
    b1 = c.post(f"/api/listings/{lst['listing_id']}/bids", json={"price_per_quintal": 3300}, headers=B).json()["bid_id"]
    sale = c.post(f"/api/bids/{b1}/accept", headers=F).json()
    assert sale["value_inr"] == pytest.approx(3300 * 12)
    # buyer disputes, assessor re-grades with a worse photo
    did = c.post(f"/api/batches/{bid_}/disputes", json={"reason": "many broken grains"}, headers=B).json()["dispute_id"]
    bad, _ = synth.generate("rice", n=160, broken_frac=0.12, discoloured_frac=0.03, stones=1, seed=6)
    res = c.post(f"/api/disputes/{did}/regrade", files={"file": ("b.png", png(bad))}, headers=A).json()
    assert res["original_grade"] == "A" and res["new_grade"] in ("B", "C")
    assert res["adjusted_price_per_quintal"] < 3300
    events = [e["event"] for e in c.get(f"/api/ledger/batch/{bid_}").json()]
    assert events == ["BATCH_CREATED", "GRADED", "LISTED", "BID", "SOLD", "DISPUTE_RAISED", "REGRADED"]
    assert c.get("/api/ledger/verify").json()["valid"]


def test_ledger_detects_tampering(env, tmp_path):
    c, F, *_ = env
    bid_ = c.post("/api/batches", json={"crop": "wheat", "weight_kg": 100}, headers=F).json()["id"]
    img, _ = synth.generate("wheat", n=120, seed=9)
    c.post(f"/api/batches/{bid_}/grade", files={"file": ("a.png", png(img))}, headers=F)
    store = c.app.state.store
    store.x("UPDATE ledger SET payload=? WHERE seq=2", ('{"grade":"A"}',))
    v = c.get("/api/ledger/verify").json()
    assert not v["valid"] and v["broken_at_seq"] == 2


def test_auth_required(env):
    c, *_ = env
    assert c.post("/api/batches", json={"crop": "rice", "weight_kg": 1}).status_code == 401
