import os
import json
import pandas as pd
from openai import OpenAI

# Initialize standard OpenAI client pointing to local Ollama instance (Qwen 2.5 7B)
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

def extract_nodes_from_batch(rows_text: str) -> list:
    """Sends a batch of text/rows to GWEN (Qwen 2.5 7B) to extract provincial board member nodes."""
    system_prompt = (
        "You are an expert data extraction assistant building a network graph of provincial officials.\n"
        "Your task is to extract all Sangguniang Panlalawigan Members / Provincial Board Members from the provided text data.\n\n"
        "CRITICAL INSTRUCTION: Do NOT extract Sangguniang Bayan (municipal) or Sangguniang Panlungsod (city) members.\n\n"
        "Output ONLY a valid JSON array containing objects with these exact keys:\n"
        "1. \"name\": Full name formatted as 'First Middle Last Suffix' (e.g., 'Robert Tabada Poculan Jr.')\n"
        "2. \"position\": Position held (e.g., 'Sangguniang Panlalawigan Member' or 'Provincial Board Member')\n"
        "3. \"location\": Province name (e.g., 'Zamboanga del Norte')\n\n"
        "If no Sangguniang Panlalawigan members are found in the batch, return an empty list: []\n"
        "Do not include markdown headers, conversational filler, or explanations. Return strictly valid JSON."
    )

    try:
        response = client.chat.completions.create(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract Sangguniang Panlalawigan board member nodes from these records:\n\n{rows_text}"}
            ],
            temperature=0.0,
            seed=42
        )

        content = response.choices[0].message.content.strip()

        # Remove potential markdown code block wrappers
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        nodes = json.loads(content)
        return nodes if isinstance(nodes, list) else []

    except Exception as e:
        print(f"Error processing batch: {e}")
        return []

def run_excel_extraction_pipeline():
    excel_path = "Provincial_incumbents.xlsx"
    output_csv = "board_members_nodes.csv"
    batch_size = 30  # Adjust batch size for context length and speed

    if not os.path.exists(excel_path):
        print(f"Error: Could not find Excel file at {excel_path}")
        return

    print(f"Loading Excel file: {excel_path}")
    df = pd.read_excel(excel_path)
    print(f"Total rows in Excel: {len(df)}")

    # Strict filtering for Sangguniang Panlalawigan / Provincial Board Members
    pos_series = df['Position'].astype(str)
    
    # Keep rows mentioning Panlalawigan / Board Member, but explicitly exclude Bayan / Panlungsod
    is_provincial = pos_series.str.contains(r'PANLALAWIGAN|PROVINCIAL BOARD|BOARD MEMBER', case=False, na=False)
    is_not_municipal_or_city = ~pos_series.str.contains(r'BAYAN|PANLUNGSOD', case=False, na=False)

    board_df = df[is_provincial & is_not_municipal_or_city].copy()
    print(f"Filtered {len(board_df)} potential Sangguniang Panlalawigan member entries to process.")

    all_nodes = []
    seen_nodes = set()

    # Process in chunks
    for i in range(0, len(board_df), batch_size):
        chunk = board_df.iloc[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(board_df) + batch_size - 1) // batch_size

        # Format rows into clean text lines for GWEN
        text_lines = []
        for _, row in chunk.iterrows():
            f_name = str(row.get('First Name', '')).strip()
            m_name = str(row.get('Middle Name', '')).strip()
            l_name = str(row.get('Last Name', '')).strip()
            suffix = str(row.get('Suffix', '')).strip()
            pos = str(row.get('Position', '')).strip()
            prov = str(row.get('Province', '')).strip()
            muni = str(row.get('City/Municipality', '')).strip()

            line = f"Name: {f_name} {m_name} {l_name} {suffix} | Position: {pos} | Province: {prov} | Municipality: {muni}"
            text_lines.append(line)

        batch_text = "\n".join(text_lines)
        print(f"Processing Batch {batch_num}/{total_batches} with GWEN...")

        nodes = extract_nodes_from_batch(batch_text)

        for node in nodes:
            name = node.get("name", "").strip()
            position = node.get("position", "").strip()
            location = node.get("location", "").strip()

            if not name:
                continue

            node_key = (name.lower(), location.lower())
            if node_key not in seen_nodes:
                seen_nodes.add(node_key)
                all_nodes.append({
                    "name": name,
                    "position": position,
                    "location": location
                })

        print(f" -> Batch {batch_num} extracted {len(nodes)} nodes. (Total unique: {len(all_nodes)})")

    # Export nodes to CSV
    nodes_df = pd.DataFrame(all_nodes)
    nodes_df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nPipeline Complete! {len(nodes_df)} unique board member nodes written to {output_csv}")

if __name__ == "__main__":
    run_excel_extraction_pipeline()