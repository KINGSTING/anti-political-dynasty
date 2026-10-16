import pandas as pd

# Load the full nationwide network
df_nodes = pd.read_csv("pulitiklan_nodes.csv")
df_edges = pd.read_csv("pulitiklan_edges.csv")

# Determine which column holds the description/status
col_desc = 'office_description' if 'office_description' in df_nodes.columns else 'Description'
col_id = 'node_id' if 'node_id' in df_nodes.columns else 'Name'

def is_incumbent(desc):
    desc_lower = str(desc).lower()
    
    # 1. Reject if they are former, dead, or just a past candidate
    if any(w in desc_lower for w in ['former', 'deceased', 'past candidate', 'historical']):
        return False
        
    # 2. Accept if the text explicitly states they are current
    if any(w in desc_lower for w in ['incumbent', 'current office']):
        return True
        
    # 3. Accept if they simply list an active title
    if any(w in desc_lower for w in ['mayor', 'governor', 'representative', 'councilor', 'board member', 'captain']):
        return True
        
    return False

# Filter Nodes
df_incumbent_nodes = df_nodes[df_nodes[col_desc].apply(is_incumbent)].copy()

# Filter Edges (Keep only connections where BOTH politicians are currently in office)
incumbent_names = set(df_incumbent_nodes[col_id])

col_a = 'person_a' if 'person_a' in df_edges.columns else 'Person_A'
col_b = 'person_b' if 'person_b' in df_edges.columns else 'Person_B'

df_incumbent_edges = df_edges[
    (df_edges[col_a].isin(incumbent_names)) & 
    (df_edges[col_b].isin(incumbent_names))
].copy()

# Export
df_incumbent_nodes.to_csv("incumbent_nodes.csv", index=False)
df_incumbent_edges.to_csv("incumbent_edges.csv", index=False)

print("Filtering Complete!")
print(f"Total Incumbent Politicians (Nodes): {len(df_incumbent_nodes)}")
print(f"Total Active Dynastic Connections (Edges): {len(df_incumbent_edges)}")