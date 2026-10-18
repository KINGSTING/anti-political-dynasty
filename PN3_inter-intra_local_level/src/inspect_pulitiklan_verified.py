"""PN3_inter-intra_local_level/src/inspect_pulitiklan_verified.py"""

import pandas as pd

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"
CV = f"{BASE}\\PN3_inter-intra_local_level\\data\\cross_validation\\PN3_pulitiklan_cross_validation.csv"
NODES = f"{BASE}\\PN3_inter-intra_local_level\\data\\inter-intra_local_nodes.csv"
PSGC = f"{BASE}\\PSGC-3Q-2026-Publication-Datafile.xlsx"

nodes = pd.read_csv(NODES, dtype={"home_psgc": str}, keep_default_na=False)
nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
id2name = dict(zip(nodes["person_id"], nodes["full_name_clean"]))
id2psgc = dict(zip(nodes["person_id"], nodes["home_psgc"]))

# PSGC → LGU name
xls = pd.ExcelFile(PSGC)
df = pd.read_excel(xls, sheet_name="PSGC")
df.columns = [str(c).strip() for c in df.columns]
code_col = next(c for c in df.columns if "10-DIGIT" in c.upper() or "PSGC" in c.upper())
name_col = next(c for c in df.columns if "NAME" in c.upper())
psgc2name = {}
for _, r in df.iterrows():
    raw = str(r[code_col]).strip() if pd.notna(r[code_col]) else ""
    if raw.endswith(".0"): raw = raw[:-2]
    psgc2name[raw.zfill(10)] = str(r[name_col]).strip()

edges = pd.read_csv(CV, dtype=str, keep_default_na=False)

for verdict in ["verified_explicit", "contradicted"]:
    sub = edges[edges["pulitiklan_verdict"] == verdict]
    print(f"\n{'=' * 78}")
    print(f"  {verdict.upper()}  ({len(sub)} edges)")
    print('=' * 78)
    for _, e in sub.iterrows():
        a, b = e["person_a_id"], e["person_b_id"]
        psgc_a = id2psgc.get(a, "")
        psgc_b = id2psgc.get(b, "")
        lgu_a = psgc2name.get(psgc_a, psgc_a)
        lgu_b = psgc2name.get(psgc_b, psgc_b)
        same_lgu = "✅ same LGU" if psgc_a == psgc_b else f"{lgu_a} ↔ {lgu_b}"
        rel = e.get("relation_label", "?")
        prob = e.get("probability", "?")
        print(f"  [{rel:<20}] P={prob:<5}  {id2name.get(a, '?')}")
        print(f"                                ↔ {id2name.get(b, '?')}")
        print(f"                                ({same_lgu})")
        print()