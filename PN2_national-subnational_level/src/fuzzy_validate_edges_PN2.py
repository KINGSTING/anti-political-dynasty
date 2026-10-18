"""
PN2 Method 3 — Fuzzy name matching (v2)
---------------------------------------
Part A (Validation): Re-score existing edges. Common-surname-only edges get
                     demoted. Genuine variant spellings get boosted.
Part B (Expansion):  Discover new edges via variant-spelled surnames inside
                     the same LGU. Only variant_confirmed and mid-confirmed
                     variant_likely pass. phonetic_match disabled.
"""

import os
import re
import unicodedata
from collections import defaultdict

import pandas as pd
from jellyfish import metaphone, soundex
from rapidfuzz.distance import JaroWinkler

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN2_national-subnational_level\data"
NODES_CSV = os.path.join(BASE, "national+subnational_nodes.csv")
EDGES_MERGED_CSV = os.path.join(BASE, "national+subnational_edges_merged.csv")
EDGES_RAW_CSV = os.path.join(BASE, "national+subnational_edges.csv")
OUT_VALIDATED_CSV = os.path.join(BASE, "edges_fuzzy_validated.csv")
OUT_NEW_EDGES_CSV = os.path.join(BASE, "edges_fuzzy_new.csv")
OUT_REPORT_TXT = os.path.join(BASE, "fuzzy_report.txt")

# ==================== CONFIG ====================
COMMON_SURNAMES = {
    "DELA CRUZ",
    "DELACRUZ",
    "REYES",
    "SANTOS",
    "GARCIA",
    "RAMOS",
    "MENDOZA",
    "BAUTISTA",
    "CASTILLO",
    "VILLANUEVA",
    "AQUINO",
    "CRUZ",
    "SANTIAGO",
    "GONZALES",
    "GONZALEZ",
    "PEREZ",
    "RODRIGUEZ",
    "TORRES",
    "FLORES",
    "RIVERA",
    "DIAZ",
    "MARTINEZ",
    "AGUILAR",
    "NAVARRO",
    "MORALES",
    "DOMINGUEZ",
    "VILLAREAL",
    "MAGBANUA",
    "JAVIER",
    "TOLENTINO",
    "SALAZAR",
    "LIM",
    "TAN",
    "SY",
    "CHUA",
    "GO",
    "ONG",
}

DYNASTIC_EXCEPTIONS = {
    "FERRIOL": {"1374"},
    "TAN": {"0722", "0730"},
    "SINGSON": {"0129"},
    "MARCOS": {"0128"},
    "AMPATUAN": {"1500", "1501"},
    "HATAMAN": {"1500", "1507"},
    "LIM": {"1339"},
    "GO": {"1374"},
    "SY": {"1374"},
}

JW_STRONG = 0.92
JW_MEDIUM = 0.85
JW_WEAK = 0.75

OUTPUT_COLUMNS = [
    "edge_id",
    "person_a_id",
    "person_b_id",
    "relation_label",
    "civil_degree",
    "kinship_type",
    "source_document",
    "is_ground_truth",
    "probability",
    "fuzzy_verdict",
    "fuzzy_score",
    "fuzzy_detail",
]


def norm(s):
  if pd.isna(s):
    return ""
  s = str(s).upper().strip()
  s = unicodedata.normalize("NFD", s)
  s = "".join(c for c in s if unicodedata.category(c) != "Mn")
  s = re.sub(r"[^A-Z\s]", " ", s)
  s = " ".join(s.split())
  s = re.sub(r"\s+(JR|SR|II|III|IV|V|VI)$", "", s).strip()
  return s


def collapse(s):
  return re.sub(r"[^A-Z]", "", str(s).upper())


def is_dynastic_exception(surname, psgc):
  if surname not in DYNASTIC_EXCEPTIONS:
    return False
  prefixes = DYNASTIC_EXCEPTIONS[surname]
  psgc_str = str(psgc).strip().zfill(10)
  return any(psgc_str.startswith(p) for p in prefixes)


