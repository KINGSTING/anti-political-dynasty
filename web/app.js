// Global state
const state = {
  dataset: "PN1",
  nodes: [], edges: [], positions: {}, psgcNames: {}, network: null,
  nodeDataSet: null, edgeDataSet: null,
  simData: null, simulation: null,
  activeScenario: "S4",
  globalHistory: null, perToPol: null
};

async function fetchCSV(url) {
  // Add a timestamp to the URL so the browser NEVER caches the CSV
  const cacheBuster = new Date().getTime();
  const separator = url.includes('?') ? '&' : '?';
  const finalUrl = `${url}${separator}v=${cacheBuster}`;
  
  const res = await fetch(finalUrl);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  const text = await res.text();
  return new Promise((resolve, reject) => {
    Papa.parse(text, {
      header: true, skipEmptyLines: true, dynamicTyping: false,
      complete: (r) => resolve(r.data), error: reject,
    });
  });
}

// ULTIMATE LOCATION MAPPING
function getLocationName(psgcCode) {
  if (!psgcCode) return "Unknown Location";
  if (!state.psgcNames || Object.keys(state.psgcNames).length === 0) return psgcCode;

  const cleanCode = String(psgcCode).trim();
  
  // Generate every possible variation of the code
  const variants = [
    cleanCode,                          // "012800000"
    cleanCode + "0",                    // "0128000000"
    cleanCode.replace(/^0+/, ''),       // "12800000"
    cleanCode.replace(/^0+/, '') + "0", // "1280000000"
    parseInt(cleanCode, 10).toString(), // "12800000"
    parseInt(cleanCode, 10).toString() + "0" // "1280000000"
  ];

  // 1. Try exact string matches for all variants
  for (const v of variants) {
    if (state.psgcNames[v]) {
      const val = state.psgcNames[v];
      return typeof val === 'string' ? val : (val.name || val.location || JSON.stringify(val));
    }
  }

  // 2. Try numeric matches (in case the JSON keys are numbers)
  for (const v of variants) {
    const num = Number(v);
    if (state.psgcNames[num]) {
      const val = state.psgcNames[num];
      return typeof val === 'string' ? val : (val.name || val.location || JSON.stringify(val));
    }
  }

  // 3. Fallback: iterate through keys and compare parsed numbers
  const targetNum = parseInt(cleanCode, 10);
  const fuzzyKey = Object.keys(state.psgcNames).find(k => {
    return parseInt(k, 10) === targetNum || parseInt(k, 10) === targetNum * 10;
  });

  if (fuzzyKey && state.psgcNames[fuzzyKey]) {
    const val = state.psgcNames[fuzzyKey];
    return typeof val === 'string' ? val : (val.name || val.location || JSON.stringify(val));
  }

  return cleanCode; 
}

async function loadDataset(key) {
  document.getElementById("loading").classList.remove("hidden");
  const cfg = DATASETS[key];

  const [nodes, edges] = await Promise.all([
    fetchCSV(cfg.nodes),
    fetchCSV(cfg.edges)
  ]);

  let positions = {};
  try {
    positions = await (await fetch(`data/${key}_positions.json?v=${Date.now()}`)).json();
  } catch (e) {}

  state.dataset = key;
  state.nodes = nodes;
  state.edges = edges;
  state.positions = positions;

  const kinship = new Map();
  for (const e of state.edges) {
    const deg = parseInt(e.civil_degree, 10) || 99;
    const k = pairKey(e.person_a_id, e.person_b_id);
    if (!kinship.has(k) || kinship.get(k).degree > deg) {
      kinship.set(k, { relation: e.relation_label || "RELATIVE", degree: deg });
    }
  }

  if (!state.globalHistory) {
    const [history, crosswalk] = await Promise.all([
      fetchCSV("data/electoral_history.csv"),
      fetchCSV("data/per_to_pol.csv")
    ]);
    state.globalHistory = history;
    state.perToPol = new Map(crosswalk.map(r => [r.person_id, r.pol_id]));
  }

  const terms = buildTermRecords(state.globalHistory, state.perToPol, new Map());
  state.simData = { kinship, terms };

  state.simulation = null; 
  
  document.getElementById("info-box").innerHTML = `
    <div class="info-placeholder">
      <h3>Ready: ${key}</h3>
      <p>Open the menu (☰) to configure policy axes and run a simulation.</p>
    </div>`;
  
  if (state.network) state.network.destroy();
  state.network = null;
  renderGraph();
  document.getElementById("loading").classList.add("hidden");
}

