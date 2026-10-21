import pandas as pd
import re
from itertools import combinations
import os

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN1_national_level\data"
EDGES = os.path.join(BASE, "national_edges.csv")
NODES = os.path.join(BASE, "national_nodes.csv")

print("Step 3: Running probabilistic maternal-line matching...")
df_nodes = pd.read_csv(NODES, dtype=str, keep_default_na=False)
df_edges = pd.read_csv(EDGES, dtype=str, keep_default_na=False)

def norm(s):
    if pd.isna(s): return ""
    s = str(s).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    return " ".join(s.split())

df_nodes["last_clean"] = df_nodes["last_name"].apply(norm)
df_nodes["mid_clean"] = df_nodes["middle_name"].apply(norm)

existing_pairs = set(tuple(sorted([r["person_a_id"], r["person_b_id"]])) for _, r in df_edges.iterrows())
new_edges = []

# 1. Same Last Name + Same Middle Name = Sibling/Cousin
for last_name, group in df_nodes.groupby("last_clean"):
    if not last_name or len(group) < 2: continue
    
    for a, b in combinations(group.to_dict("records"), 2):
        pair = tuple(sorted([a["person_id"], b["person_id"]]))
        if pair in existing_pairs: continue
        
        if a["mid_clean"] and a["mid_clean"] == b["mid_clean"]:
            new_edges.append({
                "edge_id": f"EDGE-PROB-{len(new_edges)}",
                "person_a_id": a["person_id"], "person_b_id": b["person_id"],
                "relation_label": "Sibling_or_Cousin", "civil_degree": "2",
                "kinship_type": "Consanguinity", "source_document": "Probabilistic_NameMatch",
                "is_ground_truth": "False", "probability": "0.95"
            })
            existing_pairs.add(pair)

# 2. Maternal Interlock (A's middle == B's last)
for _, a in df_nodes.iterrows():
    for _, b in df_nodes.iterrows():
        if a["person_id"] == b["person_id"]: continue
        pair = tuple(sorted([a["person_id"], b["person_id"]]))
        if pair in existing_pairs: continue
        
        if a["mid_clean"] and a["mid_clean"] == b["last_clean"]:
            new_edges.append({
                "edge_id": f"EDGE-PROB-{len(new_edges)}",
                "person_a_id": a["person_id"], "person_b_id": b["person_id"],
                "relation_label": "Maternal_Line_Kin", "civil_degree": "4",
                "kinship_type": "Consanguinity", "source_document": "Probabilistic_MaternalInterlock",
                "is_ground_truth": "False", "probability": "0.85"
            })
            existing_pairs.add(pair)

if new_edges:
    df_new = pd.DataFrame(new_edges)
    df_final = pd.concat([df_edges, df_new], ignore_index=True)
    df_final.to_csv(EDGES, index=False, encoding="utf-8-sig")
    print(f"✓ Added {len(new_edges)} probabilistic edges.")
else:
    print("No new probabilistic edges found.")