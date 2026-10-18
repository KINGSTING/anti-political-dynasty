import pandas as pd

FINAL_CSV = (
    r"PN2_national-subnational_level\data\national+subnational_edges_FINAL.csv"
)
GT_CSV = (
    r"PN2_national-subnational_level\data\national+subnational_edges_FINAL_gt.csv"
)
AUDIT_CSV = (
    r"PN2_national-subnational_level\data\national+subnational_edges_FINAL_audit.csv"
)

df = pd.read_csv(FINAL_CSV, dtype=str, keep_default_na=False)
print(f"Loaded FINAL edges: {len(df)} rows")

# Canonical undirected node-pair key
df["pair_key"] = df.apply(
    lambda r: tuple(
        sorted([str(r["person_a_id"]).strip(), str(r["person_b_id"]).strip()])
    ),
    axis=1,
)

dupes = df[df["pair_key"].duplicated(keep=False)]
print(f"Found {len(dupes)} rows representing reciprocal/duplicate node pairs.")

# Prioritize Ground Truth, then highest probability, then signal count
df["_gt_num"] = df["is_ground_truth"].astype(str).str.lower() == "true"
df["_prob_num"] = pd.to_numeric(df["probability"], errors="coerce").fillna(0)
df["_signal_num"] = pd.to_numeric(
    df["signal_count"], errors="coerce"
).fillna(0)

df_clean = (
    df.sort_values(
        by=["_gt_num", "_prob_num", "_signal_num"],
        ascending=[False, False, False],
    )
    .drop_duplicates(subset=["pair_key"], keep="first")
    .drop(columns=["pair_key", "_gt_num", "_prob_num", "_signal_num"])
    .reset_index(drop=True)
)

# Re-index edge IDs sequentially
df_clean["edge_id"] = [f"EDGE-{i+1:06d}" for i in range(len(df_clean))]

print(f"Deduplicated: {len(df)} -> {len(df_clean)} rows")

# Overwrite output files
df_clean.to_csv(FINAL_CSV, index=False)

gt_clean = df_clean[
    df_clean["is_ground_truth"].astype(str).str.lower() == "true"
]
gt_clean.to_csv(GT_CSV, index=False)

audit_clean = df_clean[
    df_clean["consensus_level"].isin(["Low_Confidence", "Contradicted"])
]
audit_clean.to_csv(AUDIT_CSV, index=False)

print(f"✅ Saved cleaned FINAL: {len(df_clean)} rows -> {FINAL_CSV}")
print(f"✅ Saved cleaned GT subset: {len(gt_clean)} rows -> {GT_CSV}")
print(f"✅ Saved cleaned Audit subset: {len(audit_clean)} rows -> {AUDIT_CSV}")