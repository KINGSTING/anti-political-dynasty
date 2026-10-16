import os
import pandas as pd

def extract_politicians():
    edges_csv = "political_dynasties_edges.csv"
    output_txt = "politician_nodes_list.txt"
    output_csv = "politician_nodes.csv"

    if not os.path.exists(edges_csv):
        print(f"Error: Could not find {edges_csv}")
        return

    print("1. Loading political_dynasties_edges.csv...")
    df = pd.read_csv(edges_csv)

    # Check for column naming variations (person_a vs Person_A)
    col_a = 'person_a' if 'person_a' in df.columns else 'Person_A'
    col_b = 'person_b' if 'person_b' in df.columns else 'Person_B'

    # Extract all unique names from both columns, stripping whitespace and removing duplicates
    politicians = set(df[col_a].dropna().astype(str).str.strip())
    politicians.update(df[col_b].dropna().astype(str).str.strip())

    # Sort alphabetically
    politicians_list = sorted(list(politicians))

    print(f"Total unique politicians found: {len(politicians_list)}")

    # Save to a plain text file (one name per line)
    with open(output_txt, "w", encoding="utf-8") as f:
        for name in politicians_list:
            f.write(f"{name}\n")

    # Also save as a clean nodes CSV file
    df_nodes = pd.DataFrame({"node_id": politicians_list})
    df_nodes.to_csv(output_csv, index=False)

    print(f"\n✅ Done! Successfully exported the list to {output_txt} and {output_csv}")

if __name__ == "__main__":
    extract_politicians()