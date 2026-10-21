#!/usr/bin/env python3
"""
8_simultaneous_concentration_simulator.py
=========================================
PN1 Simultaneous Concentration Simulator — national seats.

Rule:
  Any two office-holders A, B who:
    • hold ANY national elective position (President, VP, Senator, Rep),
    • during OVERLAPPING term windows (both seated at the same time),
    • and are related within 4th civil degree,
  → flag the pair as a simultaneous dynasty-concentration violation.
"""

import os
import re
import unicodedata
import pandas as pd

BASE_DIR = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"
DATA_DIR = os.path.join(BASE_DIR, "PN1_national_level", "data")
WEB_DATA_DIR = os.path.join(BASE_DIR, "web", "data")

INPUT_HISTORY_CSV = os.path.join(DATA_DIR, "electoral_history.csv")
INPUT_KINSHIP_CSV = os.path.join(DATA_DIR, "national_edges_FINAL.csv")
INPUT_NODES_CSV   = os.path.join(DATA_DIR, "national_nodes.csv")
OUTPUT_REPORT_CSV = os.path.join(DATA_DIR, "simultaneous_violations_national.csv")

CIVIL_DEGREE_THRESHOLD = 4

TERM_LENGTH = {
    "SENATOR": 6,
    "PRESIDENT": 6,
    "VICE_PRESIDENT": 6,
    "PARTY_LIST": 3,
    "MEMBER_HOUSE_OF_REPRESENTATIVES": 3,
}

BASE_GEO_SCOPE = {
    "SENATOR": "PH",
    "PRESIDENT": "PH",
    "VICE_PRESIDENT": "PH",
    "PARTY_LIST": "PH",
    "MEMBER_HOUSE_OF_REPRESENTATIVES": None,
}

NATIONAL_SEAT_PREFIXES = (
    "PH-SENATOR", "PH-PRESIDENT", "PH-VICE_PRESIDENT",
    "PH-PARTY_LIST", "PH-MEMBER_HOUSE_OF_REPRESENTATIVES",
    "PH-DISTRICT_REPRESENTATIVE", "PH-REPRESENTATIVE",
)

SUFFIX_TOKENS  = {"JR", "SR", "II", "III", "IV", "V", "VI"}
PREPEND_TOKENS = {"PER", "POL", "PH"}
# PATCH 1: also split on quotes and parentheses so nicknames like
#   Maria Imelda Josefa "Imee" Marcos  →  IMEE becomes its own token.
NAME_SPLIT_RE  = re.compile(r"[\s_\-/,\.'\"()]+")

NICKNAME_TO_LEGAL = {
    "WIN": "SHERWIN",   "DICK": "RICHARD",  "MIGZ": "MIGUEL",
    "KIKO": "FRANCIS",  "PING": "PANFILO",  "TITO": "VICENTE",
    "BONG": "RAMON",    "BONGBONG": "FERDINAND", "NOYNOY": "BENIGNO",
    "JINGGOY": "JOSEPH","JV": "JOSEPH",     "TESSIE": "TERESITA",
    "SONNY": "JOSE",    "DIGONG": "RODRIGO", "DODOY": "RODRIGO",
    "BATO": "RONALD",   "BISTEK": "HERBERT","CHIZ": "FRANCIS",
    "TOL": "FRANCIS",   "GRINGO": "GREGORIO","BASTE": "SEBASTIAN",
    "PULONG": "PAOLO",  "RISA": "ANA",
}

# PATCH 2: Authoritative PER → POL overrides. Checked before every fuzzy tier.
# Fill these in whenever you've confirmed the mapping by hand.
MANUAL_PER_TO_POL_OVERRIDES = {
    "PER-MARCOS-SANDRO":    "POL-PH-000215",
    "PER-MARCOS-IMEE":      "POL-PH-000017",
    "PER-COJUANGCO-MARCOS": "POL-PH-000101",   # ← optional, see note below
}

def _repair_mojibake(s):
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s

def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def _normalize(s):
    return _strip_accents(_repair_mojibake(str(s).strip())).upper()

def canonical_name_key(raw_name):
    if pd.isna(raw_name) or not str(raw_name).strip():
        return ""
    toks = [t for t in NAME_SPLIT_RE.split(_normalize(raw_name))
            if t and t not in PREPEND_TOKENS and t not in SUFFIX_TOKENS]
    return "|".join(sorted(toks)) if toks else ""

