"""
Cross-validate kinship_edges.txt against PulitiKlan datasets.

Fixes:
  - Strict name matching (full-token subset; no first-name collisions)
  - Direction-aware relation comparison (Son vs Father->son is a MATCH)
  - New-edges filter: only emits edges where BOTH endpoints are in your nodes file
"""

import os
import re
import csv
from collections import defaultdict

VISAYAS_FILE = os.path.join("data", "# PULITIKLAN — Visayas coverage and.txt")
LUZON_FILE   = os.path.join("data", "luzon-research.md")
NODES_FILE   = "kinship_nodes.csv"
EXISTING_EDGES_FILE = "kinship_edges.txt"

OUT_VERIFIED = "pulitiklan_verification.csv"
OUT_CONTRA   = "pulitiklan_contradictions.csv"
OUT_NEW      = "pulitiklan_new_edges.txt"

EDGE_RE = re.compile(
    r"^-\s+(?P<a>.+?)\s+→\s+(?P<b>.+?):\s+\*\*(?P<rel>.+?)\*\*\."
)

# ---------- name normalization ----------

def normalize_name(name):
    name = re.sub(r"[*_]", "", name)
    name = re.sub(r'[“”"\'\(\)\[\]]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def name_tokens(name):
    """All alphanumeric tokens, lowercased. Keeps jr/sr/roman numerals as
    distinguishing tokens so 'Ferdinand Marcos Sr.' and 'Ferdinand Alexander
    Marcos' do not collapse to the same set."""
    n = normalize_name(name).lower()
    toks = [t.strip(",.") for t in re.split(r"[\s,]+", n) if t.strip(",.")]
    return [t for t in toks if len(t) > 1]

def names_match(a, b):
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
    sa = ta.pop() if ta[-1] in SUFFIXES else None
    sb = tb.pop() if tb[-1] in SUFFIXES else None
    if not ta or not tb:
        return False
    if ta[-1] != tb[-1]:                    # surname must match
        return False
    if ta[0] != tb[0]:                      # first name must match
        return False
    if sa != sb:                            # suffix must match exactly
        return False
    ma, mb = set(ta[1:-1]), set(tb[1:-1])
    if not (ma <= mb or mb <= ma):          # middles: subset either way
        return False
    return True

def pair_match(a1, b1, a2, b2):
    """Same unordered pair of people?"""
    return (names_match(a1, a2) and names_match(b1, b2)) or \
           (names_match(a1, b2) and names_match(b1, a2))

# ---------- relation classification ----------

def classify_role(label):
    """Canonical role of X relative to Y."""
    s = re.sub(r"[*_]", "", label).lower()
    s = re.sub(r"[.,;:()].*", "", s).strip()

    if s in ("father", "mother", "parent", "dad", "mom"): return "parent"
    if s in ("son", "daughter", "child"): return "child"
    if s in ("brother", "sister", "sibling", "half-brother", "half-sister"): return "sibling"
    if s in ("spouse", "spouses", "husband", "wife", "married", "couple"): return "spouse"
    if s in ("uncle", "aunt"): return "uncle_aunt"
    if s in ("nephew", "niece"): return "nephew_niece"
    if "cousin" in s: return "cousin"
    if s in ("grandfather", "grandmother", "grandparent"): return "grandparent"
    if s in ("grandson", "granddaughter", "grandchild"): return "grandchild"
    if s in ("granduncle", "grandaunt"): return "granduncle_aunt"
    if s in ("grandnephew", "grandniece"): return "grandnephew_niece"
    if "in-law" in s or "in law" in s: return "in_law"
    if "step" in s: return "step"
    return "unknown"

INVERSE = {
    "parent": "child", "child": "parent",
    "sibling": "sibling", "spouse": "spouse",
    "uncle_aunt": "nephew_niece", "nephew_niece": "uncle_aunt",
    "cousin": "cousin",
    "grandparent": "grandchild", "grandchild": "grandparent",
    "granduncle_aunt": "grandnephew_niece", "grandnephew_niece": "granduncle_aunt",
    "in_law": "in_law", "step": "step", "unknown": "unknown",
}

def user_roles(rel_label):
    """User format: `A : B -> R` means 'B is A's R'."""
    b_role = classify_role(rel_label)
    a_role = INVERSE.get(b_role, "unknown")
    return (a_role, b_role)

def puliti_roles(rel_field):
    """PulitiKlan format: `X → Y: **R1 → R2**`. R1 = X's role relative to Y, R2 = Y's role relative to X."""
    for arrow in ("→", "->"):
        if arrow in rel_field:
            left, right = rel_field.split(arrow, 1)
            return (classify_role(left), classify_role(right))
    r = classify_role(rel_field)
    return (r, INVERSE.get(r, "unknown"))

def roles_equivalent(u, p):
    """Compare (a_role, b_role) tuples. Unknown acts as a wildcard."""
    ua, ub = u
    pa, pb = p
    if "unknown" in (ua, ub, pa, pb):
        return True
    return ua == pa and ub == pb

# ---------- parsers ----------

def parse_pulitiklan(path):
    edges = []
    if not os.path.exists(path):
        print(f"[WARN] missing: {path}")
        return edges
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = EDGE_RE.match(line.rstrip())
            if not m:
                continue
            a = normalize_name(m.group("a"))
            b = normalize_name(m.group("b"))
            rel = m.group("rel").strip()
            if not a or not b or "http" in a.lower() or "http" in b.lower():
                continue
            edges.append({"a": a, "b": b, "relation": rel,
                          "source": os.path.basename(path)})
    return edges

def parse_existing(path):
    pattern = re.compile(
        r"^(?P<a>.+?)\s*:\s*(?P<b>.+?)\s*->\s*(?P<rel>.+?)\s*:\s*"
        r"(?P<deg>[^:]+?)\s*:\s*(?P<type>\w+)\s*$"
    )
    edges = []
    if not os.path.exists(path):
        print(f"[WARN] missing: {path}")
        return edges
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                edges.append({"a": m.group("a").strip(), "b": m.group("b").strip(),
                              "relation": m.group("rel").strip(),
                              "degree": m.group("deg").strip(),
                              "type": m.group("type").strip()})
    return edges

def load_node_names(path):
    names = []
    if not os.path.exists(path):
        return names
    with open(path, encoding="utf-8-sig") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if row and row[0].strip():
                names.append(row[0].strip())
    return names

# ---------- main ----------

def main():
    puliti = parse_pulitiklan(VISAYAS_FILE) + parse_pulitiklan(LUZON_FILE)
    existing = parse_existing(EXISTING_EDGES_FILE)
    node_names = load_node_names(NODES_FILE)

    print(f"Parsed {len(puliti)} edges from PulitiKlan")
    print(f"Parsed {len(existing)} edges from {EXISTING_EDGES_FILE}")
    print(f"Loaded {len(node_names)} node names from {NODES_FILE}")

    verified, contradicted = [], []
    matched = 0

    for ue in existing:
        ua, ub, urel = ue["a"], ue["b"], ue["relation"]
        u_roles = user_roles(urel)
        hits = []
        for pe in puliti:
            if not pair_match(ua, ub, pe["a"], pe["b"]):
                continue
            same_order = names_match(ua, pe["a"]) and names_match(ub, pe["b"])
            pa_role, pb_role = puliti_roles(pe["relation"])
            if not same_order:
                pa_role, pb_role = pb_role, pa_role  # swap to match our A/B order
            hits.append((pe, pa_role, pb_role))
        if not hits:
            continue
        matched += 1
        for pe, pa_role, pb_role in hits:
            row = {
                "existing_a": ua, "existing_b": ub,
                "existing_relation": urel,
                "existing_a_role": u_roles[0], "existing_b_role": u_roles[1],
                "puliti_a": pe["a"], "puliti_b": pe["b"],
                "puliti_relation": pe["relation"],
                "puliti_a_role": pa_role, "puliti_b_role": pb_role,
                "source": pe["source"],
            }
            if roles_equivalent(u_roles, (pa_role, pb_role)):
                verified.append(row)
            else:
                contradicted.append(row)

    # New edges: PulitiKlan has, our dataset doesn't, and BOTH endpoints
    # already appear in our nodes file (so the edge is actionable now).
    existing_pairs = [(e["a"], e["b"]) for e in existing]
    def already_covered(a, b):
        for ea, eb in existing_pairs:
            if pair_match(a, b, ea, eb):
                return True
        return False

    def in_nodes(name):
        return any(names_match(name, n) for n in node_names)

    new_edges = []
    seen = set()
    for pe in puliti:
        if already_covered(pe["a"], pe["b"]):
            continue
        if not (in_nodes(pe["a"]) and in_nodes(pe["b"])):
            continue
        key = (pe["a"].lower(), pe["b"].lower(), pe["relation"].lower())
        if key in seen:
            continue
        seen.add(key)
        new_edges.append(pe)

    print(f"\n--- Cross-reference ---")
    print(f"Existing edges with a PulitiKlan match: {matched}")
    print(f"  Verified:       {len(verified)}")
    print(f"  Contradictions: {len(contradicted)}")
    print(f"New edges (both endpoints in your nodes file): {len(new_edges)}")

    with open(OUT_VERIFIED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "existing_a", "existing_b", "existing_relation",
            "existing_a_role", "existing_b_role",
            "puliti_a", "puliti_b", "puliti_relation",
            "puliti_a_role", "puliti_b_role", "source"])
        w.writeheader(); w.writerows(verified)

    with open(OUT_CONTRA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "existing_a", "existing_b", "existing_relation",
            "existing_a_role", "existing_b_role",
            "puliti_a", "puliti_b", "puliti_relation",
            "puliti_a_role", "puliti_b_role", "source"])
        w.writeheader(); w.writerows(contradicted)

    with open(OUT_NEW, "w", encoding="utf-8") as f:
        for h in new_edges:
            f.write(f"{h['a']} : {h['b']} -> {h['relation']}  [{h['source']}]\n")

    print(f"\n[OK] {os.path.abspath(OUT_VERIFIED)}")
    print(f"[OK] {os.path.abspath(OUT_CONTRA)}")
    print(f"[OK] {os.path.abspath(OUT_NEW)}")

    if contradicted:
        print(f"\n[!] {len(contradicted)} potential contradiction(s):")
        for c in contradicted[:10]:
            print(f"  {c['existing_a']} ↔ {c['existing_b']}: "
                  f"you: '{c['existing_relation']}' "
                  f"({c['existing_a_role']}/{c['existing_b_role']}) vs "
                  f"PK: '{c['puliti_relation']}' "
                  f"({c['puliti_a_role']}/{c['puliti_b_role']})")

if __name__ == "__main__":
    main()