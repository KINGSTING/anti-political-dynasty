/**
 * Dataset configuration — one entry per pipeline tier.
 */
const DATASETS = {
  PN1: {
    label: "National", shortLabel: "PN1",
    description: "President, VP, Senators, HOR",
    nodes: "data/PN1_nodes.csv",
    edges: "data/PN1_edges.csv",
    seats: "data/PN1_seats.csv",
    sim: {
      history:   "data/electoral_history.csv",
      crosswalk: "data/per_to_pol.csv",
      seatMeta:  "data/PN1_seats.csv",
    },
  },
  PN2: { label: "National + Subnational", shortLabel: "PN2", description: "Senators, HOR, Governors, Vice Governors",
         nodes: "data/PN2_nodes.csv", edges: "data/PN2_edges.csv", seats: "data/PN2_seats.csv" },
  PN3: { label: "Local", shortLabel: "PN3", description: "Provinces, Cities, Municipalities — 17,805 officials",
         nodes: "data/PN3_nodes.csv", edges: "data/PN3_edges.csv", seats: "data/PN3_seats.csv" },
};

const CONSENSUS_META = {
  Verified_Kinship:    { color: "#2ecc71", label: "Verified Kinship (PN1)" },
  Verified_Pulitiklan: { color: "#e74c3c", label: "Verified (external source)" },
  Rule_Based_GT:       { color: "#f39c12", label: "Rule-based ground truth" },
  Baseline_Mindanao:   { color: "#7f8c8d", label: "Mindanao baseline" },
  Consensus_High:      { color: "#3498db", label: "Consensus high" },
  Single_Method:       { color: "#95a5a6", label: "Single method" },
  Low_Confidence:      { color: "#bdc3c7", label: "Low confidence" },
  Contradicted:        { color: "#e91e63", label: "Contradicted" },
  Duplicate_Record:    { color: "#9b59b6", label: "Duplicate record" },
};

const REGIONS = {
  "01": "Region I — Ilocos", "02": "Region II — Cagayan Valley", "03": "Region III — Central Luzon",
  "04": "Region IV-A — CALABARZON", "05": "Region V — Bicol", "06": "Region VI — Western Visayas",
  "07": "Region VII — Central Visayas", "08": "Region VIII — Eastern Visayas",
  "09": "Region IX — Zamboanga Peninsula", "10": "Region X — Northern Mindanao",
  "11": "Region XI — Davao", "12": "Region XII — SOCCSKSARGEN", "13": "NCR — Metro Manila",
  "14": "CAR — Cordillera", "15": "BARMM — Bangsamoro", "16": "Region XIII — Caraga",
  "17": "MIMAROPA", "19": "BARMM",
};

const POSITION_META = {
  President:            { shape: "star",         color: "#FFD700", border: "#B8860B", size: 26, label: "President" },
  Vice_President:       { shape: "star",         color: "#C0C0C0", border: "#808080", size: 24, label: "Vice President" },
  Senator:              { shape: "hexagon",      color: "#1E3A8A", border: "#0F172A", size: 20, label: "Senator" },
  HOR_Member:           { shape: "triangle",     color: "#7C3AED", border: "#4C1D95", size: 18, label: "Congressman" },
  Governor:             { shape: "diamond",      color: "#DC2626", border: "#7F1D1D", size: 18, label: "Governor" },
  Vice_Governor:        { shape: "diamond",      color: "#F97316", border: "#7C2D12", size: 16, label: "Vice Governor" },
  Board_Member:         { shape: "box",          color: "#78350F", border: "#451A03", size: 12, label: "Board Member" },
  City_Mayor:           { shape: "triangleDown", color: "#0D9488", border: "#115E59", size: 16, label: "City Mayor" },
  City_Vice_Mayor:      { shape: "triangleDown", color: "#06B6D4", border: "#0E7490", size: 14, label: "City Vice Mayor" },
  City_Councilor:       { shape: "dot",          color: "#5EEAD4", border: "#14B8A6", size: 11, label: "City Councilor" },
  Municipal_Mayor:      { shape: "box",          color: "#16A34A", border: "#14532D", size: 15, label: "Municipal Mayor" },
  Municipal_Vice_Mayor: { shape: "box",          color: "#84CC16", border: "#3F6212", size: 13, label: "Municipal Vice Mayor" },
  Municipal_Councilor:  { shape: "dot",          color: "#BBF7D0", border: "#4ADE80", size: 10, label: "Municipal Councilor" },
  Unknown:              { shape: "dot",          color: "#95A5A6", border: "#7F8C8D", size: 10, label: "Unknown" },
};

// ---- Policy scenarios (S1–S8) ----
const SCENARIOS = {
  S1: { label: "HB 8389 Baseline",          k: 2, temporal: "simultaneous", jurisdiction: "same_chamber",       includePartyList: false },
  S2: { label: "HB 8389 + Succession",       k: 2, temporal: "both",         jurisdiction: "same_chamber",       includePartyList: false },
  S3: { label: "Senate Moderate",            k: 2, temporal: "simultaneous", jurisdiction: "cross_chamber",      includePartyList: true  },
  S4: { label: "Senate Committee Standard",  k: 2, temporal: "both",         jurisdiction: "national_wide",      includePartyList: true  },
  S5: { label: "Expanded Kinship (3rd)",     k: 3, temporal: "both",         jurisdiction: "national_wide",      includePartyList: true  },
  S6: { label: "Comprehensive Reform (4th)", k: 4, temporal: "both",         jurisdiction: "national_wide",      includePartyList: true  },
  S7: { label: "Nationwide 2nd Degree",      k: 2, temporal: "both",         jurisdiction: "nationwide_blanket", includePartyList: true  },
  S8: { label: "Maximalist Reform",          k: 4, temporal: "both",         jurisdiction: "nationwide_blanket", includePartyList: true, successionGap: 6 },
};