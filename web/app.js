const $ = id => document.getElementById(id);
let me = null;
const store = {
  get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  del: k => { try { localStorage.removeItem(k); } catch {} },
};
const auth = () => ({ Authorization: 'Bearer ' + store.get('pg_token') });
async function api(path, opt = {}) {
  opt.headers = Object.assign({}, opt.headers || {}, auth());
  if (opt.json) { opt.body = JSON.stringify(opt.json); opt.headers['Content-Type'] = 'application/json'; opt.method = opt.method || 'POST'; }
  const r = await fetch(path, opt);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || r.statusText);
  return body;
}
const money = v => v == null ? '—' : '₹' + Math.round(v).toLocaleString('en-IN');

$('lang').value = store.get('pg_lang') || 'en';
$('lang').onchange = () => { store.set('pg_lang', $('lang').value); applyI18n(); render(); };

$('register').onclick = async () => {
  const r = await api('/api/users', { json: { name: $('name').value || 'Guest', role: $('role').value,
                                               village: $('village').value, language: $('lang').value } });
  store.set('pg_token', r.token); boot();
};
$('logout').onclick = () => { store.del('pg_token'); location.reload(); };

async function boot() {
  applyI18n();
  if (!store.get('pg_token')) return;
  try { me = await api('/api/me'); } catch { store.del('pg_token'); return; }
  $('login').hidden = true; $('logout').hidden = false; $('ledgerCard').hidden = false;
  $('who').textContent = `${me.name} · ${t(me.role)}`;
  $(me.role).hidden = false;
  render();
}

async function render() {
  if (!me) return;
  if (me.role === 'farmer') renderFarmer();
  if (me.role === 'buyer') renderBuyer();
  if (me.role === 'assessor') renderAssessor();
}

// ---------- farmer ----------
$('createBatch').onclick = async () => {
  const r = await api('/api/batches', { json: { crop: $('crop').value, weight_kg: +$('weight').value, location: me.village } });
  openGrade(r.id); renderFarmer();
};
async function renderFarmer() {
  const rows = await api('/api/batches');
  $('batches').innerHTML = rows.map(b => `<tr><td>${b.id}</td><td>${t(b.crop)}</td><td>${b.weight_kg}</td>
    <td><b>${b.grade || '—'}</b></td><td>${b.status}</td><td>
    ${b.status === 'created' || b.status === 'graded' ? `<button class="ghost" onclick="openGrade(${b.id})">${t('grade')}</button>` : ''}
    ${b.status === 'graded' ? `<button onclick="listIt(${b.id})">${t('list_it')}</button>` : ''}
    ${b.status === 'listed' ? `<button class="ghost" onclick="showBids(${b.id})">${t('bid')}s</button>` : ''}
    <button class="ghost" onclick="showHistory(${b.id})">${t('history')}</button></td></tr>`).join('');
}
window.openGrade = id => { $('gradeCard').hidden = false; $('gBatch').textContent = id; $('result').innerHTML = ''; };
$('photo').onchange = () => uploadPhoto($('photo').files[0]);
$('sampleBtn').onclick = async () => {
  const b = await api('/api/batches/' + $('gBatch').textContent);
  const blob = await (await fetch(`/static/samples/${b.crop}_sample.png`)).blob();
  uploadPhoto(blob);
};
async function uploadPhoto(file) {
  const fd = new FormData(); fd.append('file', file, 'sample.png');
  $('result').textContent = '…';
  try {
    const r = await api(`/api/batches/${$('gBatch').textContent}/grade`, { method: 'POST', body: fd });
    const p = r.report.percent_by_area;
    $('result').innerHTML = `
      <div class="grade g${r.report.grade[0]}">${r.report.grade}</div>
      <p>${r.report.kernels} kernels · confidence ${(r.report.confidence * 100).toFixed(0)}%</p>
      <ul><li>Broken ${p.broken}%</li><li>Discoloured ${p.discoloured}%</li><li>Foreign matter ${p.foreign}%</li></ul>
      <p>${t('suggested')}: <b>${money(r.suggested_price.price)}</b>/qtl <small>(${r.suggested_price.basis})</small></p>
      ${r.report.notes.map(n => `<p class="warn">⚠ ${n}</p>`).join('')}
      <img src="data:image/png;base64,${r.annotated_png_b64}">
      <p class="hash">image sha256 ${r.report.image_sha256.slice(0, 16)}… · ledger #${r.ledger.seq}</p>`;
    renderFarmer();
  } catch (e) { $('result').textContent = e.message; }
}
window.listIt = async id => {
  const r = await api(`/api/batches/${id}/list`, { json: {} });
  alert(`${t('list_it')}: ${money(r.ask_per_quintal)}/qtl`); renderFarmer();
};
window.showBids = async batchId => {
  const lst = (await api('/api/listings')).find(l => l.batch_id === batchId);
  if (!lst) return;
  const bids = await api(`/api/listings/${lst.id}/bids`);
  $('history').innerHTML = `<h3>${t('bid')}s — batch ${batchId}</h3>` + (bids.map(b =>
    `<div class="row">${b.buyer}: <b>${money(b.price_per_quintal)}</b>/qtl ${b.status === 'open' ?
      `<button onclick="acceptBid(${b.id})">${t('accept')}</button>` : b.status}</div>`).join('') || '<p>No bids yet</p>');
};
window.acceptBid = async id => { const r = await api(`/api/bids/${id}/accept`, { json: {} }); alert(`Sold: ${money(r.value_inr)}`); renderFarmer(); };

