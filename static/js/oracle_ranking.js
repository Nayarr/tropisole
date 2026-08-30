// Classement d'isolation — recherche, filtres, tri, couleur des %.
(function () {
  const table = document.getElementById('rank-table');
  if (!table) return;
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr.row'));
  const search = document.getElementById('search');
  const fCtx = document.getElementById('filter-ctx');
  const fMod = document.getElementById('filter-mod');
  const fIso = document.getElementById('filter-iso');
  const count = document.getElementById('count');
  const modeBtns = [...document.querySelectorAll('.mode-btn')];
  let activeMode = 'chain';   // 'chain' = lignée complète, 'focus' = Pokémon seul

  // Échelle de couleur reprise EXACTEMENT de l'Oracle (oracle.js).
  function scoreColor(p, comp, ultra) {
    if (p >= 100 && comp === 0) return '#ffc439';   // isolation totale
    if (p >= 100)               return '#55efc4';   // var(--green)
    if (ultra)                  return '#a29bfe';   // ultra-rares only
    if (p >= 75)                return '#C9A24B';   // var(--accent)
    if (p >= 50)                return '#ffab40';   // var(--orange)
    return '#8a8a8a';                               // var(--muted)
  }

  rows.forEach(r => {
    const comp = parseInt(r.dataset.comp, 10);
    const ultra = r.dataset.ultra === '1';
    const el = r.querySelector('.iso-pct');
    if (el) {
      const color = scoreColor(parseFloat(el.dataset.pct), comp, ultra);
      el.style.color = color;
      const fill = r.querySelector('.iso-fill');
      if (fill) fill.style.background = color;
    }
    const pur = r.querySelector('.pur-pct');
    if (pur) pur.style.color = scoreColor(parseFloat(pur.dataset.pct), comp, ultra);
  });

  // Remplir le filtre par mod depuis les données
  const mods = [...new Set(rows.map(r => r.dataset.mod).filter(Boolean))].sort();
  mods.forEach(m => {
    const o = document.createElement('option');
    o.value = m; o.textContent = m;
    fMod.appendChild(o);
  });

  let sortKey = 'iso';
  let sortDir = -1; // -1 desc, 1 asc

  function apply() {
    const q = (search.value || '').toLowerCase().trim();
    const ctx = fCtx.value, mod = fMod.value, iso = parseFloat(fIso.value || '0');
    let shown = 0, inMode = 0;
    rows.forEach(r => {
      const okMode = r.dataset.mode === activeMode;
      if (okMode) inMode++;
      const okName = !q || r.dataset.name.includes(q) || ('#' + String(r.dataset.num).padStart(4, '0')).includes(q);
      const okCtx = !ctx || r.dataset.ctx === ctx;
      const okMod = !mod || r.dataset.mod === mod;
      const okIso = parseFloat(r.dataset.iso) >= iso;
      const vis = okMode && okName && okCtx && okMod && okIso;
      r.style.display = vis ? '' : 'none';
      if (vis) {
        shown++;
        const cell = r.querySelector('.c-rank');
        if (cell) cell.textContent = shown;   // renumérote ce qui est affiché
      }
    });
    count.textContent = shown + ' / ' + inMode + ' Pokémon';
  }

  function sortBy(key) {
    // Nouveau critère : décroissant pour les scores, croissant pour les concurrents.
    if (sortKey === key) sortDir = -sortDir;
    else { sortKey = key; sortDir = (key === 'comp') ? 1 : -1; }
    const attr = key;  // 'iso' | 'pur' | 'comp'
    const sorted = rows.slice().sort((a, b) => {
      const av = parseFloat(a.dataset[attr]), bv = parseFloat(b.dataset[attr]);
      if (av !== bv) return (av - bv) * sortDir;
      return parseInt(a.dataset.num) - parseInt(b.dataset.num);
    });
    sorted.forEach(r => tbody.appendChild(r));
    // maj des flèches + classe .sorted (colorée en accent)
    table.querySelectorAll('th.sortable').forEach(th => {
      const base = th.textContent.replace(/[▾▴]/g, '').trim();
      const active = th.dataset.sort === key;
      th.classList.toggle('sorted', active);
      th.textContent = active ? base + (sortDir === -1 ? ' ▾' : ' ▴') : base;
    });
  }

  modeBtns.forEach(btn => btn.addEventListener('click', () => {
    activeMode = btn.dataset.mode;
    modeBtns.forEach(b => b.classList.toggle('active', b === btn));
    apply();
  }));

  [search, fCtx, fMod, fIso].forEach(el => el.addEventListener('input', apply));
  table.querySelectorAll('th.sortable').forEach(th =>
    th.addEventListener('click', () => sortBy(th.dataset.sort)));

  apply();
})();