def _node_surnames(raw_name):
    if pd.isna(raw_name) or not str(raw_name).strip():
        return []
    toks = [t for t in NAME_SPLIT_RE.split(_normalize(raw_name))
            if t and t not in SUFFIX_TOKENS]
    if len(toks) < 2:
        return []
    forms = [toks[-1], toks[-2] + "_" + toks[-1]]
    if len(toks) >= 3 and toks[-3] in {"DE", "DEL", "DELA", "DELOS", "DELAS"}:
        forms.append(toks[-3] + "_" + toks[-2] + "_" + toks[-1])
    return list(dict.fromkeys(forms))

def _per_parts(body):
    if "-" not in body:
        return [], []
    last_seg, first_seg = body.split("-", 1)
    last_tokens = [t for t in last_seg.upper().split("_") if t]
    surnames = ["_".join(last_tokens[i:]) for i in range(len(last_tokens))]
    first_tokens = [t for t in first_seg.upper().replace("_", " ").split() if t]
    return surnames, first_tokens

def _expand_first(tok):
    return NICKNAME_TO_LEGAL.get(tok.upper(), tok.upper())

def sanitize(text):
    return "" if pd.isna(text) else str(text).strip().upper()

def normalize_seat_id(seat_id: str) -> str:
    s = (seat_id or "").strip().upper()
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")

def build_crosswalk(df_history, df_nodes):
    node_key_to_pol, node_by_token = {}, {}
    node_by_surname, node_first_tokens = {}, {}

    for _, row in df_nodes.iterrows():
        name = row.get("full_name_clean", "") or row.get("full_name", "")
        k = canonical_name_key(name)
        if not k:
            continue
        pol = row["person_id"]
        node_key_to_pol.setdefault(k, pol)
        for tok in k.split("|"):
            node_by_token.setdefault(tok, set()).add((k, pol))
        for surname in _node_surnames(name):
            node_by_surname.setdefault(surname, []).append(pol)
        node_first_tokens[pol] = set(k.split("|"))

    mask = df_history["seat_id"].fillna("").str.startswith(NATIONAL_SEAT_PREFIXES)
    targets = df_history.loc[mask, "person_id"].dropna().unique()
    print(f"   → crosswalk scoped to national seats: {len(targets):,} PERs")

    # PATCH 3: add manual_override tier
    mapping, unresolved = {}, []
    tiers = {"exact": 0, "subset": 0, "surname_nick": 0, "manual_override": 0}

    for per_id in targets:
        # Tier 0 — manual overrides win
        if per_id in MANUAL_PER_TO_POL_OVERRIDES:
            mapping[per_id] = MANUAL_PER_TO_POL_OVERRIDES[per_id]
            tiers["manual_override"] += 1
            continue

        body = per_id[4:] if per_id.upper().startswith("PER-") else per_id
        k = canonical_name_key(body)
        if not k:
            unresolved.append(per_id)
            continue

        if k in node_key_to_pol:
            mapping[per_id] = node_key_to_pol[k]
            tiers["exact"] += 1
            continue

        per_toks = set(k.split("|"))
        if len(per_toks) < 2:
            unresolved.append(per_id)
            continue

        candidates = None
        for tok in per_toks:
            bucket = node_by_token.get(tok, set())
            candidates = bucket if candidates is None else candidates & bucket
            if not candidates:
                break
        if candidates:
            matched = None
            for node_key, pol_id in candidates:
                if len(per_toks.symmetric_difference(node_key.split("|"))) <= 1:
                    matched = pol_id
                    break
            if matched:
                mapping[per_id] = matched
                tiers["subset"] += 1
                continue

        surnames, first_tokens = _per_parts(body)
        matched = None
        for surname in surnames:
            bucket = node_by_surname.get(surname)
            if not bucket:
                continue
            if len(bucket) == 1:
                matched = bucket[0]
                break
            for ft in first_tokens:
                expanded = _expand_first(ft)
                for pol_id in bucket:
                    if expanded in node_first_tokens.get(pol_id, set()):
                        matched = pol_id
                        break
                if matched:
                    break
            if matched:
                break
        if matched:
            mapping[per_id] = matched
            tiers["surname_nick"] += 1
            continue

        unresolved.append(per_id)

    # PATCH 3: extended diagnostic
    marcos_per = [p for p in targets if "MARCOS" in p.upper()]
    marcos_ok = [p for p in marcos_per if p in mapping]
    print(f"   → tiers: exact={tiers['exact']}, subset={tiers['subset']}, "
          f"surname+nickname={tiers['surname_nick']}, "
          f"manual={tiers['manual_override']}")
    print(f"   → MARCOS-family: {len(marcos_ok)}/{len(marcos_per)} resolved")
    for p in marcos_per:
        if p not in mapping:
            print(f"       ✗ still unresolved: {p}")
    return mapping, unresolved

