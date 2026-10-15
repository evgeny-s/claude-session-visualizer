const DATA = /*__DATA__*/null;
const $ = s => document.querySelector(s);
const EV = DATA.events, AG = DATA.agents;
const GAP = 4; // max playback seconds for an idle gap
const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(n | 0);
const hms = s => { s = Math.max(0, s | 0); const h = s / 3600 | 0, m = (s % 3600) / 60 | 0, x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
const short = (s, n) => (s = String(s || '')).length > n ? s.slice(0, n - 1) + '…' : s;

// ---------- time: compress idle gaps ----------
let acc = 0;
EV.forEach((e, i) => { if (i) acc += Math.min(GAP, Math.max(0, e.t - EV[i - 1].t)); e.p = acc; });
const TOTAL = Math.max(acc, 1), T0 = EV.length ? EV[0].t : 0, T1 = EV.length ? EV[EV.length - 1].t : 0;
function seg(key, v) { // index of last event with e[key] <= v
  let lo = 0, hi = EV.length - 1;
  if (!EV.length || v < EV[0][key]) return -1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (EV[m][key] <= v) lo = m; else hi = m - 1; }
  return lo;
}
function r2p(t) { const i = seg('t', t); if (i < 0) return 0; const a = EV[i], b = EV[i + 1]; if (!b) return a.p; return a.p + (b.p - a.p) * ((t - a.t) / ((b.t - a.t) || 1)); }
function p2r(p) { const i = seg('p', p); if (i < 0) return T0; const a = EV[i], b = EV[i + 1]; if (!b) return a.t; return a.t + (b.t - a.t) * ((p - a.p) / ((b.p - a.p) || 1)); }
AG.forEach(a => { a.p0 = r2p(a.t0); a.p1 = r2p(a.t1); });

// ---------- colors ----------
const COLORS = { Bash: '#22d3ee', Read: '#60a5fa', Edit: '#fbbf24', MultiEdit: '#fbbf24', Write: '#fb923c', NotebookEdit: '#fb923c', Grep: '#a78bfa', Glob: '#c084fc', Agent: '#f472b6', Task: '#f472b6', WebFetch: '#34d399', WebSearch: '#34d399', Skill: '#facc15', TodoWrite: '#94a3b8', ToolSearch: '#94a3b8', Reply: '#e2e8f0', other: '#64748b' };
const hue = s => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h % 360; };
const tcol = n => COLORS[n] || (n.startsWith('mcp__') ? '#2dd4bf' : `hsl(${hue(n)},75%,66%)`);
const agentCol = (a, i) => a.id === 'main' ? '#fbbf24' : `hsl(${(300 + i * 47) % 360},80%,68%)`;

// ---------- graph ----------
const N = {}, COLS = [[], [], [], []], LINKS = new Map();
function node(key, col, label, color, sub) { if (!N[key]) { N[key] = { key, col, label, color, sub: sub || '', count: 0, heat: 0, tok: 0, err: 0 }; COLS[col].push(N[key]); } return N[key]; }
function topK(list, cap) { const c = {}; list.forEach(x => c[x] = (c[x] || 0) + 1); const s = Object.keys(c).sort((a, b) => c[b] - c[a]); return s.length > cap ? new Set(s.slice(0, cap - 1)) : new Set(s); }

