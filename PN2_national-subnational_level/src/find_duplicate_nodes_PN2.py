"""Find potential duplicate person_id records — same LGU + similar names (PN2)."""

import os
import pandas as pd
from rapidfuzz.distance import JaroWinkler

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN2_national-subnational_level\data"
NODES = os.path.join(BASE, "national+subnational_nodes.csv")
OUT_DIR = os.path.join(BASE, "cross_validation")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "duplicate_candidates.csv")

print(f"Loading nodes: {NODES}")
nodes = pd.read_csv(NODES, dtype=str, keep_default_na=False)
nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
print(f"  {len(nodes)} nodes")

nodes["_block"] = nodes["home_psgc"] + "_" + nodes["last_name"].str[:1].str.upper()

dupes = []
blocks = nodes.groupby("_block")
print(f"Scanning {len(blocks)} blocks...")

for key, grp in blocks:
    if len(grp) < 2:
        continue
    if not key.split("_", 1)[1]:
        continue
    rows = grp.to_dict("records")
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            name_a = str(a["full_name_clean"]).upper()
            name_b = str(b["full_name_clean"]).upper()
            if not name_a or not name_b:
                continue
            jw = JaroWinkler.normalized_similarity(name_a, name_b)
            if jw >= 0.92:
                dupes.append({
                    "person_a":     a["person_id"],
                    "name_a":       a["full_name_clean"],
                    "person_b":     b["person_id"],
                    "name_b":       b["full_name_clean"],
                    "similarity":   round(jw, 3),
                    "lgu":          a["home_psgc"],
                    "same_middle":  (
                        str(a.get("middle_name", "")).upper()
                        == str(b.get("middle_name", "")).upper()
                        and bool(str(a.get("middle_name", "")).strip())
                    ),
                })

df = pd.DataFrame(dupes)
print(f"\nPotential duplicate pairs: {len(df)}")

if len(df) > 0:
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"Saved to: {OUT}\n")
    print("=== Top 20 by similarity ===")
    print(df.sort_values("similarity", ascending=False).head(20).to_string(index=False))
    print(f"\n  Near-certain (>=0.98): {(df['similarity'] >= 0.98).sum()}")
    print(f"  Strong (0.95-0.98)   : {((df['similarity'] >= 0.95) & (df['similarity'] < 0.98)).sum()}")
    print(f"  Candidate (0.92-0.95): {((df['similarity'] >= 0.92) & (df['similarity'] < 0.95)).sum()}")
else:
    print("No potential duplicates found.")

print(f"Loading nodes: {NODES}")
nodes = pd.read_csv(NODES, dtype=str, keep_default_na=False)

# ✅ FIX: drop malformed rows (header artifacts) + dedupe
before = len(nodes)
nodes = nodes[nodes["person_id"].astype(str).str.startswith("POL-PH-", na=False)].copy()
nodes = nodes.drop_duplicates(subset="person_id", keep="first").reset_index(drop=True)
if len(nodes) < before:
    print(f"  Sanitized: {before} → {len(nodes)} (dropped {before - len(nodes)})")

nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
print(f"  {len(nodes)} nodes")