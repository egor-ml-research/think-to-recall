// «Волны» (topic streamgraph, d3) and «Живая память» (topic tree with pulses of the memory's MCP calls, Canvas 2D).
// Data: DATA.flow (ctxgraph/flow.py: records with status / topic, topics), DATA.calls (calls.jsonl, ctxgraph/calls.py),
// DATA.live (the page is served by `ctxgraph view --live`: it polls `calls?offset=` for new calls).
// Shares the globals of the main viewer script (DATA, $, esc, css, showInsp, closeInsp, setMode, setTheme).
const FLOW = (() => {
  const F = DATA.flow || { records: [], topics: [] }, RECS = F.records, TOP = F.topics;
  const byRid = new Map(RECS.map(r => [r.id, r]));
  const find = id => byRid.get(String(id).slice(0, 8)) || (String(id).length < 8 ? RECS.find(r => r.id.startsWith(id)) : null);
  const ST = { decision: ["решение", "#6fd3a0", "#2f8a64"], change: ["смена решения", "#ffb347", "#b8741a"],
    report: ["отчёт", "#7aa7ff", "#3a64c2"], later: ["на потом", "#c3a6ff", "#7652c4"] };
  const light = () => document.documentElement.dataset.theme === "light" && mode !== "live";
  const stCol = (s, l = light()) => ST[s] ? ST[s][l ? 2 : 1] : (l ? "#a3a3aa" : "rgba(230,230,238,.34)");
  const tcol = k => k < 0 ? "#6b6b74" : (TOP[k] || {}).color || "#7d7d86";
  const tname = k => k < 0 ? "без темы" : (TOP[k] || {}).name || "";
  const DAY = 864e5, dms = s => Date.parse(s.slice(0, 10) + "T00:00:00Z");
  const fmtD = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(2, 4)}` : "";
  const CORAL = "#FF5F6D", GOLD = "#FFC371";

  document.head.insertAdjacentHTML("beforeend", `<style>
#waves, #livecv { position: absolute; inset: 0; width: 100%; height: 100%; display: none; }
.flowui { display: none; }
.app.flow aside, .app.flow #graph, .app.flow #graph3d, .app.flow .zoom, .app.flow #sky, .app.flow #cosmos, .app.flow .cosui { display: none !important; }
.app.flow .flowui { display: block; }
.app.flow.waves #waves, .app.flow.live #livecv { display: block; }
.app.flow.live { --canvas: #000; --side: rgba(12,10,12,.86); --solid: #0d0b0d; --raise: rgba(255,255,255,.04); --hover: rgba(255,255,255,.07);
  --line: rgba(255,255,255,.08); --line2: rgba(255,255,255,.13); --text: #ece8e6; --dim: #aca6a3; --faint: #77716e; --accent: #ff9a6b; }
.app.flow.live .stage { background: #000; } .app.flow.live .insp { color: var(--text); }
.app.flow .insp { top: 84px; bottom: 84px; }
.fglass { position: absolute; z-index: 4; background: var(--side); border: 1px solid var(--line2); border-radius: 14px;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); box-shadow: var(--shadow); color: var(--text); }
.ftop { position: absolute; left: 16px; right: 16px; top: 16px; z-index: 4; display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; pointer-events: none; }
.ftop > * { position: static; pointer-events: auto; }
.fhdr { padding: 10px 12px 10px 16px; display: flex; align-items: center; gap: 14px; max-width: calc(100vw - 32px); flex-wrap: wrap; }
.fhdr .p { font-weight: 600; font-size: 13px; } .fhdr .s { color: var(--faint); font-size: 11.5px; font-variant-numeric: tabular-nums; }
.fseg { display: flex; border: 1px solid var(--line2); border-radius: 13px; overflow: hidden; background: var(--raise); }
.fseg button, .fbtn { height: 26px; padding: 0 10px; border: 0; background: none; color: var(--dim); font: inherit; font-size: 12px; cursor: pointer; }
.fseg button.on { color: var(--text); background: var(--hover); } .fbtn:hover, .fseg button:hover { color: var(--text); }
.fbtn { border: 1px solid var(--line2); border-radius: 13px; background: var(--raise); }
.fleg { padding: 9px 14px; font-size: 12px; color: var(--dim); display: flex; gap: 12px; flex-wrap: wrap; max-width: 46vw; }
.fleg i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; vertical-align: 0; }
.ftip { position: absolute; z-index: 7; pointer-events: none; max-width: 340px; padding: 8px 11px; border-radius: 10px; font-size: 12px; line-height: 1.45;
  background: var(--solid); border: 1px solid var(--line2); box-shadow: var(--shadow); color: var(--text); display: none; }
.ftip .w { color: var(--faint); font-size: 11px; font-variant-numeric: tabular-nums; margin-bottom: 2px; }
.fbar { left: 50%; bottom: 16px; transform: translateX(-50%); padding: 8px 12px; display: none; align-items: center; gap: 10px; font-size: 12px;
  width: min(760px, calc(100vw - 32px)); flex-wrap: wrap; }
.app.flow.live .fbar { display: flex; }
.fbar select { height: 26px; border: 1px solid var(--line2); border-radius: 13px; background: var(--solid); color: var(--text); font: inherit; font-size: 12px; padding: 0 8px; }
.fprog { flex: 1; min-width: 120px; height: 4px; border-radius: 2px; background: var(--line2); cursor: pointer; position: relative; }
.fprog b { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 2px; background: linear-gradient(90deg, ${CORAL}, ${GOLD}); }
.fclock { color: var(--dim); font-variant-numeric: tabular-nums; min-width: 110px; }
.flive { color: var(--faint); } .flive.on { color: ${GOLD}; }
.ftick { right: 16px; bottom: 84px; padding: 8px 12px; font-size: 11.5px; color: var(--dim); font-variant-numeric: tabular-nums; display: none; min-width: 230px; }
.app.flow.live .ftick.has { display: block; }
.ftick div { white-space: nowrap; } .ftick b { color: ${GOLD}; font-weight: 500; }
.fempty.side { left: auto; top: auto; right: 16px; bottom: 84px; transform: none; text-align: left; padding: 10px 14px; background: var(--side); border: 1px solid var(--line2); border-radius: 12px; max-width: 360px; font-size: 12px; }
.fempty { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); color: var(--faint); font-size: 13px; text-align: center; max-width: 420px; display: none; z-index: 3; }
#waves .ax text { fill: var(--faint); font-size: 11px; } #waves .ax path, #waves .ax line { stroke: var(--line2); }
.rec .tx { margin: 10px 0; } .rec .rp { color: var(--dim); border-left: 2px solid var(--line2); padding-left: 10px; margin: 8px 0; }
.rec .ch { cursor: pointer; } .rec .ch:hover .tx { color: var(--accent); }
</style>`);
  const stage = $("#stage");
  stage.insertAdjacentHTML("beforeend", `<svg id="waves"></svg><canvas id="livecv"></canvas>
    <div class="flowui"><div class="ftop"><div class="fhdr fglass"><div><div class="p">${esc(DATA.name)}</div><div class="s" id="fSub"></div></div>
      <div class="fseg"><button data-fmode="2d">2D</button><button data-fmode="3d">3D</button><button data-fmode="cosmos">Космос</button><button data-fmode="waves">Волны</button><button data-fmode="live">Живая память</button></div>
      <button class="fbtn" id="fTheme" title="Тема">Тема</button></div>
      <div class="fleg fglass" id="fLeg"></div></div><div class="ftip" id="fTip"></div><div class="fempty" id="fEmpty"></div>
      <div class="ftick fglass" id="fTick"></div>
      <div class="fbar fglass"><button class="fbtn" id="fPlay">▶</button><button class="fbtn" id="fRe" title="С начала">↺</button>
        <select id="fPer"><option value="1">час</option><option value="24" selected>сутки</option><option value="168">неделя</option><option value="720">месяц</option><option value="0">всё</option></select>
        <select id="fSpd"><option value="1">×1</option><option value="2" selected>×2</option><option value="4">×4</option></select>
        <div class="fprog" id="fProg"><b id="fProgB"></b></div><span class="fclock" id="fClock"></span>
        <button class="fbtn flive" id="fLive" title="Новые вызовы из calls.jsonl">● эфир</button></div></div>`);
  stage.querySelectorAll("[data-fmode]").forEach(b => b.onclick = () => setMode(b.dataset.fmode));
  $("#fTheme").onclick = () => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
  const tip = $("#fTip");
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.style.display = "block";
    const W = stage.clientWidth, w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(W - w - 8, x + 14) + "px"; tip.style.top = Math.max(8, y - h - 10) + "px";
  }
  const hideTip = () => { tip.style.display = "none"; };
  const recTip = r => `<div class="w">${fmtD(r.d)} · <span style="color:${stCol(r.st)}">${ST[r.st] ? ST[r.st][0] : "запись"}</span> · ${esc(tname(r.topic))} · #${r.id}</div>${esc(r.t)}`;
  const legend = () => Object.entries(ST).map(([k, v]) => `<span><i style="background:${stCol(k)}"></i>${v[0]}</span>`).join("");

  // ── the record in the inspector, as the other views open a node ──
  function openRecord(r) {
    if (typeof r === "string") r = find(r);
    if (!r) return;
    const link = id => { const x = find(id); return x ? `<div class="item ch" data-rid="${x.id}"><div class="when"><span>${fmtD(x.d)}</span><span>#${x.id}</span></div><div class="tx">${esc(x.t)}</div></div>` : ""; };
    showInsp(`<div class="ih"><button class="x" onclick="closeInsp()">×</button>
      <div class="kind"><span class="sw" style="background:${stCol(r.st)};border-radius:50%"></span>${ST[r.st] ? ST[r.st][0] : "запись"} · #${r.id}</div>
      <h2>${esc(tname(r.topic))}</h2><div class="meta">${esc(r.ts.replace("T", " "))}</div></div>
      <div class="body rec"><div class="tx">${esc(r.t)}</div>${r.rep ? `<div class="rp">Отчёт: ${esc(r.rep)}</div>` : ""}
      ${r.chg.length ? `<div class="lbl" style="margin-top:16px">Меняет решение</div>${r.chg.map(link).join("")}` : ""}
      ${r.by.length ? `<div class="lbl" style="margin-top:16px">Решение изменено позже</div>${r.by.map(link).join("")}` : ""}
      <div class="hint">Полностью — в ассистенте: expand("#${r.id}").</div></div>`);
    $("#insp").querySelectorAll("[data-rid]").forEach(el => el.onclick = () => { openRecord(el.dataset.rid); if (mode === "live") LIVE.flare(el.dataset.rid, 1); });
  }
  function openTopicRecs(k) {
    const rs = RECS.filter(r => r.topic === k).slice().reverse(), t = TOP[k];
    showInsp(`<div class="ih"><button class="x" onclick="closeInsp()">×</button><div class="kind"><span class="sw" style="background:${tcol(k)}"></span>Тема</div>
      <h2>${esc(tname(k))}</h2><div class="meta">${rs.length} записей${t ? ` · ${fmtD(t.first)} — ${fmtD(t.last)}` : ""}</div></div>
      <div class="body">${rs.map(r => `<div class="item ch" data-rid="${r.id}" style="cursor:pointer"><div class="when"><span>${fmtD(r.d)}</span>
        <span style="color:${stCol(r.st)}">${ST[r.st] ? ST[r.st][0] : ""}</span><span>#${r.id}</span></div><div class="tx">${esc(r.t)}</div></div>`).join("")}</div>`);
    $("#insp").querySelectorAll("[data-rid]").forEach(el => el.onclick = () => openRecord(el.dataset.rid));
  }
  const keys = [...TOP.map(t => t.id), ...(RECS.some(r => r.topic < 0) ? [-1] : [])];
  const d0 = RECS.length ? dms(RECS[0].d) : Date.now(), d1 = RECS.length ? dms(RECS[RECS.length - 1].d) : Date.now();

  // ── «Волны»: x - days (weeks for a project longer than 70 days), y - records per topic ──
  const WAVES = (() => {
    const weekly = (d1 - d0) / DAY > 70, step = weekly ? 7 * DAY : DAY;
    const bin = t => weekly ? (Math.floor(t / DAY) - ((Math.floor(t / DAY) + 3) % 7)) * DAY : t;  // weeks from Monday
    const b0 = bin(d0) - step, b1 = bin(d1) + step, nb = Math.round((b1 - b0) / step) + 1;
    const rows = Array.from({ length: nb }, (_, i) => { const o = { date: new Date(b0 + i * step) }; keys.forEach(k => o[k] = 0); return o; });
    const ib = r => Math.round((bin(dms(r.d)) - b0) / step);
    RECS.forEach(r => { rows[ib(r)][r.topic]++; });
    const K = weekly ? [1, 2, 1] : [1, 2, 3, 2, 1];  // a light moving average: days with no record do not cut a stream
    const sm = rows.map((o, i) => { const q = { date: o.date }; keys.forEach(k => { let a = 0, w = 0;
      K.forEach((c, j) => { const x = rows[i + j - (K.length >> 1)]; if (x) { a += c * x[k]; w += c; } }); q[k] = a / w; }); return q; });
    let hl = null;
    const isOther = k => +k < 0 || (TOP[+k] || {}).other;  // merged small topics and records without a topic: at the edge
    const edgeOrder = ser => { const o = d3.stackOrderInsideOut(ser); return [...o.filter(i => !isOther(ser[i].key)), ...o.filter(i => isOther(ser[i].key))]; };
    const op = k => isOther(k) ? 0.32 : (light() ? 0.78 : 0.7);
    function draw() {
      const svg = d3.select("#waves"), W = Math.max(1, stage.clientWidth), H = Math.max(1, stage.clientHeight);
      svg.attr("viewBox", `0 0 ${W} ${H}`).selectAll("*").remove();
      if (!RECS.length) return;
      const top = Math.max(96, stage.querySelector(".ftop").getBoundingClientRect().bottom + 14), bot = 44, side = 28;
      const series = d3.stack().keys(keys).value((d, k) => d[k]).offset(d3.stackOffsetSilhouette).order(edgeOrder)(sm);
      const lo = d3.min(series, s => d3.min(s, p => p[0])), hi = d3.max(series, s => d3.max(s, p => p[1]));
      const x = d3.scaleUtc([rows[0].date, rows[nb - 1].date], [side, W - side]);
      const y = d3.scaleLinear([lo, hi], [H - bot, top]);
      const area = d3.area().x(p => x(p.data.date)).y0(p => y(p[0])).y1(p => y(p[1])).curve(d3.curveBasis);
      const g = svg.append("g");
      const paths = g.selectAll("path").data(series).join("path").attr("d", area).attr("fill", s => tcol(s.key))
        .attr("fill-opacity", s => hl === null || hl === s.key ? op(s.key) : .14).attr("stroke", light() ? "#fff" : "#000").attr("stroke-width", .6)
        .style("cursor", "pointer")
        .on("mousemove", (ev, s) => { const i = Math.max(0, Math.min(nb - 1, Math.round((x.invert(ev.offsetX) - b0) / step))), n = rows[i][s.key];
          showTip(`<div class="w">${weekly ? "неделя с " : ""}${fmtD(rows[i].date.toISOString())}</div><b>${esc(tname(+s.key))}</b><br>${n} ${n === 1 ? "запись" : "записей"} · всего ${RECS.filter(r => r.topic === +s.key).length}`, ev.offsetX, ev.offsetY);
          if (hl !== s.key) { hl = s.key; paths.attr("fill-opacity", t => t.key === hl ? (light() ? .85 : .78) : .18); } })
        .on("mouseleave", () => { hl = null; hideTip(); paths.attr("fill-opacity", t => op(t.key)); })
        .on("click", (ev, s) => openTopicRecs(+s.key));
      // stream names where the stream is thick enough
      const used = [];
      series.map(s => { let bi = 0, bw = 0; s.forEach((p, i) => { if (p[1] - p[0] > bw) { bw = p[1] - p[0]; bi = i; } }); return [s, bi, y(s[bi][0]) - y(s[bi][1])]; })
        .sort((a, b) => b[2] - a[2]).forEach(([s, bi, px]) => { if (px < 18) return;
        const lx = Math.min(W - side - 160, Math.max(side + 4, x(rows[bi].date) - 70)), ly = (y(s[bi][0]) + y(s[bi][1])) / 2 + 4;
        if (used.some(([ux, uy]) => Math.abs(ux - lx) < 190 && Math.abs(uy - ly) < 15)) return; used.push([lx, ly]);
        g.append("text").attr("x", lx).attr("y", ly)
          .attr("fill", light() ? "rgba(20,20,26,.78)" : "rgba(255,255,255,.86)").attr("font-size", 11.5).attr("pointer-events", "none")
          .text(tname(+s.key).length > 30 ? tname(+s.key).slice(0, 29) + "…" : tname(+s.key)); });
      // decision marks on their stream: x - the record's day, y - inside its stream at that bin
      const byKey = new Map(series.map(s => [s.key, s])), seen = {};
      const marks = RECS.filter(r => ST[r.st]).map(r => { const s = byKey.get(r.topic), i = ib(r), p = s[i], k = r.topic + ":" + i;
        seen[k] = (seen[k] || 0) + 1; const j = seen[k], n = rows[i][r.topic] || 1, f = n > 1 ? (j - 0.5) / n : 0.5;
        const tx = dms(r.d) + (weekly ? 0 : (j % 5) * DAY * 0.16 - DAY * 0.3);
        return { r, x: x(new Date(Math.max(b0, tx))), y: y(p[0] + (p[1] - p[0]) * (0.2 + 0.6 * f)) }; });
      g.selectAll("circle").data(marks).join("circle").attr("cx", m => m.x).attr("cy", m => m.y).attr("r", m => m.r.st === "change" ? 4.4 : m.r.st === "report" ? 2.1 : 3.4).attr("fill-opacity", m => m.r.st === "report" ? 0.6 : 1)
        .attr("fill", m => stCol(m.r.st)).attr("stroke", light() ? "#fff" : "#08080c").attr("stroke-width", m => m.r.st === "report" ? 0.5 : 1.2).style("cursor", "pointer")
        .on("mousemove", (ev, m) => showTip(recTip(m.r), ev.offsetX, ev.offsetY)).on("mouseleave", hideTip)
        .on("click", (ev, m) => { ev.stopPropagation(); openRecord(m.r); });
      const ax = svg.append("g").attr("class", "ax").attr("transform", `translate(0,${H - bot + 8})`)
        .call(d3.axisBottom(x).ticks(Math.max(2, Math.floor(W / 120))).tickFormat(d3.utcFormat("%d.%m")).tickSizeOuter(0));
      ax.select(".domain").remove();
    }
    return { draw };
  })();

  // ── «Живая память»: trunk = project time, branches = topics, beads = records; pulses of recall / expand ──
  const LIVE = (() => {
    const cv = $("#livecv"), ctx = cv.getContext("2d");
    let W = 1, H = 1, DPR = 1, L = 0, Rr = 1, ty = 0, dx = 60, raf = 0, on = false, hover = null, hlb = null;
    const branches = TOP.map(t => ({ t, k: t.id }));
    const beads = RECS.map(r => ({ r, x: 0, y: 0, b: null, flare: 0, f0: 0 }));
    const beadOf = new Map(beads.map(b => [b.r.id, b]));
    const X = d => L + (Rr - L) * (d1 > d0 ? (dms(d) - d0) / (d1 - d0) : 0.5);
    function layout() {
      DPR = Math.min(2, devicePixelRatio || 1); W = Math.max(1, stage.clientWidth); H = Math.max(1, stage.clientHeight);
      cv.width = Math.max(1, Math.round(W * DPR)); cv.height = Math.max(1, Math.round(H * DPR));
      const lab = Math.min(260, Math.max(150, W * 0.3)); dx = Math.max(34, Math.min(70, W * 0.05));
      L = 40 + dx; Rr = Math.max(L + 10, W - lab - 30);
      const hb = stage.querySelector(".fhdr").getBoundingClientRect().bottom, lb = $("#fLeg").getBoundingClientRect().bottom;
      const yt = Math.max(92, hb + 18, lb + 18), yb = H - 96; ty = (yt + yb) / 2;
      const order = branches.slice().sort((a, b) => a.t.first < b.t.first ? -1 : a.t.first > b.t.first ? 1 : a.k - b.k);
      const up = order.filter((_, i) => i % 2 === 0), dn = order.filter((_, i) => i % 2 === 1);
      const gap = Math.max(10, Math.min(48, (ty - yt) / Math.max(1, up.length)));
      [[up, -1], [dn, 1]].forEach(([arr, sg]) => arr.forEach((b, j) => { b.lane = ty + sg * gap * (arr.length - j); b.sg = sg; }));
      branches.forEach(b => { b.xs = X(b.t.first) - dx; b.xe = X(b.t.last); });
      const day = {};
      beads.forEach(o => { const b = o.r.topic >= 0 ? branches[o.r.topic] : null; o.b = b; o.x = X(o.r.d);
        const k = o.r.topic + o.r.d; day[k] = (day[k] || 0) + 1; const j = day[k] - 1;
        o.off = (j % 2 ? 1 : -1) * Math.ceil(j / 2) * 3.2; });
    }
    const ease = u => u <= 0 ? 0 : u >= 1 ? 1 : u * u * (3 - 2 * u);
    let now = 0;
    const sway = b => b ? Math.sin(now * 0.00035 + b.k * 1.7) * 1.6 : 0;
    const yAt = (b, x) => b ? ty + (b.lane + sway(b) - ty) * ease((x - b.xs) / dx) : ty;
    const pos = o => ({ x: o.x, y: yAt(o.b, o.x) + o.off * (o.b ? 1 : 0.6) });
    // a pulse path: from the trunk's root along the trunk to the branch, then along the branch to the bead
    function pathTo(o) {
      const pts = [], x0 = L - dx - 10, p = pos(o), xs = o.b ? Math.max(x0, o.b.xs) : p.x;
      for (let x = x0; x < xs; x += 8) pts.push([x, ty]);
      if (o.b) for (let x = xs; x < p.x; x += 6) pts.push([x, yAt(o.b, x)]);
      pts.push([p.x, p.y]); return pts;
    }
    const pulses = [], arcs = [], tick = [];
    const plen = pts => { let len = 0; for (let j = 1; j < pts.length; j++) len += Math.hypot(pts[j][0] - pts[j - 1][0], pts[j][1] - pts[j - 1][1]); return len; };
    function flare(id, s = 1, delay = 0) { const o = beadOf.get(String(id).slice(0, 8)) || (find(id) && beadOf.get(find(id).id)); if (o) { o.f0 = now + delay; o.flare = s; } return o; }
    function fire(c) {
      const os = (c.ids || []).map(id => find(id)).filter(Boolean).map(r => beadOf.get(r.id));
      if (c.tool === "recall") os.forEach((o, i) => { const len = plen(pathTo(o)); pulses.push({ t0: now + i * 110, dur: 650 + len * 0.9, o }); });
      else if (c.tool === "expand" && os.length) {
        const o = os[0]; flare(o.r.id, 1.6);
        const seen = new Set([o.r.id]), q = [o.r], chain = [];  // the record's chain of decision changes, both ways
        while (q.length) { const r = q.shift(); [...r.chg, ...r.by].forEach(id => { const x = find(id); if (x && !seen.has(x.id)) { seen.add(x.id); q.push(x); chain.push([r, x]); } }); }
        chain.forEach(([a, b], i) => { arcs.push({ a: beadOf.get(a.id), b: beadOf.get(b.id), t0: now + 300 + i * 420, dur: 900 }); flare(b.id, 1.2, 300 + i * 420 + 800); });
        os.slice(1).forEach((x, i) => flare(x.r.id, 0.45, 200 + i * 40));
      } else os.forEach((o, i) => flare(o.r.id, 0.6, i * 60));
      const hh = new Date(c.t); tick.unshift(`<div>${String(hh.getHours()).padStart(2, "0")}:${String(hh.getMinutes()).padStart(2, "0")}:${String(hh.getSeconds()).padStart(2, "0")} · <b>${esc(c.tool)}</b> · ${os.length} зап. · ${c.ms} мс</div>`);
      tick.length = Math.min(tick.length, 5); $("#fTick").innerHTML = tick.join(""); $("#fTick").classList.add("has");
    }
    function frame(t) {
      if (!on) return; now = t; raf = requestAnimationFrame(frame);
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0); ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
      // trunk
      const tg = ctx.createLinearGradient(L - dx, 0, Rr, 0); tg.addColorStop(0, "rgba(255,95,109,.55)"); tg.addColorStop(1, "rgba(255,195,113,.55)");
      ctx.strokeStyle = tg; ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.beginPath(); ctx.moveTo(L - dx - 10, ty); ctx.lineTo(Rr + 8, ty); ctx.stroke();
      ctx.fillStyle = "rgba(236,232,230,.5)"; ctx.font = "11px Segoe UI, system-ui, sans-serif"; ctx.textAlign = "left";
      ctx.fillText(fmtD(RECS[0] ? RECS[0].d : ""), L - dx - 10, ty + 18); ctx.textAlign = "right"; ctx.fillText(fmtD(RECS.length ? RECS[RECS.length - 1].d : ""), Rr + 8, ty + 18);
      // branches
      ctx.textAlign = "left";
      branches.forEach(b => {
        const a = hlb === null || hlb === b.k ? 1 : 0.3; ctx.globalAlpha = a;
        ctx.strokeStyle = b.t.color; ctx.lineWidth = hlb === b.k ? 2.2 : 1.5; ctx.beginPath();
        for (let x = b.xs; x <= b.xe; x += 5) { const y = yAt(b, x); x === b.xs ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
        ctx.lineTo(b.xe, yAt(b, b.xe)); ctx.stroke();
        ctx.setLineDash([2, 5]); ctx.globalAlpha = a * 0.35; ctx.beginPath(); ctx.moveTo(b.xe, b.lane + sway(b)); ctx.lineTo(Rr + 14, b.lane + sway(b)); ctx.stroke(); ctx.setLineDash([]);
        ctx.globalAlpha = a; ctx.fillStyle = b.t.color; ctx.font = "12px Segoe UI, system-ui, sans-serif";
        const lbl = `${b.t.name} · ${b.t.n} · ${fmtD(b.t.last)}`; b.lx = Rr + 20; b.ly = b.lane + sway(b);
        const mx = Math.floor((W - b.lx - 8) / 6.6), sh = lbl.length > mx ? lbl.slice(0, Math.max(4, mx - 1)) + "…" : lbl;
        ctx.fillText(sh, b.lx, b.ly + 4); b.lw = ctx.measureText(sh).width;
      });
      ctx.globalAlpha = 1;
      // beads
      beads.forEach(o => { const p = pos(o); o.px = p.x; o.py = p.y; const s = !!ST[o.r.st];
        const dim = hlb !== null && (!o.b || o.b.k !== hlb) ? 0.25 : 1;
        ctx.globalAlpha = dim; ctx.fillStyle = stCol(o.r.st, false); ctx.beginPath(); ctx.arc(p.x, p.y, s ? (o.r.st === "change" ? 3.4 : 2.7) : 1.6, 0, 7); ctx.fill();
        const e = o.flare ? (now - o.f0) / 2600 : 2;
        if (e >= 0 && e < 1) { const k = (1 - e) * o.flare, rr = 4 + e * 22 * Math.min(1.4, o.flare);
          const gr = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, 16 * Math.min(1.5, o.flare) + 4); gr.addColorStop(0, `rgba(255,195,113,${0.9 * k})`); gr.addColorStop(1, "rgba(255,95,109,0)");
          ctx.globalAlpha = 1; ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(p.x, p.y, 16 * Math.min(1.5, o.flare) + 4, 0, 7); ctx.fill();
          ctx.strokeStyle = `rgba(255,95,109,${0.8 * k})`; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(p.x, p.y, rr, 0, 7); ctx.stroke(); }
        else if (e >= 1) o.flare = 0; });
      ctx.globalAlpha = 1;
      // pulses: a warm head with a fading trail along the path
      for (let i = pulses.length - 1; i >= 0; i--) { const P = pulses[i], u = (now - P.t0) / P.dur; if (u < 0) continue;
        if (u >= 1) { flare(P.o.r.id, 1); pulses.splice(i, 1); continue; }
        P.pts = pathTo(P.o); P.len = plen(P.pts);  // the path follows the layout (a resize, the branches' sway)
        const head = ease(u) * P.len, tail = Math.max(0, head - 140); let acc = 0; ctx.lineWidth = 2.2;
        for (let j = 1; j < P.pts.length; j++) { const [ax, ay] = P.pts[j - 1], [bx, by] = P.pts[j], l = Math.hypot(bx - ax, by - ay);
          if (acc + l >= tail && acc <= head) { const f = (acc - tail) / 140; ctx.strokeStyle = `rgba(255,${Math.round(95 + 100 * f)},${Math.round(109 + 4 * f)},${0.15 + 0.75 * f})`;
            ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); }
          if (acc <= head && acc + l > head) { const k = (head - acc) / l, hx = ax + (bx - ax) * k, hy = ay + (by - ay) * k;
            const gr = ctx.createRadialGradient(hx, hy, 0, hx, hy, 10); gr.addColorStop(0, "rgba(255,230,190,1)"); gr.addColorStop(0.35, "rgba(255,195,113,.8)"); gr.addColorStop(1, "rgba(255,95,109,0)");
            ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(hx, hy, 10, 0, 7); ctx.fill(); }
          acc += l; } }
      // arcs of a decision-change chain (expand)
      for (let i = arcs.length - 1; i >= 0; i--) { const A = arcs[i], u = (now - A.t0) / A.dur; if (u < 0) continue; if (u > 2.4) { arcs.splice(i, 1); continue; }
        const a = { x: A.a.px, y: A.a.py }, b = { x: A.b.px, y: A.b.py }, mx = (a.x + b.x) / 2, my = Math.min(a.y, b.y) - 30 - Math.abs(b.x - a.x) * 0.12;
        const al = u <= 1 ? 1 : Math.max(0, 1 - (u - 1) / 1.4), seg = Math.min(1, u), n = 30;
        ctx.strokeStyle = `rgba(255,195,113,${0.85 * al})`; ctx.lineWidth = 1.6; ctx.beginPath();
        for (let j = 0; j <= n * seg; j++) { const s = j / n, x = (1 - s) * (1 - s) * a.x + 2 * (1 - s) * s * mx + s * s * b.x, y = (1 - s) * (1 - s) * a.y + 2 * (1 - s) * s * my + s * s * b.y; j ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
        ctx.stroke(); }
      PLAY.step(t);
    }
    const near = (x, y) => { let best = null, bd = 64; beads.forEach(o => { const d = (o.px - x) ** 2 + (o.py - y) ** 2; if (d < bd) { bd = d; best = o; } }); return best; };
    const label = (x, y) => branches.find(b => b.lx !== undefined && x >= b.lx - 4 && x <= b.lx + b.lw && Math.abs(y - b.ly) < 9);
    cv.addEventListener("mousemove", e => { const o = near(e.offsetX, e.offsetY), lb = o ? null : label(e.offsetX, e.offsetY);
      hover = o; cv.style.cursor = o || lb ? "pointer" : "default"; hlb = lb ? lb.k : null;
      if (o) showTip(recTip(o.r), e.offsetX, e.offsetY); else if (lb) showTip(`<b>${esc(lb.t.name)}</b><br>${lb.t.n} записей · ${fmtD(lb.t.first)} — ${fmtD(lb.t.last)}`, e.offsetX, e.offsetY); else hideTip(); });
    cv.addEventListener("mouseleave", () => { hover = null; hlb = null; hideTip(); });
    cv.addEventListener("click", e => { const o = near(e.offsetX, e.offsetY); if (o) { openRecord(o.r); flare(o.r.id, 1); return; }
      const lb = label(e.offsetX, e.offsetY); if (lb) openTopicRecs(lb.k); });
    return { clear() { tick.length = 0; $("#fTick").innerHTML = ""; $("#fTick").classList.remove("has"); }, start() { layout(); if (!on) { on = true; raf = requestAnimationFrame(frame); } }, stop() { on = false; cancelAnimationFrame(raf); },
      layout, fire, flare, get on() { return on; } };
  })();

  // ── playback of calls.jsonl over a period, and live calls when served by `ctxgraph view --live` ──
  const CALLS = (DATA.calls || []).slice();
  const PLAY = (() => {
    let list = [], i = 0, playing = false, next = 0, live = !!DATA.live, off = DATA.offset || 0;
    const per = () => +$("#fPer").value, spd = () => +$("#fSpd").value;
    function pick() { const last = CALLS.length ? Date.parse(CALLS[CALLS.length - 1].t) : 0, h = per();
      list = CALLS.filter(c => !h || Date.parse(c.t) >= last - h * 36e5); i = 0; next = 0; ui(); }
    function ui() { $("#fPlay").textContent = playing ? "❚❚" : "▶"; $("#fProgB").style.width = list.length ? (100 * i / list.length) + "%" : "0";
      const c = list[Math.min(i, list.length - 1)], d = c ? new Date(c.t) : null;
      $("#fClock").textContent = d ? `${d.toLocaleDateString("ru-RU")} ${d.toLocaleTimeString("ru-RU")} · ${i}/${list.length}` : "нет вызовов за период";
      $("#fLive").classList.toggle("on", live); $("#fLive").title = DATA.live ? "Новые вызовы из calls.jsonl" : "Живой эфир — через ctxgraph view --live";
      const empty = !CALLS.length; $("#fEmpty").classList.toggle("side", !!RECS.length); $("#fEmpty").style.display = empty && mode === "live" ? "block" : "none";
      $("#fEmpty").innerHTML = RECS.length ? `Журнал вызовов пуст. Он пишется, когда ассистент вызывает recall / expand через MCP-сервер ctxgraph:<br><span class="mono">~/.ctxgraph/&lt;проект&gt;/calls.jsonl</span>${DATA.live ? "<br>Жду вызовов…" : "<br>Живой эфир: <span class=\"mono\">ctxgraph view --live</span>"}` : "В памяти пока нет записей."; }
    function step(t) {
      if (!playing || !list.length) return;
      if (!next) next = t;
      if (t < next) return;
      if (i >= list.length) { playing = false; ui(); return; }
      const c = list[i++]; LIVE.fire(c);
      const n = list[i], gap = n ? Math.min(2600, Math.max(380, (Date.parse(n.t) - Date.parse(c.t)) / 60)) : 0;  // a minute of real time ~ 1 s
      next = t + gap / spd(); ui();
    }
    $("#fPlay").onclick = () => { if (i >= list.length) i = 0; playing = !playing; next = 0; ui(); };
    $("#fRe").onclick = () => { LIVE.clear(); i = 0; next = 0; playing = true; ui(); };
    $("#fPer").onchange = () => { LIVE.clear(); pick(); playing = true; ui(); };
    $("#fProg").onclick = e => { i = Math.floor(list.length * e.offsetX / Math.max(1, e.currentTarget.clientWidth)); next = 0; ui(); };
    $("#fLive").onclick = () => { if (DATA.live) { live = !live; ui(); } };
    async function poll() {
      if (!DATA.live) return;
      try { const r = await fetch(`calls?offset=${off}`, { cache: "no-store" }); const j = await r.json(); off = j.offset;
        (j.calls || []).forEach(c => { CALLS.push(c); if (live && mode === "live") LIVE.fire(c); });
        if ((j.calls || []).length) ui(); setTimeout(poll, 1500); } catch (e) { setTimeout(poll, 15000); /* the server was stopped: keep the page, retry rarely */ }
    }
    pick(); poll();
    return { step, ui, start() { if (list.length && i === 0) playing = true; ui(); } };
  })();

  let cur = "";
  function sub() { const n = RECS.length, c = k => RECS.filter(r => r.st === k).length;
    return `${fmtD(RECS[0] ? RECS[0].d : "")} — ${fmtD(RECS.length ? RECS[n - 1].d : "")} · ${n} записей · решений ${c("decision")} · смен ${c("change")} · на потом ${c("later")}` + (cur === "live" ? ` · вызовов в журнале ${CALLS.length}` : ""); }
  function start(m) {
    cur = m; hideTip();
    $("#app").classList.add("flow"); $("#app").classList.toggle("waves", m === "waves"); $("#app").classList.toggle("live", m === "live");
    stage.querySelectorAll("[data-fmode]").forEach(b => b.classList.toggle("on", b.dataset.fmode === m));
    $("#fTheme").style.display = m === "waves" ? "" : "none"; $("#fSub").textContent = sub(); $("#fLeg").innerHTML = legend();
    $("#fEmpty").style.display = "none";
    if (m === "waves") { LIVE.stop(); if (!RECS.length) { $("#fEmpty").textContent = "В памяти пока нет записей."; $("#fEmpty").style.display = "block"; } WAVES.draw(); }
    else { LIVE.start(); PLAY.start(); }
  }
  function stop() { cur = ""; LIVE.stop(); hideTip(); ["flow", "waves", "live"].forEach(c => $("#app").classList.remove(c)); }
  addEventListener("resize", () => { if (cur === "waves") WAVES.draw(); else if (cur === "live") LIVE.layout(); });
  new MutationObserver(() => { if (cur === "waves") { WAVES.draw(); $("#fLeg").innerHTML = legend(); } }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return { start, stop, openRecord, get mode() { return cur; }, fire: c => LIVE.fire(c) };
})();
window.FLOW = FLOW;
{ let m0 = DATA.mode; if (!m0) try { m0 = localStorage.getItem("ctxgraph.mode"); } catch (e) {}
  if (m0 === "waves" || m0 === "live") setMode(m0); }