for (const e of EV) if (e.k === 'say') { e.n = 'Reply'; e.tg = '→ user'; }
const acts = EV.filter(e => e.k === 'tool' || e.k === 'say');
const prompts = EV.filter(e => e.k === 'prompt');
const sysTop = topK(EV.filter(e => e.k === 'sys').map(e => e.x), 4);
const slots = Math.max(1, 12 - sysTop.size);
prompts.forEach((e, i) => {
  const b = Math.floor(i * Math.min(slots, prompts.length) / prompts.length);
  const members = prompts.filter((_, j) => Math.floor(j * Math.min(slots, prompts.length) / prompts.length) === b);
  const first = prompts.indexOf(members[0]) + 1;
  const label = members.length === 1 ? '#' + first + ' ' + e.x : '#' + first + '–' + (first + members.length - 1) + ' prompts';
  e.from = node('in:' + b, 0, label, '#fde68a', 'user').key;
});
EV.filter(e => e.k === 'sys').forEach(e => { const k = sysTop.has(e.x) ? e.x : 'system'; e.from = node('sys:' + k, 0, k, '#64748b', 'injected').key; });
AG.forEach((a, i) => { const n = node('ag:' + a.id, 1, a.label, agentCol(a, i), a.type); n.agent = a; });
const toolTop = topK(acts.map(e => e.n), 12), tgTop = topK(acts.map(e => e.tg), 16);
acts.forEach(e => {
  const tn = toolTop.has(e.n) ? e.n : 'other', tg = tgTop.has(e.tg) ? e.tg : '…other';
  e.tl = node('tl:' + tn, 2, tn.replace(/^mcp__.*__/, ''), tcol(tn)).key;
  e.tgk = node('tg:' + tg, 3, tg, '#9fb3c8').key;
});
const finalCount = {}; acts.forEach(e => { finalCount[e.tl] = (finalCount[e.tl] || 0) + 1; finalCount[e.tgk] = (finalCount[e.tgk] || 0) + 1; });
COLS[2].sort((a, b) => (finalCount[b.key] || 0) - (finalCount[a.key] || 0));
COLS[3].sort((a, b) => (finalCount[b.key] || 0) - (finalCount[a.key] || 0));
const spawnOf = {}; AG.forEach(a => { if (a.spawn) spawnOf[a.spawn] = a; });
let seedN = 1;
function link(a, b, color, kind) { const k = a + '|' + b; let L = LINKS.get(k); if (!L) LINKS.set(k, L = { a, b, color, kind: kind || 'flow', count: 0, heat: 0, seed: seedN++ }); return L; }
// pre-create links so layout order is stable
for (const e of EV) {
  if (e.from) link(e.from, 'ag:' + e.a, N[e.from].color);
  if (e.tl) { link('ag:' + e.a, e.tl, tcol(N[e.tl].label === 'other' ? 'other' : e.n)); link(e.tl, e.tgk, N[e.tl].color); }
  if (e.k === 'tool' && spawnOf[e.id]) link('ag:' + e.a, 'ag:' + spawnOf[e.id].id, '#f472b6', 'spawn');
}

// ---------- canvas ----------
const cv = $('#c'), ctx = cv.getContext('2d');
let W = 0, H = 0, DPR = 1;
const COLX = [0.015, 0.265, 0.52, 0.775], TITLES = ['INPUTS', 'AGENTS', 'TOOLS', 'TARGETS'];
let CW = 180;
function layout() {
  const r = cv.getBoundingClientRect(); DPR = window.devicePixelRatio || 1; W = r.width; H = r.height;
  cv.width = W * DPR; cv.height = H * DPR;
  CW = Math.min(210, W * 0.205);
  COLS.forEach((col, ci) => {
    const top = 34, avail = H - top - 12, n = Math.max(col.length, 1);
    const h = Math.max(14, Math.min(42, avail / n - 6)), gap = Math.min(18, (avail - h * n) / n);
    const total = n * h + (n - 1) * gap; let y = top + Math.max(0, (avail - total) / 2);
    col.forEach(nd => { nd.x = W * COLX[ci]; nd.w = CW; nd.h = h; nd.y = y; y += h + gap; });
  });
  layoutTl();
}
function ctrl(L, o) {
  const A = N[L.a], B = N[L.b];
  if (L.kind === 'spawn') { const x0 = A.x + A.w, y0 = A.y + A.h / 2 + o, x1 = B.x + B.w, y1 = B.y + B.h / 2 + o, bx = x0 + 30 + Math.min(90, Math.abs(y1 - y0) * 0.25); return [x0, y0, bx, y0, bx, y1, x1, y1]; }
  const x0 = A.x + A.w, y0 = A.y + A.h / 2 + o * 0.6, x1 = B.x, y1 = B.y + B.h / 2 + o * 0.6, dx = (x1 - x0) * 0.5;
  return [x0, y0, x0 + dx, y0 + o * 4, x1 - dx, y1 - o * 4, x1, y1];
}
function bz(c, u) { const v = 1 - u; return [v * v * v * c[0] + 3 * v * v * u * c[2] + 3 * v * u * u * c[4] + u * u * u * c[6], v * v * v * c[1] + 3 * v * v * u * c[3] + 3 * v * u * u * c[5] + u * u * u * c[7]]; }
const rnd = (s, i) => { const x = Math.sin(s * 9301 + i * 49297) * 233280; return x - Math.floor(x) - 0.5; };

