# Methodology — Philippine Political Kinship Network (2022–2025)

## 1. Scope

This dataset encodes the kinship relations among Philippine incumbent
elected officials serving in the 20th Congress (2022–2025 term, 2025
midterm cohort) and the 2025 provincial governors. Nodes represent
individual officials; edges represent civil relations up to the fourth
degree as defined under the Philippine Civil Code (Articles 963–966).

Officials included:

- President (1)
- Vice President (1)
- Senators (24)
- Members of the House of Representatives (317)
- Provincial Governors (84)

Total unique nodes: [N]
Total undirected edges: [E]
Snapshot date: [DATE]

## 2. Node inclusion criteria

An individual is included as a node if and only if they were an
incumbent elected official as of [DATE], having won in either the 2022
or 2025 national and local elections. Officials who lost reelection,
were term-limited out, resigned, or were appointed (rather than
elected) are excluded.

Notable exclusions at the national level:
- Former Senator Manny Pacquiao (not reelected 2025)
- Former Senator Panfilo "Ping" Lacson (retired 2025)
- Appointed Cabinet secretaries (not elected)

## 3. Edge inclusion criteria

Two nodes are connected by an edge if and only if:

1. A documented civil relation exists between them under Philippine
   law, and
2. That relation falls within the fourth civil degree, and
3. Both endpoints are simultaneously serving as incumbent officials
   at the time of the snapshot.

Relations are classified into two categories per Article 964:

- **Consanguinity** — blood relation
- **Affinity** — legal relation through marriage

Civil degrees are assigned per Articles 965–966:

| Degree | Consanguinity | Affinity |
|--------|---------------|----------|
| 1st    | Parent, Child | Spouse; Parent-in-law; Child-in-law |
| 2nd    | Sibling; Grandparent; Grandchild | Sibling-in-law; Grandparent-in-law; Grandchild-in-law |
| 3rd    | Uncle/Aunt; Nephew/Niece; Great-grandparent; Great-grandchild | Uncle/Aunt-in-law; Nephew/Niece-in-law |
| 4th    | First Cousin; Grandnephew/Grandniece; Great-great-grandparent; Great-great-grandchild | First Cousin-in-law |

Relations beyond the fourth degree are excluded even when documented.

## 4. Data sources

Each edge is traceable to at least one publicly available source.
Primary sources used:

1. **CSP-65 Statistical Inventory of Potential Political Dynasts**
   (Congressional Policy and Budget Research Department, House of
   Representatives) — used as the primary corroborating source for
   provincial dynasty membership.
2. **PulitiKlan.com** — used as a secondary corroborating source for
   family composition.
3. **Wikipedia biographical entries** — used for basic genealogical
   facts (parents, siblings, spouses, children).
4. **Official government biographies** (Senate, House, provincial
   government websites) — used where available.
5. **Contemporaneous news reports** (Inquirer, Rappler, PhilStar,
   Manila Bulletin) — used for recently confirmed or contested
   relations.

Where the SERB inventory and PulitiKlan agree on a relation, the edge
is marked as high-confidence. Where only one source supports a
relation, the edge is marked as medium-confidence and flagged for
manual review.

## 5. Excluded pairs and control checks

Not every shared surname reflects a kinship relation. Every pair of
incumbent officials sharing a surname was investigated; pairs that
were confirmed *unrelated* within the fourth degree are documented in
`excluded_pairs.csv` with the reason for exclusion. This file exists
to demonstrate that surname coincidence was systematically ruled out
rather than overlooked.

Common categories of exclusion:

- **Political allies with distinct lineages** — e.g., Yap and Cojuangco
  in Tarlac cooperate at the provincial level but belong to separate
  families.
- **Surname coincidence across regions** — e.g., Umali of Nueva Ecija
  and Umali of Oriental Mindoro; Uy of Misamis Oriental and Uy of
  Davao del Norte.
- **Historical kinship beyond 4th degree** — Lacsons of Negros
  Occidental and Lacsons of Cavite share distant common ancestry but
  not within the civil-degree limit.

## 6. Known limitations

1. **Incomplete source coverage.** The SERB inventory covers the House
   and provincial governors but does not enumerate the Senate or the
   executive. Senate relations were verified primarily through
   Wikipedia and news sources.

2. **Isolated nodes.** A substantial fraction of governor nodes have
   no edges. This is not a data gap — it reflects the fact that many
   provincial dynasties hold no national-level office within the
   fourth civil degree. Such families are *locally dominant but
   nationally disconnected*, which is itself a finding relevant to
   anti-political dynasty policy debate.

3. **Simultaneity snapshot.** The graph captures a single point in
   time. Succession-based dynasties (where a relative runs for the
   same office immediately after a term-limited incumbent) are not
   captured because they never hold office simultaneously.

4. **Spouse-of-spouse chains.** Affinity relations are only encoded
   where the two endpoints are themselves officials. In-law
   relations requiring an intermediate non-official node are omitted.

5. **Self-reported and news-sourced data.** All relations are drawn
   from public sources. No independent genealogical verification was
   performed beyond cross-referencing the sources listed in Section 4.

## 7. Reproducibility

The dataset is stored as two plain-text files:

- `kinship_nodes.csv` — one row per official
- `kinship_edges.txt` — one line per directed relation, format:
  `person_a : person_b -> relation : civil_degree : kinship_type`

The graph visualization script (`congress_kgn.py`) reads both files
and renders the network with position-based node styling and
civil-degree edge styling. Reciprocal edges are collapsed into a
single undirected edge for display.

## 8. Contact

[Your name and email]


Name disambiguation. All name matching required exact token-set equality, not subset matching. This prevented false-positive matches between individuals sharing a first and last name (e.g., Bonifacio Lacwasan Sr. and Bonifacio Lacwasan Jr.; Ferdinand Martin "Marty" Romualdez and his father Ferdinand Martin G. Romualdez) and between named relatives distinguished only by nickname (Rebecca "Nini" Ynares and her daughter Rebecca Maria "Mia" Ynares). Nicknames in quotation marks were preserved as distinguishing tokens rather than stripped.