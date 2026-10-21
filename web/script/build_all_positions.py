import os
import json
import re
import pandas as pd
from rapidfuzz import process, fuzz

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"
WEB_DATA = os.path.join(BASE, "web", "data")

# Hardcoded fallback for the 19th Congress (2022-2025) to guarantee accuracy
# If the text file fails, this ensures 100% of senators get hexagons.
KNOWN_SENATORS = [
    "ZUBIRI", "LEGARDA", "VILLANUEVA", "GATCHALIAN", "GO", "ESTRADA",
    "EJERCITO", "BINAY", "PIMENTEL", "CAYETANO", "PADILLA", "TULFO",
    "VILLAR", "DELA ROSA", "ESCUDERO", "MARCOS", "POE", "PACQUIAO",
    "LAPID", "PANGILINAN", "HONTIVEROS", "ANGARA"
]

def normalize(s):
    if pd.isna(s): return ""
    s = str(s).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    return " ".join(s.split())

def clean_line(line):
    # Remove (PARTY), [PARTY], numbers, and titles
    s = re.sub(r"\(.*?\)", "", line)
    s = re.sub(r"\[.*?\]", "", s)
    s = re.sub(r"[^A-Za-z\s]", " ", s) 
    s = " ".join(s.upper().split())
    s = re.sub(r"\b(SENATOR|SEN|REPRESENTATIVE|REP|CONGRESSMAN|PRESIDENT|VICE PRESIDENT)\b", "", s)
    return " ".join(s.split())

def get_name_map(nodes_csv):
    if not os.path.exists(nodes_csv): return {}, []
    df = pd.read_csv(nodes_csv, dtype=str, keep_default_na=False)
    mapping = {}
    rows = []
    for _, r in df.iterrows():
        n = normalize(r["full_name_clean"])
        if n:
            mapping[n] = r["person_id"]
            rows.append((n, r["person_id"]))
    return mapping, rows

def fuzzy_match(clean_text, node_names, threshold=80):
    if not clean_text or not node_names: return None
    
    # 1. Direct substring match
    for n in node_names:
        if clean_text in n or n in clean_text:
            return n
            
    # 2. First Name + Last Name logic (ignores middle names/initials)
    parts = clean_text.split()
    if len(parts) >= 2:
        last = parts[-1]
        for n in node_names:
            if last in n:
                # Check if ANY word from the clean text matches the node's first name
                n_parts = n.split()
                if n_parts:
                    n_first = n_parts[0]
                    if n_first in clean_text:
                        return n
                        
    # 3. Fuzzy fallback
    match = process.extractOne(clean_text, node_names, scorer=fuzz.token_set_ratio)
    if match and match[1] >= threshold:
        return match[0]
    return None

def build_pn1():
    nodes_csv = os.path.join(BASE, "PN1_national_level", "data", "national_nodes.csv")
    mapping, rows = get_name_map(nodes_csv)
    if not mapping: return
    
    lookup = {}
    node_names = list(mapping.keys())

    # 1. Manual President/VP Overrides
    for n_name, pid in rows:
        if "FERDINAND" in n_name and "MARCOS" in n_name and "ALEXANDER" not in n_name and "IMEE" not in n_name:
            lookup[pid] = {"position_type": "President", "raw_position": "President", "level": "national"}
        elif "SARA" in n_name and "DUTERTE" in n_name:
            lookup[pid] = {"position_type": "Vice_President", "raw_position": "Vice President", "level": "national"}

    # 2. Parse files
    inc_dir = os.path.join(BASE, "PN1_national_level", "data", "incumbent_list")
    files = {
        "National_executive.txt": "President",
        "Senate_members.txt": "Senator",
        "HOR_members.txt": "HOR_Member"
    }
    
    for fname, default_pos in files.items():
        path = os.path.join(inc_dir, fname)
        if not os.path.exists(path): continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                clean = clean_line(line)
                if not clean or len(clean) < 5: continue
                
                pos = default_pos
                if fname == "National_executive.txt":
                    pos = "Vice_President" if "VICE" in line.upper() else "President"
                        
                if clean in mapping:
                    pid = mapping[clean]
                    if pid not in lookup:
                        lookup[pid] = {"position_type": pos, "raw_position": pos, "level": "national"}
                else:
                    best_match = fuzzy_match(clean, node_names, threshold=75)
                    if best_match:
                        pid = mapping[best_match]
                        if pid not in lookup:
                            lookup[pid] = {"position_type": pos, "raw_position": pos, "level": "national"}

    # 3. Manual Senator Fallback
    for n_name, pid in rows:
        if pid in lookup: continue
        parts = n_name.split()
        if parts:
            last = parts[-1]
            if last in KNOWN_SENATORS:
                lookup[pid] = {"position_type": "Senator", "raw_position": "Senator", "level": "national"}

    out = os.path.join(WEB_DATA, "PN1_positions.json")
    with open(out, "w", encoding="utf-8") as f: json.dump(lookup, f, ensure_ascii=False)
    
    from collections import Counter
    counts = Counter(v["position_type"] for v in lookup.values())
    print(f"✓ PN1: {len(lookup)} positions mapped")
    for k, v in counts.items(): print(f"   - {k}: {v}")

def build_pn2():
    nodes_csv = os.path.join(BASE, "PN2_national-subnational_level", "data", "national+subnational_nodes.csv")
    mapping, rows = get_name_map(nodes_csv)
    if not mapping: return
    
    lookup = {}
    node_names = list(mapping.keys())
    inc_dir = os.path.join(BASE, "PN2_national-subnational_level", "data", "incumbent_list")
    
    csv_files = {
        "governor_list.csv": ("Province", "Governor"),
        "vice-governor_list.csv": ("Province", "Vice_Governor"),
        "city_mayors.csv": ("City", "City_Mayor"),
        "city_vice-mayors.csv": ("City", "City_Vice_Mayor")
    }
    
    for fname, (level, pos) in csv_files.items():
        path = os.path.join(inc_dir, fname)
        if not os.path.exists(path): continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        name_col = next((c for c in df.columns if "NAME" in c.upper()), None)
        if not name_col: continue
        
        for _, r in df.iterrows():
            clean = normalize(r[name_col])
            if not clean: continue
            
            if clean in mapping:
                lookup[mapping[clean]] = {"position_type": pos, "raw_position": pos, "level": level}
            else:
                best_match = fuzzy_match(clean, node_names, threshold=80)
                if best_match:
                    lookup[mapping[best_match]] = {"position_type": pos, "raw_position": pos, "level": level}

    # Merge in National positions from PN1
    pn1_out = os.path.join(WEB_DATA, "PN1_positions.json")
    if os.path.exists(pn1_out):
        with open(pn1_out, "r", encoding="utf-8") as f:
            pn1_lookup = json.load(f)
            for pid, data in pn1_lookup.items():
                if pid in mapping: lookup[pid] = data

    out = os.path.join(WEB_DATA, "PN2_positions.json")
    with open(out, "w", encoding="utf-8") as f: json.dump(lookup, f, ensure_ascii=False)
    print(f"✓ PN2: {len(lookup)} positions mapped")

if __name__ == "__main__":
    print("Building positions for all datasets...")
    build_pn1()
    build_pn2()