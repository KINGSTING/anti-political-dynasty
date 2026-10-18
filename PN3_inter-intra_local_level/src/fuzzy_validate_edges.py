"""
PN3 Method 3 — Fuzzy name matching (v2)
---------------------------------------
Part A (Validation): Re-score existing edges. Common-surname-only edges get
                     demoted. Genuine variant spellings get boosted.
                     Province-aware exceptions restore real dynasties whose
                     surnames happen to be nationally common.

Part B (Expansion):  Discover new edges via variant-spelled surnames inside
                     the same LGU. Only variant_confirmed (JW >= 0.92 or
                     collapse match) and mid-confirmed variant_likely pass.
                     phonetic_match is disabled — too noisy on PH surnames.

Output: 9-column production schema + 3 fuzzy diagnostic columns.
"""

import os
import re
from collections import defaultdict

import pandas as pd
from rapidfuzz.distance import JaroWinkler
from jellyfish import soundex, metaphone
import unicodedata

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data"
NODES_CSV          = os.path.join(BASE, "inter-intra_local_nodes.csv")
EDGES_MERGED_CSV   = os.path.join(BASE, "inter-intra_local_edges_merged.csv")
OUT_VALIDATED_CSV  = os.path.join(BASE, "inter-intra_local_edges_fuzzy_validated.csv")
OUT_NEW_EDGES_CSV  = os.path.join(BASE, "inter-intra_local_edges_fuzzy_new.csv")
OUT_REPORT_TXT     = os.path.join(BASE, "fuzzy_matching_report.txt")

# ==================== CONFIG ====================
# Top national common Filipino surnames — used to demote surname-only evidence
COMMON_SURNAMES = {
    "DELA CRUZ", "DELACRUZ", "REYES", "SANTOS", "GARCIA", "RAMOS", "MENDOZA",
    "BAUTISTA", "CASTILLO", "VILLANUEVA", "AQUINO", "CRUZ", "SANTIAGO",
    "GONZALES", "GONZALEZ", "PEREZ", "RODRIGUEZ", "TORRES", "FLORES", "RIVERA",
    "DIAZ", "MARTINEZ", "AGUILAR", "NAVARRO", "MORALES", "DOMINGUEZ",
    "VILLAREAL", "MAGBANUA", "JAVIER", "TOLENTINO", "SALAZAR", "LIM",
    "TAN", "SY", "CHUA", "GO", "ONG",
}

# Province/HUC PSGC prefixes where a "common" surname is actually a documented
# dynasty. Restores those edges from the common-surname noise filter.
# Format: surname -> set of PSGC prefixes (4-digit province or 4-digit HUC)
DYNASTIC_EXCEPTIONS = {
    "FERRIOL":   {"1374"},                # Quezon City
    "TAN":       {"0722", "0730"},        # Cebu province, Cebu City (HUC)
    "SINGSON":   {"0129"},                # Ilocos Sur
    "MARCOS":    {"0128"},                # Ilocos Norte
    "AMPATUAN":  {"1500", "1501"},        # Maguindanao del Norte, del Sur
    "HATAMAN":   {"1500", "1507"},        # Maguindanao, Basilan
    "LIM":       {"1339"},                # Manila (specific Lim clan)
    "GO":        {"1374"},                # Quezon City
    "SY":        {"1374"},                # Quezon City
}

# Thresholds (tuned for Philippine surnames)
JW_STRONG = 0.92   # variant_confirmed
JW_MEDIUM = 0.85   # variant_likely
JW_WEAK   = 0.75   # phonetic threshold (Part A only)

OUTPUT_COLUMNS = [
    "edge_id", "person_a_id", "person_b_id",
    "relation_label", "civil_degree", "kinship_type",
    "source_document", "is_ground_truth", "probability",
    "fuzzy_verdict", "fuzzy_score", "fuzzy_detail",
]


# ==================== HELPERS ====================
def norm(s):
    if pd.isna(s):
        return ""
    s = str(s).upper().strip()
    s = unicodedata.normalize("NFD", s)              # ✅ ñ → n + combining mark
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z\s]", " ", s)
    s = " ".join(s.split())
    s = re.sub(r"\s+(JR|SR|II|III|IV|V|VI)$", "", s).strip()
    return s


