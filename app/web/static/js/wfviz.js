/* wfviz — DAG renderer tự viết (không vendor lib): toposort Kahn → cột theo
   longest-path, xếp hàng barycenter, node card HTML + edge SVG bezier.
   renderGraph(el, graph, statusMap, onNodeClick) — dùng cho cả def preview
   lẫn run view (statusMap tô done/current/waiting/failed/skipped). */

const WF_ICONS = {
  start: "🏁", collect_form: "📝", crm_lookup: "🔎", ai_assess: "🤖",
  branch: "🔀", gen_pdf: "📄", send_email: "✉️", wait_event: "⏳",
  human_task: "👤", transcribe_media: "🎙️", auto_call: "📞",
  fire_action: "⚡", update_record: "🗄️", end: "🏆",
};

function wfLayout(graph) {
  const nodes = graph.nodes || [], edges = graph.edges || [];
  const ids = nodes.map(n => n.id);
  const indeg = {}, out = {}, layer = {};
  ids.forEach(id => { indeg[id] = 0; out[id] = []; layer[id] = 0; });
  edges.forEach(e => {
    if (out[e.from] && indeg[e.to] !== undefined) {
      out[e.from].push(e.to);
      indeg[e.to]++;
    }
  });
  // Kahn + longest path → cột
  const q = ids.filter(id => indeg[id] === 0);
  const order = [];
  const indegW = { ...indeg };
  while (q.length) {
    const id = q.shift();
    order.push(id);
    out[id].forEach(t => {
      layer[t] = Math.max(layer[t], layer[id] + 1);
      if (--indegW[t] === 0) q.push(t);
    });
  }
  ids.filter(id => !order.includes(id)).forEach(id => order.push(id)); // chu trình hỏng → vẫn vẽ
  const cols = {};
  order.forEach(id => { (cols[layer[id]] = cols[layer[id]] || []).push(id); });
  // barycenter 1 lượt theo cha để giảm cắt nhau
  const parents = {};
  edges.forEach(e => { (parents[e.to] = parents[e.to] || []).push(e.from); });
  const rowOf = {};
  Object.keys(cols).sort((a, b) => a - b).forEach(c => {
    if (c === "0") { cols[c].forEach((id, i) => rowOf[id] = i); return; }
    cols[c].sort((a, b) => {
      const bary = id => {
        const ps = (parents[id] || []).filter(p => rowOf[p] !== undefined);
        return ps.length ? ps.reduce((s, p) => s + rowOf[p], 0) / ps.length : 99;
      };
      return bary(a) - bary(b);
    });
    cols[c].forEach((id, i) => rowOf[id] = i);
  });
  return { layer, rowOf, cols };
}

function renderGraph(el, graph, statusMap = {}, onNodeClick = null) {
  const W = 176, H = 62, GX = 64, GY = 18, PAD = 14;
  const { layer, rowOf, cols } = wfLayout(graph);
  const nCols = Math.max(...Object.keys(cols).map(Number)) + 1;
  const nRows = Math.max(...Object.values(cols).map(a => a.length));
  const width = PAD * 2 + nCols * W + (nCols - 1) * GX;
  const height = PAD * 2 + nRows * H + (nRows - 1) * GY;
  const pos = {};
  (graph.nodes || []).forEach(n => {
    pos[n.id] = {
      x: PAD + layer[n.id] * (W + GX),
      y: PAD + (rowOf[n.id] || 0) * (H + GY),
    };
  });

  el.classList.add("wfviz");
  el.innerHTML = "";
  const inner = document.createElement("div");
  inner.className = "wfviz-inner";
  inner.style.width = width + "px";
  inner.style.height = height + "px";
  el.appendChild(inner);

  // edges (SVG dưới node)
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  inner.appendChild(svg);
  const labels = [];
  (graph.edges || []).forEach(e => {
    const a = pos[e.from], b = pos[e.to];
    if (!a || !b) return;
    const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
    const dx = Math.max(30, (x2 - x1) / 2);
    const p = document.createElementNS(svg.namespaceURI, "path");
    p.setAttribute("d", `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`);
    p.setAttribute("class", "wfedge" + (e.else ? " else" : "")
      + (statusMap[e.from] === "done" && ["done", "current", "waiting"]
        .includes(statusMap[e.to]) ? " walked" : ""));
    svg.appendChild(p);
    if (e.label || e.when) {
      labels.push({ x: (x1 + x2) / 2, y: (y1 + y2) / 2,
                    text: e.label || e.when, else: !!e.else });
    }
  });
  labels.forEach(l => {
    const pill = document.createElement("div");
    pill.className = "wfpill" + (l.else ? " else" : "");
    pill.textContent = l.text;
    pill.style.left = l.x + "px";
    pill.style.top = l.y + "px";
    inner.appendChild(pill);
  });

  // nodes
  (graph.nodes || []).forEach(n => {
    const d = document.createElement("div");
    const st = statusMap[n.id] || "";
    d.className = `wfnode t-${n.type}` + (st ? ` st-${st}` : "");
    d.style.left = pos[n.id].x + "px";
    d.style.top = pos[n.id].y + "px";
    d.style.width = W + "px";
    d.style.height = H + "px";
    const badge = { done: "✓", waiting: "⏳", failed: "✗", current: "▶" }[st] || "";
    d.innerHTML = `
      <span class="wic">${WF_ICONS[n.type] || "▫️"}</span>
      <span class="wtxt"><b>${n.label || n.id}</b><small>${n.type}</small></span>
      ${badge ? `<span class="wst">${badge}</span>` : ""}`;
    if (onNodeClick) {
      d.addEventListener("click", () => onNodeClick(n));
      d.classList.add("clickable");
    }
    inner.appendChild(d);
  });
  return { width, height };
}
