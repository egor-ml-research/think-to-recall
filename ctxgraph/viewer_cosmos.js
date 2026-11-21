// Cosmic view of the memory graph: plain Canvas 2D with its own render loop (no library).
// Core = the project; topics (Louvain communities) = constellations on a tilted disk; concepts = stars.
// Shares the globals of the main viewer script (DATA, $, esc, col, R, lit, vis, openTopic, openNode, closeInsp, ...).
const COS = (() => {
  const CSS = `
#cosmos { position: absolute; inset: 0; display: none; width: 100%; height: 100%; touch-action: none; }
.cosui { display: none; }
.app.cos { grid-template-columns: 0 1fr 0 !important; display: block;
  --canvas: #030306; --side: rgba(13,13,19,.88); --raise: rgba(255,255,255,.04); --hover: rgba(255,255,255,.07);
  --line: rgba(255,255,255,.08); --line2: rgba(255,255,255,.13); --text: #e6e6ec; --dim: #a6a6b0; --faint: #72727c;
  --accent: #b3a6f5; --yes: #66c29a; --no: #e08479; }
.app.cos aside, .app.cos #graph, .app.cos #graph3d, .app.cos .zoom, .app.cos #sky { display: none !important; }
.app.cos .stage { position: fixed; inset: 0; height: auto; background: #030306; }
.app.cos #cosmos, .app.cos .cosui { display: block; }
.app.cos .insp { position: fixed; right: 16px; top: 62px; bottom: 78px; width: 392px; max-width: calc(100vw - 32px); z-index: 6;
  border: 1px solid var(--line2); border-radius: 14px; backdrop-filter: blur(16px); box-shadow: 0 24px 70px rgba(0,0,0,.55); }
.app.cos.no-insp .insp { display: none; }
.app.cos .ih { background: #0e0e15; border-radius: 14px 14px 0 0; }
.cg { position: absolute; left: 24px; top: 20px; width: min(340px, calc(100vw - 48px)); color: #e6e6ec; z-index: 3;
  text-shadow: 0 1px 12px #000; pointer-events: auto; }
.cg .p { font-weight: 600; font-size: 13px; } .cg .s { color: #8a8a94; font-size: 11.5px; font-variant-numeric: tabular-nums; }
.cg h1 { font-size: 24px; font-weight: 600; letter-spacing: -.02em; margin: 26px 0 2px; }
.cg .since { color: #8a8a94; font-size: 12px; margin-bottom: 12px; }
.cg .sum { font-size: 13.5px; line-height: 1.55; color: #d4d4dc; }
.cg .h { font-size: 10.5px; font-weight: 600; color: #e0a46a; text-transform: uppercase; letter-spacing: .08em; margin: 16px 0 6px; }
.cg .d { display: grid; grid-template-columns: 52px 1fr; gap: 8px; font-size: 12px; color: #c4c4cc; margin: 3px 0; }
.cg .d b { font-weight: 500; color: #e0a46a; font-variant-numeric: tabular-nums; } .cg .d.no b { color: #e08479; } .cg .d.yes b { color: #66c29a; }
.cg .d span { overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.cg .ln { display: block; color: #9fb7ff; font-size: 12.5px; margin-top: 6px; cursor: pointer; } .cg .ln:hover { color: #c9d6ff; }
.cg .hide { position: absolute; right: 0; top: 0; border: 0; background: none; color: #6d6d76; cursor: pointer; font-size: 15px; }
.cg.min .body2 { display: none; }
.cglass { background: rgba(20,20,28,.66); border: 1px solid rgba(255,255,255,.1); backdrop-filter: blur(12px); color: #d8d8e0; }
.chome { position: absolute; left: 50%; top: 18px; transform: translateX(-50%); z-index: 3; height: 30px; padding: 0 16px; border-radius: 15px;
  font: inherit; font-size: 12.5px; cursor: pointer; }
.ctr { position: absolute; right: 18px; top: 18px; z-index: 3; display: flex; gap: 8px; }
.ctr button, .cbar button { font: inherit; font-size: 12.5px; cursor: pointer; }
.ctr .pg { height: 30px; padding: 0 14px; border-radius: 15px; }
.cseg { display: flex; height: 30px; border-radius: 15px; overflow: hidden; }
.cseg button { border: 0; background: none; color: #8f8f99; padding: 0 11px; } .cseg button.on { color: #fff; background: rgba(255,255,255,.1); }
.cbar { position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 3; display: flex; gap: 2px; padding: 4px; border-radius: 12px; }
.cbar button { width: 34px; height: 30px; border: 0; border-radius: 8px; background: none; color: #a8a8b2; font-size: 15px; }
.cbar button:hover, .chome:hover, .ctr .pg:hover { background: rgba(255,255,255,.1); color: #fff; }
.cbar .sep { width: 1px; margin: 6px 3px; background: rgba(255,255,255,.12); }
.ctip { position: absolute; z-index: 4; pointer-events: none; padding: 3px 8px; border-radius: 6px; font-size: 12px; display: none;
  background: rgba(14,14,20,.88); color: #eee; border: 1px solid rgba(255,255,255,.1); white-space: nowrap; }
.cdash { position: fixed; inset: 0; z-index: 8; display: none; background: rgba(2,2,6,.35); }
.cdash.on { display: block; }
.cdash .w { position: absolute; left: 50%; top: 58px; transform: translateX(-50%); width: min(1040px, calc(100vw - 32px)); max-height: calc(100vh - 128px);
  overflow: auto; border-radius: 16px; padding: 16px; background: rgba(16,16,23,.84); border: 1px solid rgba(255,255,255,.1);
  backdrop-filter: blur(18px); box-shadow: 0 30px 90px rgba(0,0,0,.6); color: #e6e6ec; }
.cdash input { width: 100%; height: 40px; padding: 0 14px; border-radius: 10px; border: 1px solid rgba(255,255,255,.16); background: rgba(255,255,255,.04);
  color: #eee; font: inherit; font-size: 14px; outline: none; } .cdash input:focus { border-color: #8d7ff0; }
.dg { display: grid; gap: 12px; margin-top: 14px; }
.dg.c4 { grid-template-columns: repeat(4, 1fr); } .dg.c3 { grid-template-columns: 1.3fr 1fr 1fr; } .dg.c2 { grid-template-columns: 1fr 1fr; }
@media (max-width: 860px) { .dg.c4, .dg.c3 { grid-template-columns: 1fr 1fr; } .dg.c2 { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .dg.c4, .dg.c3 { grid-template-columns: 1fr; } .cg { display: none; } }
.dc { border-radius: 12px; padding: 14px; background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08); min-width: 0; }
.dc.st { border-color: color-mix(in srgb, var(--c) 55%, transparent); background: linear-gradient(160deg, color-mix(in srgb, var(--c) 10%, transparent), rgba(255,255,255,.02)); }
.dc .big { font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.dc .cap { font-size: 12px; color: #c4c4cc; } .dc .cap2 { font-size: 11.5px; color: #7d7d87; }
.dc .bdg { float: right; font-size: 11px; padding: 1px 7px; border-radius: 6px; color: var(--c); border: 1px solid color-mix(in srgb, var(--c) 50%, transparent); }
.mb { display: flex; align-items: flex-end; gap: 3px; height: 30px; margin-top: 10px; } .mb i { flex: 1; background: var(--c); border-radius: 2px 2px 0 0; opacity: .85; min-height: 2px; }
.dc .t { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 7px; } .dc .t i { width: 7px; height: 7px; border-radius: 2px; background: var(--c); }
.dc .t2 { font-size: 11.5px; color: #7d7d87; margin: 2px 0 10px; }
.br { cursor: pointer; padding: 4px 0; } .br:hover .nm { color: #fff; }
.br .l { display: flex; justify-content: space-between; gap: 8px; font-size: 12.5px; color: #cfcfd7; }
.br .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .br .v { color: #7d7d87; font-variant-numeric: tabular-nums; }
.br .bb { height: 4px; border-radius: 2px; background: rgba(255,255,255,.06); margin-top: 4px; } .br .bb i { display: block; height: 100%; border-radius: 2px; background: var(--c); }
.dcl { font-size: 10.5px; font-weight: 600; color: #7d7d87; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px; }
.dd { padding: 7px 0; border-bottom: 1px solid rgba(255,255,255,.06); font-size: 12.5px; cursor: pointer; } .dd:last-child { border-bottom: 0; }
.dd .m { font-size: 11px; color: #7d7d87; margin-top: 2px; display: flex; gap: 8px; } .dd .m .k { color: var(--c); }
.dd .x { overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; color: #d8d8e0; }
.ach text { fill: #6f6f79; font-size: 10px; font-family: inherit; }
`;
  document.head.insertAdjacentHTML("beforeend", `<style>${CSS}</style>`);
  const stage = $("#stage");
  stage.insertAdjacentHTML("beforeend", `<canvas id="cosmos"></canvas>
  <div class="cosui">
    <div class="cg" id="cg"></div>
    <button class="chome cglass" id="cHome">Обзор</button>
    <div class="ctr"><button class="pg cglass" id="cDash">Панель</button>
      <div class="cseg cglass"><button data-mode="2d">2D</button><button data-mode="3d">3D</button><button data-mode="cosmos">Космос</button><button data-mode="waves">Волны</button><button data-mode="live">Живая</button></div></div>
    <div class="cbar cglass"><button id="cOut" title="Отдалить">−</button><button id="cIn" title="Приблизить">+</button><span class="sep"></span>
      <button id="cReset" title="Вернуть вид">⟲</button><button id="cPause" title="Пауза вращения">❚❚</button><button id="cFull" title="Во весь экран">⛶</button></div>
    <div class="ctip" id="cTip"></div>
  </div>
  <div class="cdash" id="cdash"><div class="w" id="cdw"></div></div>`);
  const cv = $("#cosmos"), ctx = cv.getContext("2d"), tip = $("#cTip");
  let W = 1, H = 1, DPR = 1, F = 1, running = false, raf = 0, last = 0, paused = false, time = 0;

  // ---------- deterministic layout ----------
  let seed = 1234567;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const gauss = () => { let u = 0; while (!u) u = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rnd()); };
  const T = DATA.topics, K = Math.max(1, T.length);
  const conv = DATA.nodes.filter(n => !isCode(n));
  const tc = T.map((t, i) => {
    const a = 2 * Math.PI * i / K + 0.35, r = (i % 2 ? 470 : 330) + 18 * Math.sqrt(i);
    return { x: r * Math.cos(a), y: (rnd() - 0.5) * 50, z: r * Math.sin(a), spread: 24 + 7.5 * Math.sqrt(t.size) };
  });
  const P = new Map();  // concept id -> world position
  const byTopic = T.map(() => []);
  conv.forEach(n => { if (n.topic >= 0 && byTopic[n.topic]) byTopic[n.topic].push(n); });
  byTopic.forEach((ns, t) => {
    ns.sort((a, b) => b.deg - a.deg);
    const c = tc[t];
    ns.forEach((n, k) => {
      const s = c.spread * (0.35 + 0.75 * Math.sqrt((k + 1) / ns.length));
      P.set(n.id, { x: c.x + gauss() * s * 0.6, y: c.y + gauss() * s * 0.22, z: c.z + gauss() * s * 0.6 });
    });
  });
  conv.forEach(n => { if (!P.has(n.id)) { const a = rnd() * 2 * Math.PI, r = 620 + gauss() * 40;
    P.set(n.id, { x: r * Math.cos(a), y: gauss() * 20, z: r * Math.sin(a) }); } });
  const dust = Array.from({ length: 1100 }, () => {
    const r = 70 + Math.pow(rnd(), 1.6) * 680, arm = rnd() < 0.5 ? 0 : Math.PI;
    const a = arm + Math.log(r / 60) * 1.9 + gauss() * 0.42;
    return { x: r * Math.cos(a), y: gauss() * (6 + r * 0.03), z: r * Math.sin(a), a: 0.12 + rnd() * 0.4, s: 0.5 + rnd() * 1.1, w: rnd() < 0.25 };
  });
  const stars = Array.from({ length: 1500 }, () => {
    const u = rnd() * 2 - 1, th = rnd() * 2 * Math.PI, q = Math.sqrt(1 - u * u);
    return { x: q * Math.cos(th), y: u, z: q * Math.sin(th), a: 0.15 + Math.pow(rnd(), 3) * 0.85, s: rnd() < 0.06 ? 1.6 : 0.8 + rnd() * 0.5,
      ph: rnd() * 6.28, c: rnd() < 0.1 ? "#bcd0ff" : rnd() < 0.08 ? "#ffd9b0" : "#ffffff" };
  });
  const orbits = [560, 690, 830, 980].map((r, i) => ({ r, inc: (i - 1.5) * 0.09, rot: i * 1.3, ph: rnd() * 6.28, sp: 0.05 + 0.03 * rnd() * (i % 2 ? -1 : 1), tail: 1.1 + 0.5 * rnd() }));
  const links = DATA.links.filter(l => P.has(l.source) && P.has(l.target)).map(l => {
    const a = byId.get(l.source), b = byId.get(l.target);
    return { a, b, t: a.topic === b.topic ? a.topic : -1 };
  });

  // sprites: soft glow per colour
  const sprite = new Map();
  function glow(colr) {
    if (sprite.has(colr)) return sprite.get(colr);
    const c = document.createElement("canvas"); c.width = c.height = 64; const g = c.getContext("2d");
    const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.12, colr); gr.addColorStop(0.35, colr + "55"); gr.addColorStop(1, colr + "00");
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64); sprite.set(colr, c); return c;
  }
  let neb = null;
  function nebula() {
    neb = document.createElement("canvas"); neb.width = Math.max(1, W); neb.height = Math.max(1, H); const g = neb.getContext("2d");
    const blobs = [[0.5, 0.5, 0.55, "60,50,110", 0.22], [0.3, 0.35, 0.4, "40,70,120", 0.14], [0.72, 0.62, 0.45, "90,50,100", 0.13],
      [0.62, 0.28, 0.3, "130,90,60", 0.07], [0.2, 0.8, 0.35, "50,60,90", 0.12], [0.88, 0.15, 0.3, "70,60,120", 0.08]];
    blobs.forEach(([x, y, r, c, a]) => { const R0 = r * Math.max(W, H);
      const gr = g.createRadialGradient(x * W, y * H, 0, x * W, y * H, R0);
      gr.addColorStop(0, `rgba(${c},${a})`); gr.addColorStop(1, `rgba(${c},0)`); g.fillStyle = gr; g.fillRect(0, 0, W, H); });
  }

  // ---------- camera ----------
  const HOME = { tx: 0, ty: 0, tz: 0, dist: 1500, pitch: 1.0 };
  const cam = { ...HOME, yaw: 0.6 };
  let tw = null;
  const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  function fly(to, ms = 1100) { tw = { a: { ...cam }, b: { ...cam, ...to }, t0: performance.now(), ms }; }
  let cy = 1, sy = 0, cp = 1, sp = 0;
  function prep() { cy = Math.cos(cam.yaw); sy = Math.sin(cam.yaw); cp = Math.cos(cam.pitch); sp = Math.sin(cam.pitch); }
  const out = { x: 0, y: 0, s: 0, d: 0 };
  function proj(p) {  // world -> screen; false when behind the camera
    const dx = p.x - cam.tx, dy = p.y - cam.ty, dz = p.z - cam.tz;
    const x1 = dx * cy - dz * sy, z1 = dx * sy + dz * cy;
    const y2 = dy * cp + z1 * sp, d = -dy * sp + z1 * cp + cam.dist;
    if (d < 15) return false;
    const s = F / d; out.x = W / 2 + x1 * s; out.y = H / 2 - y2 * s; out.s = s; out.d = d; return true;
  }

  // ---------- render ----------
  let hits = [], tHits = [];
  function frame(now) {
    if (!running) return;
    raf = requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - (last || now)) / 1000); last = now; time += dt;
    if (!paused && !drag) cam.yaw += dt * 0.035;
    if (tw) { const k = Math.min(1, (now - tw.t0) / tw.ms), e = ease(k);
      for (const key of ["tx", "ty", "tz", "dist", "pitch"]) cam[key] = tw.a[key] + (tw.b[key] - tw.a[key]) * e;
      if (k >= 1) tw = null; }
    draw();
  }
  function draw() {
    prep();
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
    ctx.fillStyle = "#030306"; ctx.fillRect(0, 0, W, H);
    if (neb) { ctx.globalAlpha = 0.9 + 0.1 * Math.sin(time * 0.3); ctx.drawImage(neb, 0, 0, W, H); }
    // background stars: directions only (no parallax), turn with the camera
    ctx.globalCompositeOperation = "lighter";
    const Fs = Math.max(W, H) * 0.7;
    for (const st of stars) {
      const x1 = st.x * cy - st.z * sy, z1 = st.x * sy + st.z * cy, y2 = st.y * cp + z1 * sp, d = -st.y * sp + z1 * cp;
      if (d < 0.15) continue;
      const X = W / 2 + x1 / d * Fs, Y = H / 2 - y2 / d * Fs;
      if (X < 0 || Y < 0 || X > W || Y > H) continue;
      ctx.globalAlpha = st.a * (0.75 + 0.25 * Math.sin(time * 1.3 + st.ph)); ctx.fillStyle = st.c; ctx.fillRect(X, Y, st.s, st.s);
    }
    // galactic dust
    for (const p of dust) { if (!proj(p)) continue;
      ctx.globalAlpha = p.a * Math.min(1, out.s * 1.6); ctx.fillStyle = p.w ? "#ffd7a8" : "#c8c8ff";
      const z = Math.max(0.6, p.s * out.s * 1.4); ctx.fillRect(out.x, out.y, z, z); }
    // orbits with comet heads
    ctx.lineCap = "round";
    for (const o of orbits) {
      const head = o.ph + time * o.sp, N = 64, pts = [];
      const ci = Math.cos(o.inc), si = Math.sin(o.inc), cr = Math.cos(o.rot), sr = Math.sin(o.rot);
      const at = a => { const x = o.r * Math.cos(a), z0 = o.r * Math.sin(a), y = z0 * si, z = z0 * ci;
        return { x: x * cr - z * sr, y, z: x * sr + z * cr }; };
      for (let i = 0; i <= N; i++) { const a = head - Math.sign(o.sp) * o.tail * (1 - i / N); pts.push(proj(at(a)) ? [out.x, out.y] : null); }
      for (let i = 1; i <= N; i++) { if (!pts[i] || !pts[i - 1]) continue; const f = i / N;
        ctx.globalAlpha = 0.5 * f * f; ctx.strokeStyle = "#e9ecff"; ctx.lineWidth = 0.6 + 1.6 * f;
        ctx.beginPath(); ctx.moveTo(pts[i - 1][0], pts[i - 1][1]); ctx.lineTo(pts[i][0], pts[i][1]); ctx.stroke(); }
      if (pts[N]) { ctx.globalAlpha = 0.9; ctx.drawImage(glow("#dfe6ff"), pts[N][0] - 9, pts[N][1] - 9, 18, 18); }
    }
    // the core
    const cOk = proj({ x: 0, y: 0, z: 0 }), cx = out.x, cyy = out.y, cs = out.s;
    if (cOk) blackHole(cx, cyy, cs, out.d);
    // edges, batched: faint between topics, topic colour inside a topic
    const f = hover || nodeSel, sel = topicSel;
    ctx.lineWidth = 0.6;
    const groups = new Map();
    for (const l of links) { if (!vis(l.a) || !vis(l.b)) continue;
      const hot = f && (l.a.id === f.id || l.b.id === f.id);
      const key = hot ? "hot" : l.t; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(l); }
    for (const [key, ls] of groups) {
      ctx.beginPath();
      for (const l of ls) { if (!proj(P.get(l.a.id))) continue; const x0 = out.x, y0 = out.y;
        if (!proj(P.get(l.b.id))) continue; ctx.moveTo(x0, y0); ctx.lineTo(out.x, out.y); }
      if (key === "hot") { ctx.strokeStyle = "#ffffff"; ctx.globalAlpha = 0.55; }
      else if (key === -1) { ctx.strokeStyle = "#b8b8d8"; ctx.globalAlpha = sel !== null || q || f ? 0.006 : 0.014; }
      else { ctx.strokeStyle = col(key); ctx.globalAlpha = (sel === null || sel === key) && !q && !f ? 0.2 : 0.05; }
      ctx.stroke();
    }
    // concept stars
    hits = [];
    for (const n of conv) { if (!vis(n) || !proj(P.get(n.id))) continue;
      const on = lit(n), r = Math.max(0.9, R(n) * out.s * 1.15), sz = r * 5.5;
      ctx.globalAlpha = on ? 0.95 : 0.13;
      ctx.drawImage(glow(col(n.topic)), out.x - sz / 2, out.y - sz / 2, sz, sz);
      hits.push({ n, x: out.x, y: out.y, r: Math.max(5, r * 1.6), on });
    }
    ctx.globalCompositeOperation = "source-over";
    // labels
    ctx.textAlign = "center";
    if (cOk) {
      const ly = cyy + Math.max(28, 140 * cs); ctx.font = "600 12.5px -apple-system, Segoe UI, sans-serif";
      const w = ctx.measureText(DATA.name).width + 26; ctx.globalAlpha = 0.85; ctx.fillStyle = "rgba(20,20,28,.7)";
      rr(cx - w / 2, ly - 12, w, 24, 12); ctx.fill(); ctx.strokeStyle = "rgba(255,255,255,.14)"; ctx.lineWidth = 1; ctx.stroke();
      ctx.globalAlpha = 1; ctx.fillStyle = "#f0f0f4"; ctx.textBaseline = "middle"; ctx.fillText(DATA.name, cx, ly + 0.5);
    }
    tHits = [];
    T.forEach((t, i) => { if (!proj({ x: tc[i].x, y: tc[i].y + tc[i].spread * 0.5, z: tc[i].z })) return;
      const dim = sel !== null && sel !== i;
      ctx.globalAlpha = dim ? 0.35 : 0.95; ctx.textBaseline = "bottom";
      ctx.font = "600 12px -apple-system, Segoe UI, sans-serif"; ctx.fillStyle = "#f2f2f6"; ctx.shadowColor = "#000"; ctx.shadowBlur = 8;
      const nm = t.name.split(" · ").slice(0, 2).join(" · ");
      ctx.fillText(nm, out.x, out.y - 8);
      ctx.font = "11px -apple-system, Segoe UI, sans-serif"; ctx.fillStyle = "#8f8f9a"; ctx.textBaseline = "top";
      ctx.fillText(`${t.size} понятий`, out.x, out.y - 6); ctx.shadowBlur = 0;
      tHits.push({ t: i, x: out.x, y: out.y - 8, w: ctx.measureText(nm).width / 2 + 34 });
    });
    // concept labels when close to a topic, on search, or around the hovered/selected concept
    const close = cam.dist < 800;
    ctx.font = "11px -apple-system, Segoe UI, sans-serif"; ctx.textBaseline = "top"; ctx.shadowColor = "#000"; ctx.shadowBlur = 6;
    const lab = hits.filter(h => h.on && ((q) || (f && (h.n.id === f.id || nbrs.get(f.id).has(h.n.id))) ||
      (close && (sel === null || inTopic(h.n, sel)) && h.r > 3.2)));
    lab.sort((a, b) => b.r - a.r).slice(0, 60).forEach(h => { ctx.globalAlpha = 0.9; ctx.fillStyle = "#e4e4ec"; ctx.fillText(h.n.label, h.x, h.y + h.r * 0.8 + 2); });
    ctx.shadowBlur = 0; ctx.globalAlpha = 1;
  }
  // black hole: halo, an accretion disk of concentric rings made of 0/1 glyphs in a square pixel font, each glyph
  // flickering on its own (far half drawn behind the shadow, near half in front), lensed arcs and a photon ring
  const PIX = { 0: ["111", "101", "101", "101", "111"], 1: ["010", "110", "010", "010", "111"] };
  const RING_COL = ["#fff4dc", "#ffd79a", "#ffc070", "#ffa95c", "#f08a45", "#d9683a", "#b9502e"];
  const glyphs = {};  // colour -> [sprite of 0, sprite of 1]
  function glyph(c, d) {
    if (!glyphs[c]) glyphs[c] = [0, 1].map(v => { const s = document.createElement("canvas"), px = 4;
      s.width = 3 * px; s.height = 5 * px; const g = s.getContext("2d"); g.fillStyle = c;
      PIX[v].forEach((row, y) => [...row].forEach((b, x) => { if (b === "1") g.fillRect(x * px, y * px, px - 0.6, px - 0.6); })); return s; });
    return glyphs[c][d];
  }
  const DISK = [];
  for (let k = 0; k < 11; k++) {
    const r = 54 + k * 8, n = Math.round(2 * Math.PI * r / 7.2), c = RING_COL[Math.min(RING_COL.length - 1, Math.floor(k * 0.7))];
    for (let i = 0; i < n; i++) DISK.push({ r, a: 2 * Math.PI * i / n + k * 0.37, c, d: rnd() < 0.5 ? 0 : 1, ph: rnd() * 6.28,
      fs: 1.5 + rnd() * 4, flip: rnd() < 0.18 ? 0.3 + rnd() * 1.2 : 0, sp: 0.9 / Math.sqrt(r / 54), b: 0.55 + 0.45 * (1 - k / 11) });
  }
  function blackHole(cx, cy0, cs, cd) {
    const hr = 240 * cs, g = ctx.createRadialGradient(cx, cy0, 0, cx, cy0, hr);
    g.addColorStop(0, "rgba(255,190,120,0.3)"); g.addColorStop(0.25, "rgba(220,120,70,0.1)"); g.addColorStop(1, "rgba(120,70,150,0)");
    ctx.globalCompositeOperation = "lighter"; ctx.globalAlpha = 1; ctx.fillStyle = g; ctx.fillRect(cx - hr, cy0 - hr, 2 * hr, 2 * hr);
    const rh = 40 * cs, gh = Math.max(4, 6.5 * cs), gw = gh * 0.6, front = [];
    const put = (p, al) => { ctx.globalAlpha = al; ctx.drawImage(glyph(p.c, p.dd), p.x - gw / 2, p.y - gh / 2, gw, gh); };
    for (const p of DISK) {
      const a = p.a + time * p.sp * 0.25;
      if (!proj({ x: p.r * Math.cos(a), y: 0, z: p.r * Math.sin(a) })) continue;
      const dop = 0.6 + 0.4 * Math.max(-1, Math.min(1, -(out.x - cx) / (p.r * cs + 1e-6)));  // approaching side brighter
      const al = p.b * dop * (0.3 + 0.7 * (0.5 + 0.5 * Math.sin(time * p.fs + p.ph)));
      const q0 = { x: out.x, y: out.y, c: p.c, dd: p.flip ? (p.d + Math.floor(time * p.flip + p.ph)) % 2 : p.d };
      if (out.d > cd) put(q0, al); else front.push([q0, al]);
    }
    // lensed image of the far disk: bright arcs over (and fainter under) the shadow
    for (const [top, al] of [[true, 0.8], [false, 0.3]]) {
      for (let j = 0; j < 4; j++) {
        ctx.beginPath(); ctx.ellipse(cx, cy0, rh * (1.28 + j * 0.2), rh * (1.12 + j * 0.2), 0, top ? Math.PI : 0, top ? 2 * Math.PI : Math.PI);
        ctx.globalAlpha = al * (0.6 - j * 0.12); ctx.strokeStyle = j ? "#ffb060" : "#fff0d0"; ctx.lineWidth = Math.max(1, (j ? 6 : 3) * cs); ctx.stroke();
      }
    }
    // shadow + photon ring
    ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
    const sg = ctx.createRadialGradient(cx, cy0, rh * 0.85, cx, cy0, rh * 1.25);
    sg.addColorStop(0, "#000"); sg.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = sg; ctx.beginPath(); ctx.arc(cx, cy0, rh * 1.25, 0, 2 * Math.PI); ctx.fill();
    ctx.fillStyle = "#000"; ctx.beginPath(); ctx.arc(cx, cy0, rh, 0, 2 * Math.PI); ctx.fill();
    ctx.globalCompositeOperation = "lighter";
    ctx.globalAlpha = 0.85 + 0.15 * Math.sin(time * 2.1); ctx.strokeStyle = "#ffe6c0"; ctx.lineWidth = Math.max(0.8, 1.6 * cs);
    ctx.beginPath(); ctx.arc(cx, cy0, rh * 1.03, 0, 2 * Math.PI); ctx.stroke();
    ctx.globalAlpha = 0.3; ctx.lineWidth = Math.max(2, 6 * cs); ctx.stroke();
    for (const [p, al] of front) put(p, al);
  }
  function rr(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

  function size() {
    DPR = Math.min(2, window.devicePixelRatio || 1); W = stage.clientWidth || innerWidth; H = stage.clientHeight || innerHeight;
    cv.width = W * DPR; cv.height = H * DPR; F = Math.min(W, H) * 1.05; nebula();
  }
  // the same starfield and nebula, still, behind the 2D / 3D graphs
  function drawSky() {
    const c = $("#sky"); if (!c) return;
    const w = stage.clientWidth || innerWidth || 1, h = stage.clientHeight || innerHeight || 1, d = Math.min(2, devicePixelRatio || 1);
    c.width = w * d; c.height = h * d; const g = c.getContext("2d"); g.setTransform(d, 0, 0, d, 0, 0);
    g.fillStyle = "#030306"; g.fillRect(0, 0, w, h); W = w; H = h; nebula(); g.drawImage(neb, 0, 0, w, h);
    for (const st of stars) { g.globalAlpha = st.a * 0.85; g.fillStyle = st.c; g.fillRect((st.x * 0.5 + 0.5) * w, (st.z * 0.5 + 0.5) * h, st.s, st.s); }
  }
  addEventListener("resize", () => { if (running) size(); else drawSky(); });

  // ---------- interaction ----------
  let drag = null;
  const pick = (x, y) => { let best = null, bd = 1e9;
    for (const h of hits) { const d = Math.hypot(h.x - x, h.y - y); if (d < h.r + 4 && d < bd && h.on) { bd = d; best = h; } } return best; };
  const pickT = (x, y) => tHits.find(h => Math.abs(h.x - x) < h.w && y > h.y - 22 && y < h.y + 22);
  cv.addEventListener("contextmenu", e => e.preventDefault());
  cv.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, pan: e.button === 2 || e.shiftKey }; cv.setPointerCapture(e.pointerId); tw = null; });
  cv.addEventListener("pointermove", e => {
    const b = cv.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top;
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
      if (drag.pan) { const k = cam.dist / F;
        cam.tx -= (dx * cy + dy * sy) * k; cam.tz -= (-dx * sy + dy * cy) * k; }
      else { cam.yaw += dx * 0.005; cam.pitch = Math.max(0.12, Math.min(1.5, cam.pitch + dy * 0.004)); }
      return;
    }
    const h = pick(x, y), th = !h && pickT(x, y);
    hover = h ? h.n : null;
    cv.style.cursor = h || th ? "pointer" : "grab";
    if (h) { tip.style.display = "block"; tip.textContent = `${h.n.label} · ${h.n.n}`; tip.style.left = x + 12 + "px"; tip.style.top = y + 10 + "px"; }
    else tip.style.display = "none";
  });
  cv.addEventListener("pointerup", e => {
    const moved = drag && Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) > 4; drag = null;
    if (moved) return;
    const b = cv.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top;
    const h = pick(x, y); if (h) return openNode(h.n.id);
    const th = pickT(x, y); if (th) return openTopic(th.t);
    nodeSel = null; if (topicSel === null) closeInsp();
  });
  cv.addEventListener("pointerleave", () => { hover = null; tip.style.display = "none"; });
  cv.addEventListener("wheel", e => { e.preventDefault(); tw = null; cam.dist = Math.max(90, Math.min(4000, cam.dist * Math.exp(e.deltaY * 0.0012))); }, { passive: false });
  const zoomBy = k => fly({ dist: Math.max(90, Math.min(4000, cam.dist * k)) }, 350);
  $("#cIn").onclick = () => zoomBy(1 / 1.35); $("#cOut").onclick = () => zoomBy(1.35);
  const home = () => { closeInsp(); fly(HOME); };
  $("#cReset").onclick = home; $("#cHome").onclick = home;
  $("#cPause").onclick = () => { paused = !paused; $("#cPause").textContent = paused ? "▶" : "❚❚"; $("#cPause").title = paused ? "Вращать" : "Пауза вращения"; };
  $("#cFull").onclick = () => { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {}); };

  function flyTopic(t) { if (t === null || t === undefined || !tc[t]) return;
    const c = tc[t]; fly({ tx: c.x, ty: c.y, tz: c.z, dist: 160 + c.spread * 3.2, pitch: 0.85 }); }
  function flyNode(id) { const n = byId.get(id), p = P.get(id); if (p) fly({ tx: p.x, ty: p.y, tz: p.z, dist: 240, pitch: 0.8 }); return n; }

  // ---------- greeting card ----------
  const day = s => new Date(s + "T00:00:00Z"), iso = d => d.toISOString().slice(0, 10);
  const addD = (s, k) => { const d = day(s); d.setUTCDate(d.getUTCDate() + k); return iso(d); };
  const daysBetween = (a, b) => Math.round((day(b) - day(a)) / 864e5);
  const st = DATA.stats, daily = DATA.daily || {}, decs = DATA.decisions;
  const short = (s, n = 110) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  const ddmm = s => s ? s.slice(8, 10) + "." + s.slice(5, 7) : "";
  function greeting() {
    // visits: {last, prev}; "since the last visit" means the visit before today
    const today = iso(new Date()), key = "ctxgraph.visit." + DATA.name;
    let v = {}; try { v = JSON.parse(localStorage.getItem(key) || "{}") || {}; } catch (e) {}
    if (v.last && v.last !== today) v = { last: today, prev: v.last }; else v.last = today;
    try { localStorage.setItem(key, JSON.stringify(v)); } catch (e) {}
    const lastVisit = v.prev && v.prev < (st.to || today) ? v.prev : null;
    const since = lastVisit || (st.to ? addD(st.to, -7) : today);
    const newer = decs.filter(d => d.ts > since), turns = Object.entries(daily).filter(([d]) => d > since).reduce((a, [, v]) => a + v, 0);
    const tCount = new Map(); newer.forEach(d => d.topic >= 0 && tCount.set(d.topic, (tCount.get(d.topic) || 0) + 1));
    const tops = [...tCount].sort((a, b) => b[1] - a[1]).slice(0, 2).map(([t]) => `«${esc(T[t].name.split(" · ")[0])}»`);
    const h = new Date().getHours(), hi = h < 5 ? "Доброй ночи" : h < 12 ? "Доброе утро" : h < 18 ? "Добрый день" : "Добрый вечер";
    const ago = lastVisit ? daysBetween(lastVisit, today) : null;
    const yes = newer.filter(d => d.kind === "yes").length, no = newer.filter(d => d.kind === "no").length;
    let sum;
    if (!turns && !newer.length) sum = `${lastVisit ? "С последнего визита" : "За последнюю неделю"} нового нет. Последняя активность — ${esc(st.to)}.`;
    else sum = `С ${lastVisit ? "последнего визита" : "прошлой недели проекта"}: ${turns} реплик и ${newer.length} решений`
      + (newer.length ? ` (делать — ${yes}, не делать — ${no})` : "") + (tops.length ? `; больше всего про ${tops.join(" и ")}.` : ".");
    const recent = decs.slice(-4).reverse(), hold = decs.filter(d => d.kind === "hold").slice(-2).reverse();
    const row = d => `<div class="d ${d.kind}"><b>${ddmm(d.ts)}</b><span>${esc(short(d.t))}</span></div>`;
    $("#cg").innerHTML = `<button class="hide" id="cgHide" title="Свернуть">–</button>
      <div class="p">${esc(DATA.name)}</div><div class="s">${esc(st.from)} — ${esc(st.to)} · ${st.turns} реплик · ${T.length} тем</div>
      <div class="body2"><h1>${hi}.</h1>
      <div class="since">С последнего визита: ${lastVisit ? `${esc(lastVisit)}, ${ago} дн. назад` : "сегодня или впервые — показана последняя неделя проекта"} (${esc(addD(since, 1))} — ${esc(st.to)})</div>
      <div class="sum">${sum}</div>
      ${recent.length ? `<div class="h">Последние решения</div>${recent.map(row).join("")}` : ""}
      ${hold.length ? `<div class="h">Отложено</div>${hold.map(row).join("")}` : ""}
      <span class="ln" id="cgDec">${decs.length} решений в журнале →</span><span class="ln" id="cgDash">Панель проекта →</span></div>`;
    $("#cgHide").onclick = () => { $("#cg").classList.toggle("min"); $("#cgHide").textContent = $("#cg").classList.contains("min") ? "+" : "–"; };
    $("#cgDec").onclick = openDecisions; $("#cgDash").onclick = openDash;
    if (innerWidth < 900) { $("#cg").classList.add("min"); $("#cgHide").textContent = "+"; }  // narrow: keep the scene visible
  }

  // ---------- dashboard ----------
  const end = st.to || iso(new Date());
  const days = k => Array.from({ length: k }, (_, i) => addD(end, i - k + 1));
  const decDaily = {}; decs.forEach(d => { if (d.ts) decDaily[d.ts] = (decDaily[d.ts] || 0) + 1; });
  const weeks = (src, n = 8) => Array.from({ length: n }, (_, w) => days(7 * n).slice(7 * w, 7 * w + 7).reduce((a, d) => a + (src[d] || 0), 0));
  const firstDaily = {}; conv.forEach(n => { if (n.first) firstDaily[n.first] = (firstDaily[n.first] || 0) + 1; });
  const lastDaily = {}; conv.forEach(n => { if (n.last) lastDaily[n.last] = (lastDaily[n.last] || 0) + 1; });
  const wk = days(7), upd = conv.filter(n => n.last && n.last >= wk[0]).length;
  const mb = a => { const m = Math.max(1, ...a); return `<div class="mb">${a.map(v => `<i style="height:${Math.max(6, 100 * v / m)}%" title="${v}"></i>`).join("")}</div>`; };
  const card = (c, big, cap, cap2, badge, bars) => `<div class="dc st" style="--c:${c}"><span class="bdg">${badge}</span><div class="big">${big}</div>
    <div class="cap">${cap}</div><div class="cap2">${cap2}</div>${mb(bars)}</div>`;
  function activity() {
    const ds = days(30), v = ds.map(d => daily[d] || 0), dv = ds.map(d => decDaily[d] || 0), m = Math.max(1, ...v);
    const Wc = 600, Hc = 150, bw = Wc / 30;
    return `<svg class="ach" viewBox="0 0 ${Wc} ${Hc + 18}" width="100%" preserveAspectRatio="none" style="height:170px">
      <line x1="0" x2="${Wc}" y1="${Hc}" y2="${Hc}" stroke="rgba(255,255,255,.1)"/>
      ${v.map((x, i) => `<rect x="${i * bw + 2}" y="${Hc - Hc * 0.92 * x / m}" width="${bw - 4}" height="${Hc * 0.92 * x / m}" rx="2" fill="#9b7cf2"><title>${ds[i]}: ${x} реплик, ${dv[i]} решений</title></rect>`
        + (dv[i] ? `<circle cx="${i * bw + bw / 2}" cy="${Hc - Hc * 0.92 * x / m - 6}" r="2.5" fill="#66c29a"/>` : "")).join("")}
      <text x="0" y="${Hc + 14}">${ddmm(ds[0])}</text><text x="${Wc / 2}" y="${Hc + 14}" text-anchor="middle">${ddmm(ds[15])}</text>
      <text x="${Wc}" y="${Hc + 14}" text-anchor="end">${ddmm(ds[29])}</text><text x="2" y="10">${m}</text></svg>`;
  }
  const decRow = d => `<div class="dd" data-t="${d.topic}" style="--c:${d.kind === "yes" ? "#66c29a" : d.kind === "no" ? "#e08479" : "#e0a46a"}">
    <div class="x">${mk(d.t)}</div><div class="m"><span class="k">${d.kind === "yes" ? "делать" : d.kind === "no" ? "не делать" : "отложено"}</span><span>${esc(d.ts)}</span>
    ${d.topic >= 0 ? `<span>${esc(T[d.topic].name.split(" · ")[0])}</span>` : ""}</div></div>`;
  let dq = "";
  const mk = s => { const e = esc(s); if (!dq) return e; const i = e.toLowerCase().indexOf(esc(dq)); return i < 0 ? e : e.slice(0, i) + "<mark>" + e.slice(i, i + esc(dq).length) + "</mark>" + e.slice(i + esc(dq).length); };
  function dashBody() {
    if (dq) {
      const cs = conv.filter(n => n.label.toLowerCase().includes(dq)).sort((a, b) => b.n - a.n).slice(0, 40);
      const ds = decs.filter(d => d.t.toLowerCase().includes(dq)).slice().reverse().slice(0, 40);
      return `<div class="dg c2"><div class="dc"><div class="dcl">Понятия · ${cs.length}</div>${cs.map(n => `<div class="br" data-id="${esc(n.id)}" style="--c:${col(n.topic)}"><div class="l"><span class="nm">${mk(n.label)}</span><span class="v">${n.n}</span></div></div>`).join("") || `<div class="cap2">Нет.</div>`}</div>
        <div class="dc"><div class="dcl">Решения · ${ds.length}</div>${ds.map(decRow).join("") || `<div class="cap2">Нет.</div>`}</div></div>`;
    }
    const tw8 = weeks(daily), dw8 = weeks(decDaily), fw8 = weeks(firstDaily), lw7 = wk.map(d => lastDaily[d] || 0);
    const maxT = Math.max(1, ...T.map(t => t.size)), top = conv.slice().sort((a, b) => b.deg - a.deg).slice(0, 8), maxD = Math.max(1, ...top.map(n => n.deg));
    return `<div class="dg c4">
      ${card("#f08a4b", st.turns, "Реплики", `${Object.keys(daily).length} активных дней`, `+${tw8[7]} за неделю`, tw8)}
      ${card("#52c98c", decs.length, "Решения", `делать ${decs.filter(d => d.kind === "yes").length} · не делать ${decs.filter(d => d.kind === "no").length}`, `+${dw8[7]} за неделю`, dw8)}
      ${card("#5b8ff0", st.concepts, "Понятия", `${st.shown} на карте · ${T.length} тем`, `${st.bridges} общих`, fw8)}
      ${card("#a271f0", upd, "Обновлено за неделю", "понятия, упомянутые за 7 дней", `${Math.round(100 * upd / Math.max(1, conv.length))}%`, lw7)}</div>
    <div class="dg c3">
      <div class="dc" style="--c:#9b7cf2"><div class="t"><i></i>Активность</div><div class="t2">Реплик в день, последние 30 дней · точки — дни с решениями</div>${activity()}</div>
      <div class="dc" style="--c:#52c98c"><div class="t"><i></i>Темы по размеру</div><div class="t2">Понятий в теме · клик — перелететь</div>
        ${T.slice(0, 9).map(t => `<div class="br" data-t="${t.id}" style="--c:${t.color}"><div class="l"><span class="nm">${esc(t.name.split(" · ").slice(0, 2).join(" · "))}</span><span class="v">${t.size}</span></div><div class="bb"><i style="width:${100 * t.size / maxT}%"></i></div></div>`).join("")}</div>
      <div class="dc" style="--c:#5b8ff0"><div class="t"><i></i>Самые связанные понятия</div><div class="t2">Сумма весов связей · клик — открыть</div>
        ${top.map(n => `<div class="br" data-id="${esc(n.id)}" style="--c:${col(n.topic)}"><div class="l"><span class="nm">${esc(n.label)}</span><span class="v">${Math.round(n.deg)}</span></div><div class="bb"><i style="width:${100 * n.deg / maxD}%"></i></div></div>`).join("")}</div></div>
    <div class="dg c2"><div class="dc"><div class="dcl">Последние решения</div>${decs.slice(-6).reverse().map(decRow).join("") || `<div class="cap2">Пока нет.</div>`}</div>
      <div class="dc"><div class="dcl">Отложено</div>${decs.filter(d => d.kind === "hold").slice(-6).reverse().map(decRow).join("") || `<div class="cap2">Нет.</div>`}</div></div>`;
  }
  function drawDash() {
    $("#dashBody").innerHTML = dashBody();
    $("#dashBody").querySelectorAll("[data-t]").forEach(el => el.onclick = () => { const t = +el.dataset.t; if (t >= 0) { closeDash(); openTopic(t); } });
    $("#dashBody").querySelectorAll("[data-id]").forEach(el => el.onclick = () => { closeDash(); openNode(el.dataset.id); });
  }
  function openDash() {
    $("#cdw").innerHTML = `<input id="dq" type="search" placeholder="Искать понятия и решения…" autocomplete="off"><div id="dashBody"></div>`;
    $("#dq").value = dq; $("#dq").oninput = e => { dq = e.target.value.trim().toLowerCase(); q = dq; drawDash(); };
    drawDash(); $("#cdash").classList.add("on"); setTimeout(() => $("#dq").focus(), 30);
  }
  function closeDash() { $("#cdash").classList.remove("on"); }
  $("#cDash").onclick = () => $("#cdash").classList.contains("on") ? closeDash() : openDash();
  $("#cdash").onclick = e => { if (e.target.id === "cdash") closeDash(); };
  addEventListener("keydown", e => { if (e.key === "Escape" && running) { if ($("#cdash").classList.contains("on")) closeDash(); else home(); } });
  stage.querySelectorAll(".cosui [data-mode]").forEach(b => b.onclick = () => setMode(b.dataset.mode));

  let greeted = false;
  return {
    start() { if (running) return; running = true; size(); if (!greeted) { greeted = true; greeting(); } last = 0; raf = requestAnimationFrame(frame); },
    stop() { running = false; cancelAnimationFrame(raf); closeDash(); if (dq) { dq = ""; q = $("#q").value.trim().toLowerCase(); } },
    flyTopic, flyNode, home, openDash, draw, sky: drawSky,
  };
})();
window.COS = COS;
// the background must never stop the page: a window without a size yet (opened in the background) used to throw
try { COS.sky(); } catch (e) { console.warn("sky", e); }
addEventListener("load", () => { try { COS.sky(); } catch (e) {} });
$("#openDash").onclick = () => COS.openDash();
{ let m0 = DATA.mode; if (!m0) try { m0 = localStorage.getItem("ctxgraph.mode"); } catch (e) {}
  if (m0 === "3d" || m0 === "cosmos") setMode(m0); }
