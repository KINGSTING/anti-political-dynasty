"""
Cross-validate PN1/PN2/PN3 edges against Pulitiklan verified research (v2)
-------------------------------------------------------------------------
v1 recall was low (296/21356 = 1.4%). Root cause: matcher only extracts
2-4 word capitalized sequences, missing:
  - Surname-only mentions ("Marcos was...")
  - Family plurals ("the Aquinos", "Marcos clan")
  - Possessives ("Aquino's cousin")

v2 adds:
  - Surname index for broad mention matching (boosts verified_mentioned)
  - Family-plural detector ("the Xs", "X family", "X clan", "X dynasty")
  - Possessive stripping ("Aquino's" -> "Aquino")
  - Kinship pairs STILL require full-name match in same sentence (precision safe)
"""

import os
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"

PN1_EDGES = os.path.join(BASE, "PN1_national_level", "data", "national_edges.csv")
PN1_NODES = os.path.join(BASE, "PN1_national_level", "data", "national_nodes.csv")
PN2_EDGES = os.path.join(BASE, "PN2_national-subnational_level", "data",
                         "national+subnational_edges_merged.csv")
PN2_NODES = os.path.join(BASE, "PN2_national-subnational_level", "data",
                         "national+subnational_nodes.csv")
PN3_EDGES = os.path.join(BASE, "PN3_inter-intra_local_level", "data",
                         "inter-intra_local_edges_structurally_validated.csv")
PN3_NODES = os.path.join(BASE, "PN3_inter-intra_local_level", "data",
                         "inter-intra_local_nodes.csv")

PULITIKLAN_VISAYAS = os.path.join(BASE, "data", "# PULITIKLAN — Visayas coverage and.txt")
PULITIKLAN_LUZON   = os.path.join(BASE, "data", "luzon-research.md")

OUT_DIR = os.path.join(BASE, "PN3_inter-intra_local_level", "data", "cross_validation")
os.makedirs(OUT_DIR, exist_ok=True)

# ==================== CONFIG ====================
MINDANAO_PREFIXES = {"09", "10", "11", "12", "15", "16", "19"}

KINSHIP_KEYWORDS = [
    "father", "mother", "son", "daughter", "brother", "sister",
    "wife", "husband", "spouse", "married to", "married",
    "cousin", "uncle", "aunt", "nephew", "niece",
    "grandfather", "grandmother", "grandson", "granddaughter",
    "sibling", "siblings", "child", "children", "parent", "parents",
    "family", "relatives", "kin", "dynasty", "clan", "relative",
    "in-law", "brother-in-law", "sister-in-law",
    "father-in-law", "mother-in-law",
    "son-in-law", "daughter-in-law",
    "godson", "goddaughter",
]

# ✅ NEW: family-reference keywords (strong kinship signal)
FAMILY_REFERENCE_KEYWORDS = ["family", "dynasty", "clan", "house of", "descendants"]

CONTRADICTION_KEYWORDS = [
    "not related", "no relation", "denied", "denies", "not a relative",
    "unrelated", "not family", "not kin", "disputes",
    "not connected", "denies relation", "denied relationship",
]

SUFFIXES_TO_STRIP = {"JR", "SR", "II", "III", "IV", "V", "VI", "JR.", "SR."}

# Skip tokens that aren't real surnames (common English/place words that get capitalized)
NON_SURNAME_TOKENS = {
    "THE", "AND", "BUT", "FOR", "WITH", "FROM", "THIS", "THAT", "WHEN", "WHERE",
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
    "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
    "PHILIPPINES", "FILIPINO", "MANILA", "LUZON", "VISAYAS", "MINDANAO",
    "CONGRESS", "SENATE", "SENATOR", "CONGRESSMAN", "REPRESENTATIVE",
    "GOVERNOR", "MAYOR", "VICE", "COUNCILOR", "BARANGAY", "MUNICIPALITY",
    "PROVINCE", "CITY", "REGION", "DISTRICT",
}


# ==================== HELPERS ====================
def normalize(s):
    if pd.isna(s):
        return ""
    s = str(s).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    s = " ".join(s.split())
    s = re.sub(r"\s+(JR|SR|II|III|IV|V|VI)$", "", s).strip()
    return s


def extract_variants(full_name):
    """Generate full-name variants for precise matching."""
    if pd.isna(full_name) or not str(full_name).strip():
        return []
    s = str(full_name).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    tokens = [t for t in s.split() if t not in SUFFIXES_TO_STRIP]
    if len(tokens) < 2:
        return []
    variants = set()
    variants.add(" ".join(tokens))
    variants.add(f"{tokens[0]} {tokens[-1]}")
    variants.add(f"{tokens[-1]} {tokens[0]}")
    if len(tokens) >= 3:
        variants.add(f"{tokens[-1]} {' '.join(tokens[:-1])}")
    return list(variants)


