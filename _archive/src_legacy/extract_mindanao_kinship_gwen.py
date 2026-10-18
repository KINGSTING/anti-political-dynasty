import os
import re
import csv
import json
from openai import OpenAI
from pypdf import PdfReader

# Initialize standard OpenAI client pointing to local Ollama instance (Qwen 2.5 7B)
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# List of Mindanao provinces/regions to filter relevant SERB narrative pages
MINDANAO_KEYWORDS = [
    "MINDANAO", "ZAMBOANGA", "BUKIDNON", "CAMIGUIN", "LANAO", "MISAMIS",
    "DAVAO", "COTABATO", "SARANGANI", "SULTAN KUDARAT", "AGUSAN", "SURIGAO",
    "DINAGAT", "BASILAN", "SULU", "TAWI-TAWI", "MAGUINDANAO", "BARMM",
    "REGION IX", "REGION X", "REGION XI", "REGION XII", "REGION XIII"
]

def is_mindanao_page(page_text: str) -> bool:
    """Checks if the page text mentions any Mindanao province or region."""
    text_upper = page_text.upper()
    return any(keyword in text_upper for keyword in MINDANAO_KEYWORDS)

def extract_nodes_and_edges(page_text: str, page_num: int) -> dict:
    """
    Sends narrative text to Qwen 2.5 7B to extract structured nodes and kinship edges.
    Returns a dict containing 'nodes' and 'edges'.
    """
    system_prompt = (
        "You are an expert political data analyst extracting political dynasty networks from Philippine SERB narrative reports.\n"
        "Your task is to identify all political figures (nodes) and their kinship ties (edges) for Mindanao regions.\n\n"
        "Return ONLY a pure JSON object with two keys:\n"
        "1. \"nodes\": A list of objects with fields:\n"
        "   - \"name\": Full Name (e.g., \"Rodrigo Duterte\")\n"
        "   - \"province_region\": Province or Region name in Mindanao\n"
        "   - \"office\": Political office/position held (or \"Unknown\" if unspecified)\n"
        "2. \"edges\": A list of objects with fields:\n"
        "   - \"person_a\": Name of Person A\n"
        "   - \"person_b\": Name of Person B\n"
        "   - \"relation_label\": Relationship (e.g., \"Father -> son\", \"Spouses\", \"Uncle -> niece\", \"Siblings\")\n"
        "   - \"kinship_type\": \"Consanguinity\" or \"Affinity\"\n"
        "   - \"civil_degree\": \"1st degree\", \"2nd degree\", \"3rd degree\", \"4th degree\", or \"Unknown\"\n\n"
        "If no relationships are present, return {\"nodes\": [], \"edges\": []}.\n"
        "Do not include code block syntax outside JSON or conversational filler. Output raw valid JSON only."
    )

    try:
        response = client.chat.completions.create(
            model="qwen2.5:7b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract Mindanao nodes and kinship edges from SERB Page {page_num}:\n\n{page_text}"}
            ],
            temperature=0.0,
            seed=42
        )

        content = response.choices[0].message.content.strip()

        # Clean markdown code block wrappings if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)
        return {
            "nodes": data.get("nodes", []),
            "edges": data.get("edges", [])
        }

    except Exception as e:
        print(f"  [!] Error parsing JSON from Qwen on Page {page_num}: {e}")
        return {"nodes": [], "edges": []}

def run_mindanao_extraction():
    pdf_filename = "data/CSP-65-STATISTICAL-INVENTORY-OF-POTENTIAL-POLITICAL-DYNASTS.pdf"
    pdf_path = os.path.join(os.getcwd(), pdf_filename)

    output_nodes_csv = "mindanao_kinship_nodes.csv"
    output_edges_csv = "mindanao_kinship_edges.csv"
    output_edges_txt = "mindanao_kinship_edges.txt"

    if not os.path.exists(pdf_path):
        print(f"Error: File not found at {pdf_path}")
        return

    print(f"Loading SERB Report: {pdf_path}")
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    print(f"Total PDF pages: {total_pages}")

    all_nodes = {}  # Key: normalized_name -> dict
    all_edges = []  # List of edge dicts

    # Headers
    node_headers = ["name", "province_region", "office"]
    edge_headers = ["page_num", "person_a", "person_b", "relation_label", "kinship_type", "civil_degree"]

    for index, page in enumerate(reader.pages):
        page_num = index + 1
        page_text = page.extract_text() or ""

        if len(page_text.strip()) < 40 or not is_mindanao_page(page_text):
            continue

        print(f"Processing Mindanao narrative page {page_num}/{total_pages} with Qwen 2.5 7B...")
        result = extract_nodes_and_edges(page_text, page_num)

        # Aggregate Nodes
        nodes_found = result.get("nodes", [])
        for node in nodes_found:
            name = node.get("name", "").strip()
            if name:
                key = name.lower()
                if key not in all_nodes:
                    all_nodes[key] = {
                        "name": name,
                        "province_region": node.get("province_region", "").strip(),
                        "office": node.get("office", "").strip()
                    }

        # Aggregate Edges
        edges_found = result.get("edges", [])
        for edge in edges_found:
            pa = edge.get("person_a", "").strip()
            pb = edge.get("person_b", "").strip()
            if pa and pb:
                all_edges.append({
                    "page_num": page_num,
                    "person_a": pa,
                    "person_b": pb,
                    "relation_label": edge.get("relation_label", "").strip(),
                    "kinship_type": edge.get("kinship_type", "").strip(),
                    "civil_degree": edge.get("civil_degree", "").strip()
                })

        print(f"  -> Extracted {len(nodes_found)} nodes and {len(edges_found)} edges on page {page_num}.")

    # Save Nodes CSV
    with open(output_nodes_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=node_headers)
        writer.writeheader()
        for node in all_nodes.values():
            writer.writerow(node)
    print(f"\n[OK] Saved {len(all_nodes)} unique nodes to {output_nodes_csv}")

    # Save Edges CSV
    with open(output_edges_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=edge_headers)
        writer.writeheader()
        writer.writerows(all_edges)
    print(f"[OK] Saved {len(all_edges)} edges to {output_edges_csv}")

    # Save Edges formatted TXT (compatible with parse_pulitiklan.py)
    with open(output_edges_txt, mode="w", encoding="utf-8") as f:
        for e in all_edges:
            f.write(
                f"{e['person_a']} : {e['person_b']} -> {e['relation_label']} : "
                f"{e['civil_degree']} : {e['kinship_type']}  [SERB Page {e['page_num']}]\n"
            )
    print(f"[OK] Saved formatted text edges to {output_edges_txt}")

if __name__ == "__main__":
    run_mindanao_extraction()