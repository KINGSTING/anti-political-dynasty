import os
import networkx as nx
import numpy as np
import pandas as pd

# File Paths
MERGED_EDGES_FILE = r"PN2_national-subnational_level\data\national+subnational_edges_merged.csv"
NODES_FILE = (
    r"PN2_national-subnational_level\data\national+subnational_nodes.csv"
)

print("=== RUNNING GNN PROBABILISTIC KINSHIP ROBUSTNESS AUDIT ===")

# 1. Load Data
if not os.path.exists(MERGED_EDGES_FILE):
    raise FileNotFoundError(f"Missing merged edge file: {MERGED_EDGES_FILE}")
if not os.path.exists(NODES_FILE):
    raise FileNotFoundError(f"Missing node attribute file: {NODES_FILE}")

edges_df = pd.read_csv(MERGED_EDGES_FILE)
nodes_df = pd.read_csv(NODES_FILE)

# Ensure string ID formats
edges_df['person_a_id'] = edges_df['person_a_id'].astype(str).str.strip()
edges_df['person_b_id'] = edges_df['person_b_id'].astype(str).str.strip()
nodes_df['person_id'] = nodes_df['person_id'].astype(str).str.strip()

# Deduplicate Nodes
nodes_clean = nodes_df.drop_duplicates(subset=['person_id'], keep='first')
node_map = nodes_clean.set_index('person_id').to_dict('index')

# Separate Ground Truth vs GNN Inferred Edges
gt_edges = edges_df[edges_df['is_ground_truth'] == True]
inferred_edges = edges_df[edges_df['is_ground_truth'] == False]

print(f"Total Graph Edges           : {len(edges_df)}")
print(f"-> Verified Ground-Truth    : {len(gt_edges)}")
print(f"-> GNN Inferred Kinships    : {len(inferred_edges)}")

# --- HELPER RESOLUTION FUNCTIONS ---


def get_node_name(node, fallback_id=''):
    """Extracts clean full name or constructs from parts."""
    if not node:
        return fallback_id
    if 'full_name_clean' in node and pd.notna(node['full_name_clean']):
        return str(node['full_name_clean']).strip()

    parts = [
        str(node.get(c, '')).strip()
        for c in ['first_name', 'middle_name', 'last_name']
        if c in node and pd.notna(node[c])
    ]
    parts = [p for p in parts if p and p.lower() != 'nan']
    return ' '.join(parts) if parts else fallback_id


def get_psgc_code(node):
    """Formats PSGC code to a standardized 9-digit zero-padded string."""
    if not node or 'home_psgc' not in node or pd.isna(node['home_psgc']):
        return ''
    raw_val = str(node['home_psgc']).strip()
    if raw_val.endswith('.0'):
        raw_val = raw_val[:-2]
    # Pad leading zero if 8-digit string (e.g. 12800000 -> 012800000)
    return raw_val.zfill(9)


def check_surname_interlock(node_a, node_b, name_a='', name_b=''):
    """Evaluates direct consanguinity, maternal/paternal interlock, or cross-surname ties."""
    if not node_a or not node_b:
        return 'Missing Node Data'

    suffixes = {'jr', 'jr.', 'sr', 'sr.', 'iii', 'ii', 'iv', 'v'}
    common_first_names = {
        'juan',
        'maria',
        'jose',
        'mark',
        'john',
        'paul',
        'anne',
        'mary',
        'francis',
        'luis',
        'carlos',
        'david',
    }

    # Extract explicit last names and maternal maiden names
    last_a = str(node_a.get('last_name', '')).strip().lower()
    last_b = str(node_b.get('last_name', '')).strip().lower()

    maternal_a = str(node_a.get('maternal_maiden_name', '')).strip().lower()
    maternal_b = str(node_b.get('maternal_maiden_name', '')).strip().lower()

    if last_a and last_b and last_a == last_b:
        return 'Direct Last Name Match'

    if (
        (maternal_a and last_b and maternal_a == last_b)
        or (maternal_b and last_a and maternal_b == last_a)
        or (maternal_a and maternal_b and maternal_a == maternal_b)
    ):
        return 'Interlock Match (Maternal/Paternal Maiden)'

    # Token-level fallback check across full name tokens
    def get_tokens(node, resolved_name):
        combined = f"{resolved_name} {node.get('middle_name', '')}".lower()
        for char in [',', '.', '-', '/']:
            combined = combined.replace(char, ' ')
        return set(combined.split()) - suffixes

    tokens_a = get_tokens(node_a, name_a)
    tokens_b = get_tokens(node_b, name_b)
    shared = (tokens_a.intersection(tokens_b)) - common_first_names

    if len(shared) > 0:
        return 'Interlock Match (Token Overlap)'

    return 'Cross-Surname / Extended'


# --- AUDIT 1: PROBABILITY DISTRIBUTION ANALYSIS ---
probs = (
    inferred_edges['probability'].values
    if len(inferred_edges) > 0
    else np.array([1.0])
)
print("\n--- 1. INFERRED KINSHIP CONFIDENCE DISTRIBUTION ---")
if len(inferred_edges) > 0:
    print(f"Mean Probability            : {np.mean(probs):.4f}")
    print(f"Median Probability          : {np.median(probs):.4f}")
    print(f"Std Deviation               : {np.std(probs):.4f}")
    print(f"High Confidence (P >= 0.90)  : {(probs >= 0.90).sum()}")
    print(f"Strong Confidence (P >= 0.85): {len(probs)}")
