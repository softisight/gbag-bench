# SEALED — test set of the v0.5 verifying judge

Do not open the `.jsonl` files in this folder until the v0.5 judge is frozen
(PROTOCOL_v0.4.md, deviation D12). They are model answers that nobody has read: that is
the only thing that makes them a test.

- Drawn on 2026-09-25 by `scripts/draw_sealed_test_set.py`, before any v0.5 design work.
- Their SHA-256 fingerprints are recorded in PROTOCOL_v0.4.md (D12). A file whose
  fingerprint no longer matches is no longer the test set.
- Arbitration happens after the judge is frozen, with the same rules as the reserve (D9):
  proof by SQL for every condemnation, blind to every judge output, `disputed` excluded.