const sprites = {};
function sprite(color) {
  if (sprites[color]) return sprites[color];
  const s = document.createElement('canvas'); s.width = s.height = 32; const g = s.getContext('2d');
  const gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  gr.addColorStop(0, '#fff'); gr.addColorStop(0.18, color); gr.addColorStop(0.5, color + '55'); gr.addColorStop(1, 'transparent');
  g.fillStyle = gr; g.fillRect(0, 0, 32, 32);
  return sprites[color] = s;
}
const hexify = c => { if (c.startsWith('#')) return c; const d = document.createElement('canvas').getContext('2d'); d.fillStyle = c; return d.fillStyle; };
for (const n of Object.values(N)) n.color = hexify(n.color);
for (const L of LINKS.values()) L.color = hexify(L.color);

// ---------- state ----------
let now = 0, idx = 0, playing = true, parts = [], running = [], cur = null, logs = [], dirty = true;
let S = {};
function reset() {
  for (const n of Object.values(N)) { n.count = 0; n.heat = 0; n.tok = 0; n.err = 0; }
  for (const L of LINKS.values()) { L.count = 0; L.heat = 0; }
  S = { tools: 0, out: 0, ctx: 0, err: 0 }; parts = []; running = []; cur = null; logs = []; idx = 0; dirty = true;
}
const agentById = Object.fromEntries(AG.map(a => [a.id, a]));
function hit(L, live, n) { L.count++; L.heat = Math.min(1, L.heat + 0.7); return L; }
function apply(e, live) {
  const ag = N['ag:' + e.a];
  if (e.k === 'tok') { S.out += e.o; S.ctx = e.i; if (ag) ag.tok += e.o; return; }
  if (e.k === 'think') { if (ag) ag.heat = 1; return; }
  if (e.k === 'prompt' || e.k === 'sys') {
    const n = N[e.from]; n.count++; n.heat = 1; if (ag) ag.heat = 1;
    const L = hit(LINKS.get(e.from + '|ag:' + e.a));
    if (live) shoot([L], n.color, e.k === 'prompt' ? 4 : 1);
    pushLog(e); if (e.k === 'prompt') cur = e; return;
  }
  // tool / say
  const tl = N[e.tl], tg = N[e.tgk];
  ag.count++; tl.count++; tg.count++; ag.heat = tl.heat = tg.heat = 1;
  if (e.k === 'tool') S.tools++;
  if (e.err) { S.err++; tl.err++; tg.err++; }
  const L1 = hit(LINKS.get('ag:' + e.a + '|' + e.tl)), L2 = hit(LINKS.get(e.tl + '|' + e.tgk));
  if (live) shoot([L1, L2], e.err ? '#f43f5e' : tl.color, 3);
  const child = e.k === 'tool' && spawnOf[e.id];
  if (child) { const L = hit(LINKS.get('ag:' + e.a + '|ag:' + child.id)); if (live) shoot([L], '#f472b6', 6, 0.5); }
  e.pe = e.end ? r2p(e.end) : e.p + 0.3;
  running.push(e); cur = e; pushLog(e);
}
function pushLog(e) { logs.push(e); if (logs.length > 60) logs.splice(0, logs.length - 60); dirty = true; }
function shoot(path, color, n, speed) {
  for (let i = 0; i < n; i++) {
    if (parts.length > 700) return;
    parts.push({ path, u: -i * 0.07, sp: (speed || 1.1) * (0.85 + Math.random() * 0.3), o: (Math.random() - 0.5) * 8, color, big: 1 });
  }
}
function seek(p) {
  reset(); now = Math.max(0, Math.min(TOTAL, p));
  while (idx < EV.length && EV[idx].p <= now) apply(EV[idx++], false);
  running = running.filter(e => e.pe > now);
}

