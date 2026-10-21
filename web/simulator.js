// simulator.js — provision-axis engine

const TERM_LENGTH = {
  SENATOR: 6, PRESIDENT: 6, VICE_PRESIDENT: 6,
  PARTY_LIST: 3, MEMBER_HOUSE_OF_REPRESENTATIVES: 3,
  GOVERNOR: 3, VICE_GOVERNOR: 3, BOARD_MEMBER: 3,
  MAYOR: 3, VICE_MAYOR: 3, COUNCILOR: 3
};

function classifySeatId(seatId) {
  const s = (seatId || "").toUpperCase().replace(/-{2,}/g, "-").replace(/^-|-$/g, "");
  if (s.startsWith("PH-NAT-SEN") || s.startsWith("PH-SENATOR")) return { posClass: "SENATOR", geo: "PH", chamber: "SENATE" };
  if (s.startsWith("PH-NAT-PRES") || s.startsWith("PH-PRESIDENT")) return { posClass: "PRESIDENT", geo: "PH", chamber: "EXEC" };
  if (s.startsWith("PH-NAT-VP") || s.startsWith("PH-VICE_PRESIDENT")) return { posClass: "VICE_PRESIDENT", geo: "PH", chamber: "EXEC" };
  if (s.startsWith("PH-PL-") || s.startsWith("PH-PARTY_LIST")) return { posClass: "PARTY_LIST", geo: "PH", chamber: "HOUSE" };
  if (s.startsWith("PH-DIST-") || s.startsWith("PH-MEMBER_HOUSE") || s.startsWith("PH-REPRESENTATIVE")) {
    const parts = s.split("-");
    const province = parts[2] || "";
    return { posClass: "MEMBER_HOUSE_OF_REPRESENTATIVES", geo: province, chamber: "HOUSE" };
  }
  const parts = s.split("-");
  if (parts.length >= 2) {
    return { posClass: parts[1], geo: parts[2] || "UNKNOWN", chamber: "LOCAL" };
  }
  return null;
}

function pairKey(a, b) { return a < b ? `${a}|${b}` : `${b}|${a}`; }

function buildTermRecords(history, perToPol, seatMeta) {
  const out = [];
  for (const h of history) {
    if (String(h.is_winner).toLowerCase() !== "true") continue;
    const year = parseInt(h.election_year, 10);
    if (!year || year < 2000) continue;
    const pol = perToPol.get(h.person_id);
    if (!pol) continue;
    const seat = seatMeta.get(h.seat_id) || classifySeatId(h.seat_id);
    if (!seat || !seat.posClass) continue;
    const termLen = TERM_LENGTH[seat.posClass] || 3;
    out.push({
      personId: pol, perId: h.person_id, seatId: h.seat_id,
      posClass: seat.posClass, geo: seat.geo, chamber: seat.chamber,
      electionYear: year, termStart: year, termEnd: year + termLen,
    });
  }
  return out;
}

function runScenario(state, axes) {
  const flags = [];
  const disqualifiedSet = new Set();
  const seen = new Set();
  
  // Helper to check if a person is in the graph (incumbent)
  const isIncumbent = (id) => state.nodes.some(n => n.person_id === id);

  // 1. SIMULTANEOUS RULE
  // Since PN1_nodes.csv is the list of incumbents, any edge between them is a violation.
  if (axes.temporal === "simultaneous" || axes.temporal === "both") {
    state.edges.forEach(e => {
      const a = e.person_a_id;
      const b = e.person_b_id;
      
      // Both must be in the graph (incumbents)
      if (!isIncumbent(a) || !isIncumbent(b)) return;

      const link = state.simData.kinship.get(pairKey(a, b));
      if (!link || link.degree > axes.k) return;
      
      const posA = state.positions[a]?.position_type || "Unknown";
      const posB = state.positions[b]?.position_type || "Unknown";
      
      if (!axes.includePartyList && (posA.includes("Party") || posB.includes("Party"))) {
          return;
      }

      const key = `SIMULTANEOUS|${pairKey(a, b)}`;
      if (seen.has(key)) return;
      seen.add(key);

      flags.push({
        rule: "SIMULTANEOUS",
        person_a: { polId: a, seat: "Current", electionYear: 2025, term: "2025", positionClass: posA },
        person_b: { polId: b, seat: "Current", electionYear: 2025, term: "2025", positionClass: posB },
        relation: link.relation,
        degree: link.degree,
        groupKey: "PH",
        overlap: "2025"
      });
    });
  }

  // 2. SUCCESSION RULE
  // We use the electoral history to find if one succeeded the other.
  if (axes.temporal === "succession" || axes.temporal === "both") {
    const target = state.simData.terms.filter(r => r.termStart <= 2025 && 2025 <= r.termEnd);
    const gap = axes.successionGap || 3;
    
    for (const t of target) {
      const prior = state.simData.terms.filter(p =>
        p.electionYear === 2025 - gap &&
        p.seatId === t.seatId && p.personId !== t.personId
      );
      for (const p of prior) {
        const link = state.simData.kinship.get(pairKey(t.personId, p.personId));
        if (!link || link.degree > axes.k) continue;
        
        const key = `SUCCESSION|${pairKey(t.personId, p.personId)}|${t.seatId}`;
        if (seen.has(key)) continue;
        seen.add(key);
        
        flags.push({
          rule: "SUCCESSION",
          person_a: { polId: p.personId, seat: p.seatId, electionYear: p.electionYear, term: `${p.termStart}-${p.termEnd}`, positionClass: p.posClass },
          person_b: { polId: t.personId, seat: t.seatId, electionYear: t.electionYear, term: `${t.termStart}-${t.termEnd}`, positionClass: t.posClass },
          relation: link.relation,
          degree: link.degree,
          groupKey: t.seatId,
          overlap: null
        });
      }
    }
  }

  // Deduplicate
  const deduped = [];
  const dedupeKeys = new Set();
  flags.forEach(f => {
    const k = `${f.rule}|${pairKey(f.person_a.polId, f.person_b.polId)}|${f.groupKey}`;
    if (!dedupeKeys.has(k)) {
      dedupeKeys.add(k);
      deduped.push(f);
    }
  });

  // Disqualified Logic
  if (axes.resolution && axes.resolution !== "flag_only") {
    for (const f of deduped) {
      if (f.rule === "SUCCESSION") {
        disqualifiedSet.add(f.person_b.polId);
        continue;
      }
      if (axes.resolution === "remove_later") {
        const later = f.person_a.electionYear >= f.person_b.electionYear ? f.person_a : f.person_b;
        disqualifiedSet.add(later.polId);
      } else if (axes.resolution === "remove_all") {
        disqualifiedSet.add(f.person_a.polId);
        disqualifiedSet.add(f.person_b.polId);
      }
    }
  }

  return {
    flags: deduped,
    disqualified: disqualifiedSet,
    summary: {
      targetYear: 2025,
      targetWinners: state.nodes.length, // Use graph nodes for simultaneous
      flaggedPairs: deduped.length,
      disqualifiedCount: disqualifiedSet.size,
    },
  };
}