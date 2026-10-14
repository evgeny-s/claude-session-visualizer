// ---------- session picker (served mode only) ----------
const SERVED = location.protocol.startsWith('http'), pickEl = $('#pick'), qEl = $('#q'), sessEl = $('#sess');
let shown = [], total = 0, sel = 0, loading = null, query = '', gen = 0;
const PAGE = 50;
async function openPick() {
  pickEl.hidden = false; qEl.value = ''; qEl.focus();
  if (!shown.length || query) { query = ''; await reload(); }
}
function closePick() { pickEl.hidden = true; history.replaceState(null, '', location.pathname); }
async function reload() { gen++; shown = []; total = 0; sel = 0; sessEl.replaceChildren(); sessEl.scrollTop = 0; loading = null; await more(); }
function more() { // fetch next page; one request in flight at a time
  if (loading || (total && shown.length >= total)) return loading;
  const g = gen;
  return loading = fetch(`/api/sessions?offset=${shown.length}&limit=${PAGE}&q=${encodeURIComponent(query)}`).then(r => r.json()).then(r => {
    if (g !== gen) return; // list was reset meanwhile
    total = r.total; const start = shown.length; shown.push(...r.items);
    sessEl.append(...r.items.map((s, k) => row(s, start + k)));
    $('#pickN').textContent = shown.length + ' / ' + total;
    if (!shown.length) sessEl.textContent = 'nothing found';
  }).finally(() => { if (g !== gen) return; loading = null; if ( sessEl.scrollHeight <= sessEl.clientHeight + 40) more(); });
}
function row(s, i) {
  const li = document.createElement('li'), d = new Date(s.mtime * 1000);
  const cells = [['d', d.toLocaleDateString(undefined, { month: '2-digit', day: '2-digit' }) + ' ' + d.toTimeString().slice(0, 5)], ['p', s.project], ['t', s.title || s.id.slice(0, 8)],
    ['k', s.id === DATA.id ? '▶ playing' : (s.subs ? s.subs + (s.subs > 1 ? ' agents · ' : ' agent · ') : '') + (s.kb >= 1024 ? (s.kb / 1024).toFixed(1) + ' MB' : s.kb + ' KB')]];
  for (const [c, txt] of cells) { const sp = document.createElement('span'); sp.className = c; sp.textContent = txt; li.append(sp); }
  li.className = (i === sel ? 'sel ' : '') + (s.id === DATA.id ? 'cur' : '');
  li.onclick = () => go(s.id);
  li.onmouseenter = () => markSel(i);
  return li;
}
function markSel(i) { sel = i; [...sessEl.children].forEach((x, j) => x.classList.toggle('sel', j === i)); }
sessEl.onscroll = () => { if (sessEl.scrollTop + sessEl.clientHeight > sessEl.scrollHeight - 120) more(); };
function go(id) { if (id === DATA.id) closePick(); else location.href = '/s/' + id; }
async function playText(text) {
  const err = $('#pasteErr'); err.textContent = text.trim() ? 'parsing…' : 'nothing pasted';
  if (!text.trim()) return;
  const r = await fetch('/api/paste', { method: 'POST', body: text });
  if (!r.ok) { err.textContent = await r.text(); return; }
  location.href = (await r.json()).url;
}
$('#pasteGo').onclick = () => playText($('#pasteTxt').value);
pickEl.ondragover = ev => { ev.preventDefault(); pickEl.classList.add('drop'); };
pickEl.ondragleave = () => pickEl.classList.remove('drop');
pickEl.ondrop = async ev => { ev.preventDefault(); pickEl.classList.remove('drop'); const f = ev.dataTransfer.files[0]; if (f) playText(await f.text()); };
function pickKey(ev) {
  if (ev.key === 'Escape') return closePick();
  if (ev.target.id === 'pasteTxt') { if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) playText(ev.target.value); return; }
  if (ev.key === 'Enter' && shown[sel]) return go(shown[sel].id);
  if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
    ev.preventDefault(); markSel(Math.max(0, Math.min(shown.length - 1, sel + (ev.key === 'ArrowDown' ? 1 : -1))));
    sessEl.children[sel]?.scrollIntoView({ block: 'nearest' });
  }
}
let qTimer; qEl.oninput = () => { clearTimeout(qTimer); qTimer = setTimeout(() => { query = qEl.value.trim(); reload(); }, 220); };
pickEl.onclick = ev => { if (ev.target === pickEl) closePick(); };
if (SERVED) { $('#bPick').hidden = false; $('#bPick').onclick = openPick; if (location.hash.includes('pick')) openPick(); }
