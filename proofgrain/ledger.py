"""Tamper-evident event ledger (hash chain).

Every important action (batch created, graded, listed, bid accepted, dispute,
re-grade, settlement) is appended as an event whose hash covers the previous
event's hash. Changing any historical record breaks every hash after it, so
`verify()` exposes tampering. Publishing the head hash daily (SMS to farmer
groups, a public bulletin, or a public blockchain) makes rewriting history
detectable even by outsiders.
"""
from __future__ import annotations

import hashlib
import json
import time

GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def event_hash(seq, batch_id, event, payload, actor, ts, prev_hash) -> str:
    body = canonical({"seq": seq, "batch_id": batch_id, "event": event, "payload": payload,
                      "actor": actor, "ts": round(ts, 6), "prev": prev_hash})
    return hashlib.sha256(body.encode()).hexdigest()


class Ledger:
    def __init__(self, db):
        self.db = db
        db.x("""CREATE TABLE IF NOT EXISTS ledger(seq INTEGER PRIMARY KEY, batch_id INTEGER, event TEXT,
                payload TEXT, actor INTEGER, ts REAL, prev_hash TEXT, hash TEXT)""")

    def head(self):
        r = self.db.q("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1")
        return (r[0]["seq"], r[0]["hash"]) if r else (0, GENESIS)

    def append(self, batch_id, event, payload, actor):
        with self.db.lock:
            r = self.db.conn.execute("SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (r[0] + 1, r[1]) if r else (1, GENESIS)
            ts = time.time()
            h = event_hash(seq, batch_id, event, payload, actor, ts, prev)
            self.db.conn.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)",
                                 (seq, batch_id, event, canonical(payload), actor, ts, prev, h))
            self.db.conn.commit()
        return {"seq": seq, "hash": h}

    def history(self, batch_id):
        rows = self.db.q("SELECT * FROM ledger WHERE batch_id=? ORDER BY seq", (batch_id,))
        for r in rows:
            r["payload"] = json.loads(r["payload"])
        return rows

    def verify(self):
        prev = GENESIS
        rows = self.db.q("SELECT * FROM ledger ORDER BY seq")
        for r in rows:
            expect = event_hash(r["seq"], r["batch_id"], r["event"], json.loads(r["payload"]),
                                r["actor"], r["ts"], prev)
            if r["prev_hash"] != prev or r["hash"] != expect:
                return {"valid": False, "broken_at_seq": r["seq"], "events": len(rows)}
            prev = r["hash"]
        return {"valid": True, "events": len(rows), "head": prev}