def extract_surname(full_name):
    """Get just the surname (last token after suffix strip)."""
    parts = normalize(full_name).split()
    return parts[-1] if parts else ""


def build_name_index(nodes_df):
    """variant_string → [person_id, ...]"""
    idx = defaultdict(list)
    for _, r in nodes_df.iterrows():
        for v in extract_variants(r.get("full_name_clean", "")):
            idx[v].append(r["person_id"])
    return idx


def build_surname_index(nodes_df):
    """
    ✅ NEW: surname → [person_id, ...]
    Excludes non-surname artifacts and single-char tokens.
    """
    idx = defaultdict(list)
    for _, r in nodes_df.iterrows():
        sn = extract_surname(r.get("full_name_clean", ""))
        if len(sn) < 2:
            continue
        if sn in NON_SURNAME_TOKENS:
            continue
        idx[sn].append(r["person_id"])
    return idx


def strip_possessive(text):
    """'Aquino's' -> 'Aquino'; 'Marcoses'' -> 'Marcoses'"""
    return re.sub(r"'[sS]\b", "", text)


def extract_full_name_sequences(text):
    """Extract 2-4 word capitalized sequences (multi-word names)."""
    pattern = r"\b[A-Z][a-zA-Z'\-]+(?:\s+(?:[A-Z][a-zA-Z'\-]+|[A-Z]\.)){1,3}\b"
    sequences = set()
    for s in re.findall(pattern, text):
        s = " ".join(s.split()).upper()
        words = s.split()
        if 2 <= len(words) <= 4:
            sequences.add(s)
    return sequences


def extract_single_capitalized(text):
    """✅ NEW: extract single capitalized words (potential surnames)."""
    pattern = r"\b[A-Z][a-zA-Z'\-]{1,30}\b"
    tokens = set()
    for t in re.findall(pattern, text):
        t = t.upper().strip()
        if len(t) >= 3 and t not in NON_SURNAME_TOKENS:
            tokens.add(t)
    return tokens


def extract_family_plurals(text):
    """
    ✅ NEW: detect 'the Aquinos', 'Marcos family', 'Singson clan', 'the Marcoses'.
    Returns set of base surnames extracted from these phrases.
    """
    found = set()
    text_upper = text.upper()

    # Pattern 1: "the Xs" / "the Xes" (pluralized surname)
    for m in re.finditer(r"\bTHE\s+([A-Z][A-Z]+(?:ES|S))\b", text_upper):
        word = m.group(1)
        base = word[:-2] if word.endswith("ES") else word[:-1] if word.endswith("S") else word
        if len(base) >= 3 and base not in NON_SURNAME_TOKENS:
            found.add(base)

    # Pattern 2: "X family" / "X clan" / "X dynasty" / "X political family"
    for m in re.finditer(
        r"\b([A-Z][A-Z]+(?:-[A-Z]+)?)\s+(?:POLITICAL\s+)?(?:FAMILY|CLAN|DYNASTY)\b",
        text_upper,
    ):
        base = m.group(1)
        if len(base) >= 3 and base not in NON_SURNAME_TOKENS:
            found.add(base)

    # Pattern 3: "House of X"
    for m in re.finditer(r"\bHOUSE\s+OF\s+([A-Z][A-Z]+(?:-[A-Z]+)?)\b", text_upper):
        base = m.group(1)
        if len(base) >= 3 and base not in NON_SURNAME_TOKENS:
            found.add(base)

    return found


def split_sentences(text):
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n+", " . ", text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def region_of_psgc(psgc):
    if not psgc or pd.isna(psgc):
        return ""
    s = str(psgc).strip().replace(".0", "")
    return s.zfill(10)[:2]


def is_mindanao(psgc):
    return region_of_psgc(psgc) in MINDANAO_PREFIXES


def has_kinship_keyword(s):
    sl = s.lower()
    return any(kw in sl for kw in KINSHIP_KEYWORDS)


def has_family_reference(s):
    sl = s.lower()
    return any(kw in sl for kw in FAMILY_REFERENCE_KEYWORDS)


def has_contradiction_keyword(s):
    sl = s.lower()
    return any(kw in sl for kw in CONTRADICTION_KEYWORDS)


