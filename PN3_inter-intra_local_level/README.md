### Known data issues (v1)

7 potential duplicate person records detected in PN3 (0.04% of 17,805 nodes):
- 3 exact-name duplicates (Homer Matias Domingo, Pete Joseph Lomugdang Rivera, Felipe Guarin Guasa)
- 4 typo variants (Gertos B/R, Panganiban JR/III, Arban o/i, Lagon e/o)

Full list: `PN3_inter-intra_local_level/data/cross_validation/duplicate_candidates.csv`

Impact: Creates ~10 spurious intra-duplicate edges. Downstream consensus
demotes them to P=0.10 (`Contradicted` level). Dashboard filters them out
by default.

Fix scheduled for v2: node-level deduplication + pipeline re-run.