import os
import csv
import json
from openai import OpenAI
from pypdf import PdfReader

# Initialize standard OpenAI client pointing to local Ollama instance (Qwen 2.5 7B)
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

def extract_edges_from_text(page_text: str, page_num: int) -> list:
    """Sends page text to local model and parses strict CSV-like rows for edges."""
    
    system_prompt = (
        "You are an expert data extraction assistant building a relational database of political dynasties "
        "in the Philippines. Your task is to extract all relational edges (familial/kinship ties) from the provided text. "
        "You must output ONLY valid JSON format containing a list of objects with these exact keys:\n"
        "1. \"person_a\"\n"
        "2. \"person_b\"\n"
        "3. \"relation_label\" (e.g., Father -> son, Spouses, Uncle -> niece)\n"
        "4. \"kinship_type\" (Consanguinity or Affinity)\n"
        "5. \"civil_degree\" (1st degree, 2nd degree, 3rd degree, 4th degree, or Unknown)\n\n"
        "If no relationships are present on the page, return an empty JSON list: []\n"
        "Do not include conversational filler, markdown code blocks outside of JSON, or explanations. Output pure JSON."
    )

    try:
        response = client.chat.completions.create(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract edges from page {page_num} text:\n\n{page_text}"}
            ],
            temperature=0.0,  # Zero temperature for deterministic reproducibility
            seed=42
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean up potential markdown formatting if the model wraps JSON in code blocks
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        edges_data = json.loads(content)
        return edges_data if isinstance(edges_data, list) else []

    except Exception as e:
        print(f"Error processing page {page_num}: {e}")
        return []

def run_full_pipeline():
    pdf_path = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\data\CSP-65-STATISTICAL-INVENTORY-OF-POTENTIAL-POLITICAL-DYNASTS.pdf"
    output_csv = "political_dynasties_edges.csv"

    if not os.path.exists(pdf_path):
        print(f"Error: Could not find PDF at {pdf_path}")
        return

    print(f"Loading PDF: {pdf_path}")
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    print(f"Total pages to scan: {total_pages}")

    # Prepare CSV file headers
    csv_headers = ["page_num", "person_a", "person_b", "relation_label", "kinship_type", "civil_degree"]
    
    with open(output_csv, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=csv_headers)
        writer.writeheader()

        # Iterate through all pages in the document
        for index, page in enumerate(reader.pages):
            page_num = index + 1
            page_text = page.extract_text()

            if not page_text or len(page_text.strip()) < 30:
                continue  # Skip blank or image-only cover/map pages

            print(f"Processing Page {page_num}/{total_pages} on RTX 4090...")
            edges = extract_edges_from_text(page_text, page_num)

            if edges:
                for edge in edges:
                    row = {
                        "page_num": page_num,
                        "person_a": edge.get("person_a", "").strip(),
                        "person_b": edge.get("person_b", "").strip(),
                        "relation_label": edge.get("relation_label", "").strip(),
                        "kinship_type": edge.get("kinship_type", "").strip(),
                        "civil_degree": edge.get("civil_degree", "").strip(),
                    }
                    writer.writerow(row)
                print(f" -> Successfully recorded {len(edges)} relationship edges from page {page_num}.")

    print(f"\nPipeline Complete! All extracted edges saved to {output_csv}")

if __name__ == "__main__":
    run_full_pipeline()