// ---------- draw ----------
let fitCache = new Map();
function fit(text, w) {
  const k = text + '|' + (w | 0); if (fitCache.has(k)) return fitCache.get(k);
  let t = text; if (ctx.measureText(t).width > w) { while (t.length > 1 && ctx.measureText(t + '…').width > w) t = t.slice(0, -1); t += '…'; }
  if (fitCache.size > 4000) fitCache.clear(); fitCache.set(k, t); return t;
}
function rr(x, y, w, h, r) { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h); }
function drawBg() {
  ctx.fillStyle = 'rgba(255,255,255,0.025)';
  for (let x = 0; x < W; x += 24) for (let y = 30; y < H; y += 24) ctx.fillRect(x, y, 1, 1);
  ctx.font = '600 9px "JetBrains Mono",Menlo,monospace'; ctx.textBaseline = 'middle';
  COLS.forEach((col, ci) => {
    ctx.fillStyle = '#5b6678'; ctx.fillText(TITLES[ci], W * COLX[ci], 14);
    ctx.fillStyle = '#334155'; ctx.fillText(String(col.length), W * COLX[ci] + CW - 18, 14);
    if (ci < 3) { // dotted guide rails between columns
      const gx = W * COLX[ci] + CW + (W * COLX[ci + 1] - W * COLX[ci] - CW) / 2;
      ctx.fillStyle = 'rgba(148,163,184,0.10)';
      for (let y = 34; y < H - 10; y += 6) { ctx.fillRect(gx - 14, y, 1, 1.5); ctx.fillRect(gx + 14, y, 1, 1.5); }
    }
  });
}
function drawLinks() {
  ctx.globalCompositeOperation = 'lighter';
  for (const L of LINKS.values()) {
    if (!L.count) continue;
    const k = Math.min(7, 1 + Math.floor(Math.log2(L.count + 1) * 1.6));
    ctx.beginPath();
    for (let i = 0; i < k; i++) {
      const c = ctrl(L, (i - (k - 1) / 2) * 1.8 + rnd(L.seed, i) * 3);
      ctx.moveTo(c[0], c[1]); ctx.bezierCurveTo(c[2], c[3], c[4], c[5], c[6], c[7]);
    }
    ctx.strokeStyle = L.color; ctx.lineWidth = L.kind === 'spawn' ? 1.2 : 0.7;
    ctx.globalAlpha = Math.min(0.9, 0.07 + 0.1 * Math.min(1, L.count / 25) + 0.55 * L.heat);
    ctx.stroke();
  }
  ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
}
function drawParts(dt) {
  ctx.globalCompositeOperation = 'lighter';
  const keep = [];
  for (const q of parts) {
    q.u += dt * q.sp;
    const hop = Math.floor(q.u), L = q.path[Math.max(0, hop)];
    if (q.u >= q.path.length) continue;
    keep.push(q); if (q.u < 0) continue;
    const c = ctrl(L, q.o), sp = sprite(q.color);
    const steps = q.big ? 7 : 1;
    for (let s = 0; s < steps; s++) {
      const u = (q.u - hop) - s * 0.022; if (u < 0) break;
      const [x, y] = bz(c, u), r = (q.big ? 11 : 5) * (1 - s / steps);
      ctx.globalAlpha = (q.big ? 1 : 0.55) * (1 - s / steps);
      ctx.drawImage(sp, x - r, y - r, r * 2, r * 2);
    }
  }
  parts = keep; ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
}
function ambient(dt) {
  for (const L of LINKS.values()) {
    if (!L.count || parts.length > 900) continue;
    if (Math.random() < dt * Math.min(2.5, 0.25 * Math.log2(1 + L.count)) * (0.35 + L.heat))
      parts.push({ path: [L], u: 0, sp: 0.25 + Math.random() * 0.3, o: (Math.random() - 0.5) * 10, color: L.color, big: 0 });
  }
}
function drawNodes() {
  const maxc = COLS.map(col => Math.max(1, ...col.map(n => n.count)));
  for (const col of COLS) for (const n of col) {
    const a = n.agent, started = !a || now >= a.p0, live = a && now >= a.p0 && now <= a.p1 + 0.5;
    const isCur = cur && (n.key === cur.tl || n.key === 'ag:' + cur.a || n.key === cur.tgk || n.key === cur.from);
    ctx.globalAlpha = started && (n.count || a) ? 1 : 0.28;
    rr(n.x, n.y, n.w, n.h, 3);
    ctx.fillStyle = 'rgba(9,13,20,0.92)'; ctx.fill();
    if (n.heat > 0.04 || isCur) { ctx.shadowColor = n.color; ctx.shadowBlur = 22 * Math.max(n.heat, isCur ? 0.5 : 0); }
    ctx.strokeStyle = isCur ? n.color : `rgba(148,163,184,${0.13 + 0.5 * n.heat})`; ctx.lineWidth = isCur ? 1.4 : 1; ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = n.color; ctx.fillRect(n.x, n.y + 3, 2, n.h - 6);
    if (n.err) { ctx.fillStyle = '#f43f5e'; ctx.fillRect(n.x + n.w - 3, n.y + 3, 2, n.h - 6); }
    // ports
    ctx.fillStyle = n.color; ctx.fillRect(n.x - 1.5, n.y + n.h / 2 - 1.5, 3, 3); ctx.fillRect(n.x + n.w - 1.5, n.y + n.h / 2 - 1.5, 3, 3);
    const big = n.h >= 28, ty = big ? n.y + n.h * 0.36 : n.y + n.h / 2;
    ctx.textBaseline = 'middle';
    ctx.font = `600 ${n.h < 18 ? 9 : 11}px "JetBrains Mono",Menlo,monospace`;
    const cnt = a ? (n.count ? n.count + '' : '') : (n.count ? String(n.count) : '');
    ctx.fillStyle = n.color; const cw = cnt ? ctx.measureText(cnt).width + 8 : 0;
    ctx.fillText(cnt, n.x + n.w - cw, ty);
    ctx.fillStyle = '#d8e1ee'; ctx.fillText(fit(n.label, n.w - 16 - cw), n.x + 9, ty);
    if (big) {
      ctx.font = '9px "JetBrains Mono",Menlo,monospace'; ctx.fillStyle = '#5b6678';
      const sub = a ? (live ? '● LIVE  ' : started ? '○ done  ' : '· idle  ') + a.type + (n.tok ? '  ' + fmt(n.tok) + ' tok' : '') : n.sub;
      if (a && live) ctx.fillStyle = '#34d399';
      ctx.fillText(fit(sub, n.w - 18), n.x + 9, n.y + n.h * 0.72);
      // activity bar
      ctx.fillStyle = 'rgba(148,163,184,0.08)'; ctx.fillRect(n.x + 9, n.y + n.h - 4, n.w - 18, 1.5);
      ctx.fillStyle = n.color; ctx.fillRect(n.x + 9, n.y + n.h - 4, (n.w - 18) * n.count / maxc[n.col], 1.5);
    }
    ctx.globalAlpha = 1;
  }
}