def classify_seat(seat_id: str):
    s = normalize_seat_id(seat_id)
    if s.startswith("PH-SENATOR"):
        return ("SENATOR", "PH")
    if s.startswith("PH-PRESIDENT"):
        return ("PRESIDENT", "PH")
    if s.startswith("PH-VICE_PRESIDENT"):
        return ("VICE_PRESIDENT", "PH")
    if s.startswith("PH-PARTY_LIST"):
        return ("PARTY_LIST", "PH")
    if s.startswith(("PH-MEMBER_HOUSE_OF_REPRESENTATIVES",
                     "PH-DISTRICT_REPRESENTATIVE", "PH-REPRESENTATIVE")):
        parts = s.split("-")
        province = parts[2] if len(parts) >= 3 else ""
        return ("MEMBER_HOUSE_OF_REPRESENTATIVES", province)
    return ("", "")

def main():
    print("🚀 PN1 — Simultaneous Concentration Simulator (National-Wide logic)\n")

    for p in (INPUT_HISTORY_CSV, INPUT_KINSHIP_CSV, INPUT_NODES_CSV):
        if not os.path.exists(p):
            raise FileNotFoundError(f"❌ Missing required file asset at '{p}'")

    df_history = pd.read_csv(INPUT_HISTORY_CSV, dtype=str, keep_default_na=False)
    df_edges   = pd.read_csv(INPUT_KINSHIP_CSV, dtype=str, keep_default_na=False)
    df_nodes   = pd.read_csv(INPUT_NODES_CSV,   dtype=str, keep_default_na=False)

    df_history["seat_id"] = df_history["seat_id"].fillna("").apply(normalize_seat_id)

    print(f"📊 Loaded {len(df_history):,} election entries, "
          f"{len(df_edges):,} kinship edges, {len(df_nodes):,} nodes.")

    print("\n💎 Building PER → POL crosswalk...")
    per_to_pol, _ = build_crosswalk(df_history, df_nodes)

    # Export per_to_pol.csv for the Web App
    os.makedirs(WEB_DATA_DIR, exist_ok=True)
    per_to_pol_df = pd.DataFrame(list(per_to_pol.items()), columns=['person_id', 'pol_id'])
    per_to_pol_export_path = os.path.join(WEB_DATA_DIR, "per_to_pol.csv")
    per_to_pol_df.to_csv(per_to_pol_export_path, index=False)
    print(f"💾 Exported web dependency: {per_to_pol_export_path}")

    pol_in_graph = set()
    for _, r in df_edges.iterrows():
        pol_in_graph.add(sanitize(r.get("person_a_id", "")))
        pol_in_graph.add(sanitize(r.get("person_b_id", "")))
    overlap_pols = set(per_to_pol.values()) & pol_in_graph
    print(f"🔗 {len(overlap_pols):,} resolved persons appear in the kinship graph.")

    id_to_real_name = dict(zip(df_nodes["person_id"], df_nodes["full_name_clean"]))

    kinship = {}
    for _, r in df_edges.iterrows():
        a = sanitize(r["person_a_id"])
        b = sanitize(r["person_b_id"])
        rel = r.get("relation_label", "RELATIVE") or "RELATIVE"
        try:
            deg = int(r["civil_degree"])
        except (ValueError, KeyError):
            deg = CIVIL_DEGREE_THRESHOLD
        kinship[(a, b)] = kinship[(b, a)] = {"relation": rel, "degree": deg}

    nat_mask = df_history["seat_id"].str.startswith(NATIONAL_SEAT_PREFIXES)
    df_nat = df_history[nat_mask].copy()
    df_nat["election_year"] = pd.to_numeric(
        df_nat["election_year"], errors="coerce").fillna(0).astype(int)
    winners = df_nat[df_nat["is_winner"].str.lower() == "true"].copy()

    print(f"🏛️  {len(winners):,} national winners across "
          f"{winners['seat_id'].nunique():,} seat_ids.")

    records = []
    skipped_unresolved = 0
    for _, row in winners.iterrows():
        year = int(row["election_year"])
        if year < 2000:
            continue

        seat_id = row["seat_id"]
        pos_class, geo_scope = classify_seat(seat_id)
        if not pos_class:
            continue

        term_len = TERM_LENGTH.get(pos_class)
        if not term_len:
            continue

        pol_id = per_to_pol.get(row["person_id"])
        if not pol_id:
            skipped_unresolved += 1
            continue

        records.append({
            "pol_id":          pol_id,
            "name":            id_to_real_name.get(pol_id, row["person_id"]),
            "position_class":  pos_class,
            "geo_scope":       geo_scope,
            "seat_id":         seat_id,
            "election_year":   year,
            "term_start":      year,
            "term_end":        year + term_len,
        })

    office_df = pd.DataFrame(records).drop_duplicates().reset_index(drop=True)
    print(f"📋 {len(office_df):,} resolved term records built "
          f"({skipped_unresolved:,} PERs skipped — unresolved).")

    if office_df.empty:
        print("⚠️  Nothing to simulate.")
        return

    # =========================================================================
    # National-Wide Blanket (Cross-Chamber)
    # =========================================================================
    flagged = []
    group_counts = {}

    office_df["group_key"] = "NATIONAL_LEVEL_PH"

    for group_key, group in office_df.groupby("group_key"):
        person_terms = {}
        person_name = {}
        person_class = {}

        for pol_id, g in group.groupby("pol_id"):
            terms = [
                (int(r["term_start"]), int(r["term_end"]), r["seat_id"],
                 int(r["election_year"]))
                for _, r in g.iterrows()
            ]
            person_terms[pol_id] = terms
            person_name[pol_id] = g["name"].iloc[0]
            person_class[pol_id] = g["position_class"].iloc[0]

        pol_ids = sorted(person_terms.keys())
        pairs_checked = 0
        local_flags = 0

        for i, a in enumerate(pol_ids):
            for b in pol_ids[i + 1:]:
                link = kinship.get((a, b))
                if not link or link["degree"] > CIVIL_DEGREE_THRESHOLD:
                    continue

                pairs_checked += 1

                seen_windows = set()
                for a_start, a_end, a_seat, a_yr in person_terms[a]:
                    for b_start, b_end, b_seat, b_yr in person_terms[b]:
                        ov_start = max(a_start, b_start)
                        ov_end = min(a_end, b_end)
                        if ov_end <= ov_start:
                            continue

                        window_key = (ov_start, ov_end)
                        if window_key in seen_windows:
                            continue
                        seen_windows.add(window_key)

                        a_pos = person_class[a]
                        b_pos = person_class[b]

                        if a_pos == b_pos:
                            tier = "DIRECT (same office class)"
                        else:
                            tier = "CROSS-OFFICE NATIONAL (e.g., VP & Rep)"

                        flagged.append({
                            "position_class":                   f"{a_pos} / {b_pos}",
                            "geo_scope":                        "PH",
                            "person_a_pol_id":                  a,
                            "person_a_name":                    person_name[a],
                            "person_a_elected":                 a_yr,
                            "person_a_seat":                    a_seat,
                            "person_a_term":                    f"{a_start}-{a_end}",
                            "person_b_pol_id":                  b,
                            "person_b_name":                    person_name[b],
                            "person_b_elected":                 b_yr,
                            "person_b_seat":                    b_seat,
                            "person_b_term":                    f"{b_start}-{b_end}",
                            "bloodline_relation":               link["relation"],
                            "civil_degree_distance":            link["degree"],
                            "overlap_window":                   f"{ov_start}-{ov_end}",
                            "overlap_years":                    ov_end - ov_start,
                            "confidence_tier":                  tier,
                            "simulation_disqualification_status": "BANNED",
                        })
                        local_flags += 1

        group_counts[group_key] = {
            "office_holders": len(pol_ids),
            "kin_pairs":      pairs_checked,
            "flags":          local_flags,
        }
    # =========================================================================

    print("\n=== Group diagnostics ===")
    for gk, stats in sorted(group_counts.items()):
        print(f"   {gk:55s}  holders={stats['office_holders']:>4d}  "
              f"kin_pairs={stats['kin_pairs']:>3d}  "
              f"flags={stats['flags']:>3d}")

    if not flagged:
        print("\n✅ No simultaneous-concentration violations detected.")
        return

    out = (pd.DataFrame(flagged)
           .drop_duplicates(subset=["position_class", "geo_scope",
                                    "person_a_pol_id", "person_b_pol_id",
                                    "overlap_window"])
           .sort_values(["position_class", "geo_scope",
                         "overlap_window", "person_a_name"])
           .reset_index(drop=True))

    os.makedirs(os.path.dirname(OUTPUT_REPORT_CSV), exist_ok=True)
    out.to_csv(OUTPUT_REPORT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n🚨 SIMULTANEOUS SIMULATION COMPLETE — "
          f"{len(out):,} concentration violation(s) flagged.")
    print(f"💾 Report → '{OUTPUT_REPORT_CSV}'")


if __name__ == "__main__":
    main()