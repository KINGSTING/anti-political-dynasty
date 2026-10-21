import pandas as pd
import os

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN1_national_level\data"
EDGES = os.path.join(BASE, "national_edges.csv")

print("Step 1: Fixing manual edges...")
df = pd.read_csv(EDGES, dtype=str, keep_default_na=False)

# 1. Remove the wrong edge (Jocelyn mapped as Raffy's wife)
df = df[df["edge_id"] != "EDGE-000041"]

new_edges = [
    # Sandro Marcos <-> Martin Romualdez (First Cousin Once Removed)
    {"edge_id": "EDGE-MAN-01", "person_a_id": "POL-PH-000215", "person_b_id": "POL-PH-000266", "relation_label": "First_Cousin_Once_Removed", "civil_degree": "4", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
    {"edge_id": "EDGE-MAN-02", "person_a_id": "POL-PH-000266", "person_b_id": "POL-PH-000215", "relation_label": "First_Cousin_Once_Removed", "civil_degree": "4", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
    # Jocelyn Tulfo is Sister to Raffy and Erwin
    {"edge_id": "EDGE-MAN-03", "person_a_id": "POL-PH-000310", "person_b_id": "POL-PH-000022", "relation_label": "Sister", "civil_degree": "2", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
    {"edge_id": "EDGE-MAN-04", "person_a_id": "POL-PH-000022", "person_b_id": "POL-PH-000310", "relation_label": "Brother", "civil_degree": "2", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
    {"edge_id": "EDGE-MAN-05", "person_a_id": "POL-PH-000310", "person_b_id": "POL-PH-000021", "relation_label": "Sister", "civil_degree": "2", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
    {"edge_id": "EDGE-MAN-06", "person_a_id": "POL-PH-000021", "person_b_id": "POL-PH-000310", "relation_label": "Brother", "civil_degree": "2", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
    # Jocelyn is Aunt of Raffy Jr
    {"edge_id": "EDGE-MAN-07", "person_a_id": "POL-PH-000310", "person_b_id": "POL-PH-000311", "relation_label": "Aunt", "civil_degree": "3", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
    {"edge_id": "EDGE-MAN-08", "person_a_id": "POL-PH-000311", "person_b_id": "POL-PH-000310", "relation_label": "Nephew", "civil_degree": "3", "kinship_type": "Consanguinity", "source_document": "Manual_Correction", "is_ground_truth": "True", "probability": "1.0"},
]

df = pd.concat([df, pd.DataFrame(new_edges)], ignore_index=True)
df = df.drop_duplicates(subset=["person_a_id", "person_b_id"])
df.to_csv(EDGES, index=False, encoding="utf-8-sig")
print(f"✓ Saved. Total edges now: {len(df)}")