// ---------- timeline ----------
const tl = $('#tl'), tctx = tl.getContext('2d'), tlStatic = document.createElement('canvas');
let TW = 0, TH = 0;
function layoutTl() {
  const r = tl.getBoundingClientRect(); TW = r.width; TH = r.height;
  tl.width = tlStatic.width = TW * DPR; tl.height = tlStatic.height = TH * DPR;
  const g = tlStatic.getContext('2d'); g.setTransform(DPR, 0, 0, DPR, 0, 0);
  const lanes = AG.length, lh = Math.max(2, Math.min(12, (TH - 22) / lanes)), x = p => 6 + (TW - 12) * p / TOTAL;
  // token area
  const B = 160, buck = new Array(B).fill(0); EV.forEach(e => { if (e.k === 'tok') buck[Math.min(B - 1, e.p / TOTAL * B | 0)] += e.o; });
  const mx = Math.max(1, ...buck); g.fillStyle = 'rgba(251,191,36,0.10)';
  buck.forEach((v, i) => { const h = (TH - 8) * v / mx; g.fillRect(6 + (TW - 12) * i / B, TH - 4 - h, (TW - 12) / B - 1, h); });
  AG.forEach((a, i) => {
    const y = 6 + i * lh;
    g.fillStyle = 'rgba(148,163,184,0.07)'; g.fillRect(x(a.p0), y, Math.max(2, x(a.p1) - x(a.p0)), lh - 1);
    for (const e of EV) if (e.a === a.id && (e.k === 'tool' || e.k === 'say' || e.k === 'prompt')) {
      g.fillStyle = e.err ? '#f43f5e' : e.k === 'prompt' ? '#fde68a' : N[e.tl].color; g.fillRect(x(e.p), y, 1.5, lh - 1);
    }
  });
}
function drawTl() {
  tctx.setTransform(DPR, 0, 0, DPR, 0, 0); tctx.clearRect(0, 0, TW, TH);
  tctx.drawImage(tlStatic, 0, 0, TW, TH);
  const px = 6 + (TW - 12) * now / TOTAL;
  tctx.fillStyle = 'rgba(4,6,10,0.55)'; tctx.fillRect(px, 0, TW - px, TH);
  tctx.shadowColor = '#fbbf24'; tctx.shadowBlur = 10; tctx.fillStyle = '#fbbf24'; tctx.fillRect(px - 1, 0, 2, TH); tctx.shadowBlur = 0;
}