# ==================== PULITIKLAN PARSING ====================
def parse_pulitiklan_file(path, name_index, surname_index):
    print(f"\nParsing: {os.path.basename(path)}")
    if not os.path.exists(path):
        print(f"  ⚠ file not found")
        return set(), set(), set()

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    print(f"  {len(text):,} chars")

    mentioned_ids = set()
    kinship_pairs = set()
    contradiction_pairs = set()

    sentences = split_sentences(text)
    print(f"  {len(sentences):,} sentences")

    sent_with_kinship = 0
    sent_with_contradiction = 0
    sent_with_surname_only = 0
    sent_with_family_ref = 0

    for sent in sentences:
        sent_clean = strip_possessive(sent)
        sent_upper = sent_clean.upper()

        # ---- Tier 1: Full-name matches (precise) ----
        full_name_candidates = extract_full_name_sequences(sent_upper)
        full_name_ids = set()
        for cand in full_name_candidates:
            for pid in name_index.get(cand, []):
                full_name_ids.add(pid)

        # ---- Tier 2: Surname-only matches (broad, for mentioned_ids only) ----
        surname_candidates = extract_single_capitalized(sent_upper)
        surname_ids = set()
        for sn in surname_candidates:
            for pid in surname_index.get(sn, []):
                surname_ids.add(pid)
        if surname_ids:
            sent_with_surname_only += 1

        # ---- Tier 3: Family-plural references ----
        family_bases = extract_family_plurals(sent_upper)
        family_ids = set()
        for base in family_bases:
            for pid in surname_index.get(base, []):
                family_ids.add(pid)
        if family_ids:
            sent_with_family_ref += 1

        # ---- Add all discovered IDs to mentioned set (broad) ----
        all_ids = full_name_ids | surname_ids | family_ids
        mentioned_ids.update(all_ids)

        # ---- Kinship pair extraction requires full-name or family-ref ----
        # (surname-only matches don't create pairs — too noisy)
        pair_ids = full_name_ids | family_ids
        if len(pair_ids) < 2:
            continue

        has_kin = has_kinship_keyword(sent_clean)
        has_fam_ref = has_family_reference(sent_clean)
        has_con = has_contradiction_keyword(sent_clean)

        if has_kin or has_fam_ref:
            sent_with_kinship += 1
            for a in pair_ids:
                for b in pair_ids:
                    if a != b:
                        kinship_pairs.add(frozenset({a, b}))

        if has_con:
            sent_with_contradiction += 1
            for a in pair_ids:
                for b in pair_ids:
                    if a != b:
                        contradiction_pairs.add(frozenset({a, b}))

    print(f"  Unique politicians mentioned (full+surname+family): {len(mentioned_ids):,}")
    print(f"  Sentences with surname-only matches:               {sent_with_surname_only:,}")
    print(f"  Sentences with family-plural refs:                 {sent_with_family_ref:,}")
    print(f"  Sentences with kinship context:                    {sent_with_kinship:,}")
    print(f"  Sentences with contradiction context:              {sent_with_contradiction:,}")
    print(f"  Kinship pairs extracted:                           {len(kinship_pairs):,}")
    print(f"  Contradiction pairs extracted:                     {len(contradiction_pairs):,}")

    return mentioned_ids, kinship_pairs, contradiction_pairs


# ==================== EDGE CLASSIFICATION ====================
def classify_edge(row, id2psgc, mentioned, kin_pairs, con_pairs):
    a = row["person_a_id"]
    b = row["person_b_id"]

    if is_mindanao(id2psgc.get(a, "")) or is_mindanao(id2psgc.get(b, "")):
        return "baseline_mindanao"

    key = frozenset({a, b})
    if key in con_pairs:
        return "contradicted"
    if key in kin_pairs:
        return "verified_explicit"
    if a in mentioned and b in mentioned:
        return "verified_mentioned"
    return "unverifiable"


# ==================== DATASET PROCESSING ====================
def load_dataset(name, edges_path, nodes_path):
    if not os.path.exists(edges_path):
        print(f"\n⚠ {name}: edges file missing")
        return None, None, None
    if not os.path.exists(nodes_path):
        print(f"\n⚠ {name}: nodes file missing")
        return None, None, None

    print(f"\nLoading {name}...")
    edges = pd.read_csv(edges_path, dtype=str, keep_default_na=False)
    nodes = pd.read_csv(nodes_path, dtype={"home_psgc": str}, keep_default_na=False)
    nodes["home_psgc"] = nodes["home_psgc"].str.strip().str.zfill(10)
    print(f"  edges: {len(edges)}, nodes: {len(nodes)}")
    id2psgc = dict(zip(nodes["person_id"], nodes["home_psgc"]))
    return edges, nodes, id2psgc


