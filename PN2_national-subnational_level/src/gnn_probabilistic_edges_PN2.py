import pandas as pd

# 1. File Paths
GT_FILE = r"PN2_national-subnational_level\data\national+subnational_edges.csv"
GNN_FILE = r"gnn_probabilistic_edges.csv"
OUTPUT_FILE = (
    r"PN2_national-subnational_level\data\national+subnational_edges_merged.csv"
)

# 2. Load Datasets
gt_df = pd.read_csv(GT_FILE)
gnn_df = pd.read_csv(GNN_FILE)

# Clean IDs
gt_df['person_a_id'] = gt_df['person_a_id'].astype(str).str.strip()
gt_df['person_b_id'] = gt_df['person_b_id'].astype(str).str.strip()
gnn_df['person_a_id'] = gnn_df['person_a_id'].astype(str).str.strip()
gnn_df['person_b_id'] = gnn_df['person_b_id'].astype(str).str.strip()

# 3. Format Ground-Truth Baseline (Verified Anchors)
gt_df['is_ground_truth'] = True
if 'probability' not in gt_df.columns:
    gt_df['probability'] = 1.00

# 4. Filter High-Confidence GNN Predictions (e.g., P >= 0.85)
CONFIDENCE_THRESHOLD = 0.85
gnn_filtered = gnn_df[gnn_df['probability'] >= CONFIDENCE_THRESHOLD].copy()
gnn_filtered['is_ground_truth'] = False

if 'source_document' not in gnn_filtered.columns:
    gnn_filtered['source_document'] = 'GNN_Inferred_Kinship'

# 5. Prevent Duplicates (Remove predictions that match existing ground-truth edges)
gt_keys = set(
    tuple(sorted([a, b]))
    for a, b in zip(gt_df['person_a_id'], gt_df['person_b_id'])
)

gnn_filtered['edge_key'] = [
    tuple(sorted([a, b]))
    for a, b in zip(gnn_filtered['person_a_id'], gnn_filtered['person_b_id'])
]
gnn_filtered = gnn_filtered[~gnn_filtered['edge_key'].isin(gt_keys)]
gnn_filtered.drop(columns=['edge_key'], inplace=True)

# 6. Combine Ground Truth & Inferred Edges
merged_df = pd.concat([gt_df, gnn_filtered], ignore_index=True)
merged_df.to_csv(OUTPUT_FILE, index=False)

print("=== NATIONAL + SUBNATIONAL EDGE MERGE COMPLETE ===")
print(f"Verified Ground-Truth Edges (National / Top Tier) : {len(gt_df)}")
print(
    f"Inferred GNN Kinship Edges (P >= {CONFIDENCE_THRESHOLD})        : {len(gnn_filtered)}"
)
print(f"Total Unified Graph Edges                          : {len(merged_df)}")