// ---------- DOM panels ----------
$('#title').textContent = DATA.title;
document.title = 'Claude Session · ' + short(DATA.title, 40);
$('#meta').textContent = DATA.id.slice(0, 8) + ' · ' + new Date(T0 * 1000).toLocaleString() + ' · ' + EV.length + ' events' + (DATA.synthetic ? ' · timing synthetic' : '');
const mixEl = $('#mix'), mixRows = COLS[2].map(n => { const d = document.createElement('div'), s = document.createElement('span'), b = document.createElement('b'), m = document.createElement('em'); s.textContent = n.label; b.style.background = n.color; d.append(s, b, m); mixEl.append(d); return { n, b, m }; });
const totalTools = acts.filter(e => e.k === 'tool').length;
function agentName(id) { const a = agentById[id]; return a ? (a.id === 'main' ? 'main' : short(a.label, 30)) : id; }
function logLine(e) {
  const li = document.createElement('li'), t = document.createElement('span');
  t.className = 't'; t.textContent = new Date(e.t * 1000).toTimeString().slice(0, 8); li.append(t);
  const who = e.a === 'main' ? '' : '[' + short(agentName(e.a), 14) + '] ';
  if (e.k === 'sys') { li.className = 'sys'; li.append(who + '⚙ ' + e.x); }
  else if (e.k === 'prompt') { li.append(who + '▶ ' + e.x); li.style.color = '#fde68a'; }
  else { if (e.err) li.className = 'err'; li.append(who + e.n.replace(/^mcp__.*__/, '') + ' → ' + (e.k === 'say' ? e.x : e.tg)); }
  return li;
}
let lastCur = null, lastStatus = '';
function panels() {
  $('#sTools').textContent = S.tools; $('#bTools').style.width = (100 * S.tools / Math.max(1, totalTools)) + '%';
  $('#sOut').textContent = fmt(S.out); $('#sCtx').textContent = fmt(S.ctx);
  $('#sAg').innerHTML = ''; $('#sAg').append(String(AG.filter(a => now >= a.p0).length)); const sm = document.createElement('small'); sm.textContent = '/ ' + AG.length; $('#sAg').append(sm);
  $('#sErr').textContent = S.err; $('#tErr').classList.toggle('err', S.err > 0);
  const rt = p2r(now); $('#sWall').textContent = hms(rt - T0); $('#bWall').style.width = (100 * (rt - T0) / Math.max(1, T1 - T0)) + '%';
  $('#clock').textContent = new Date(rt * 1000).toLocaleTimeString();
  $('#pos').textContent = Math.round(100 * now / TOTAL) + '% · ' + idx + '/' + EV.length + ' events';
  const mx = Math.max(1, ...mixRows.map(r => r.n.count));
  mixRows.forEach(r => { r.b.style.width = (100 * r.n.count / mx) + '%'; r.m.textContent = r.n.count; });
  if (dirty) { const ul = $('#log'); ul.replaceChildren(...logs.slice(-40).map(logLine)); $('#logN').textContent = idx + ' / ' + EV.length; dirty = false; }
  const st = !cur ? '' : cur.k === 'prompt' ? 'PROMPT' : now < cur.pe ? 'RUNNING' : cur.err ? 'ERROR' : 'OK';
  if (cur !== lastCur || st !== lastStatus) {
    lastCur = cur; lastStatus = st;
    const s = $('#nowStatus'); s.textContent = st; s.className = st === 'RUNNING' ? 'run' : st === 'ERROR' ? 'err' : st === 'OK' ? 'ok' : '';
    if (cur) {
      $('#nowTool').textContent = cur.k === 'prompt' ? 'User prompt' : cur.n === 'Reply' ? 'Reply' : cur.n.replace(/^mcp__.*__/, '') + ' · ' + cur.tg;
      $('#nowTool').style.color = cur.k === 'prompt' ? '#fde68a' : N[cur.tl].color;
      $('#nowAgent').textContent = '◆ ' + agentName(cur.a);
      $('#nowText').textContent = cur.x || '';
      $('#nowOut').textContent = st === 'OK' || st === 'ERROR' ? cur.out || '' : '';
      $('#nowOut').style.display = $('#nowOut').textContent ? '' : 'none';
    }
  }
}

