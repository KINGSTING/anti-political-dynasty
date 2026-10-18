"""Find potential duplicate person_id records — same LGU + similar names."""

import pandas as pd
from rapidfuzz.distance import JaroWinkler

NODES = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_nodes.csv"
OUT   = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\cross_validation\duplicate_candidates.csv"

print(f"Loading nodes: {NODES}")
nodes = pd.read_csv(NODES, dtype=str, keep_default_na=False)
nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
print(f"  {len(nodes)} nodes")

# Block by (LGU, first letter of last name) to keep pair comparisons manageable
nodes["_block"] = (
    nodes["home_psgc"] + "_" +
    nodes["last_name"].str[:1].str.upper()
)

dupes = []
blocks = nodes.groupby("_block")
print(f"Scanning {len(blocks)} blocks...")

for key, grp in blocks:
    if len(grp) < 2:
        continue
    if not key.split("_", 1)[1]:  # skip empty surname-initial blocks
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

    print("=== Top 30 by similarity ===")
    top = df.sort_values("similarity", ascending=False).head(30)
    print(top.to_string(index=False))

    # Breakdown by similarity + same-middle flag
    print(f"\n=== Summary ===")
    print(f"  Similarity >= 0.98 (near-certain dupes): {(df['similarity'] >= 0.98).sum()}")
    print(f"  Similarity 0.95-0.98 (strong dupes):     {((df['similarity'] >= 0.95) & (df['similarity'] < 0.98)).sum()}")
    print(f"  Similarity 0.92-0.95 (candidate dupes):  {((df['similarity'] >= 0.92) & (df['similarity'] < 0.95)).sum()}")
    print(f"  Same middle name + similar full name:    {(df['similarity'] >= 0.92).sum() if 'same_middle' not in df.columns else (df['same_middle']).sum()}")
else:
    print("No potential duplicates found.")