"""Persistence and marketplace logic: users, batches, listings, bids, trades, disputes."""
from __future__ import annotations

import json
import secrets
import sqlite3
import statistics
import threading
import time

from .ledger import Ledger

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, role TEXT, phone TEXT, village TEXT,
  language TEXT, token TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, farmer_id INTEGER, crop TEXT, weight_kg REAL,
  location TEXT, grade TEXT, report TEXT, image_sha TEXT, status TEXT, created REAL);
CREATE TABLE IF NOT EXISTS listings(id INTEGER PRIMARY KEY, batch_id INTEGER, ask_per_quintal REAL,
  status TEXT, created REAL);
CREATE TABLE IF NOT EXISTS bids(id INTEGER PRIMARY KEY, listing_id INTEGER, buyer_id INTEGER,
  price_per_quintal REAL, status TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, listing_id INTEGER, bid_id INTEGER, crop TEXT,
  grade TEXT, price_per_quintal REAL, weight_kg REAL, ts REAL);
CREATE TABLE IF NOT EXISTS disputes(id INTEGER PRIMARY KEY, batch_id INTEGER, raised_by INTEGER, reason TEXT,
  status TEXT, regrade TEXT, original_grade TEXT, new_grade TEXT, adjusted_price REAL, ts REAL);
"""

# Illustrative reference prices (INR / quintal) used until local trade history exists.
BASE_PRICE = {"rice": 3100.0, "wheat": 2450.0}
GRADE_MULT = {"A": 1.08, "B": 1.0, "C": 0.92, "Below grade": 0.8}


class Store:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.conn.executescript(SCHEMA)
        self.ledger = Ledger(self)

    def q(self, sql, a=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, a).fetchall()]

    def one(self, sql, a=()):
        r = self.q(sql, a)
        return r[0] if r else None

    def x(self, sql, a=()):
        with self.lock:
            c = self.conn.execute(sql, a)
            self.conn.commit()
            return c.lastrowid

    # ---- users ----
    def add_user(self, name, role, phone="", village="", language="en"):
        tok = secrets.token_urlsafe(24)
        uid = self.x("INSERT INTO users(name,role,phone,village,language,token) VALUES(?,?,?,?,?,?)",
                     (name, role, phone, village, language, tok))
        return uid, tok

    def user_by_token(self, tok):
        return self.one("SELECT id,name,role,village,language FROM users WHERE token=?", (tok,))

    # ---- batches ----
    def create_batch(self, farmer_id, crop, weight_kg, location):
        bid = self.x("INSERT INTO batches(farmer_id,crop,weight_kg,location,status,created) VALUES(?,?,?,?,?,?)",
                     (farmer_id, crop, weight_kg, location, "created", time.time()))
        self.ledger.append(bid, "BATCH_CREATED", {"crop": crop, "weight_kg": weight_kg, "location": location}, farmer_id)
        return bid

    def batch(self, bid):
        b = self.one("SELECT * FROM batches WHERE id=?", (bid,))
        if b and b["report"]:
            b["report"] = json.loads(b["report"])
        return b

    def set_grade(self, bid, report: dict, actor):
        self.x("UPDATE batches SET grade=?, report=?, image_sha=?, status='graded' WHERE id=?",
               (report["grade"], json.dumps(report), report["image_sha256"], bid))
        return self.ledger.append(bid, "GRADED", {"grade": report["grade"], "image_sha256": report["image_sha256"],
                                                  "percent_by_area": report["percent_by_area"],
                                                  "kernels": report["kernels"]}, actor)

    # ---- pricing ----
    def suggested_price(self, crop, grade, days=90):
        since = time.time() - days * 86400
        prices = [r["price_per_quintal"] for r in
                  self.q("SELECT price_per_quintal FROM trades WHERE crop=? AND grade=? AND ts>?", (crop, grade, since))]
        if len(prices) >= 3:
            return {"price": round(statistics.median(prices), 0), "basis": f"median of {len(prices)} local trades"}
        return {"price": round(BASE_PRICE[crop] * GRADE_MULT.get(grade, 1.0), 0), "basis": "reference price x grade factor"}

    def price_history(self, crop):
        return self.q("SELECT grade, price_per_quintal, weight_kg, ts FROM trades WHERE crop=? ORDER BY ts", (crop,))

    # ---- market ----
    def list_batch(self, bid, ask, actor):
        lid = self.x("INSERT INTO listings(batch_id,ask_per_quintal,status,created) VALUES(?,?,?,?)",
                     (bid, ask, "open", time.time()))
        self.x("UPDATE batches SET status='listed' WHERE id=?", (bid,))
        self.ledger.append(bid, "LISTED", {"listing_id": lid, "ask_per_quintal": ask}, actor)
        return lid

    def open_listings(self, crop=None):
        sql = """SELECT l.*, b.crop, b.weight_kg, b.grade, b.location, b.report, u.name AS farmer,
                 (SELECT MAX(price_per_quintal) FROM bids WHERE listing_id=l.id AND status='open') AS best_bid
                 FROM listings l JOIN batches b ON b.id=l.batch_id JOIN users u ON u.id=b.farmer_id
                 WHERE l.status='open'"""
        rows = self.q(sql + (" AND b.crop=?" if crop else "") + " ORDER BY l.created DESC", (crop,) if crop else ())
        for r in rows:
            rep = json.loads(r.pop("report") or "{}")
            r["percent_by_area"] = rep.get("percent_by_area")
            r["confidence"] = rep.get("confidence")
        return rows

    def place_bid(self, lid, buyer_id, price):
        lst = self.one("SELECT * FROM listings WHERE id=?", (lid,))
        if not lst or lst["status"] != "open":
            raise ValueError("listing not open")
        bid = self.x("INSERT INTO bids(listing_id,buyer_id,price_per_quintal,status,ts) VALUES(?,?,?,?,?)",
                     (lid, buyer_id, price, "open", time.time()))
        self.ledger.append(lst["batch_id"], "BID", {"bid_id": bid, "price_per_quintal": price}, buyer_id)
        return bid

    def bids_for(self, lid):
        return self.q("""SELECT b.*, u.name AS buyer FROM bids b JOIN users u ON u.id=b.buyer_id
                         WHERE listing_id=? ORDER BY price_per_quintal DESC""", (lid,))

    def accept_bid(self, bid_id, actor):
        bid = self.one("SELECT * FROM bids WHERE id=?", (bid_id,))
        if not bid or bid["status"] != "open":
            raise ValueError("bid not open")
        lst = self.one("SELECT * FROM listings WHERE id=?", (bid["listing_id"],))
        b = self.batch(lst["batch_id"])
        if b["farmer_id"] != actor:
            raise PermissionError("only the farmer can accept")
        self.x("UPDATE bids SET status='rejected' WHERE listing_id=? AND id<>?", (lst["id"], bid_id))
        self.x("UPDATE bids SET status='accepted' WHERE id=?", (bid_id,))
        self.x("UPDATE listings SET status='sold' WHERE id=?", (lst["id"],))
        self.x("UPDATE batches SET status='sold' WHERE id=?", (b["id"],))
        tid = self.x("INSERT INTO trades(listing_id,bid_id,crop,grade,price_per_quintal,weight_kg,ts) VALUES(?,?,?,?,?,?,?)",
                     (lst["id"], bid_id, b["crop"], b["grade"], bid["price_per_quintal"], b["weight_kg"], time.time()))
        value = round(bid["price_per_quintal"] * b["weight_kg"] / 100, 2)
        self.ledger.append(b["id"], "SOLD", {"trade_id": tid, "buyer_id": bid["buyer_id"],
                                             "price_per_quintal": bid["price_per_quintal"], "value_inr": value}, actor)
        return {"trade_id": tid, "value_inr": value}

    # ---- disputes ----
    def raise_dispute(self, batch_id, buyer_id, reason):
        did = self.x("INSERT INTO disputes(batch_id,raised_by,reason,status,original_grade,ts) VALUES(?,?,?,?,?,?)",
                     (batch_id, buyer_id, reason, "open", self.batch(batch_id)["grade"], time.time()))
        self.ledger.append(batch_id, "DISPUTE_RAISED", {"dispute_id": did, "reason": reason}, buyer_id)
        return did

    def resolve_dispute(self, did, regrade: dict, assessor_id):
        d = self.one("SELECT * FROM disputes WHERE id=?", (did,))
        if not d or d["status"] != "open":
            raise ValueError("dispute not open")
        trade = self.one("""SELECT t.* FROM trades t JOIN listings l ON l.id=t.listing_id
                            WHERE l.batch_id=? ORDER BY t.ts DESC LIMIT 1""", (d["batch_id"],))
        old, new = d["original_grade"], regrade["grade"]
        adjusted = None
        if trade:
            adjusted = round(trade["price_per_quintal"] * GRADE_MULT[new] / GRADE_MULT[old], 0)
        self.x("UPDATE disputes SET status='resolved', regrade=?, new_grade=?, adjusted_price=? WHERE id=?",
               (json.dumps(regrade), new, adjusted, did))
        self.ledger.append(d["batch_id"], "REGRADED", {"dispute_id": did, "original_grade": old, "new_grade": new,
                                                       "image_sha256": regrade["image_sha256"],
                                                       "adjusted_price_per_quintal": adjusted}, assessor_id)
        return {"original_grade": old, "new_grade": new, "adjusted_price_per_quintal": adjusted}
