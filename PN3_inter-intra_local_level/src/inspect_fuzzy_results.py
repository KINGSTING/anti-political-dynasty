"""Inspect fuzzy matching output — verify new and dropped edges."""

import re
from collections import Counter

import pandas as pd

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data"

NODES    = f"{BASE}\\inter-intra_local_nodes.csv"
ORIGINAL = f"{BASE}\\inter-intra_local_edges_merged.csv"
FUZZY    = f"{BASE}\\inter-intra_local_edges_fuzzy_validated.csv"
NEW      = f"{BASE}\\inter-intra_local_edges_fuzzy_new.csv"


# ==================== HELPERS ====================
def norm(s):
    """Same normalization the fuzzy script uses — strips suffix from last token."""
    if pd.isna(s):
        return ""
    s = str(s).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    s = re.sub(r"\s+(JR|SR|II|III|IV|V|VI)$", "", s).strip()
    return " ".join(s.split())


def surname_of(full_name):
    """Extract last token after normalization; returns '' if artifact (single char)."""
    parts = norm(full_name).split()
    if not parts:
        return ""
    last = parts[-1]
    return last if len(last) >= 2 else ""   # ✅ skip single-char parsing artifacts


COMMON_SURNAMES = {
    "DELA CRUZ", "DELACRUZ", "REYES", "SANTOS", "GARCIA", "RAMOS", "MENDOZA",
    "BAUTISTA", "CASTILLO", "VILLANUEVA", "AQUINO", "CRUZ", "SANTIAGO",
    "GONZALES", "GONZALEZ", "PEREZ", "RODRIGUEZ", "TORRES", "FLORES", "RIVERA",
    "DIAZ", "MARTINEZ", "AGUILAR", "NAVARRO", "MORALES", "DOMINGUEZ",
    "VILLAREAL", "MAGBANUA", "JAVIER", "TOLENTINO", "SALAZAR", "LIM",
    "TAN", "SY", "CHUA", "GO", "ONG",
}


def load():
    nodes = pd.read_csv(NODES, dtype=str, keep_default_na=False)
    orig  = pd.read_csv(ORIGINAL, dtype=str, keep_default_na=False)
    fuzzy = pd.read_csv(FUZZY, dtype=str, keep_default_na=False)
    new   = (pd.read_csv(NEW, dtype=str, keep_default_na=False)
             if pd.io.common.file_exists(NEW) else pd.DataFrame())
    id2name = dict(zip(nodes["person_id"], nodes["full_name_clean"]))
    id2node = nodes.set_index("person_id").to_dict("index")
    return orig, fuzzy, new, id2name, id2node


# ==================== NEW EDGES ====================
def show_new_edges(new, id2name, n=15):
    print(f"\n=== NEW EDGES ({len(new)}) ===")
    if len(new) == 0:
        print("  (none)")
        return
    print(new["fuzzy_verdict"].value_counts().to_string())
    print()
    for _, e in new.head(n).iterrows():
        a = id2name.get(e["person_a_id"], "?")
        b = id2name.get(e["person_b_id"], "?")
        v = e["fuzzy_verdict"]
        p = e["probability"]
        print(f"[{v:<18}] P={p:<5}  {a}  <->  {b}")


# ==================== DROPPED EDGES ====================
def show_dropped_edges(orig, fuzzy, id2name, id2node, n=20):
    def key(e):
        return tuple(sorted([e["person_a_id"], e["person_b_id"]]))

    orig_keys  = {key(e) for _, e in orig.iterrows()}
    fuzzy_keys = {key(e) for _, e in fuzzy.iterrows()}
    dropped    = orig_keys - fuzzy_keys

    # ✅ Build lookup so we know each dropped edge's original relation_label
    orig_by_key = {key(e): e.to_dict() for _, e in orig.iterrows()}

    print(f"\n=== DROPPED EDGES ({len(dropped)}) ===")
    for k in list(dropped)[:n]:
        a = id2name.get(k[0], "?")
        b = id2name.get(k[1], "?")
        rel = orig_by_key.get(k, {}).get("relation_label", "?")
        print(f"  [{rel:<22}] {a}  <->  {b}")

    # ---- Drops by relation label (tells us WHICH signals were filtered) ----
    drop_by_label = Counter()
    for k in dropped:
        rel = orig_by_key.get(k, {}).get("relation_label", "unknown")
        drop_by_label[rel] += 1

    print(f"\n  Drops by relation_label:")
    for rel, cnt in drop_by_label.most_common():
        print(f"    {rel:<25} {cnt}")

    # ✅ For each dropped edge, identify the SIGNAL that triggered the drop
    #    (last name for Distant_Kin/Sibling/Parent_Child; middle for Shared_Maternal_Line)
    def triggering_signal(k):
        rel = orig_by_key.get(k, {}).get("relation_label", "")
        if rel == "Shared_Maternal_Line":
            mid = norm(id2node.get(k[0], {}).get("middle_name", ""))
            return mid, "middle"
        else:
            sn = surname_of(id2name.get(k[0], ""))
            return sn, "last"

    # ---- Surname breakdown using the TRIGGERING signal (not last names) ----
    trigger_surnames = Counter()
    for k in dropped:
        sn, _ = triggering_signal(k)
        if sn:
            trigger_surnames[sn] += 1

    print(f"\n  Top surnames that TRIGGERED the drop:")
    for surname, cnt in trigger_surnames.most_common(15):
        print(f"    {surname:<25} {cnt}")

    # ---- Genuine rare drops: triggering surname is NOT common ----
    rare_drops = []
    for k in dropped:
        sn, source = triggering_signal(k)
        if not sn or len(sn) < 2:           # skip artifacts
            continue
        if sn in COMMON_SURNAMES:            # correctly dropped
            continue
        rare_drops.append((k, sn, source, orig_by_key.get(k, {}).get("relation_label", "?")))

    if rare_drops:
        print(f"\n  ⚠ {len(rare_drops)} dropped edges with NON-common TRIGGERING surname:")
        for k, sn, src, rel in rare_drops[:10]:
            a = id2name.get(k[0], "?")
            b = id2name.get(k[1], "?")
            print(f"    [{rel:<22}] {sn:<15} ({src})  {a}  <->  {b}")
        if len(rare_drops) > 10:
            print(f"    ... and {len(rare_drops) - 10} more")
        print(f"\n  → These deserve manual review. If any are real dynasties,")
        print(f"    add the surname+province to DYNASTIC_EXCEPTIONS in fuzzy_validate_edges.py")
    else:
        print(f"\n  ✅ All dropped edges have common TRIGGERING surnames — filter is calibrated correctly")


# ==================== MAIN ====================
def main():
    orig, fuzzy, new, id2name, id2node = load()
    print(f"Original edges : {len(orig)}")
    print(f"After fuzzy    : {len(fuzzy)}")
    print(f"New discovered : {len(new)}")

    show_new_edges(new, id2name)
    show_dropped_edges(orig, fuzzy, id2name, id2node)

    # ---- Summary verdict ----
    print(f"\n{'=' * 60}")
    net = len(fuzzy) - len(orig)
    print(f"Net change: {net:+d} edges ({net/len(orig)*100:+.1f}%)")
    if net < 0:
        print("✅ Filter removed more than it added — common-surname noise was the bulk")
    else:
        print("⚠ Expansion outgrew filtering — review new edges carefully")


if __name__ == "__main__":
    main()