def collapse(s):
    """Remove all non-letters for variant comparison (DELA CRUZ == DELACRUZ)."""
    return re.sub(r"[^A-Z]", "", str(s).upper())


def is_dynastic_exception(surname, psgc):
    """True if surname is dynastic in this LGU's province/HUC."""
    if surname not in DYNASTIC_EXCEPTIONS:
        return False
    prefixes = DYNASTIC_EXCEPTIONS[surname]
    psgc_str = str(psgc).strip().zfill(10)
    return any(psgc_str.startswith(p) for p in prefixes)


def fuzzy_score(name_a, name_b):
    """
    Returns (score, verdict, detail).
    Verdicts: exact | variant_confirmed | variant_likely | phonetic_match | no_match | missing
    """
    a = normalize(name_a)
    b = normalize(name_b)
    if not a or not b:
        return 0.0, "missing", "one or both empty"
    if a == b:
        return 1.0, "exact", "identical"
    if collapse(a) == collapse(b):
        return 1.0, "variant_confirmed", "same letters, different spacing"

    jw = JaroWinkler.normalized_similarity(a, b)
    if jw >= JW_STRONG:
        return jw, "variant_confirmed", f"JW={jw:.3f}"

    if jw >= JW_MEDIUM:
        return jw, "variant_likely", f"JW={jw:.3f}"

    sx_a, sx_b = soundex(a), soundex(b)
    mp_a, mp_b = metaphone(a), metaphone(b)
    if (sx_a and sx_a == sx_b or mp_a and mp_a == mp_b) and jw >= JW_WEAK:
        return 0.70, "phonetic_match", f"JW={jw:.3f}"

    return jw, "no_match", f"JW={jw:.3f}"


# ==================== PART A — Validation ====================
def validate_existing_edges(edges_df, id_to_node, report):
    """Re-score each existing edge based on fuzzy confirmation of its key signal."""
    results = []
    stats = {"kept": 0, "boosted": 0, "demoted": 0, "dropped": 0,
             "exceptions_applied": 0}

    for _, e in edges_df.iterrows():
        p_a = id_to_node.get(e["person_a_id"], {})
        p_b = id_to_node.get(e["person_b_id"], {})
        row = e.to_dict()

        if not p_a or not p_b:
            row["fuzzy_verdict"] = "missing_node"
            row["fuzzy_score"]   = 0.0
            row["fuzzy_detail"]  = "node not found"
            results.append(row)
            stats["kept"] += 1
            continue

        rel = row["relation_label"]

        # Which name justified this edge?
        if rel == "Shared_Maternal_Line":
            confirm_score, confirm_verdict, confirm_detail = fuzzy_score(
                p_a.get("middle_name", ""), p_b.get("middle_name", "")
            )
            confirm_name = normalize(p_a.get("middle_name", ""))
        else:
            confirm_score, confirm_verdict, confirm_detail = fuzzy_score(
                p_a.get("last_name", ""), p_b.get("last_name", "")
            )
            confirm_name = normalize(p_a.get("last_name", ""))

        row["fuzzy_verdict"] = confirm_verdict
        row["fuzzy_score"]   = round(confirm_score, 3)
        row["fuzzy_detail"]  = confirm_detail

        prob = float(e["probability"])
        is_gt = str(e.get("is_ground_truth", "False")).lower() == "true"

        # ✅ FIX: province-aware dynasty exception overrides "common" classification
        is_common = confirm_name in COMMON_SURNAMES
        if is_common and is_dynastic_exception(confirm_name, p_a.get("home_psgc", "")):
            is_common = False
            stats["exceptions_applied"] += 1
            row["fuzzy_detail"] += " [dynastic_exception]"

        adjusted = prob
        action = "kept"

        if confirm_verdict == "no_match":
            adjusted = prob - 0.20
            action = "demoted"

        elif is_common and confirm_verdict == "exact":
            # Common surname + exact-only match = likely coincidence
            if rel == "Distant_Kin":
                adjusted = prob - 0.15
                action = "demoted"
            elif rel == "Shared_Maternal_Line":
                adjusted = prob - 0.10
                action = "demoted"

        elif confirm_verdict == "variant_confirmed":
            # ✅ FIX: genuine variant spelling — always strengthen
            adjusted = min(0.99, prob + 0.05)
            action = "boosted"

        elif confirm_verdict == "variant_likely":
            # ✅ FIX: only boost if middle name also confirms structure
            mid_a = normalize(p_a.get("middle_name", ""))
            mid_b = normalize(p_b.get("middle_name", ""))
            if mid_a and mid_a == mid_b:
                adjusted = min(0.99, prob + 0.05)
                action = "boosted"
            # else: leave unchanged (weak signal, don't act)

        # phonetic_match: no action (too noisy for surname strengthening)

        adjusted = max(0.0, min(1.0, adjusted))
        row["probability"] = round(adjusted, 3)

        if adjusted < 0.50 and not is_gt:
            stats["dropped"] += 1
            continue

        stats[action] += 1
        results.append(row)

    report.append("Part A — Validation:")
    report.append(f"  Kept                 : {stats['kept']}")
    report.append(f"  Boosted              : {stats['boosted']}")
    report.append(f"  Demoted              : {stats['demoted']}")
    report.append(f"  Dropped              : {stats['dropped']}")
    report.append(f"  Dynastic exceptions  : {stats['exceptions_applied']}")
    return pd.DataFrame(results), stats