// ---------- controls ----------
const SPEEDS = [1, 2, 5, 10, 25, 50, 100];
let speed = SPEEDS.reduce((b, s) => Math.abs(s - TOTAL / 90) < Math.abs(b - TOTAL / 90) ? s : b, 1);
const spEl = $('#speeds');
SPEEDS.forEach(s => { const b = document.createElement('button'); b.textContent = s + '×'; b.onclick = () => { speed = s; syncSpeed(); }; spEl.append(b); });
function syncSpeed() { [...spEl.children].forEach((b, i) => b.classList.toggle('on', SPEEDS[i] === speed)); }
syncSpeed();
function setPlay(v) { playing = v; if (playing && now >= TOTAL) seek(0); $('#bPlay').textContent = playing ? '❚❚' : '▶'; }
$('#bPlay').onclick = () => setPlay(!playing);
$('#bRestart').onclick = () => { seek(0); setPlay(true); };
let drag = false;
const tlSeek = ev => { const r = tl.getBoundingClientRect(); seek((ev.clientX - r.left - 6) / (r.width - 12) * TOTAL); };
tl.onpointerdown = ev => { drag = true; tl.setPointerCapture(ev.pointerId); tlSeek(ev); };
tl.onpointermove = ev => drag && tlSeek(ev);
tl.onpointerup = () => drag = false;
addEventListener('keydown', ev => {
  if (!pickEl.hidden) return pickKey(ev);
  if (ev.key === 'o' && SERVED) return openPick();
  if (ev.code === 'Space') { ev.preventDefault(); setPlay(!playing); }
  if (ev.code === 'ArrowRight') seek(now + TOTAL * 0.03);
  if (ev.code === 'ArrowLeft') seek(now - TOTAL * 0.03);
  if (ev.key === 'r') { seek(0); setPlay(true); }
});
addEventListener('resize', () => { layout(); fitCache.clear(); });

// ---------- loop ----------
let last = performance.now(), lastPanel = 0;
function frame(t) {
  const dt = Math.min(0.05, (t - last) / 1000); last = t;
  if (playing) {
    now = Math.min(TOTAL, now + dt * speed);
    while (idx < EV.length && EV[idx].p <= now) apply(EV[idx++], true);
    if (now >= TOTAL) setPlay(false);
  }
  running = running.filter(e => e.pe > now);
  for (const e of running) { N[e.tl].heat = Math.max(N[e.tl].heat, 0.55); }
  const decay = Math.exp(-dt * 1.6);
  for (const n of Object.values(N)) n.heat *= decay;
  for (const L of LINKS.values()) L.heat *= decay;
  ambient(dt);
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0); ctx.clearRect(0, 0, W, H);
  drawBg(); drawLinks(); drawParts(dt); drawNodes(); drawTl();
  if (t - lastPanel > 90) { panels(); lastPanel = t; }
  requestAnimationFrame(frame);
}
reset(); layout();
const h0 = /t=([\d.]+)/.exec(location.hash); if (h0) seek(TOTAL * +h0[1]);
requestAnimationFrame(frame);
