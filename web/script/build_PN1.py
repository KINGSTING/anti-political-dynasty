import os
import json
import pandas as pd

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"
WEB_DATA = os.path.join(BASE, "web", "data")

def build_pn1():
    nodes_csv = os.path.join(BASE, "PN1_national_level", "data", "national_nodes.csv")
    if not os.path.exists(nodes_csv): return
    df = pd.read_csv(nodes_csv, dtype=str, keep_default_na=False)
    
    lookup = {}
    for _, r in df.iterrows():
        pid = r["person_id"]
        
        if pid == "POL-PH-000001":
            lookup[pid] = {"position_type": "President", "raw_position": "President", "level": "national"}
        elif pid == "POL-PH-000002":
            lookup[pid] = {"position_type": "Vice_President", "raw_position": "Vice President", "level": "national"}
        # The exact 23 Senators in your dataset (IDs 3-26, excluding 16)
        elif pid in [
            "POL-PH-000003", "POL-PH-000004", "POL-PH-000005", "POL-PH-000006",
            "POL-PH-000007", "POL-PH-000008", "POL-PH-000009", "POL-PH-000010",
            "POL-PH-000011", "POL-PH-000012", "POL-PH-000013", "POL-PH-000014",
            "POL-PH-000015", "POL-PH-000017", "POL-PH-000018", "POL-PH-000019",
            "POL-PH-000020", "POL-PH-000021", "POL-PH-000022", "POL-PH-000023",
            "POL-PH-000024", "POL-PH-000025", "POL-PH-000026"
        ]:
            lookup[pid] = {"position_type": "Senator", "raw_position": "Senator", "level": "national"}
        else:
            lookup[pid] = {"position_type": "HOR_Member", "raw_position": "Congressman", "level": "national"}

    out = os.path.join(WEB_DATA, "PN1_positions.json")
    with open(out, "w", encoding="utf-8") as f: json.dump(lookup, f, ensure_ascii=False)
    
    from collections import Counter
    counts = Counter(v["position_type"] for v in lookup.values())
    print(f"✓ PN1: {len(lookup)} positions mapped")
    for k, v in counts.items(): print(f"   - {k}: {v}")

if __name__ == "__main__":
    print("Building positions...")
    build_pn1()