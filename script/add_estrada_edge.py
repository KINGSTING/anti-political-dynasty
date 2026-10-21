import pandas as pd
import os

EDGES = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN1_national_level\data\national_edges.csv"
NODES = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN1_national_level\data\national_nodes.csv"

df_edges = pd.read_csv(EDGES, dtype=str, keep_default_na=False)
df_nodes = pd.read_csv(NODES, dtype=str, keep_default_na=False)

def find_node(first_name, last_name):
    mask = df_nodes["full_name_clean"].str.contains(first_name, case=False, na=False) & \
           df_nodes["full_name_clean"].str.contains(last_name, case=False, na=False)
    res = df_nodes[mask]
    return res.iloc[0]["person_id"] if not res.empty else None

# Find Jinggoy (Jose Pimentel Ejercito Jr) and JV (Joseph Victor Ejercito)
jinggoy = find_node("Jinggoy", "Estrada") or find_node("Jose Pimentel", "Ejercito")
jv = find_node("Joseph Victor", "Ejercito")
erap = find_node("Joseph", "Estrada") or find_node("Jose Marcelo", "Ejercito")

if jinggoy and jv:
    exists = ((df_edges["person_a_id"] == jinggoy) & (df_edges["person_b_id"] == jv)) | \
             ((df_edges["person_a_id"] == jv) & (df_edges["person_b_id"] == jinggoy))
             
    if not exists.any():
        new_edge = pd.DataFrame([{
            "edge_id": "EDGE-MANUAL-ESTRADA",
            "person_a_id": jinggoy,
            "person_b_id": jv,
            "relation_label": "Half_Sibling",
            "civil_degree": "2",
            "kinship_type": "Consanguinity",
            "source_document": "Manual_OSINT",
            "is_ground_truth": "True",
            "probability": "1.0"
        }])
        df_edges = pd.concat([df_edges, new_edge], ignore_index=True)
        df_edges.to_csv(EDGES, index=False, encoding="utf-8-sig")
        print(f"✓ Added Half_Sibling edge: Jinggoy Estrada <-> JV Ejercito")
    else:
        print("Edge already exists.")

# Also make sure Erap connects to both
if erap and jinggoy:
    new_edge = pd.DataFrame([{
        "edge_id": "EDGE-MANUAL-ERAP-JINGGOY",
        "person_a_id": erap,
        "person_b_id": jinggoy,
        "relation_label": "Parent_Child",
        "civil_degree": "1",
        "kinship_type": "Consanguinity",
        "source_document": "Manual_OSINT",
        "is_ground_truth": "True",
        "probability": "1.0"
    }])
    df_edges = pd.concat([df_edges, new_edge], ignore_index=True)

if erap and jv:
    new_edge = pd.DataFrame([{
        "edge_id": "EDGE-MANUAL-ERAP-JV",
        "person_a_id": erap,
        "person_b_id": jv,
        "relation_label": "Parent_Child",
        "civil_degree": "1",
        "kinship_type": "Consanguinity",
        "source_document": "Manual_OSINT",
        "is_ground_truth": "True",
        "probability": "1.0"
    }])
    df_edges = pd.concat([df_edges, new_edge], ignore_index=True)

df_edges = df_edges.drop_duplicates(subset=["person_a_id", "person_b_id"])
df_edges.to_csv(EDGES, index=False, encoding="utf-8-sig")
print("✓ Saved edges")