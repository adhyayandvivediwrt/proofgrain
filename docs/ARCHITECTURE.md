# Proofgrain architecture

## Actors
* **Farmer** – creates batches, photographs samples, lists, accepts bids.
* **Buyer** – browses graded listings, bids, raises disputes.
* **Assessor** – independent (FPO / mandi lab), re-grades disputed batches.

## Data model
```
users(id, name, role, phone, village, language, token)
batches(id, farmer_id, crop, weight_kg, location, grade, report JSON, image_sha, status)
listings(id, batch_id, ask_per_quintal, status)
bids(id, listing_id, buyer_id, price_per_quintal, status)
trades(id, listing_id, bid_id, crop, grade, price_per_quintal, weight_kg, ts)
disputes(id, batch_id, raised_by, reason, status, regrade JSON, original_grade, new_grade, adjusted_price)
ledger(seq, batch_id, event, payload JSON, actor, ts, prev_hash, hash)
```

Batch states: `created → graded → listed → sold`. Disputes run alongside a sale.

## Grading algorithm
1. Resize to the canonical 900×640 frame. The app's camera overlay makes the user frame it this way.
2. Read the median colour of each of the 6 card patches. Fit `T (4×3)` so that `[rgb,1]·T ≈ reference`.
3. Apply `T` to the whole image.
4. Foreground = pixels more than 55 units (Euclidean RGB) from the mat colour, card box excluded. Then binary opening and connected components.
5. Per object: area, principal-axis length and width (4√λ of the pixel-coordinate covariance), mean RGB.
6. Foreign matter: dark and unsaturated. Discoloured: crop-specific colour rule. Broken: length below 72 % of the 85th-percentile kernel length.
7. Area-weighted percentages approximate weight percentages. Grade = the best grade whose limits are all met.

## Price discovery
`suggested = median(trades of same crop & grade, last 90 days)` once there are at least 3 trades.
Before that, `reference price × grade factor` (A 1.08, B 1.00, C 0.92, Below 0.80).
A dispute that changes the grade adjusts the price by the ratio of the grade factors.

## Security notes
* Role checks run on every write endpoint.
* The original photo bytes are hashed and stored, so an assessor can audit them.
* For production: phone OTP login, HTTPS, signed device attestations, and object storage for images.
