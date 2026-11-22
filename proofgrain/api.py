"""Proofgrain API.  Run: uvicorn proofgrain.api:app --reload"""
from __future__ import annotations

import base64
import os

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import grader
from .store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class UserIn(BaseModel):
    name: str
    role: str = Field(pattern="^(farmer|buyer|assessor)$")
    phone: str = ""
    village: str = ""
    language: str = "en"


class BatchIn(BaseModel):
    crop: str = Field(pattern="^(rice|wheat)$")
    weight_kg: float = Field(gt=0)
    location: str = ""


class ListIn(BaseModel):
    ask_per_quintal: float | None = None


class BidIn(BaseModel):
    price_per_quintal: float = Field(gt=0)


class DisputeIn(BaseModel):
    reason: str


def create_app(db_path: str | None = None) -> FastAPI:
    data = os.path.join(ROOT, "data")
    db_path = db_path or os.environ.get("PROOFGRAIN_DB", os.path.join(data, "proofgrain.db"))
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    img_dir = os.path.join(os.path.dirname(db_path), "images")
    os.makedirs(img_dir, exist_ok=True)
    s = Store(db_path)
    app = FastAPI(title="Proofgrain", version="1.0")

    def user(authorization: str = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        u = s.user_by_token(authorization[7:])
        if not u:
            raise HTTPException(401, "invalid token")
        return u

    def role(*roles):
        def dep(u=Depends(user)):
            if u["role"] not in roles:
                raise HTTPException(403, f"requires role {roles}")
            return u
        return dep

    async def run_grading(file: UploadFile, crop: str):
        raw = await file.read()
        try:
            img = grader.load_image(raw)
        except Exception:
            raise HTTPException(400, "not a valid image")
        report, kernels, corrected = grader.grade_image(img, crop, raw)
        png = grader.annotate(corrected, kernels)
        with open(os.path.join(img_dir, f"{report.image_sha256}.png"), "wb") as f:
            f.write(png)
        with open(os.path.join(img_dir, f"{report.image_sha256}.orig"), "wb") as f:
            f.write(raw)
        return report.to_dict(), png

    @app.post("/api/users")
    def register(u: UserIn):
        uid, tok = s.add_user(**u.model_dump())
        return {"id": uid, "token": tok}

    @app.get("/api/me")
    def me(u=Depends(user)):
        return u

    @app.post("/api/batches")
    def create_batch(b: BatchIn, u=Depends(role("farmer"))):
        return {"id": s.create_batch(u["id"], b.crop, b.weight_kg, b.location)}

    @app.get("/api/batches")
    def my_batches(u=Depends(user)):
        rows = s.q("SELECT id,crop,weight_kg,grade,status,location,created FROM batches WHERE farmer_id=? ORDER BY id DESC",
                   (u["id"],))
        return rows

    @app.get("/api/batches/{bid}")
    def get_batch(bid: int):
        b = s.batch(bid)
        if not b:
            raise HTTPException(404)
        return b

    @app.post("/api/batches/{bid}/grade")
    async def grade(bid: int, file: UploadFile = File(...), u=Depends(role("farmer", "assessor"))):
        b = s.batch(bid)
        if not b:
            raise HTTPException(404)
        if u["role"] == "farmer" and b["farmer_id"] != u["id"]:
            raise HTTPException(403)
        if b["status"] not in ("created", "graded"):
            raise HTTPException(409, "batch already listed - use a dispute to re-grade")
        report, png = await run_grading(file, b["crop"])
        entry = s.set_grade(bid, report, u["id"])
        return {"report": report, "ledger": entry, "suggested_price": s.suggested_price(b["crop"], report["grade"]),
                "annotated_png_b64": base64.b64encode(png).decode()}

    @app.post("/api/grade/preview")
    async def preview(crop: str = Form("rice"), file: UploadFile = File(...)):
        """Grade a photo without recording it (field practice / training)."""
        report, png = await run_grading(file, crop)
        return {"report": report, "annotated_png_b64": base64.b64encode(png).decode()}

    @app.get("/api/images/{sha}")
    def image(sha: str):
        p = os.path.join(img_dir, f"{sha}.png")
        if not sha.isalnum() or not os.path.exists(p):
            raise HTTPException(404)
        return FileResponse(p, media_type="image/png")

    @app.post("/api/batches/{bid}/list")
    def list_batch(bid: int, body: ListIn, u=Depends(role("farmer"))):
        b = s.batch(bid)
        if not b or b["farmer_id"] != u["id"]:
            raise HTTPException(404)
        if b["status"] != "graded":
            raise HTTPException(409, "grade the batch before listing")
        ask = body.ask_per_quintal or s.suggested_price(b["crop"], b["grade"])["price"]
        return {"listing_id": s.list_batch(bid, ask, u["id"]), "ask_per_quintal": ask}

    @app.get("/api/listings")
    def listings(crop: str | None = None):
        return s.open_listings(crop)

    @app.post("/api/listings/{lid}/bids")
    def bid(lid: int, body: BidIn, u=Depends(role("buyer"))):
        try:
            return {"bid_id": s.place_bid(lid, u["id"], body.price_per_quintal)}
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/listings/{lid}/bids")
    def bids(lid: int):
        return s.bids_for(lid)

    @app.post("/api/bids/{bid_id}/accept")
    def accept(bid_id: int, u=Depends(role("farmer"))):
        try:
            return s.accept_bid(bid_id, u["id"])
        except ValueError as e:
            raise HTTPException(409, str(e))
        except PermissionError as e:
            raise HTTPException(403, str(e))

    @app.post("/api/batches/{bid}/disputes")
    def dispute(bid: int, body: DisputeIn, u=Depends(role("buyer"))):
        if not s.batch(bid):
            raise HTTPException(404)
        return {"dispute_id": s.raise_dispute(bid, u["id"], body.reason)}

    @app.get("/api/disputes")
    def disputes(u=Depends(user)):
        return s.q("SELECT * FROM disputes ORDER BY ts DESC")

    @app.post("/api/disputes/{did}/regrade")
    async def regrade(did: int, file: UploadFile = File(...), u=Depends(role("assessor"))):
        d = s.one("SELECT * FROM disputes WHERE id=?", (did,))
        if not d:
            raise HTTPException(404)
        report, _ = await run_grading(file, s.batch(d["batch_id"])["crop"])
        try:
            return {"report": report, **s.resolve_dispute(did, report, u["id"])}
        except ValueError as e:
            raise HTTPException(409, str(e))

    @app.get("/api/price/suggest")
    def suggest(crop: str, grade: str):
        return s.suggested_price(crop, grade)

    @app.get("/api/price/history")
    def history(crop: str):
        return s.price_history(crop)

    @app.get("/api/ledger/verify")
    def verify():
        return s.ledger.verify()

    @app.get("/api/ledger/batch/{bid}")
    def batch_history(bid: int):
        return s.ledger.history(bid)

    @app.get("/api/grade-specs")
    def specs():
        return grader.GRADE_SPECS

    web = os.path.join(ROOT, "web")
    app.mount("/static", StaticFiles(directory=web), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(web, "index.html"))

    app.state.store = s
    return app


app = create_app() if os.environ.get("PROOFGRAIN_NO_AUTOAPP") != "1" else None