def process_dataset(name, edges, id2psgc, mentioned, kin_pairs, con_pairs):
    if edges is None or edges.empty:
        return None

    print(f"\nClassifying {len(edges)} {name} edges...")
    classifications = [
        classify_edge(row, id2psgc, mentioned, kin_pairs, con_pairs)
        for _, row in edges.iterrows()
    ]
    out = edges.copy()
    out["pulitiklan_verdict"] = classifications

    dist = out["pulitiklan_verdict"].value_counts()
    print(f"\n  {name} verdict distribution:")
    for v in ["verified_explicit", "verified_mentioned", "contradicted",
              "baseline_mindanao", "unverifiable"]:
        cnt = dist.get(v, 0)
        pct = cnt / len(out) * 100 if len(out) else 0
        print(f"    {v:<22}: {cnt:>5} ({pct:5.1f}%)")

    out_file = os.path.join(OUT_DIR, f"{name}_pulitiklan_cross_validation.csv")
    out.to_csv(out_file, index=False, encoding="utf-8-sig")
    print(f"  → {out_file}")
    return out


# ==================== MAIN ====================
def main():
    print("=" * 70)
    print("=== PULITIKLAN CROSS-VALIDATION v2 (improved recall) ===")
    print("=" * 70)

    pn1_edges, pn1_nodes, pn1_id2psgc = load_dataset("PN1", PN1_EDGES, PN1_NODES)
    pn2_edges, pn2_nodes, pn2_id2psgc = load_dataset("PN2", PN2_EDGES, PN2_NODES)
    pn3_edges, pn3_nodes, pn3_id2psgc = load_dataset("PN3", PN3_EDGES, PN3_NODES)

    if any(x is None for x in [pn1_nodes, pn2_nodes, pn3_nodes]):
        print("\nCRITICAL: missing node files.")
        return

    # ---- Build unified indexes ----
    print("\n=== Building unified indexes ===")
    all_nodes = pd.concat(
        [pn1_nodes, pn2_nodes, pn3_nodes], ignore_index=True
    ).drop_duplicates(subset=["person_id"])
    print(f"  Total unique nodes: {len(all_nodes):,}")

    name_index = build_name_index(all_nodes)
    surname_index = build_surname_index(all_nodes)
    print(f"  Full-name variants:   {len(name_index):,}")
    print(f"  Unique surnames:      {len(surname_index):,}")

    # ---- Parse Pulitiklan ----
    print("\n=== Parsing Pulitiklan files ===")
    vis_m, vis_k, vis_c = parse_pulitiklan_file(
        PULITIKLAN_VISAYAS, name_index, surname_index
    )
    luz_m, luz_k, luz_c = parse_pulitiklan_file(
        PULITIKLAN_LUZON, name_index, surname_index
    )

    mentioned = vis_m | luz_m
    kin_pairs = vis_k | luz_k
    con_pairs = vis_c | luz_c

    print(f"\n=== Combined Pulitiklan coverage ===")
    print(f"  Total politicians mentioned: {len(mentioned):,}")
    print(f"  Total kinship pairs:         {len(kin_pairs):,}")
    print(f"  Total contradiction pairs:   {len(con_pairs):,}")

    # ---- Classify ----
    print("\n=== Classifying datasets ===")
    pn1_out = process_dataset("PN1", pn1_edges, pn1_id2psgc, mentioned, kin_pairs, con_pairs)
    pn2_out = process_dataset("PN2", pn2_edges, pn2_id2psgc, mentioned, kin_pairs, con_pairs)
    pn3_out = process_dataset("PN3", pn3_edges, pn3_id2psgc, mentioned, kin_pairs, con_pairs)

    # ---- Summary ----
    print("\n" + "=" * 70)
    print("=== FINAL SUMMARY ===")
    print("=" * 70)

    rows = []
    for name, df in [("PN1", pn1_out), ("PN2", pn2_out), ("PN3", pn3_out)]:
        if df is None or df.empty:
            rows.append({"dataset": name, "total": 0})
            continue
        row = {"dataset": name, "total": len(df)}
        for v in ["verified_explicit", "verified_mentioned", "contradicted",
                  "baseline_mindanao", "unverifiable"]:
            cnt = (df["pulitiklan_verdict"] == v).sum()
            row[v] = cnt
            row[f"{v}_pct"] = round(cnt / len(df) * 100, 1)
        rows.append(row)

    summary = pd.DataFrame(rows)
    print(summary.to_string(index=False))

    summary_file = os.path.join(OUT_DIR, "_summary_all_datasets.csv")
    summary.to_csv(summary_file, index=False, encoding="utf-8-sig")
    print(f"\n→ {summary_file}")


if __name__ == "__main__":
    main()