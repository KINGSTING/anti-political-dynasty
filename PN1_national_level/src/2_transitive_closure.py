import pandas as pd
import networkx as nx
import os

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN1_national_level\data"
EDGES = os.path.join(BASE, "national_edges.csv")

print("Step 2: Running transitive inference...")
df_edges = pd.read_csv(EDGES, dtype=str, keep_default_na=False)

G = nx.DiGraph()
for _, r in df_edges.iterrows():
    G.add_edge(r["person_a_id"], r["person_b_id"], label=r["relation_label"])

new_edges = []
existing_pairs = set(tuple(sorted([r["person_a_id"], r["person_b_id"]])) for _, r in df_edges.iterrows())

def add_edge(a, b, rel, degree):
    key = tuple(sorted([a, b]))
    if key not in existing_pairs:
        existing_pairs.add(key)
        new_edges.append({
            "edge_id": f"EDGE-TRANS-{len(new_edges)}",
            "person_a_id": a, "person_b_id": b,
            "relation_label": rel, "civil_degree": degree,
            "kinship_type": "Consanguinity", "source_document": "Transitive_Inference",
            "is_ground_truth": "True", "probability": "1.0"
        })

# 1. Siblings of Parents = Aunts/Uncles (Degree 3)
for node in G.nodes():
    parents = [u for u, v, data in G.in_edges(node, data=True) if any(x in data["label"] for x in ["Parent", "Father", "Mother"])]
    for p in parents:
        siblings = [v for u, v, data in G.out_edges(p, data=True) if any(x in data["label"] for x in ["Sibling", "Brother", "Sister"])]
        siblings += [u for u, v, data in G.in_edges(p, data=True) if any(x in data["label"] for x in ["Sibling", "Brother", "Sister"])]
        for aunt_uncle in set(siblings):
            if aunt_uncle != node:
                add_edge(aunt_uncle, node, "Aunt/Uncle", "3")

# 2. Children of Siblings = Nieces/Nephews (Degree 3)
for node in G.nodes():
    siblings = [v for u, v, data in G.out_edges(node, data=True) if any(x in data["label"] for x in ["Sibling", "Brother", "Sister"])]
    siblings += [u for u, v, data in G.in_edges(node, data=True) if any(x in data["label"] for x in ["Sibling", "Brother", "Sister"])]
    for s in set(siblings):
        children = [v for u, v, data in G.out_edges(s, data=True) if any(x in data["label"] for x in ["Son", "Daughter", "Child"])]
        for nephew in set(children):
            if nephew != node:
                add_edge(node, nephew, "Nephew/Niece", "3")

# 3. Children of Aunts/Uncles = First Cousins (Degree 4)
for node in G.nodes():
    aunts_uncles = [v for u, v, data in G.out_edges(node, data=True) if "Aunt" in data["label"] or "Uncle" in data["label"]]
    aunts_uncles += [u for u, v, data in G.in_edges(node, data=True) if "Aunt" in data["label"] or "Uncle" in data["label"]]
    for au in set(aunts_uncles):
        cousins = [v for u, v, data in G.out_edges(au, data=True) if any(x in data["label"] for x in ["Son", "Daughter", "Child"])]
        for cousin in set(cousins):
            if cousin != node:
                add_edge(node, cousin, "First_Cousin", "4")

if new_edges:
    df_new = pd.DataFrame(new_edges)
    df_final = pd.concat([df_edges, df_new], ignore_index=True)
    df_final.to_csv(EDGES, index=False, encoding="utf-8-sig")
    print(f"✓ Added {len(new_edges)} transitive edges (Aunts, Uncles, Cousins).")
else:
    print("No new transitive edges found.")