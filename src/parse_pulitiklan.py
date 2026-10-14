import os
import re
import pandas as pd

def parse_pulitiklan_networks(data_dir="data"):
    nodes_data = []
    edges_data = []
    seen_nodes = set()
    
    # Nodes: - **Name** — Description
    node_pattern = re.compile(r"^[-*]\s+\*\*([^*]+)\*\*\s+—\s+([^\n\r]+)", re.MULTILINE)
    
    # Edges: Person A -> Person B: Relation (Allows missing asterisks!)
    edge_pattern = re.compile(
        r"^[-*]?\s*([^\n\r:]+?)\s*(?:→|->)\s*([^\n\r:]+?):\s*\*?\*?([^*\n\r]+)\*?\*?", 
        re.MULTILINE
    )

    for filename in os.listdir(data_dir):
        if ("coverage" in filename.lower() or "research" in filename.lower()) and "portrait" not in filename.lower() and (filename.endswith(".txt") or filename.endswith(".md")):
            print(f"Parsing {filename}...")
            filepath = os.path.join(data_dir, filename)
            
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()

            # 1. PARSE NODES
            for name, desc in node_pattern.findall(text):
                clean_name = name.strip()
                if clean_name not in seen_nodes:
                    seen_nodes.add(clean_name)

                    office = desc.split(".")[0].strip()
                    
                    status = "Historical / Unspecified"
                    desc_lower = desc.lower()
                    if "current office" in desc_lower or "incumbent" in desc_lower:
                        status = "Incumbent"
                    elif "former" in desc_lower or "past candidate" in desc_lower:
                        status = "Historical"
                        
                    nodes_data.append({
                        "node_id": clean_name,
                        "office_description": office,
                        "status": status
                    })

            # 2. PARSE EDGES
            for p1, p2, relation in edge_pattern.findall(text):
                person_a = re.sub(r"^[-*]\s*", "", p1).strip()
                person_b = p2.strip()
                relation_clean = relation.strip()
                rel_lower = relation_clean.lower()

                # Automatically add nodes if they weren't explicitly profiled
                for p in [person_a, person_b]:
                    if p not in seen_nodes:
                        seen_nodes.add(p)
                        nodes_data.append({
                            "node_id": p,
                            "office_description": "Unspecified / Inferred",
                            "status": "Inferred from Edge"
                        })

                # -- LEGAL KINSHIP MAPPING --
                rel_type = "Consanguinity"
                degree = None

                # Affinity
                if any(w in rel_lower for w in ["married", "spouses", "wife", "husband"]):
                    rel_type = "Affinity"
                    degree = 1
                elif "in-law" in rel_lower:
                    rel_type = "Affinity"
                    if any(w in rel_lower for w in ["father", "mother", "son", "daughter"]):
                        degree = 1
                    elif any(w in rel_lower for w in ["brother", "sister", "sibling"]):
                        degree = 2

                # Consanguinity
                elif any(w in rel_lower for w in ["father", "mother", "son", "daughter", "parent"]):
                    if degree is None:
                        rel_type = "Consanguinity"
                        degree = 1
                elif any(w in rel_lower for w in ["brother", "sister", "sibling", "twins", "half-"]):
                    if degree is None:
                        rel_type = "Consanguinity"
                        degree = 2
                elif any(w in rel_lower for w in ["grandfather", "grandmother", "grandson", "granddaughter"]):
                    rel_type = "Consanguinity"
                    degree = 2
                elif any(w in rel_lower for w in ["uncle", "aunt", "nephew", "niece"]):
                    rel_type = "Consanguinity"
                    degree = 3
                elif "second cousin" in rel_lower:
                    rel_type = "Consanguinity"
                    degree = 6
                elif "cousin" in rel_lower:
                    rel_type = "Consanguinity"
                    degree = 4
                else:
                    rel_type = "Consanguinity"
                    degree = 99

                edges_data.append({
                    "person_a": person_a,
                    "person_b": person_b,
                    "relation_label": relation_clean,
                    "kinship_type": rel_type,
                    "civil_degree": degree
                })

    df_nodes = pd.DataFrame(nodes_data)
    df_edges = pd.DataFrame(edges_data)

    df_nodes.to_csv("pulitiklan_nodes.csv", index=False)
    df_edges.to_csv("pulitiklan_edges.csv", index=False)

    print("\nExtraction Complete!")
    print(f"Total Nodes: {len(df_nodes)}")
    print(f"Total Edges: {len(df_edges)}")
    print("Exported to: pulitiklan_nodes.csv and pulitiklan_edges.csv")

if __name__ == "__main__":
    parse_pulitiklan_networks(data_dir="data")