// ---------- buyer ----------
async function renderBuyer() {
  const rows = await api('/api/listings');
  $('listings').innerHTML = rows.map(l => `<tr><td>${l.batch_id}</td><td>${t(l.crop)}</td><td><b>${l.grade}</b></td>
    <td>${l.weight_kg}</td><td>${l.percent_by_area ? l.percent_by_area.broken : '—'}</td><td>${money(l.ask_per_quintal)}</td>
    <td>${money(l.best_bid)}</td><td><input id="bid${l.id}" type="number" value="${Math.round(l.best_bid || l.ask_per_quintal)}" style="width:90px">
    <button onclick="placeBid(${l.id})">${t('bid')}</button>
    <button class="ghost" onclick="showHistory(${l.batch_id})">${t('history')}</button></td></tr>`).join('');
}
window.placeBid = async id => { await api(`/api/listings/${id}/bids`, { json: { price_per_quintal: +$('bid' + id).value } }); renderBuyer(); };

// ---------- assessor ----------
async function renderAssessor() {
  const ds = await api('/api/disputes');
  $('disputes').innerHTML = ds.map(d => `<div class="row">#${d.id} batch ${d.batch_id}: "${d.reason}" — ${d.status}
    ${d.status === 'open' ? `<input type="file" onchange="regrade(${d.id}, this.files[0])">` :
      `${d.original_grade} → <b>${d.new_grade}</b>, adjusted ${money(d.adjusted_price)}`}</div>`).join('') || '<p>No disputes</p>';
}
window.regrade = async (id, file) => {
  const fd = new FormData(); fd.append('file', file);
  await api(`/api/disputes/${id}/regrade`, { method: 'POST', body: fd }); renderAssessor();
};

// ---------- ledger ----------
window.showHistory = async id => {
  const h = await api(`/api/ledger/batch/${id}`);
  $('history').innerHTML = `<h3>${t('history')} — batch ${id}</h3>` + h.map(e =>
    `<div class="row"><code>#${e.seq}</code> <b>${e.event}</b> ${new Date(e.ts * 1000).toLocaleString()}
     <span class="hash">${e.hash.slice(0, 12)}… ← ${e.prev_hash.slice(0, 8)}…</span></div>`).join('');
  $('ledgerCard').scrollIntoView({ behavior: 'smooth' });
};
$('verify').onclick = async () => {
  const v = await api('/api/ledger/verify');
  $('verifyOut').innerHTML = v.valid ? `✅ ${v.events} events intact · head ${v.head.slice(0, 12)}…`
                                     : `❌ chain broken at event #${v.broken_at_seq}`;
};
boot();