def fuzzy_score(name_a, name_b):
  a = norm(name_a)
  b = norm(name_b)
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


def validate_existing_edges(edges_df, id_to_node, report):
  results = []
  stats = {
      "kept": 0,
      "boosted": 0,
      "demoted": 0,
      "dropped": 0,
      "exceptions_applied": 0,
  }

  for _, e in edges_df.iterrows():
    p_a = id_to_node.get(e.get("person_a_id", ""), {})
    p_b = id_to_node.get(e.get("person_b_id", ""), {})
    row = e.to_dict()

    if not p_a or not p_b:
      row["fuzzy_verdict"] = "missing_node"
      row["fuzzy_score"] = 0.0
      row["fuzzy_detail"] = "node not found"
      results.append(row)
      stats["kept"] += 1
      continue

    rel = row.get("relation_label", "")

    if rel == "Shared_Maternal_Line":
      confirm_score, confirm_verdict, confirm_detail = fuzzy_score(
          p_a.get("middle_name", ""), p_b.get("middle_name", "")
      )
      confirm_name = norm(p_a.get("middle_name", ""))
    else:
      confirm_score, confirm_verdict, confirm_detail = fuzzy_score(
          p_a.get("last_name", ""), p_b.get("last_name", "")
      )
      confirm_name = norm(p_a.get("last_name", ""))

    row["fuzzy_verdict"] = confirm_verdict
    row["fuzzy_score"] = round(confirm_score, 3)
    row["fuzzy_detail"] = confirm_detail

    try:
      prob = float(e.get("probability", 0.5))
    except (ValueError, TypeError):
      prob = 0.5

    is_gt = str(e.get("is_ground_truth", "False")).lower() == "true"

    is_common = confirm_name in COMMON_SURNAMES
    if is_common and is_dynastic_exception(
        confirm_name, p_a.get("home_psgc", "")
    ):
      is_common = False
      stats["exceptions_applied"] += 1
      row["fuzzy_detail"] += " [dynastic_exception]"

    adjusted = prob
    action = "kept"

    if confirm_verdict == "no_match":
      adjusted = prob - 0.20
      action = "demoted"
    elif is_common and confirm_verdict == "exact":
      if rel == "Distant_Kin":
        adjusted = prob - 0.15
        action = "demoted"
      elif rel == "Shared_Maternal_Line":
        adjusted = prob - 0.10
        action = "demoted"
    elif confirm_verdict == "variant_confirmed":
      adjusted = min(0.99, prob + 0.05)
      action = "boosted"
    elif confirm_verdict == "variant_likely":
      mid_a = norm(p_a.get("middle_name", ""))
      mid_b = norm(p_b.get("middle_name", ""))
      if mid_a and mid_a == mid_b:
        adjusted = min(0.99, prob + 0.05)
        action = "boosted"

    adjusted = max(0.0, min(1.0, adjusted))
    row["probability"] = round(adjusted, 3)

    if adjusted < 0.50 and not is_gt:
      stats["dropped"] += 1
      continue

    stats[action] += 1
    results.append(row)

  report.append("Part A — Validation:")
  report.append(f"  Kept               : {stats['kept']}")
  report.append(f"  Boosted            : {stats['boosted']}")
  report.append(f"  Demoted            : {stats['demoted']}")
  report.append(f"  Dropped            : {stats['dropped']}")
  report.append(f"  Dynastic exceptions: {stats['exceptions_applied']}")
  return pd.DataFrame(results), stats


