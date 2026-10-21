import pandas as pd
import os

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN1_national_level\data"
EDGES = os.path.join(BASE, "national_edges.csv")
OUT_FINAL = os.path.join(BASE, "national_edges_FINAL.csv")

print("Step 4: Running final consensus and cleanup...")
df = pd.read_csv(EDGES, dtype=str, keep_default_na=False)

# Fix empty columns from original file
if "probability" not in df.columns:
    df["probability"] = "1.0"
df["probability"] = df["probability"].replace("", "1.0") 
    
if "is_ground_truth" not in df.columns:
    df["is_ground_truth"] = "True"
df["is_ground_truth"] = df["is_ground_truth"].replace("", "True")

# Deduplicate reciprocal pairs
df["pair_key"] = df.apply(lambda r: tuple(sorted([r["person_a_id"], r["person_b_id"]])), axis=1)
df["_gt"] = df["is_ground_truth"].astype(str).str.lower() == "true"
df["_prob"] = pd.to_numeric(df["probability"], errors="coerce").fillna(1.0)

df = (df.sort_values(by=["_gt", "_prob"], ascending=[False, False])
        .drop_duplicates(subset=["pair_key"], keep="first")
        .drop(columns=["pair_key", "_gt", "_prob"])
        .reset_index(drop=True))

# Assign consensus levels
def get_consensus(row):
    if row.get("source_document") == "Manual_Correction":
        return "Verified_Kinship"
    if str(row.get("is_ground_truth", "")).lower() == "true":
        return "Rule_Based_GT"
    
    prob = pd.to_numeric(row.get("probability", 0), errors="coerce")
    if pd.notna(prob) and float(prob) >= 0.85:
        return "Consensus_High"
    return "Low_Confidence"

df["consensus_level"] = df.apply(get_consensus, axis=1)
df["edge_id"] = [f"EDGE-{i+1:06d}" for i in range(len(df))]

# Ensure schema
cols = ["edge_id", "person_a_id", "person_b_id", "relation_label", "civil_degree", 
        "kinship_type", "consensus_level", "probability", "is_ground_truth", "source_document"]
for c in cols:
    if c not in df.columns: df[c] = ""

df[cols].to_csv(OUT_FINAL, index=False, encoding="utf-8-sig")
print(f"✓ Final PN1 edge file saved: {OUT_FINAL}")
print(f"  Total edges: {len(df)}")
print(df["consensus_level"].value_counts().to_string())