# ==================== PART B — Expansion ====================
def expand_with_variants(nodes_df, existing_edges_df, report):
    """
    Discover new edges via variant-spelled surnames inside the same LGU.
    ✅ Only variant_confirmed passes automatically.
    ✅ variant_likely requires a middle-name match (structural confirmation).
    ❌ phonetic_match disabled — too noisy on Filipino surnames.
    """
    existing_pairs = set()
    for _, e in existing_edges_df.iterrows():
        existing_pairs.add(tuple(sorted([e["person_a_id"], e["person_b_id"]])))

    blocks = defaultdict(list)
    for _, n in nodes_df.iterrows():
        last = normalize(n.get("last_name", ""))
        if not last:
            continue
        sx = soundex(last) or f"_{last[:3]}"
        blocks[(n["home_psgc"], sx)].append(n.to_dict())

    new_edges = []
    verdict_counts = defaultdict(int)
    skipped_no_mid = 0

    for (lgu, sx), group in blocks.items():
        if len(group) < 2:
            continue
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                pair = tuple(sorted([a["person_id"], b["person_id"]]))
                if pair in existing_pairs:
                    continue

                last_a = normalize(a.get("last_name", ""))
                last_b = normalize(b.get("last_name", ""))
                if last_a == last_b:
                    continue  # exact match already in graph

                score, verdict, detail = fuzzy_score(last_a, last_b)

                # ✅ FIX: only variant_confirmed and variant_likely
                if verdict not in ("variant_confirmed", "variant_likely"):
                    continue

                mid_a = normalize(a.get("middle_name", ""))
                mid_b = normalize(b.get("middle_name", ""))
                mid_match = bool(mid_a and mid_a == mid_b)

                # ✅ FIX: variant_likely requires mid confirmation
                if verdict == "variant_likely" and not mid_match:
                    skipped_no_mid += 1
                    continue

                # Score composition
                base = 0.50  # same LGU
                if verdict == "variant_confirmed":
                    base += 0.30 if mid_match else 0.15
                elif verdict == "variant_likely" and mid_match:
                    base += 0.25

                if base < 0.50:
                    continue

                verdict_counts[verdict] += 1
                new_edges.append({
                    "person_a_id": a["person_id"],
                    "person_b_id": b["person_id"],
                    "relation_label": "Fuzzy_Variant_Kin",
                    "civil_degree": 6,
                    "kinship_type": "Consanguinity",
                    "source_document": "Fuzzy_Name_Match",
                    "is_ground_truth": False,
                    "probability": round(min(0.85, base), 3),
                    "fuzzy_verdict": verdict,
                    "fuzzy_score": round(score, 3),
                    "fuzzy_detail": detail,
                })

    report.append("\nPart B — Expansion:")
    report.append(f"  New edges discovered      : {len(new_edges)}")
    report.append(f"  Skipped (variant_likely, no mid match): {skipped_no_mid}")
    if verdict_counts:
        report.append("  Verdict breakdown:")
        for v, c in verdict_counts.items():
            report.append(f"    {v}: {c}")

    df_new = (pd.DataFrame(new_edges)
              if new_edges
              else pd.DataFrame(columns=OUTPUT_COLUMNS))
    return df_new