async function boot() {
  buildScenarioGrid();
  
  try {
    state.psgcNames = await (await fetch("data/psgc_names.json?v=" + Date.now())).json();
    console.log("Loaded PSGC data.");
  } catch (e) {
    console.warn("Could not load psgc_names.json. Locations will show raw codes.");
  }

  await loadDataset("PN1");
}

function buildScenarioGrid() {
  const grid = document.getElementById("scenario-grid");
  Object.keys(SCENARIOS).forEach(key => {
    const btn = document.createElement("button");
    btn.className = `scenario-btn ${key === state.activeScenario ? 'active' : ''}`;
    btn.textContent = key;
    btn.title = SCENARIOS[key].label;
    btn.onclick = () => {
      document.querySelectorAll(".scenario-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeScenario = key;
      
      const s = SCENARIOS[key];
      document.getElementById("axis-simultaneous").checked = (s.temporal === "simultaneous" || s.temporal === "both");
      document.getElementById("axis-succession").checked = (s.temporal === "succession" || s.temporal === "both");
      document.getElementById("axis-partylist").checked = s.includePartyList;
      document.getElementById("axis-degree").value = s.k;
    };
    grid.appendChild(btn);
  });
  
  const defaultBtn = document.querySelector(`.scenario-btn:nth-child(${Object.keys(SCENARIOS).indexOf(state.activeScenario)+1})`);
  if (defaultBtn) defaultBtn.click();
}

function renderGraph() {
  const container = document.getElementById("graph");
  const dqSet = state.simulation?.disqualified || new Set();
  const flaggedKeys = state.simulation?.flaggedPairKeys || new Set();

  const connectedIds = new Set();
  state.edges.forEach(e => {
    connectedIds.add(e.person_a_id);
    connectedIds.add(e.person_b_id);
  });

  const nodes = state.nodes
    .filter(n => connectedIds.has(n.person_id))
    .map(n => {
      const posMeta = POSITION_META[state.positions[n.person_id]?.position_type] || POSITION_META.Unknown;
      const isDQ = dqSet.has(n.person_id);
      
      const lguName = getLocationName(n.home_psgc);
      
      return {
        id: n.person_id, 
        label: n.full_name_clean, 
        title: `${n.full_name_clean}\nLocation: ${lguName}`, 
        shape: posMeta.shape, 
        size: isDQ ? posMeta.size + 5 : posMeta.size,
        color: isDQ ? { background: "#7f0000", border: "#e74c3c" } : { background: posMeta.color, border: posMeta.border },
        borderWidth: isDQ ? 3 : 1,
        font: { color: "#bdc3c7", size: 12 } // Ensures labels are readable
      };
    });

  const edges = state.edges.map((e, idx) => {
    const isFlagged = flaggedKeys.has(pairKey(e.person_a_id, e.person_b_id));
    return {
      id: `e${idx}`, from: e.person_a_id, to: e.person_b_id,
      color: isFlagged ? "#e74c3c" : "#34495e",
      width: isFlagged ? 4 : 1,
      dashes: isFlagged
    };
  });

  state.nodeDataSet = new vis.DataSet(nodes);
  state.edgeDataSet = new vis.DataSet(edges);

  // Tuned Physics Options to bring nodes closer together
  const options = {
    edges: { width: 1 },
    physics: {
      enabled: state.physicsOn,
      barnesHut: { 
        gravitationalConstant: -2500, // Reduced from -8000 (pulls nodes closer)
        centralGravity: 0.4,          // Pulls everything towards the center
        springLength: 120,            // Length of the edges
        springConstant: 0.05,         // Stiffness of the edges
        avoidOverlap: 0.5             // Prevents labels from overlapping too much
      },
      stabilization: { iterations: 200 },
    },
    interaction: { hover: true, tooltipDelay: 100, multiselect: false },
  };

  if (state.network) {
    state.network.setData({ nodes: state.nodeDataSet, edges: state.edgeDataSet });
    state.network.setOptions(options);
    // Fit the graph to the screen after updating data
    setTimeout(() => state.network.fit({ animation: true }), 500);
  } else {
    state.network = new vis.Network(container, { nodes: state.nodeDataSet, edges: state.edgeDataSet }, options);
    
    // Auto-zoom and center the graph when it finishes stabilizing
    state.network.on("stabilizationIterationsDone", function () {
      state.network.fit({ animation: true });
    });

    state.network.on("click", function (params) {
      if (params.nodes.length > 0) {
        showNodeInfo(params.nodes[0]);
      }
    });
  }
}

function showNodeInfo(personId) {
  const node = state.nodes.find(n => n.person_id === personId);
  if (!node) return;

  const posData = state.positions[personId] || {};
  const posType = posData.position_type || "Unknown";
  const posMeta = POSITION_META[posType] || POSITION_META.Unknown;

  const locationName = getLocationName(node.home_psgc);

  const uniqueConnections = new Map();
  state.edges.forEach(e => {
    let otherId = null;
    let relation = e.relation_label;
    
    if (e.person_a_id === personId) otherId = e.person_b_id;
    else if (e.person_b_id === personId) otherId = e.person_a_id;

    if (otherId && !uniqueConnections.has(otherId)) {
      uniqueConnections.set(otherId, { relation: relation, degree: e.civil_degree });
    }
  });

  const connectionsHtml = Array.from(uniqueConnections.entries()).map(([otherId, data]) => {
    const otherNode = state.nodes.find(n => n.person_id === otherId);
    const isFlagged = state.simulation?.flaggedPairKeys?.has(pairKey(personId, otherId));
    
    return `
      <div onclick="showNodeInfo('${otherId}')" style="margin-bottom: 8px; padding: 8px; background: #2c3e50; border-radius: 4px; font-size: 12px; cursor: pointer; transition: background 0.2s; ${isFlagged ? 'border-left: 3px solid #e74c3c;' : ''}" onmouseover="this.style.background='#34495e'" onmouseout="this.style.background='#2c3e50'">
        <div style="color: #ecf0f1; font-weight: 600; margin-bottom: 2px;">${otherNode?.full_name_clean || otherId}</div>
        <div style="color: #bdc3c7;">${data.relation || "Relative"} (k${data.degree || "?"})</div>
      </div>
    `;
  }).join("") || "<p style='color:#7f8c8d; font-size:12px;'>No kinship edges found.</p>";

  document.getElementById("info-box").innerHTML = `
    <div style="margin-bottom: 20px;">
      <h3 style="color:white; margin-bottom: 4px; font-size: 18px;">${node.full_name_clean}</h3>
      <div style="font-size: 13px; color: #3498db; font-weight: 500; margin-bottom: 2px;">${posMeta.label}</div>
      <div style="font-size: 12px; color: #e67e22; font-weight: bold;">📍 ${locationName}</div>
    </div>
    <h4 style="color:white; margin-bottom: 10px; font-size: 14px;">Kinship Connections (${uniqueConnections.size})</h4>
    <div style="max-height: 500px; overflow-y: auto; padding-right: 5px;">
      ${connectionsHtml}
    </div>
    ${state.simulation ? `<button class="btn-primary" onclick="showInfoBox()" style="margin-top:20px;">← Back to Simulation Results</button>` : ''}
  `;
}

// Modal Logic
document.getElementById("open-menu-btn").onclick = () => document.getElementById("menu-modal").classList.remove("hidden");
document.getElementById("close-menu-btn").onclick = () => document.getElementById("menu-modal").classList.add("hidden");

document.getElementById("run-btn").onclick = async () => {
  document.getElementById("menu-modal").classList.add("hidden");
  
  const selectedDataset = document.querySelector('input[name="dataset-scope"]:checked').value;
  if (selectedDataset !== state.dataset) {
    await loadDataset(selectedDataset);
  }

  document.getElementById("loading").classList.remove("hidden");

  const preset = state.activeScenario;
  const axes = { ...SCENARIOS[preset] };
  
  const sim = document.getElementById("axis-simultaneous").checked;
  const suc = document.getElementById("axis-succession").checked;
  axes.temporal = (sim && suc) ? "both" : sim ? "simultaneous" : suc ? "succession" : "none";
  axes.k = parseInt(document.getElementById("axis-degree").value, 10);
  axes.includePartyList = document.getElementById("axis-partylist").checked;
  axes.targetYear = 2025;

  const result = runScenario(state, axes);
  const flaggedPairKeys = new Set(result.flags.map(f => pairKey(f.person_a.polId, f.person_b.polId)));
  state.simulation = { ...result, axes, flaggedPairKeys };

  renderGraph();
  showInfoBox();
  document.getElementById("loading").classList.add("hidden");
};

function showInfoBox() {
  const panel = document.getElementById("info-box");
  const sim = state.simulation;
  if (!sim) return;
  
  const axes = sim.axes;
  
  const totalIncumbents = state.nodes.length;
  const affectedIds = new Set();
  const positionBreakdown = {};

  sim.flags.forEach(f => {
    affectedIds.add(f.person_a.polId);
    affectedIds.add(f.person_b.polId);
  });

  affectedIds.forEach(id => {
    const posData = state.positions[id] || {};
    const posType = posData.position_type || "Unknown";
    positionBreakdown[posType] = (positionBreakdown[posType] || 0) + 1;
  });

  const uniqueAffected = affectedIds.size;
  const affectedPercent = totalIncumbents > 0 ? ((uniqueAffected / totalIncumbents) * 100).toFixed(1) : 0;
  
  let temporalStr = "None";
  if (axes.temporal === "both") temporalStr = "Simultaneous + Succession";
  else if (axes.temporal === "simultaneous") temporalStr = "Simultaneous Only";
  else if (axes.temporal === "succession") temporalStr = "Succession Only";

  const plStr = axes.includePartyList ? "Included" : "Excluded";
  const scenarioName = SCENARIOS[state.activeScenario]?.label || "Custom";

  let breakdownHtml = "";
  Object.entries(positionBreakdown)
    .sort((a, b) => b[1] - a[1])
    .forEach(([pos, count]) => {
      if (pos === "Unknown") return;
      const displayPos = pos.replace(/_/g, " ");
      breakdownHtml += `
        <div style="display:flex; justify-content:space-between; font-size:11px; color:#bdc3c7; margin-bottom:2px;">
          <span>${displayPos}</span>
          <span style="font-weight:bold; color:#e74c3c;">${count}</span>
        </div>
      `;
    });

  const summaryHtml = `
    <div style="background: #2c3e50; padding: 15px; border-radius: 6px; margin-bottom: 20px; border-top: 4px solid #e74c3c;">
      
      <div style="font-size: 14px; color: #ecf0f1; font-weight: bold; margin-bottom: 10px;">Policy Impact Dashboard</div>
      
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;">
        <div style="background: #1a1f2e; padding: 10px; border-radius: 4px; text-align: center;">
          <div style="font-size: 10px; color: #7f8c8d; text-transform: uppercase;">Total Incumbents</div>
          <div style="font-size: 18px; color: white; font-weight: bold;">${totalIncumbents}</div>
        </div>
        <div style="background: #1a1f2e; padding: 10px; border-radius: 4px; text-align: center;">
          <div style="font-size: 10px; color: #7f8c8d; text-transform: uppercase;">Affected Politicians</div>
          <div style="font-size: 18px; color: #e74c3c; font-weight: bold;">${uniqueAffected}</div>
        </div>
      </div>

      <div style="text-align: center; margin-bottom: 15px;">
        <div style="font-size: 24px; color: #e74c3c; font-weight: bold;">${affectedPercent}%</div>
        <div style="font-size: 11px; color: #bdc3c7;">of the government affected by this scenario</div>
      </div>

      <div style="border-top: 1px solid #34495e; padding-top: 10px; margin-bottom: 10px;">
        <div style="font-size: 11px; color: #7f8c8d; margin-bottom: 5px; text-transform: uppercase;">Breakdown by Position</div>
        ${breakdownHtml || '<div style="font-size:11px; color:#7f8c8d;">No positions found.</div>'}
      </div>

      <div style="border-top: 1px solid #34495e; padding-top: 10px;">
        <div style="font-size: 11px; color: #bdc3c7; margin-bottom: 3px;"><strong>Scenario:</strong> ${state.activeScenario} (${scenarioName})</div>
        <div style="font-size: 11px; color: #bdc3c7; margin-bottom: 3px;"><strong>Bans:</strong> ${temporalStr}</div>
        <div style="font-size: 11px; color: #bdc3c7; margin-bottom: 3px;"><strong>Civil Degree (k):</strong> ${axes.k}</div>
        <div style="font-size: 11px; color: #bdc3c7;"><strong>Party-List:</strong> ${plStr}</div>
      </div>

    </div>
  `;

  const rows = sim.flags.map(f => {
    const nameA = state.nodes.find(n => n.person_id === f.person_a.polId)?.full_name_clean || f.person_a.polId;
    const nameB = state.nodes.find(n => n.person_id === f.person_b.polId)?.full_name_clean || f.person_b.polId;
    return `<div class="result-item" onclick="showNodeInfo('${f.person_a.polId}')">
      <div class="pair">${nameA} ↔ ${nameB}</div>
      <div class="meta">${f.relation} (k${f.degree}) · ${f.rule}</div>
    </div>`;
  }).join("") || "<p style='color:#7f8c8d;'>No violations found under this scenario.</p>";

  window.exportSimulationResults = function() {
    if (!state.simulation) return;
    let csvContent = "data:text/csv;charset=utf-8,";
    csvContent += "POLICY IMPACT DASHBOARD\n";
    csvContent += `Scenario,${state.activeScenario} (${SCENARIOS[state.activeScenario]?.label || "Custom"})\n`;
    csvContent += `Total Incumbents,${totalIncumbents}\n`;
    csvContent += `Affected Politicians,${uniqueAffected}\n`;
    csvContent += `Percentage Affected,${affectedPercent}%\n\n`;
    csvContent += "RULE,PERSON_A,PERSON_B,RELATION,DEGREE,OVERLAP\n";
    state.simulation.flags.forEach(f => {
      const nameA = state.nodes.find(n => n.person_id === f.person_a.polId)?.full_name_clean || f.person_a.polId;
      const nameB = state.nodes.find(n => n.person_id === f.person_b.polId)?.full_name_clean || f.person_b.polId;
      csvContent += `${f.rule},"${nameA}","${nameB}",${f.relation},${f.degree},"${f.overlap || ''}"\n`;
    });
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `policy_impact_${state.activeScenario}_${state.dataset}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  panel.innerHTML = `
    <h3 style="color:white; margin-bottom:10px;">Results (${state.dataset})</h3>
    ${summaryHtml}
    
    <button class="btn-primary" onclick="exportSimulationResults()" style="margin-bottom: 15px; background: #27ae60; border: none; padding: 10px; border-radius: 4px; cursor: pointer; color: white; width: 100%; font-weight: bold;">
      📥 Export Results to CSV
    </button>

    <p style="color:#7f8c8d; font-size:12px; margin-bottom:15px;">Found <b>${sim.flags.length}</b> flagged pairs.</p>
    <div style="max-height: 50vh; overflow-y: auto; padding-right: 5px;">
        ${rows}
    </div>
  `;
}

function pairKey(a, b) { return a < b ? `${a}|${b}` : `${b}|${a}`; }

function generateMissingCrosswalk() {
  const missing = new Set();
  state.edges.forEach(e => {
    const hasA = state.simData.terms.some(t => t.personId === e.person_a_id);
    const hasB = state.simData.terms.some(t => t.personId === e.person_b_id);
    if (!hasA) missing.add(e.person_a_id);
    if (!hasB) missing.add(e.person_b_id);
  });

  let csvLines = [];
  missing.forEach(polId => {
    const node = state.nodes.find(n => n.person_id === polId);
    if (!node) return;
    
    const last = (node.last_name || "").toUpperCase();
    const first = (node.first_name || "").toUpperCase();
    
    const perMatches = new Set();
    state.globalHistory.forEach(h => {
      const pid = (h.person_id || "").toUpperCase();
      if (pid.includes(last) && pid.includes(first)) {
        perMatches.add(h.person_id);
      }
    });
    
    if (perMatches.size >= 1) {
      csvLines.push(`${Array.from(perMatches)[0]},${polId}`);
    }
  });

  console.log("=== COPY THESE LINES TO per_to_pol.csv ===");
  console.log(csvLines.join("\n"));
  alert("Check the console (F12) for the missing CSV lines to paste into per_to_pol.csv!");
}

boot();