def expand_with_variants(nodes_df, existing_edges_df, report):
  existing_pairs = set()
  for _, e in existing_edges_df.iterrows():
    p_a = str(e.get("person_a_id", ""))
    p_b = str(e.get("person_b_id", ""))
    if p_a and p_b:
      existing_pairs.add(tuple(sorted([p_a, p_b])))

  blocks = defaultdict(list)
  for _, n in nodes_df.iterrows():
    last = norm(n.get("last_name", ""))
    if not last:
      continue
    sx = soundex(last) or f"_{last[:3]}"
    blocks[(n.get("home_psgc", ""), sx)].append(n.to_dict())

  new_edges = []
  verdict_counts = defaultdict(int)
  skipped_no_mid = 0

  for (lgu, sx), group in blocks.items():
    if len(group) < 2:
      continue
    for i, a in enumerate(group):
      for b in group[i + 1 :]:
        pair = tuple(sorted([a["person_id"], b["person_id"]]))
        if pair in existing_pairs:
          continue
        last_a = norm(a.get("last_name", ""))
        last_b = norm(b.get("last_name", ""))
        if last_a == last_b:
          continue
        score, verdict, detail = fuzzy_score(last_a, last_b)
        if verdict not in ("variant_confirmed", "variant_likely"):
          continue
        mid_a = norm(a.get("middle_name", ""))
        mid_b = norm(b.get("middle_name", ""))
        mid_match = bool(mid_a and mid_a == mid_b)
        if verdict == "variant_likely" and not mid_match:
          skipped_no_mid += 1
          continue
        base = 0.50
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
  for v, c in verdict_counts.items():
    report.append(f"    {v}: {c}")

  df_new = (
      pd.DataFrame(new_edges)
      if new_edges
      else pd.DataFrame(columns=OUTPUT_COLUMNS)
  )
  return df_new


def main():
  print(f"Loading nodes: {NODES_CSV}")
  nodes = pd.read_csv(NODES_CSV, dtype={"home_psgc": str}, keep_default_na=False)

  before = len(nodes)
  nodes = nodes[
      nodes["person_id"].astype(str).str.startswith("POL-PH-", na=False)
  ].copy()
  nodes = nodes.drop_duplicates(subset="person_id", keep="first").reset_index(
      drop=True
  )
  if len(nodes) < before:
    print(
        f"  Sanitized nodes: {before} -> {len(nodes)} (dropped"
        f" {before - len(nodes)} malformed/duplicate)"
    )

  nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
  print(f"  {len(nodes)} nodes loaded")

  id_to_node = nodes.set_index("person_id").to_dict(orient="index")

  edges_path = (
      EDGES_MERGED_CSV
      if os.path.exists(EDGES_MERGED_CSV)
      else EDGES_RAW_CSV
  )
  print(f"Loading edges: {edges_path}")
  edges = pd.read_csv(edges_path, dtype=str, keep_default_na=False)

  edges = edges.rename(
      columns={"person_id_a": "person_a_id", "person_id_b": "person_b_id"}
  )
  for col in ["person_a_id", "person_b_id"]:
    if col in edges.columns:
      edges = edges[edges[col].astype(str).str.startswith("POL-PH-", na=False)]

  print(f"  {len(edges)} raw edges loaded")

  report = []
  report.append("=== PN2 FUZZY VALIDATION & EXPANSION REPORT ===")
  report.append(f"Input nodes: {len(nodes)}")
  report.append(f"Input edges: {len(edges)}\n")

  val_df, _ = validate_existing_edges(edges, id_to_node, report)
  new_df = expand_with_variants(nodes, val_df, report)

  val_df.to_csv(OUT_VALIDATED_CSV, index=False)
  print(f"\nSaved validated edges ({len(val_df)} rows) to: {OUT_VALIDATED_CSV}")

  if not new_df.empty:
    new_df.to_csv(OUT_NEW_EDGES_CSV, index=False)
    print(f"Saved new fuzzy edges ({len(new_df)} rows) to: {OUT_NEW_EDGES_CSV}")

  report_text = "\n".join(report)
  with open(OUT_REPORT_TXT, "w", encoding="utf-8") as f:
    f.write(report_text)
  print(f"Report written to: {OUT_REPORT_TXT}\n")
  print(report_text)


if __name__ == "__main__":
  main()