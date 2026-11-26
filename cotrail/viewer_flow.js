// «Живая память»: the project's chats and code as two trees (three.js) with pulses of the memory's MCP calls;
// a 2D Canvas fallback without WebGL.
// Data: DATA.flow (cotrail/flow.py: records with status / topic, topics), DATA.calls (calls.jsonl, cotrail/calls.py),
// DATA.live (the page is served by `cotrail view --live`: it polls `calls?offset=` for new calls).
// Shares the globals of the main viewer script (DATA, $, esc, css, showInsp, closeInsp, setMode, setTheme).
const FLOW = (() => {
  const F = DATA.flow || { records: [], topics: [] }, RECS = F.records, TOP = F.topics;
  const byRid = new Map(RECS.map(r => [r.id, r]));
  const find = id => byRid.get(String(id).slice(0, 8)) || (String(id).length < 8 ? RECS.find(r => r.id.startsWith(id)) : null);
  const ST = { decision: [tr("решение"), "#6fd3a0", "#2f8a64"], change: [tr("смена решения"), "#ffb347", "#b8741a"],
    report: [tr("отчёт"), "#7aa7ff", "#3a64c2"], later: [tr("на потом"), "#c3a6ff", "#7652c4"] };
  const light = () => document.documentElement.dataset.theme === "light" && mode !== "live";
  const stCol = (s, l = light()) => ST[s] ? ST[s][l ? 2 : 1] : (l ? "#a3a3aa" : "rgba(230,230,238,.34)");
  const tcol = k => k < 0 ? "#6b6b74" : (TOP[k] || {}).color || "#7d7d86";
  const tname = k => { if (k < 0) return tr("без темы"); const t = TOP[k] || {}; return t.other ? tr("другие темы ({0})", t.merged || "") : t.name || ""; };
  const DAY = 864e5, dms = s => Date.parse(s.slice(0, 10) + "T00:00:00Z");
  const fmtD = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(2, 4)}` : "";
  const CORAL = "#FF5F6D", GOLD = "#FFC371";

  document.head.insertAdjacentHTML("beforeend", `<style>
#livecv { position: absolute; inset: 0; width: 100%; height: 100%; display: none; }
.flowui { display: none; }
.app.flow aside, .app.flow #graph, .app.flow #graph3d, .app.flow .zoom, .app.flow #sky, .app.flow #cosmos, .app.flow .cosui { display: none !important; }
.app.flow .flowui { display: block; }
.app.flow.live #livecv { display: block; }
#live3d { position: absolute; inset: 0; display: none; background: #000; overflow: hidden; } #live3d canvas { display: block; cursor: grab; }
.app.flow.live.l3 #livecv { display: none; } .app.flow.live.l3 #live3d { display: block; }
.l3labs { position: absolute; inset: 0; pointer-events: none; } .l3lab.k { color: #a9dcff; } .l3lab.root { font-size: 13px; font-weight: 600; letter-spacing: .02em; } .l3lab { position: absolute; left: 0; top: 0; white-space: nowrap; font-size: 11.5px; color: #ffd9b0; text-shadow: 0 0 8px #000, 0 0 2px #000; }
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
.rec .tx { margin: 10px 0; } .rec .rp { color: var(--dim); border-left: 2px solid var(--line2); padding-left: 10px; margin: 8px 0; }
.rec .ch { cursor: pointer; } .rec .ch:hover .tx { color: var(--accent); }
</style>`);
  const stage = $("#stage");
  stage.insertAdjacentHTML("beforeend", `<canvas id="livecv"></canvas>
    <div class="flowui"><div class="ftop"><div class="fhdr fglass"><div><div class="p">${esc(DATA.name)}</div><div class="s" id="fSub"></div></div>
      <div class="fseg"><button data-fmode="2d">2D</button><button data-fmode="3d">3D</button><button data-fmode="cosmos">Космос</button><button data-fmode="live">Живая память</button></div><button class="fbtn" id="fLang" title="Язык">${I18N.lang === "ru" ? "EN" : "RU"}</button></div>
      <div class="fleg fglass" id="fLeg"></div></div><div class="ftip" id="fTip"></div><div class="fempty" id="fEmpty"></div>
      <div class="ftick fglass" id="fTick"></div>
      <div class="fbar fglass"><button class="fbtn" id="fPlay">▶</button><button class="fbtn" id="fRe" title="С начала">↺</button>
        <select id="fPer"><option value="1">час</option><option value="24" selected>сутки</option><option value="168">неделя</option><option value="720">месяц</option><option value="0">всё</option></select>
        <select id="fSpd"><option value="1">×1</option><option value="2" selected>×2</option><option value="4">×4</option></select>
        <div class="fprog" id="fProg"><b id="fProgB"></b></div><span class="fclock" id="fClock"></span>
        <button class="fbtn flive" id="fLive" title="Новые вызовы из calls.jsonl">● эфир</button></div></div>`);
  stage.querySelectorAll("[data-fmode]").forEach(b => b.onclick = () => setMode(b.dataset.fmode));
  $("#fLang").onclick = () => I18N.set(I18N.lang === "ru" ? "en" : "ru");
  const tip = $("#fTip");
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.style.display = "block";
    const W = stage.clientWidth, w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(W - w - 8, x + 14) + "px"; tip.style.top = Math.max(8, y - h - 10) + "px";
  }
  const hideTip = () => { tip.style.display = "none"; };
  const recTip = r => `<div class="w">${fmtD(r.d)} · <span style="color:${stCol(r.st)}">${ST[r.st] ? ST[r.st][0] : tr("запись")}</span> · ${esc(tname(r.topic))} · #${r.id}</div>${esc(r.t)}`;
  const legend = () => Object.entries(ST).map(([k, v]) => `<span><i style="background:${stCol(k)}"></i>${v[0]}</span>`).join("");

  // ── the record in the inspector, as the other views open a node ──
  function openRecord(r) {
    if (typeof r === "string") r = find(r);
    if (!r) return;
    const link = id => { const x = find(id); return x ? `<div class="item ch" data-rid="${x.id}"><div class="when"><span>${fmtD(x.d)}</span><span>#${x.id}</span></div><div class="tx">${esc(x.t)}</div></div>` : ""; };
    showInsp(`<div class="ih"><button class="x" onclick="closeInsp()">×</button>
      <div class="kind"><span class="sw" style="background:${stCol(r.st)};border-radius:50%"></span>${ST[r.st] ? ST[r.st][0] : tr("запись")} · #${r.id}</div>
      <h2>${esc(tname(r.topic))}</h2><div class="meta">${esc(r.ts.replace("T", " "))}</div></div>
      <div class="body rec"><div class="tx">${esc(r.t)}</div>${r.rep ? `<div class="rp">${tr("Отчёт: {0}", esc(r.rep))}</div>` : ""}
      ${r.chg.length ? `<div class="lbl" style="margin-top:16px">Меняет решение</div>${r.chg.map(link).join("")}` : ""}
      ${r.by.length ? `<div class="lbl" style="margin-top:16px">Решение изменено позже</div>${r.by.map(link).join("")}` : ""}
      <div class="hint">${tr("Полностью — в ассистенте: {0}.", `<code>expand("#${r.id}")</code>`)}</div></div>`);
    $("#insp").querySelectorAll("[data-rid]").forEach(el => el.onclick = () => { openRecord(el.dataset.rid); if (mode === "live") LIVE.flare(el.dataset.rid, 1); });
  }
  function openTopicRecs(k) {
    const rs = RECS.filter(r => r.topic === k).slice().reverse(), t = TOP[k];
    showInsp(`<div class="ih"><button class="x" onclick="closeInsp()">×</button><div class="kind"><span class="sw" style="background:${tcol(k)}"></span>Тема</div>
      <h2>${esc(tname(k))}</h2><div class="meta">${tr("{0} записей", rs.length)}${t ? ` · ${fmtD(t.first)} — ${fmtD(t.last)}` : ""}</div></div>
      <div class="body">${rs.map(r => `<div class="item ch" data-rid="${r.id}" style="cursor:pointer"><div class="when"><span>${fmtD(r.d)}</span>
        <span style="color:${stCol(r.st)}">${ST[r.st] ? ST[r.st][0] : ""}</span><span>#${r.id}</span></div><div class="tx">${esc(r.t)}</div></div>`).join("")}</div>`);
    $("#insp").querySelectorAll("[data-rid]").forEach(el => el.onclick = () => openRecord(el.dataset.rid));
  }
  const keys = [...TOP.map(t => t.id), ...(RECS.some(r => r.topic < 0) ? [-1] : [])];
  const d0 = RECS.length ? dms(RECS[0].d) : Date.now(), d1 = RECS.length ? dms(RECS[RECS.length - 1].d) : Date.now();

  // ── «Живая память»: trunk = project time, branches = topics, beads = records; pulses of recall / expand ──
  const LIVE2 = (() => {  // the 2D fallback when WebGL / three.js is not available
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
      const hh = new Date(c.t); tick.unshift(`<div>${String(hh.getHours()).padStart(2, "0")}:${String(hh.getMinutes()).padStart(2, "0")}:${String(hh.getSeconds()).padStart(2, "0")} · <b>${esc(c.tool)}</b> · ${tr("{0} зап. · {1} мс", os.length, c.ms)}</div>`);
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
      if (o) showTip(recTip(o.r), e.offsetX, e.offsetY); else if (lb) showTip(`<b>${esc(lb.t.name)}</b><br>${tr("{0} записей", lb.t.n)} · ${fmtD(lb.t.first)} — ${fmtD(lb.t.last)}`, e.offsetX, e.offsetY); else hideTip(); });
    cv.addEventListener("mouseleave", () => { hover = null; hlb = null; hideTip(); });
    cv.addEventListener("click", e => { const o = near(e.offsetX, e.offsetY); if (o) { openRecord(o.r); flare(o.r.id, 1); return; }
      const lb = label(e.offsetX, e.offsetY); if (lb) openTopicRecs(lb.k); });
    return { clear() { tick.length = 0; $("#fTick").innerHTML = ""; $("#fTick").classList.remove("has"); }, start() { layout(); if (!on) { on = true; raf = requestAnimationFrame(frame); } }, stop() { on = false; cancelAnimationFrame(raf); },
      layout, fire, flare, get on() { return on; } };
  })();

  // ── «Живая память» in 3D (three.js, MIT): the memory as a living tree (see build() below) with the Graphify code as a
  // second tree beside it. Pulses: recall runs from the root up the branches to each returned message, which flashes;
  // expand lights the record and runs along its chain of decision changes. The camera turns by itself; drag / wheel.
  const LIVE3 = !window.THREE ? null : (() => {
    const T = THREE, TR = DATA.trees || { sessions: [], turns: [], code: [] };
    const C0 = new T.Color(CORAL), C1 = new T.Color(GOLD), WHITE = new T.Color("#fff3e6"), K0 = new T.Color("#3f7fc4"), K1 = new T.Color("#9fe0ff");
    const host = document.createElement("div"); host.id = "live3d"; stage.appendChild(host);
    const labs = document.createElement("div"); labs.className = "l3labs"; host.appendChild(labs);
    let R = null, scene, cam, on = false, raf = 0, W = 1, H = 1, DPR = 1, last = 0, now = 0, built = false;
    let seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    const SIZE = { change: 15, decision: 12.5, later: 10, report: 7 };
    const orb = { r: 2150, th: 1.45, ph: 1.36, auto: 1, drag: null, tx: 0, ty: 430, tz: 0 };
    const UP = new T.Vector3(0, 1, 0);
    let beads = [], geo, pts, pulsePts, pulses = [], tips = [], tick = [], lines = [], beadOf = new Map();
    // ── the living tree: the memory grows as a tree that forks again and again into finer, slightly curved branches.
    // Conversations: trunk = the project -> members (team memory) -> big areas (the dominant topic of the chats) -> chats
    // (side sessions grow out of their parent chat) -> topics -> messages at the tips (records bigger, decisions
    // brightest), coral at the trunk -> gold at the tips. Code (Graphify): a second tree beside it, folders -> files ->
    // symbols, in blue. Past each tip a couple of finer twigs with dim points: decoration only, no data.
    const MAXD = 6, K0h = K0.clone().multiplyScalar(1), deco = [];
    const perp = d => new T.Vector3().crossVectors(d, Math.abs(d.y) < 0.9 ? UP : new T.Vector3(1, 0, 0)).normalize();
    function curveOf(a, d, len, bend) { const side = perp(d).applyAxisAngle(d, rnd() * 6.28).multiplyScalar(len * bend);
      const m = a.clone().add(d.clone().multiplyScalar(len * 0.5)).add(side), b = a.clone().add(d.clone().multiplyScalar(len)).add(side.clone().multiplyScalar(0.4));
      return new T.QuadraticBezierCurve3(a, m, b); }
    const colAt = (depth, code, side) => { const f = Math.min(1, depth / (MAXD + 1)); let c = code ? K0h.clone().lerp(K1, f).multiplyScalar(0.55) : C0.clone().lerp(C1, f).multiplyScalar(1 - 0.45 * f);
      if (side) c = c.lerp(WHITE, 0.25); return c; };
    function seg(curve, depth, code, side, n) { const pts = curve.getPoints(n), c = colAt(depth, code, side);
      for (let i = 0; i < n; i++) lines.push(pts[i].x, pts[i].y, pts[i].z, pts[i + 1].x, pts[i + 1].y, pts[i + 1].z, c.r, c.g, c.b, c.r, c.g, c.b); }
    // the hierarchy
    function chatTree() {
      const ss = TR.sessions, turnsOf = ss.map(() => []); TR.turns.forEach(r => turnsOf[r[1]] && turnsOf[r[1]].push(r));
      const topicOf = new Map(); turnsOf.forEach(rs => { let cur = -1; rs.forEach(r => { const x = find(r[0]); if (x && r[3] === "u") cur = x.topic; topicOf.set(r, cur); }); });
      const dom = i => { const c = {}; turnsOf[i].forEach(r => { const k = topicOf.get(r); if (k >= 0 && !(TOP[k] || {}).other) c[k] = (c[k] || 0) + 1; });
        const k = Object.keys(c).sort((a, b) => c[b] - c[a])[0]; return k === undefined ? -1 : +k; };
      const chatNode = i => { const byT = new Map(), node = { name: ss[i].label, side: ss[i].side, ses: i, kids: [] };
        turnsOf[i].forEach(r => { const k = topicOf.get(r); if (!byT.has(k)) { const t = { kids: [], side: ss[i].side }; byT.set(k, t); node.kids.push(t); } byT.get(k).kids.push({ leaf: r, ses: i, side: ss[i].side }); });
        return node; };
      const nodes = ss.map((_, i) => turnsOf[i].length ? chatNode(i) : null);
      ss.forEach((s, i) => { if (s.side && nodes[i] && nodes[s.parent]) nodes[s.parent].kids.push(nodes[i]); });  // side sessions grow out of their parent
      const mains = ss.map((s, i) => i).filter(i => nodes[i] && !(ss[i].side && nodes[ss[i].parent]));
      const sizeOf = {}; mains.forEach(i => { const k = dom(i); sizeOf[k] = (sizeOf[k] || 0) + ss[i].n; });
      const big = Object.keys(sizeOf).map(Number).filter(k => k >= 0).sort((a, b) => sizeOf[b] - sizeOf[a]).slice(0, 6);
      const byArea = (is) => { const m = new Map(); is.forEach(i => { const k = big.includes(dom(i)) ? dom(i) : "other";
        if (!m.has(k)) m.set(k, { name: k === "other" ? tr("другие темы ({0})", "").replace(" ()", "") : tname(k).split(" · ").slice(0, 2).join(" · "), label: true, kids: [] }); m.get(k).kids.push(nodes[i]); });
        return [...m.values()]; };
      const MEM = (TR.members && TR.members.length > 1) ? TR.members : null;
      return { kids: MEM ? MEM.map(m => ({ name: m, label: true, kids: byArea(mains.filter(i => (ss[i].author || "") === m)) })).filter(x => x.kids.length) : byArea(mains) };
    }
    function codeTree() {
      const layers = (TR.codes && TR.codes.length) ? TR.codes.map(c => ({ dirs: c.dirs, name: c.member })) : [{ dirs: TR.code || [], name: "" }];
      const dirs = Lr => Lr.dirs.map(d => ({ name: `${d.name} · ${d.n}`, label: !layers[1], kids: d.files.map(f => ({ kids: f.nodes.map(nd => ({ leaf: nd, f: f.name, m: Lr.name })) })) }));
      const kids = layers.length > 1 ? layers.map(Lr => ({ name: `${tr("код")}: ${Lr.name}`, label: true, kids: dirs(Lr) })) : dirs(layers[0]);
      return { kids: kids.filter(k => k.kids.length) };
    }
    const weigh = n => n.w = n.leaf ? 1 : n.kids.reduce((a, c) => a + weigh(c), 0);
    // growth: each node is one curved segment; children fan out around its end (and along it when there are many)
    function grow(node, a, d, len, depth, path, code, side) {
      const c = curveOf(a, d, len, 0.06 + 0.04 * depth), end = c.getPoint(1), dir = c.getTangent(1).normalize(), sd = side || node.side;
      seg(c, depth, code, sd, depth < 2 ? 16 : 8);
      const here = [...path, { curve: c, a: 0, b: 1 }];
      if (node.label && node.name) tips.push({ p: end.clone(), text: node.name, code, depth });
      if (node.leaf) {
        if (code) add(end, K1.clone().multiplyScalar(0.75), 3.0, { kind: "code", nd: node.leaf, f: node.f, m: node.m }, here);
        else { const r = node.leaf, x = r[3] === "u" ? find(r[0]) : null, st = x ? x.st : r[4];
          let col = C1.clone().lerp(WHITE, r[3] === "u" ? 0.25 : 0); if (st === "decision" || st === "change") col = WHITE.clone(); if (sd) col.lerp(WHITE, 0.2);
          const b = add(end, col, r[3] === "u" ? (SIZE[st] || 6.5) : 3.6, { kind: "turn", r, s: node.ses }, here); beadOf.set(r[0], b); }
        twigs(end, dir, len * 0.5, depth, code ? 1 : 2, code); return;
      }
      const kids = node.kids.slice().sort((x, y) => y.w - x.w), n = kids.length, spread = depth === 0 ? 0.75 : depth === 1 ? 0.9 : 0.62 + 0.06 * Math.min(4, n);
      kids.forEach((k, i) => {
        const share = Math.sqrt(k.w / node.w), az = i * 2.39996 + rnd() * 0.6, tilt = spread * (0.45 + 0.55 * (1 - share)) * (n === 1 ? 0.25 : 1);
        const nd = dir.clone().applyAxisAngle(perp(dir), tilt).applyAxisAngle(dir, az).lerp(UP, depth < 1 ? 0.2 : depth < 3 ? 0.08 : 0.02).normalize();
        const s0 = n > 6 && i > 2 ? 0.55 + 0.45 * rnd() : 1, at = c.getPoint(s0);
        const kl = len * (k.leaf ? 0.3 + 0.18 * rnd() : 0.6 + 0.3 * share) * (depth === 0 ? 1.35 : 1);
        grow(k, at, nd, Math.max(kl, 3), depth + 1, s0 < 1 ? [...path, { curve: c, a: 0, b: s0 }] : here, code, sd);
      });
    }
    function twigs(a, d, len, depth, left, code) {
      if (left <= 0) return;
      for (let i = 0; i < 2; i++) { const nd = d.clone().applyAxisAngle(perp(d), 0.5 + 0.4 * rnd()).applyAxisAngle(d, rnd() * 6.28).lerp(UP, 0.1).normalize();
        const c = curveOf(a, nd, len * (0.5 + 0.4 * rnd()), 0.12), e = c.getPoint(1); seg(c, depth + 1, code, false, 4); deco.push({ p: e, code }); twigs(e, nd, len * 0.6, depth + 1, left - 1, code); }
    }
    const add = (pos, col, size, info, path) => { const b = { pos, col, size, info, path, flash: 0, f0: 0, i: beads.length }; beads.push(b); return b; };
    let trunk = null;
    function build() {
      built = true;
      R = new T.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
      R.setClearColor(0x000000, 1); host.insertBefore(R.domElement, labs);
      scene = new T.Scene(); scene.fog = new T.FogExp2(0x000000, 0.0004);
      cam = new T.PerspectiveCamera(40, 1, 1, 60000);
      const chat = chatTree(), code = codeTree(); weigh(chat); weigh(code);
      const H = 70 + 15 * Math.sqrt(chat.w || 1), HK = 70 + 15 * Math.sqrt(code.w || 1), GAP = code.w ? 1.55 * (H + HK) : 0;
      const A = new T.Vector3(-GAP / 2, 0, 0), B = new T.Vector3(GAP / 2, 0, 0);
      if (chat.w) grow(chat, A, UP.clone(), H, 0, [], false, false);
      if (code.w) grow(code, B, UP.clone(), HK, 0, [], true, false);
      trunk = A;
      // branches: one LineSegments
      const lg = new T.BufferGeometry(), nl = lines.length / 12, LP = new Float32Array(nl * 6), LC = new Float32Array(nl * 6);
      for (let i = 0; i < nl; i++) { LP.set(lines.slice(i * 12, i * 12 + 6), i * 6); LC.set(lines.slice(i * 12 + 6, i * 12 + 12), i * 6); }
      lg.setAttribute("position", new T.BufferAttribute(LP, 3)); lg.setAttribute("color", new T.BufferAttribute(LC, 3));
      scene.add(new T.LineSegments(lg, new T.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.75, blending: T.AdditiveBlending, depthWrite: false, fog: true })));
      // the data beads (pickable), then decoration and stars (not pickable)
      const n = beads.length, P = new Float32Array(n * 3), Cc = new Float32Array(n * 3), S = new Float32Array(n), F = new Float32Array(n);
      beads.forEach((b, i) => { P.set([b.pos.x, b.pos.y, b.pos.z], i * 3); Cc.set([b.col.r, b.col.g, b.col.b], i * 3); S[i] = b.size; });
      geo = new T.BufferGeometry(); geo.setAttribute("position", new T.BufferAttribute(P, 3)); geo.setAttribute("acol", new T.BufferAttribute(Cc, 3));
      geo.setAttribute("size", new T.BufferAttribute(S, 1)); geo.setAttribute("flash", new T.BufferAttribute(F, 1));
      pts = new T.Points(geo, glow()); scene.add(pts);
      const box = new T.Box3(); beads.forEach(b => box.expandByPoint(b.pos)); deco.forEach(d => box.expandByPoint(d.p)); box.expandByPoint(A); box.expandByPoint(B);
      const sz = box.getSize(new T.Vector3()), ctr = box.getCenter(new T.Vector3()), ext = Math.max(1, sz.length());
      const dp = [], dc = [], ds = [];
      deco.forEach(({ p, code }) => { const c = (code ? K1 : C1).clone().multiplyScalar(code ? 0.35 : 0.5 + 0.3 * rnd()); dp.push(p.x, p.y, p.z); dc.push(c.r, c.g, c.b); ds.push(1.4 + rnd()); });
      for (let i = 0; i < 1400; i++) { const r = ext * (0.9 + rnd() * 2.5), th = rnd() * 6.283, ph = Math.acos(2 * rnd() - 1);
        dp.push(ctr.x + r * Math.sin(ph) * Math.cos(th), ctr.y + r * Math.cos(ph) * 0.6, ctr.z + r * Math.sin(ph) * Math.sin(th)); const g = 0.25 + rnd() * 0.3; dc.push(g, g * 0.9, g * 0.85); ds.push(1.2 + rnd() * 1.5); }
      const dg = new T.BufferGeometry(); dg.setAttribute("position", new T.Float32BufferAttribute(dp, 3)); dg.setAttribute("acol", new T.Float32BufferAttribute(dc, 3));
      dg.setAttribute("size", new T.Float32BufferAttribute(ds, 1)); dg.setAttribute("flash", new T.Float32BufferAttribute(new Float32Array(ds.length), 1)); scene.add(new T.Points(dg, glow()));
      const pn = 64 * 10, pg = new T.BufferGeometry(); pg.setAttribute("position", new T.BufferAttribute(new Float32Array(pn * 3), 3));
      pg.setAttribute("acol", new T.BufferAttribute(new Float32Array(pn * 3), 3)); pg.setAttribute("size", new T.BufferAttribute(new Float32Array(pn), 1));
      pg.setAttribute("flash", new T.BufferAttribute(new Float32Array(pn), 1)); pulsePts = new T.Points(pg, glow()); pulsePts.frustumCulled = false; scene.add(pulsePts);
      // fog and point scale follow the tree's size (a small demo or a large store)
      scene.fog.density = 0.32 / ext; scene.traverse(o => { if (o.material && o.material.uniforms) o.material.uniforms.uFog.value = 0.28 / ext; });
      if (chat.w) tips.push({ p: A.clone().add(new T.Vector3(0, -0.03 * ext, 0)), text: tr("разговоры"), root: true });
      if (code.w) tips.push({ p: B.clone().add(new T.Vector3(0, -0.03 * ext, 0)), text: tr("код · Graphify"), root: true, code: true });
      orb.tx = ctr.x; orb.ty = ctr.y; orb.tz = ctr.z; orb.r = 1.9 * Math.max(sz.y, sz.x * 0.62) + 40; orb.ph = 1.5; orb.th = Math.PI / 2;
      tips.forEach(tp => { if (!tp.text) return; tp.el = document.createElement("div"); tp.el.className = "l3lab" + (tp.code ? " k" : "") + (tp.root ? " root" : ""); tp.el.textContent = tp.text; labs.appendChild(tp.el); });
      const cvs = R.domElement;
      cvs.addEventListener("pointerdown", e => { orb.drag = [e.clientX, e.clientY, e.clientX, e.clientY]; orb.auto = 0; cvs.setPointerCapture(e.pointerId); });
      cvs.addEventListener("pointermove", e => { if (orb.drag) { orb.th += (e.clientX - orb.drag[0]) * 0.005; orb.ph = Math.max(0.35, Math.min(2.2, orb.ph - (e.clientY - orb.drag[1]) * 0.005));
        orb.drag[0] = e.clientX; orb.drag[1] = e.clientY; return; } hoverAt(e); });
      cvs.addEventListener("pointerup", e => { const d = orb.drag; orb.drag = null; setTimeout(() => { orb.auto = 1; }, 2500);
        if (d && Math.hypot(e.clientX - d[2], e.clientY - d[3]) < 4) { const b = pick(e); if (b) open(b); } });
      cvs.addEventListener("wheel", e => { e.preventDefault(); orb.r = Math.max(40, Math.min(60000, orb.r * (e.deltaY > 0 ? 1.1 : 0.9))); }, { passive: false });
      cvs.addEventListener("pointerleave", () => hideTip());
    }
    function glow() {
      return new T.ShaderMaterial({ transparent: true, depthWrite: false, blending: T.AdditiveBlending,
        uniforms: { uPix: { value: 1 }, uFog: { value: 0.00034 }, uK: { value: 1500 } },
        vertexShader: `attribute float size; attribute float flash; attribute vec3 acol; varying vec3 vC; varying float vA; varying float vF;
          uniform float uPix; uniform float uFog; uniform float uK;
          void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); float d = max(1.0, -mv.z); vA = exp(-d * d * uFog * uFog);
            vC = acol; vF = flash; gl_PointSize = min(64.0, max(1.4 * uPix, size * (1.0 + flash * 1.8) * uPix * (uK / d))); gl_Position = projectionMatrix * mv; }`,
        fragmentShader: `varying vec3 vC; varying float vA; varying float vF;
          void main() { vec2 p = gl_PointCoord - 0.5; float r = length(p) * 2.0; if (r > 1.0) discard;
            float core = smoothstep(0.36, 0.0, r), halo = pow(1.0 - r, 2.3) * 0.65;
            vec3 c = vC * (halo + core * 0.9) + vec3(1.0, 0.94, 0.86) * core * (0.35 + vF);
            gl_FragColor = vec4(c * vA * (1.0 + vF * 1.4), 1.0); }` });
    }
    function size() {
      DPR = Math.min(2, devicePixelRatio || 1); W = Math.max(1, stage.clientWidth); H = Math.max(1, stage.clientHeight);
      R.setPixelRatio(DPR); R.setSize(W, H); cam.aspect = W / H; cam.updateProjectionMatrix();
      scene.traverse(o => { if (o.material && o.material.uniforms) { o.material.uniforms.uPix.value = DPR; o.material.uniforms.uK.value = 1.6 * H; } });
    }
    const ray = new T.Raycaster(); ray.params.Points.threshold = 5;
    function pick(e) { const r = R.domElement.getBoundingClientRect(); ray.setFromCamera({ x: (e.clientX - r.left) / r.width * 2 - 1, y: -(e.clientY - r.top) / r.height * 2 + 1 }, cam);
      const h = ray.intersectObject(pts)[0]; return h ? beads[h.index] : null; }
    const sesName = i => (TR.sessions[i] || {}).label || "";
    function tipOf(b) { const x = b.info;
      if (x.kind === "code") return `<div class="w">${tr("код")}${x.m ? " · " + esc(x.m) : ""} · ${esc(x.f)}${x.nd[1] ? ":" + esc(x.nd[1]) : ""}</div>${esc(x.nd[0])}`;
      const r = x.r, s = TR.sessions[x.s] || {}; return `<div class="w">${fmtD(r[2].slice(0, 10))} ${r[2].slice(11, 16)} · ${r[3] === "u" ? (s.author ? esc(s.author) : tr("вы")) : tr("ассистент")}${ST[r[4]] ? " · " + ST[r[4]][0] : ""} · ${tr(s.side ? "сессия-субагент" : "чат")} #${r[0]}</div>${esc(r[5])}`; }
    function hoverAt(e) { const b = pick(e); R.domElement.style.cursor = b ? "pointer" : "grab"; const r = R.domElement.getBoundingClientRect();
      if (b) showTip(tipOf(b), e.clientX - r.left, e.clientY - r.top); else hideTip(); }
    function open(b) { flare(b, 1); const x = b.info;
      if (x.kind === "turn" && find(x.r[0])) return openRecord(x.r[0]);
      showInsp(`<div class="ih"><button class="x" onclick="closeInsp()">×</button><div class="kind">${tr(x.kind === "code" ? "Код · Graphify" : (x.r[3] === "u" ? "Ваша реплика" : "Ответ ассистента"))}</div>
        <h2>${esc(x.kind === "code" ? x.nd[0] : sesName(x.s))}</h2><div class="meta">${esc(x.kind === "code" ? x.f + (x.nd[1] ? ":" + x.nd[1] : "") : x.r[2].replace("T", " "))}</div></div>
        <div class="body rec"><div class="tx">${esc(x.kind === "code" ? "" : x.r[5])}</div>${x.kind === "turn" ? `<div class="hint">${tr("Полностью — в ассистенте: {0}.", `<code>expand("#${x.r[0]}")</code>`)}</div>` : ""}</div>`); }
    // a pulse path: from the root up the trunk, along the branch (and its forks / parents) to the bead
    function pathOf(b) {
      const segs = b.path.filter(s => s.b > s.a).map(s => { const c = s.curve, a = s.a, z = s.b; return { len: c.getLength() * (z - a), at: f => c.getPointAt(a + (z - a) * f) }; });
      const end = segs.length ? segs[segs.length - 1].at(1) : b.pos.clone(); segs.push({ len: end.distanceTo(b.pos), at: f => end.clone().lerp(b.pos, f) });
      const len = segs.reduce((a, s) => a + s.len, 0) || 1;
      return { len, at: x => { let d = x * len; for (const s of segs) { if (d <= s.len || s === segs[segs.length - 1]) return s.at(s.len ? Math.min(1, d / s.len) : 1); d -= s.len; } } };
    }
    const bead = id => { const k = String(id).slice(0, 8); return beadOf.get(k) || [...beadOf.entries()].find(([x]) => x.startsWith(k))?.[1]; };
    function flare(b, s = 1, delay = 0) { if (typeof b === "string") b = bead(b); if (b) { b.f0 = now + delay; b.flash = s; } }
    function fire(c) {
      if (!built) return;
      const bs = (c.ids || []).map(bead).filter(Boolean);
      if (c.tool === "recall") bs.forEach((b, i) => { const p = pathOf(b); pulses.push({ p, b, t0: now + i * 120, dur: 1000 + p.len * 0.9 }); });
      else if (c.tool === "expand" && bs.length) { const b = bs[0], p = pathOf(b); pulses.push({ p, b, t0: now, dur: 1000 + p.len * 0.9, s: 1.8 });
        const r0 = find(b.info.r ? b.info.r[0] : ""), seen = new Set(r0 ? [r0.id] : []), q = r0 ? [r0] : []; let k = 0;
        while (q.length) { const r = q.shift(); [...r.chg, ...r.by].forEach(id => { const x = find(id), xb = x && bead(x.id), from = bead(r.id); if (xb && from && !seen.has(x.id)) { seen.add(x.id); q.push(x); k++;
          pulses.push({ p: { len: 1, at: f => from.pos.clone().lerp(xb.pos, f).add(new T.Vector3(0, Math.sin(f * Math.PI) * 40, 0)) }, b: xb, t0: now + 1600 + k * 500, dur: 900, s: 1.3 }); } }); } }
      else bs.forEach((b, i) => flare(b, 0.6, i * 60));
      const hh = new Date(c.t); tick.unshift(`<div>${String(hh.getHours()).padStart(2, "0")}:${String(hh.getMinutes()).padStart(2, "0")}:${String(hh.getSeconds()).padStart(2, "0")} · <b>${esc(c.tool)}</b> · ${tr("{0} зап. · {1} мс", bs.length, c.ms)}</div>`);
      tick.length = Math.min(tick.length, 5); $("#fTick").innerHTML = tick.join(""); $("#fTick").classList.add("has");
    }
    const V = new T.Vector3();
    function frame(t) {
      if (!on) return; raf = requestAnimationFrame(frame); const dt = last ? Math.min(64, t - last) : 16; last = t; now = t;
      if (orb.auto && !orb.drag) orb.th += dt * 0.00005;
      cam.position.set(orb.tx + orb.r * Math.sin(orb.ph) * Math.cos(orb.th), orb.ty + orb.r * Math.cos(orb.ph), orb.tz + orb.r * Math.sin(orb.ph) * Math.sin(orb.th)); cam.lookAt(orb.tx, orb.ty, orb.tz);
      const F = geo.attributes.flash.array; let dirty = false;
      for (const b of beads) { if (!b.flash) continue; const e = (now - b.f0) / 2400, v = e < 0 ? 0 : e >= 1 ? 0 : b.flash * (1 - e) * (1 - e); if (e >= 1) b.flash = 0; F[b.i] = v; dirty = true; }
      if (dirty) geo.attributes.flash.needsUpdate = true;
      const pp = pulsePts.geometry.attributes, PP = pp.position.array, PC = pp.acol.array, PS = pp.size.array; PS.fill(0);
      let slot = 0;
      for (let i = pulses.length - 1; i >= 0; i--) { const q = pulses[i], u = (now - q.t0) / q.dur; if (u < 0) continue;
        if (u >= 1) { flare(q.b, q.s || 1); pulses.splice(i, 1); continue; } if (slot >= 64) continue;
        const e = u * u * (3 - 2 * u);
        for (let j = 0; j < 10; j++) { const p = q.p.at(Math.max(0, e - j * 0.016)), k = slot * 10 + j; PP[k * 3] = p.x; PP[k * 3 + 1] = p.y; PP[k * 3 + 2] = p.z;
          const c = j ? C0.clone().lerp(C1, 1 - j / 10) : WHITE; PC.set([c.r, c.g, c.b], k * 3); PS[k] = (j ? 11 * (1 - j / 10) : 16) * (q.s || 1); }
        slot++; }
      pp.position.needsUpdate = pp.acol.needsUpdate = pp.size.needsUpdate = true;
      R.render(scene, cam);
      tips.forEach(tp => { if (!tp.el) return; V.copy(tp.p).project(cam); const vis = V.z < 1 && Math.abs(V.x) < 1.05 && Math.abs(V.y) < 1.05;
        tp.el.style.display = vis ? "" : "none"; if (!vis) return; const d = cam.position.distanceTo(tp.p);
        tp.el.style.transform = `translate(${(V.x + 1) / 2 * W + 8}px, ${(1 - V.y) / 2 * H - 8}px)`; tp.el.style.opacity = tp.root ? 0.95 : Math.max(0.15, Math.min(0.9, 1.5 - d / (1.4 * orb.r))); });
      PLAY.step(t);
    }
    return { l3: true, legend: `<span><i style="background:linear-gradient(90deg,${CORAL},${GOLD})"></i>${tr("разговоры")}: ${tr("ствол → реплики")}</span><span><i style="background:${GOLD};box-shadow:0 0 6px #fff"></i>${tr("боковые ветки — сессии-субагенты")}</span><span><i style="background:#6fb0e8"></i>${tr("код (Graphify)")}</span><span>${tr("крупнее — решения и смены решений")}</span>`,
      start() { if (!built) build(); $("#app").classList.add("l3"); size(); if (!on) { on = true; last = 0; raf = requestAnimationFrame(frame); } },
      stop() { on = false; cancelAnimationFrame(raf); $("#app").classList.remove("l3"); }, layout() { if (built) size(); }, fire, flare,
      count: () => beads.length,
      clear() { tick.length = 0; $("#fTick").innerHTML = ""; $("#fTick").classList.remove("has"); } };
  })();
  const LIVE = LIVE3 || LIVE2;

  // ── playback of calls.jsonl over a period, and live calls when served by `cotrail view --live` ──
  const CALLS = (DATA.calls || []).slice();
  const PLAY = (() => {
    let list = [], i = 0, playing = false, next = 0, live = !!DATA.live, off = DATA.offset || 0;
    const per = () => +$("#fPer").value, spd = () => +$("#fSpd").value;
    function pick() { const last = CALLS.length ? Date.parse(CALLS[CALLS.length - 1].t) : 0, h = per();
      list = CALLS.filter(c => !h || Date.parse(c.t) >= last - h * 36e5); i = 0; next = 0; ui(); }
    function ui() { $("#fPlay").textContent = playing ? "❚❚" : "▶"; $("#fProgB").style.width = list.length ? (100 * i / list.length) + "%" : "0";
      const c = list[Math.min(i, list.length - 1)], d = c ? new Date(c.t) : null;
      $("#fClock").textContent = d ? `${d.toLocaleDateString(I18N.lang === "ru" ? "ru-RU" : "en-US")} ${d.toLocaleTimeString(I18N.lang === "ru" ? "ru-RU" : "en-US")} · ${i}/${list.length}` : tr("нет вызовов за период");
      $("#fLive").classList.toggle("on", live); $("#fLive").title = tr(DATA.live ? "Новые вызовы из calls.jsonl" : "Живой эфир — через cotrail view --live");
      const empty = !CALLS.length; $("#fEmpty").classList.toggle("side", !!RECS.length); $("#fEmpty").style.display = empty && mode === "live" ? "block" : "none";
      $("#fEmpty").innerHTML = RECS.length ? `${tr("Журнал вызовов пуст. Он пишется, когда ассистент вызывает recall / expand через MCP-сервер cotrail:")}<br><span class="mono">${esc(tr("~/.cotrail/<проект>/calls.jsonl"))}</span>${DATA.live ? "<br>" + tr("Жду вызовов…") : "<br>" + tr("Живой эфир:") + " <span class=\"mono\">cotrail view --live</span>"}` : tr("В памяти пока нет записей."); }
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
    return tr("{0} — {1} · {2} записей · решений {3} · смен {4} · на потом {5}", fmtD(RECS[0] ? RECS[0].d : ""), fmtD(RECS.length ? RECS[n - 1].d : ""), n, c("decision"), c("change"), c("later")) + (cur === "live" ? tr(" · вызовов в журнале {0}", CALLS.length) : ""); }
  function start(m) {
    cur = m; hideTip();
    $("#app").classList.add("flow"); $("#app").classList.toggle("live", m === "live");
    stage.querySelectorAll("[data-fmode]").forEach(b => b.classList.toggle("on", b.dataset.fmode === m));
    $("#fSub").textContent = sub(); $("#fLeg").innerHTML = m === "live" && LIVE.l3 ? LIVE.legend : legend();
    $("#fEmpty").style.display = "none";
    LIVE.start(); PLAY.start();
  }
  function stop() { cur = ""; LIVE.stop(); hideTip(); ["flow", "live"].forEach(c => $("#app").classList.remove(c)); }
  addEventListener("resize", () => { if (cur === "live") LIVE.layout(); });
  return { start, stop, openRecord, get mode() { return cur; }, fire: c => LIVE.fire(c) };
})();
window.FLOW = FLOW;
{ let m0 = DATA.mode; if (!m0) try { m0 = localStorage.getItem("cotrail.mode"); } catch (e) {}
  if (m0 === "live") setMode(m0); }
