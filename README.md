# Proofgrain — Photo-Based Crop Grading & Fair-Price Marketplace

Small farmers are routinely under-paid because grain quality is judged *by eye* by the
buyer. Proofgrain lets a farmer photograph a grain sample on a blue mat next to a
printed colour card. Computer vision grades it objectively, the result is written to a
**tamper-evident ledger**, and buyers bid against a verified grade. Disputes go to an
independent assessor whose re-grade automatically adjusts the price.

```
 Photo (mat + colour card)
   └─> colour correction (affine fit to 6 reference patches)
        └─> segmentation (distance from mat colour, morphology, connected components)
             └─> per-kernel measurements (area, length, width, mean RGB)
                  └─> whole / broken / discoloured / foreign  →  % by area  →  Grade A/B/C
                       └─> ledger: GRADED (image SHA-256 + result)
                            └─> listing → bids → SOLD → (dispute → REGRADED → price adjusted)
```

## Modules
| File | Purpose |
|---|---|
| `proofgrain/synth.py` | Synthetic grading-mat photos with ground truth (rice & wheat, broken / discoloured kernels, stones, random camera colour cast, noise) |
| `proofgrain/color.py` | Least-squares affine colour correction from the reference card, with fit residual as a quality signal |
| `proofgrain/grader.py` | Segmentation, kernel measurement, classification, per-crop grade specifications, confidence & guidance notes (too few kernels, clumps, card not visible), annotated output image |
| `proofgrain/ledger.py` | SHA-256 hash-chained event log with full-chain verification |
| `proofgrain/store.py` | Users, batches, listings, bids, trades, disputes; price suggestion from local trade medians with fallback reference price × grade factor |
| `proofgrain/api.py` | FastAPI with bearer-token auth and role checks (farmer / buyer / assessor) |
| `web/` | Mobile-first web app in **English, Hindi, Marathi**: farmer flow, buyer market, assessor dispute desk, ledger viewer |

## Quick start
```bash
pip install -r requirements.txt
python scripts/make_samples.py         # sample photos -> samples/ and web/samples/
uvicorn proofgrain.api:app --reload    # http://127.0.0.1:8000
pytest -q                              # 8 tests
python scripts/evaluate.py             # grading error vs ground truth
```
Open the app in three browser profiles (farmer, buyer, assessor) to play the whole flow.
For "Use a sample photo", run `make_samples.py` first.

## Grade specifications (illustrative, editable in `grader.GRADE_SPECS`)
| Crop | Grade | Broken ≤ | Discoloured ≤ | Foreign ≤ |
|---|---|---|---|---|
| Rice | A / B / C | 5 / 15 / 25 % | 2 / 5 / 8 % | 0.5 / 1 / 2 % |
| Wheat | A / B / C | 3 / 6 / 10 % | 2 / 4 / 6 % | 0.75 / 1.5 / 3 % |

These are placeholders. Replace them with the specification of the relevant agency or
buyer contract (e.g. FCI / AGMARK) before real use.

## Why it is tamper-evident
Each ledger event's hash = SHA-256(seq, batch, event, payload, actor, time, **previous hash**).
Editing any past record (for example changing a grade from C to A) breaks every later
hash. `GET /api/ledger/verify` finds the first broken event, and a test proves it. The
photo's SHA-256 is in the GRADED event, so the image can't be quietly swapped either.

## Limitations and next steps
* Real photos: kernels touch and overlap. Add watershed splitting, or a small
  instance-segmentation model (YOLOv8-seg / Mask R-CNN) trained on labelled field photos.
* Moisture can't be measured from an RGB photo. Add a Bluetooth moisture meter reading.
* On-device inference: port the grader to TFLite in a Flutter app so it works offline in the field.
* Anchor the daily ledger head hash publicly (SMS bulletin or a public chain).
* Phone-OTP login in place of demo token registration.