else:
    print("No GNN inferred edges present.")

# --- AUDIT 2: SURNAME & DUAL-NAME INTERLOCK ALIGNMENT ---
direct_matches = 0
interlock_matches = 0
cross_surnames = 0

for _, row in inferred_edges.iterrows():
    p_a = node_map.get(row['person_a_id'], {})
    p_b = node_map.get(row['person_b_id'], {})

    name_a = get_node_name(p_a, row['person_a_id'])
    name_b = get_node_name(p_b, row['person_b_id'])

    status = check_surname_interlock(p_a, p_b, name_a, name_b)

    if status == 'Direct Last Name Match':
        direct_matches += 1
    elif 'Interlock Match' in status:
        interlock_matches += 1
    else:
        cross_surnames += 1

total_inferred = len(inferred_edges)
print("\n--- 2. SURNAME & DUAL-NAME INTERLOCK ALIGNMENT ---")
if total_inferred > 0:
    print(
        f"Direct Last Name Matches         : {direct_matches} ({direct_matches / total_inferred * 100:.2f}%)"
    )
    print(
        f"Maternal/Interlock Surname Matches: {interlock_matches} ({interlock_matches / total_inferred * 100:.2f}%)"
    )
    print(
        f"Total Kin-Aligned Matches        : {direct_matches + interlock_matches} ({(direct_matches + interlock_matches) / total_inferred * 100:.2f}%)"
    )
    print(
        f"Cross-Surname / Extended Ties    : {cross_surnames} ({cross_surnames / total_inferred * 100:.2f}%)"
    )

# --- AUDIT 3: GEOGRAPHIC LOCATION COHERENCE (PSGC-BASED) ---
same_province = 0
same_region = 0
cross_region = 0
missing_psgc = 0

for _, row in inferred_edges.iterrows():
    p_a = node_map.get(row['person_a_id'], {})
    p_b = node_map.get(row['person_b_id'], {})

    psgc_a = get_psgc_code(p_a)
    psgc_b = get_psgc_code(p_b)

    if not psgc_a or not psgc_b:
        missing_psgc += 1
        continue

    reg_a, reg_b = psgc_a[:2], psgc_b[:2]
    prov_a, prov_b = psgc_a[:4], psgc_b[:4]

    if prov_a == prov_b:
        same_province += 1
        same_region += 1
    elif reg_a == reg_b:
        same_region += 1
    else:
        cross_region += 1

valid_psgc_total = total_inferred - missing_psgc
print("\n--- 3. GEOGRAPHIC LOCATION COHERENCE (PSGC ANALYSIS) ---")
if valid_psgc_total > 0:
    print(
        f"Intra-Province Kinship Edges     : {same_province} ({same_province / valid_psgc_total * 100:.2f}%)"
    )
    print(
        f"Intra-Region Kinship Edges       : {same_region} ({same_region / valid_psgc_total * 100:.2f}%)"
    )
    print(
        f"Inter-Regional Kinship Edges     : {cross_region} ({cross_region / valid_psgc_total * 100:.2f}%)"
    )
if missing_psgc > 0:
    print(f"Nodes Missing PSGC Attributes    : {missing_psgc}")

# --- AUDIT 4: GRAPH TOPOLOGY & CLAN SIZE AUDIT ---
G = nx.Graph()
for _, row in edges_df.iterrows():
    G.add_edge(
        row['person_a_id'],
        row['person_b_id'],
        weight=row.get('probability', 1.0),
    )

components = [c for c in nx.connected_components(G)]
component_sizes = [len(c) for c in components]

print("\n--- 4. NETWORK TOPOLOGY & CLAN SIZE AUDIT ---")
print(f"Total Disjoint Dynastic Clans : {len(components)}")
print(
    f"Largest Single Clan Size      : {max(component_sizes) if component_sizes else 0} officials"
)
print(
    f"Average Clan Size             : {np.mean(component_sizes):.2f} officials"
    if component_sizes
    else "0"
)

# --- AUDIT 5: SAMPLE EXTRACTOR FOR MANUAL OSINT CHECK ---
sample_size = min(20, len(inferred_edges))
if sample_size > 0:
    sample_df = inferred_edges.sample(n=sample_size, random_state=42)

    print(
        f"\n=== 5. RANDOMIZED SAMPLE FOR MANUAL OSINT AUDIT ({sample_size} PAIRS) ==="
    )
    for _, row in sample_df.iterrows():
        p_a = node_map.get(row['person_a_id'], {})
        p_b = node_map.get(row['person_b_id'], {})

        name_a = get_node_name(p_a, row['person_a_id'])
        name_b = get_node_name(p_b, row['person_b_id'])
        psgc_code = get_psgc_code(p_a)

        interlock_status = check_surname_interlock(
            p_a, p_b, name_a, name_b
        )
        prob_val = row.get('probability', 1.0)
        rel_label = row.get('relation_label', 'Inferred')

        print(
            f"[{prob_val:.2f}] {name_a} <---> {name_b} (PSGC: {psgc_code}) | Rel: {rel_label} | Alignment: {interlock_status}"
        )