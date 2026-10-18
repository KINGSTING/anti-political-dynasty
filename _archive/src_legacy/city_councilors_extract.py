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
    """Sends a batch of text/rows to Qwen 2.5 7B to extract Sangguniang Panlungsod (city councilor) nodes."""
    system_prompt = (
        "You are an expert data extraction assistant building a network graph of city officials.\n"
        "Your task is to extract all Sangguniang Panlungsod Members / City Councilors from the provided text data.\n\n"
        "CRITICAL INSTRUCTION: Do NOT extract Sangguniang Bayan (municipal) or "
        "Sangguniang Panlalawigan (provincial board) members. Only extract CITY councilors "
        "(Sangguniang Panlungsod Members / City Councilors).\n\n"
        "Output ONLY a valid JSON array containing objects with these exact keys:\n"
        "1. \"name\": Full name formatted as 'First Middle Last Suffix' (e.g., 'Maria Clara Santos Reyes Jr.')\n"
        "2. \"position\": Position held (e.g., 'Sangguniang Panlungsod Member' or 'City Councilor')\n"
        "3. \"location\": City name (e.g., 'Quezon City', 'Cebu City', 'Davao City')\n\n"
        "If no Sangguniang Panlungsod members are found in the batch, return an empty list: []\n"
        "Do not include markdown headers, conversational filler, or explanations. Return strictly valid JSON."
    )

    try:
        response = client.chat.completions.create(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract Sangguniang Panlungsod / City Councilor nodes from these records:\n\n{rows_text}"}
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
    excel_path = "city_incumbents.xlsx"
    output_csv = "city_councilors_nodes.csv"
    batch_size = 30  # Adjust batch size for context length and speed

    if not os.path.exists(excel_path):
        print(f"Error: Could not find Excel file at {excel_path}")
        return

    print(f"Loading Excel file: {excel_path}")
    df = pd.read_excel(excel_path)
    print(f"Total rows in Excel: {len(df)}")

    # ---- Strict filtering for Sangguniang Panlungsod / City Councilors ----
    pos_series = df['Position'].astype(str)

    # Keep rows mentioning Panlungsod / City Councilor / City Council
    is_city = pos_series.str.contains(
        r'PANLUNGSOD|CITY COUNCILOR|CITY COUNCIL|CITY COUNCILMEMB',
        case=False, na=False
    )
    # Explicitly exclude municipal (Bayan) and provincial (Panlalawigan / Provincial Board)
    is_not_municipal = ~pos_series.str.contains(r'\bBAYAN\b', case=False, na=False)
    is_not_provincial = ~pos_series.str.contains(
        r'PANLALAWIGAN|PROVINCIAL BOARD', case=False, na=False
    )

    councilor_df = df[is_city & is_not_municipal & is_not_provincial].copy()
    print(f"Filtered {len(councilor_df)} potential Sangguniang Panlungsod member entries to process.")

    all_nodes = []
    seen_nodes = set()

    # Process in chunks
    for i in range(0, len(councilor_df), batch_size):
        chunk = councilor_df.iloc[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(councilor_df) + batch_size - 1) // batch_size

        # Format rows into clean text lines for the model
        text_lines = []
        for _, row in chunk.iterrows():
            f_name = str(row.get('First Name', '')).strip()
            m_name = str(row.get('Middle Name', '')).strip()
            l_name = str(row.get('Last Name', '')).strip()
            suffix = str(row.get('Suffix', '')).strip()
            pos = str(row.get('Position', '')).strip()
            prov = str(row.get('Province', '')).strip()
            muni = str(row.get('City/Municipality', '')).strip()

            line = (
                f"Name: {f_name} {m_name} {l_name} {suffix} | "
                f"Position: {pos} | Province: {prov} | City/Municipality: {muni}"
            )
            text_lines.append(line)

        batch_text = "\n".join(text_lines)
        print(f"Processing Batch {batch_num}/{total_batches}...")

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
                    "Name": name,
                    "Position": position,
                    "Location": location
                })

        print(f" -> Batch {batch_num} extracted {len(nodes)} nodes. "
              f"(Total unique: {len(all_nodes)})")

    # Export nodes to CSV with the requested column order: Name, Position, Location
    if all_nodes:
        nodes_df = pd.DataFrame(all_nodes, columns=["Name", "Position", "Location"])
    else:
        nodes_df = pd.DataFrame(columns=["Name", "Position", "Location"])

    nodes_df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nPipeline Complete! {len(nodes_df)} unique city councilor nodes "
          f"written to {output_csv}")


if __name__ == "__main__":
    run_excel_extraction_pipeline()