# ==================== MAIN ====================
def main():
    print(f"Loading nodes: {NODES_CSV}")
    nodes = pd.read_csv(NODES_CSV, dtype={"home_psgc": str}, keep_default_na=False)
    nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
    print(f"  {len(nodes)} nodes")

    print(f"Loading edges: {EDGES_MERGED_CSV}")
    edges = pd.read_csv(EDGES_MERGED_CSV, dtype=str, keep_default_na=False)
    print(f"  {len(edges)} edges")

    id_to_node = nodes.set_index("person_id").to_dict("index")
    report = ["=== PN3 Fuzzy Name Matching Report (v2) ===",
              f"Input edges: {len(edges)}", ""]

    # ---- Part A: Validation ----
    print("\n=== Part A: Validating existing edges ===")
    df_validated, stats_a = validate_existing_edges(edges, id_to_node, report)
    print(f"  {len(df_validated)} edges survive validation")
    print(f"    kept={stats_a['kept']} boosted={stats_a['boosted']} "
          f"demoted={stats_a['demoted']} dropped={stats_a['dropped']} "
          f"exceptions={stats_a['exceptions_applied']}")

    # ---- Part B: Expansion ----
    print("\n=== Part B: Discovering new edges via variant spellings ===")
    df_new = expand_with_variants(nodes, edges, report)
    print(f"  {len(df_new)} new edges discovered")

    # ---- Combine + dedupe ----
    df_validated["edge_id"] = ""
    df_new["edge_id"] = ""

    combined = pd.concat([df_validated, df_new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["person_a_id", "person_b_id"]).reset_index(drop=True)

    START = 5000
    combined["edge_id"] = [f"EDGE-{START + i:06d}" for i in range(len(combined))]

    for col in OUTPUT_COLUMNS:
        if col not in combined.columns:
            combined[col] = ""

    combined = combined[OUTPUT_COLUMNS]
    combined.to_csv(OUT_VALIDATED_CSV, index=False, encoding="utf-8-sig")
    if len(df_new):
        df_new[OUTPUT_COLUMNS].to_csv(OUT_NEW_EDGES_CSV, index=False, encoding="utf-8-sig")

    # ---- Final report ----
    report += [
        "",
        "=== Summary ===",
        f"Original edges       : {len(edges)}",
        f"After validation     : {len(df_validated)}",
        f"New fuzzy edges      : {len(df_new)}",
        f"Final combined edges : {len(combined)}",
        "",
        "Verdict distribution (combined):",
    ]
    for verdict, cnt in combined["fuzzy_verdict"].value_counts().items():
        report.append(f"  {verdict}: {cnt}")
    report.append("")
    report.append("Relation labels after fuzzy (combined):")
    for rel, cnt in combined["relation_label"].value_counts().items():
        report.append(f"  {rel}: {cnt}")

    with open(OUT_REPORT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print(f"\n{'=' * 60}")
    print("=== SUMMARY ===")
    print(f"Original edges       : {len(edges)}")
    print(f"After validation     : {len(df_validated)}")
    print(f"New fuzzy edges      : {len(df_new)}")
    print(f"Final combined edges : {len(combined)}")
    print(f"\nSaved:")
    print(f"  {OUT_VALIDATED_CSV}")
    if len(df_new):
        print(f"  {OUT_NEW_EDGES_CSV}")
    print(f"  {OUT_REPORT_TXT}")


if __name__ == "__main__":
    main()