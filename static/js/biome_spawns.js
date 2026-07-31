// Nom du Pokémon selon la langue (cross-langue pour la recherche)
function pname(p){ return (LANG === 'en' && p.pokemon_en) ? p.pokemon_en : p.pokemon; }
const BUCKET_CLASS = {
  'common': 'badge-common',
  'uncommon': 'badge-uncommon',
  'rare': 'badge-rare',
  'ultra-rare': 'badge-ultra-rare',
  'filler': 'badge-filler'
};
const EV_COLORS = {
  hp: '#ff6b81', atk: '#ffa07a', def: '#74b9ff',
  spa: '#a29bfe', spd: '#55efc4', spe: '#C9A24B',
};
const EV_LABELS = {
  hp: 'PV', atk: 'Atk', def: 'Déf', spa: 'A.S', spd: 'D.S', spe: 'Vit',
};



const TIME_ICONS = LANG === 'en'
  ? { day: '☀️ Day', dusk: '🌆 Dusk', night: '🌙 Night' }
  : { day: '☀️ Jour', dusk: '🌆 Crépuscule', night: '🌙 Nuit' };
const WEATHER_ICONS = LANG === 'en'
  ? { clear: '🌤️ Clear', rain: '🌧️ Rain' }
  : { clear: '🌤️ Ensoleillé', rain: '🌧️ Pluie' };
const CONTEXTE_ICONS = {
  grounded: '🌿', fishing: '🎣', submerged: '🌊', surface: '💧', seafloor: '🪨'
};
const CONTEXTE_LABELS = {
  grounded: 'Grounded', fishing: 'Fishing', submerged: 'Submerged',
  surface: 'Surface', seafloor: 'Seafloor'
};


let currentSort = { col: 'numero', dir: 'asc' };
let data = [...RAW_DATA];

let yMinFilter = -64;
let yMaxFilter = 320;
let heightMinCm = 0;
let heightMaxCm = 1000;
let HEIGHT_PAGE_MIN = 0;
let HEIGHT_PAGE_MAX = 1000;
let HEIGHT_PAGE_MAX_M = 10.0;

function initHeightSlider() {
  const heights = data.map(p => p.hitbox_height).filter(h => h !== null && h > 0);
  if (heights.length === 0) return;
  HEIGHT_PAGE_MIN = Math.floor(Math.min(...heights) * 100);
  HEIGHT_PAGE_MAX = Math.ceil(Math.max(...heights) * 100);
  const minEl = document.getElementById('height-min-slider');
  const maxEl = document.getElementById('height-max-slider');
  minEl.min = HEIGHT_PAGE_MIN; minEl.max = HEIGHT_PAGE_MAX; minEl.value = HEIGHT_PAGE_MIN;
  maxEl.min = HEIGHT_PAGE_MIN; maxEl.max = HEIGHT_PAGE_MAX; maxEl.value = HEIGHT_PAGE_MAX;
  heightMinCm = HEIGHT_PAGE_MIN;
  heightMaxCm = HEIGHT_PAGE_MAX;
  HEIGHT_PAGE_MAX_M = HEIGHT_PAGE_MAX / 100;
  updateHeightDisplay();
}

function updateHeightDisplay() {
  heightMinCm = parseInt(document.getElementById('height-min-slider').value);
  heightMaxCm = parseInt(document.getElementById('height-max-slider').value);
  document.getElementById('height-range-display').textContent =
    `${(heightMinCm/100).toFixed(2)} → ${(heightMaxCm/100).toFixed(2)} bloc(s)`;
  // Sync number inputs
  const minIn = document.getElementById('height-min-input');
  const maxIn = document.getElementById('height-max-input');
  if (minIn) minIn.value = (heightMinCm/100).toFixed(2);
  if (maxIn) maxIn.value = (heightMaxCm/100).toFixed(2);
}

function syncHeightFromInput() {
  const minIn = document.getElementById('height-min-input');
  const maxIn = document.getElementById('height-max-input');
  const minEl = document.getElementById('height-min-slider');
  const maxEl = document.getElementById('height-max-slider');
  let minV = Math.round(parseFloat(minIn.value) * 100);
  let maxV = Math.round(parseFloat(maxIn.value) * 100);
  if (isNaN(minV)) minV = HEIGHT_PAGE_MIN;
  if (isNaN(maxV)) maxV = HEIGHT_PAGE_MAX;
  minV = Math.max(HEIGHT_PAGE_MIN, Math.min(HEIGHT_PAGE_MAX, minV));
  maxV = Math.max(HEIGHT_PAGE_MIN, Math.min(HEIGHT_PAGE_MAX, maxV));
  minEl.value = minV; maxEl.value = maxV;
  heightMinCm = minV; heightMaxCm = maxV;
  document.getElementById('height-range-display').textContent =
    `${(minV/100).toFixed(2)} → ${(maxV/100).toFixed(2)} bloc(s)`;
  render();
}

function resetHeightFilter() {
  document.getElementById('height-min-slider').value = HEIGHT_PAGE_MIN;
  document.getElementById('height-max-slider').value = HEIGHT_PAGE_MAX;
  heightMinCm = HEIGHT_PAGE_MIN;
  heightMaxCm = HEIGHT_PAGE_MAX;
  const minIn = document.getElementById('height-min-input');
  const maxIn = document.getElementById('height-max-input');
  if (minIn) minIn.value = (HEIGHT_PAGE_MIN/100).toFixed(2);
  if (maxIn) maxIn.value = (HEIGHT_PAGE_MAX/100).toFixed(2);
  updateHeightDisplay();
  render();
}

function resetYFilter() {
  yMinFilter = -64; yMaxFilter = 320;
  document.getElementById('y-min-slider').value = -64;
  document.getElementById('y-max-slider').value = 320;
  const minIn = document.getElementById('y-min-input');
  const maxIn = document.getElementById('y-max-input');
  if (minIn) minIn.value = -64;
  if (maxIn) maxIn.value = 320;
  updateYDisplay();
  render();
}

function updateYDisplay() {
  const mn = parseInt(document.getElementById('y-min-slider').value);
  const mx = parseInt(document.getElementById('y-max-slider').value);
  yMinFilter = mn; yMaxFilter = mx;
  document.getElementById('y-range-display').textContent = `${mn} → ${mx}`;
  // Sync number inputs
  const minIn = document.getElementById('y-min-input');
  const maxIn = document.getElementById('y-max-input');
  if (minIn) minIn.value = mn;
  if (maxIn) maxIn.value = mx;
}

function syncYFromInput() {
  const minIn = document.getElementById('y-min-input');
  const maxIn = document.getElementById('y-max-input');
  const minEl = document.getElementById('y-min-slider');
  const maxEl = document.getElementById('y-max-slider');
  let minV = parseInt(minIn.value);
  let maxV = parseInt(maxIn.value);
  if (isNaN(minV)) minV = -64;
  if (isNaN(maxV)) maxV = 320;
  minV = Math.max(-64, Math.min(320, minV));
  maxV = Math.max(-64, Math.min(320, maxV));
  minEl.value = minV; maxEl.value = maxV;
  yMinFilter = minV; yMaxFilter = maxV;
  document.getElementById('y-range-display').textContent = `${minV} → ${maxV}`;
  minIn.value = minV; maxIn.value = maxV;
  render();
}

// ── Multi-select filter state ─────────────────────────────────────────────────
const FILTERS = ['bucket', 'contexte', 'time', 'weather', 'special', 'structure', 'preset_filter', 'ev', 'type', 'egg_group'];
const filterState = {};
FILTERS.forEach(f => filterState[f] = { include: new Set(), exclude: new Set() });

function toggleDropdown(name) {
  FILTERS.forEach(f => {
    if (f !== name) document.getElementById(`ms-dropdown-${f}`).classList.remove('open');
  });
  document.getElementById(`ms-dropdown-${name}`).classList.toggle('open');
}

// Close dropdowns when clicking outside
document.addEventListener('click', e => {
  const sprite = e.target.closest('.fav-sprite-pick');
  if (sprite) {
    selectFavPokemon(parseInt(sprite.dataset.num), sprite.dataset.name, sprite.dataset.sprite);
    return;
  }
  if (!e.target.closest('.ms-wrap')) {
    FILTERS.forEach(f => document.getElementById(`ms-dropdown-${f}`).classList.remove('open'));
  }
});

function toggleOpt(filter, value, mode) {
  const state = filterState[filter];
  const opposite = mode === 'incl' ? 'exclude' : 'include';
  const current  = mode === 'incl' ? 'include' : 'exclude';

  // Remove from opposite set if present
  state[opposite].delete(value);

  // Toggle in current set
  if (state[current].has(value)) {
    state[current].delete(value);
  } else {
    state[current].add(value);
  }

  updateFilterUI(filter);
  render();
}

function clearFilter(filter) {
  filterState[filter].include.clear();
  filterState[filter].exclude.clear();
  updateFilterUI(filter);
  render();
}

function updateFilterUI(filter) {
  const state = filterState[filter];
  const btn = document.querySelector(`#ms-${filter} .ms-btn`);
  const badgeIncl = document.getElementById(`ms-badge-incl-${filter}`);
  const badgeExcl = document.getElementById(`ms-badge-excl-${filter}`);

  const ni = state.include.size;
  const ne = state.exclude.size;

  badgeIncl.style.display = ni > 0 ? 'inline-flex' : 'none';
  badgeIncl.textContent = `+${ni}`;
  badgeExcl.style.display = ne > 0 ? 'inline-flex' : 'none';
  badgeExcl.textContent = `−${ne}`;

  btn.classList.toggle('has-filter', ni > 0);
  btn.classList.toggle('has-exclude', ne > 0);

  // Update individual option rows
  const allOptions = document.querySelectorAll(`#ms-dropdown-${filter} .ms-option`);
  allOptions.forEach(optEl => {
    // For structure filter, use data-structure-name attribute; otherwise parse from id
    let val;
    if (filter === 'structure') {
      val = optEl.dataset.structureName;
      if (!val) return;
    } else {
      const idParts = optEl.id.split(`opt-${filter}-`);
      if (idParts.length < 2) return;
      val = idParts[1];
    }

    optEl.classList.remove('incl-active', 'excl-active');
    if (state.include.has(val)) optEl.classList.add('incl-active');
    else if (state.exclude.has(val)) optEl.classList.add('excl-active');

    const inclBtn = optEl.querySelector('.ms-toggle.incl');
    const exclBtn = optEl.querySelector('.ms-toggle.excl');
    if (inclBtn) inclBtn.classList.toggle('active', state.include.has(val));
    if (exclBtn) exclBtn.classList.toggle('active', state.exclude.has(val));
  });
}

// ── Filter logic ──────────────────────────────────────────────────────────────
function matchFilter(filter, getValues, p) {
  // getValues(p) → array of values the entry has for this filter dimension
  const { include, exclude } = filterState[filter];
  const vals = getValues(p);

  // Exclude: if ANY excluded value matches → hide
  for (const v of exclude) {
    if (vals.includes(v)) return false;
  }

  // Include: if ANY included values set → entry must match at least one
  if (include.size > 0) {
    let matched = false;
    for (const v of include) {
      if (vals.includes(v)) { matched = true; break; }
    }
    if (!matched) return false;
  }

  return true;
}

function filteredData() {
  const q = document.getElementById('search').value.toLowerCase();
  const yFiltered = yMinFilter > -64 || yMaxFilter < 320;

  return data.filter(p => {
    if (q && !(p.pokemon||'').toLowerCase().includes(q)
           && !(p.pokemon_en||'').toLowerCase().includes(q)) return false;

    // Y range
    if (yFiltered) {
      const pmin = p.y_min !== null ? p.y_min : -64;
      const pmax = p.y_max !== null ? p.y_max : 320;
      if (pmax < yMinFilter || pmin > yMaxFilter) return false;
    }

    // bucket
    if (!matchFilter('bucket', p => [p.bucket], p)) return false;

    // contexte
    if (!matchFilter('contexte', p => p.contextes, p)) return false;

    // time — 'always' = no time constraint (times=[])
    if (!matchFilter('time', p => p.times.length === 0 ? ['always'] : p.times, p)) return false;

    // weather — 'any' = no weather constraint (weathers=[])
    if (!matchFilter('weather', p => p.weathers.length === 0 ? ['any'] : p.weathers, p)) return false;

    // special — logique AND : doit avoir TOUTES les conditions incluses
    {
      const types = p.condition_tags.map(t => t.type);
      if (p.presets) p.presets.forEach(pr => { if (!types.includes(pr)) types.push(pr); });
      if (types.length === 0) types.push('none');
      // Exclusions : OR (si une exclue matche → caché)
      for (const v of filterState['special'].exclude) {
        if (types.includes(v)) return false;
      }
      // Inclusions : AND (toutes doivent être présentes)
      for (const v of filterState['special'].include) {
        if (!types.includes(v)) return false;
      }
    }

    // Preset filter — logique OR pour include, OR pour exclude
    {
      const presets = (p.presets && p.presets.length > 0) ? p.presets : ['none'];
      for (const v of filterState['preset_filter'].exclude) {
        if (presets.includes(v)) return false;
      }
      if (filterState['preset_filter'].include.size > 0) {
        const matched = [...filterState['preset_filter'].include].some(v => presets.includes(v));
        if (!matched) return false;
      }
    }

    // Structure spécifique
    if (!matchFilter('structure', p => p.structure_ids && p.structure_ids.length > 0 ? p.structure_ids : ['none'], p)) return false;

    // EV stats
    if (!matchFilter('ev', p => {
      return ['hp','atk','def','spa','spd','spe'].filter(s => p.ev[s] > 0);
    }, p)) return false;

    // Type filter
    if (!matchFilter('type', p => (p.types || []), p)) return false;

    // Groupe d'œufs
    if (!matchFilter('egg_group', p => p.egg_groups && p.egg_groups.length > 0 ? p.egg_groups : ['unknown'], p)) return false;

    // Height filter — actif seulement si les sliders sont bougés depuis la plage de la page
    if (heightMinCm > HEIGHT_PAGE_MIN || heightMaxCm < HEIGHT_PAGE_MAX) {
      const ph = p.hitbox_height;
      if (ph === null || ph === 0) {
        if (heightMinCm > HEIGHT_PAGE_MIN) return false;
      } else {
        const phCm = Math.round(ph * 100);
        if (phCm < heightMinCm || phCm > heightMaxCm) return false;
      }
    }

    return true;
  });
}

function sortData(rows) {
  const { col, dir } = currentSort;
  const mult = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    let va, vb;
    if (col === 'ev_total') { va = a.ev.total; vb = b.ev.total; }
    else if (col === 'poids') { va = a.poids; vb = b.poids; }
    else if (col === 'numero') { va = a.numero; vb = b.numero; }
    else if (col === 'pokemon') { va = pname(a); vb = pname(b); }
    else if (col === 'bucket') { va = a.bucket; vb = b.bucket; }
    else if (col === 'time') { va = a.times.join(','); vb = b.times.join(','); }
    else if (col === 'weather') { va = a.weathers.join(','); vb = b.weathers.join(','); }
    else if (col === 'hitbox_height') { va = a.hitbox_height ?? -1; vb = b.hitbox_height ?? -1; }
    else { va = a.numero; vb = b.numero; }
    if (typeof va === 'string') return mult * va.localeCompare(vb);
    return mult * (va - vb);
  });
}

function renderLumiere(profils) {
  if (!profils || profils.length === 0) return '<span style="color:var(--muted);font-size:0.7rem">—</span>';

  return profils.map(([lmin, lmax, sky]) => {
    const parts = [];

    // Skylight
    if (sky === 'True') {
      parts.push('<span class="lum-badge lum-sky-yes" title="Doit voir le ciel">☀️ Ciel requis</span>');
    } else if (sky === 'False') {
      parts.push('<span class="lum-badge lum-sky-no" title="Ne doit PAS voir le ciel">🚫 Sans ciel</span>');
    }

    // Niveau de lumière
    if (lmin !== null || lmax !== null) {
      const mn = lmin !== null ? Math.round(lmin) : '?';
      const mx = lmax !== null ? Math.round(lmax) : '?';
      const isDark = (lmax !== null && lmax <= 7);
      const isBright = (lmin !== null && lmin >= 8);
      const cls = isDark ? 'lum-dark' : isBright ? 'lum-bright' : 'lum-mixed';
      const icon = isDark ? '🌑' : isBright ? '🌕' : '🌗';
      parts.push(`<span class="lum-badge ${cls}" title="Niveau de lumière du ciel requis">${icon} ${mn}–${mx}</span>`);
    }

    return `<div class="lum-profil">${parts.join('')}</div>`;
  }).join('');
}

function renderEVBars(ev) {
  const stats = ['hp','atk','def','spa','spd','spe'];
  return stats.map(s => {
    const val = ev[s];
    const h = val === 0 ? '0%' : (val / 3 * 100) + '%';
    const color = val === 0 ? 'rgba(42,42,58,0.4)' : EV_COLORS[s];
    return `<div class="ev-bar-item">
      <div class="ev-bar-bg">
        <div class="ev-bar-fill" style="height:${h};background:${color}"></div>
      </div>
      <div class="ev-bar-num" style="color:${val > 0 ? EV_COLORS[s] : 'var(--muted)'}">${EV_LABELS[s]}</div>
    </div>`;
  }).join('');
}

function render() {
  const filtered = sortData(filteredData());
  const n = filtered.length;
  document.getElementById('results-count').textContent = `${n.toLocaleString('fr')} entrée${n > 1 ? 's' : ''} de spawn`;

  const tbody = document.getElementById('tbody');
  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="15" class="empty">Aucun résultat</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map((p, i) => {
    const bClass = BUCKET_CLASS[p.bucket] || 'badge-grey';
    const bLabel = BUCKET_FR[p.bucket] || '—';
    const isSource = p.numero === SOURCE_NUM;
    const delay = Math.min(i * 0.015, 0.4);

    const contextesHtml = p.contextes.length
      ? p.contextes.map(c => `<span class="badge-contexte badge-ctx-${c}" title="${CONTEXTE_LABELS[c] || c}">${CONTEXTE_ICONS[c] || '?'} ${CONTEXTE_LABELS[c] || c}</span>`).join('')
      : '<span class="badge-preset none">∅ Vide</span>';

    // Presets
    const PRESET_TOOLTIPS = {
      natural: "Blocs naturels : Herbe, Terre, Podzol, Mycélium, Terre racinaire, Mousse, Boue, Pierre, Deepslate, Andésite, Diorite, Granite, Tuf, Calcite, Bloc de spéléothème, Grès",
      urban: "Blocs urbains : Planches (toutes variantes), Briques (argile/pierre/Nether), Béton, Poudre de béton, Laine (toutes couleurs), Terre cuite",
      water: "Eau",
      treetop: "Feuilles : Chêne, Sapin, Jungle, Bouleau, Acacia, Chêne noir, Mangrove, Cerisier, Azalée, Azalée fleurie",
      foliage: "Feuilles d'arbres (côtés et dessous des Leaf blocks)",
      lava: "Lave",
      derelict: "Structures abandonnées : Cobblestone mousu, Planches vieillies, Pierre taillée fissurée",
      webs: "Toiles d'araignées (Cobweb)",
    };
    const presetsHtml = p.presets && p.presets.length > 0
      ? `<div class="preset-list">${p.presets.map(pr => {
          const tip = PRESET_TOOLTIPS[pr];
          return tip
            ? `<span class="badge-preset ${pr} has-tooltip" data-tooltip="${tip}">🏷 ${pr}</span>`
            : `<span class="badge-preset ${pr}" title="${pr}">🏷 ${pr}</span>`;
        }).join('')}</div>`
      : '<span style="color:var(--muted);font-size:0.7rem">—</span>';

    // CanSeeSky
    const skyVal = p.peut_voir_ciel;
    const skyHtml = skyVal === 'true'  ? '<span class="badge-sky-yes">☀️ Oui</span>'
                  : skyVal === 'false' ? '<span class="badge-sky-no">🚫 Non</span>'
                  : '<span class="badge-sky-any">—</span>';

    // Conditions
    // Y level tag (sera injecté dans le cond-tags-cell)
    const yTag = (p.y_min !== null || p.y_max !== null)
      ? `<span class="cond-tag y_range">Y: ${p.y_min ?? '?'} → ${p.y_max ?? '?'}</span>`
      : '';

    const allCondTags = [
      ...(p.condition_tags || []).map(t =>
        `<span class="cond-tag ${t.type}" title="${t.label}">${t.icon} <span style="font-size:0.62rem">${t.label}</span></span>`
      ),
      ...(yTag ? [yTag] : []),
    ];
    const condTagsHtml = allCondTags.length > 0
      ? `<div class="cond-tags-cell">${allCondTags.join('')}</div>`
      : '<span style="color:var(--muted);font-size:0.7rem">—</span>';

    const antiTagsHtml = p.anticondition_tags && p.anticondition_tags.length > 0
      ? `<div class="cond-tags-cell">${p.anticondition_tags.map(t =>
          `<span class="cond-tag anti-tag" title="${t.label}">${t.icon} <span style="font-size:0.62rem">${t.label}</span></span>`
        ).join('')}</div>`
      : '<span style="color:var(--muted);font-size:0.7rem">—</span>';

    const yHtml = '';  // intégré dans condTagsHtml

    // Temps : [] = pas de contrainte = toujours
    const timeHtml = p.times.length
      ? p.times.map(t => `<span class="badge-time">${TIME_ICONS[t] || t}</span>`).join(' ')
      : '<span class="badge-time badge-time-always" title="Aucune contrainte horaire — spawn toujours">🕐 Toujours</span>';

    // Météo : [] = toute météo
    const weatherHtml = p.weathers.length
      ? p.weathers.map(w => `<span class="badge-weather">${WEATHER_ICONS[w] || w}</span>`).join(' ')
      : '<span style="color:var(--muted);font-size:0.7rem">—</span>';

    return `
      <tr class="${isSource ? 'is-source' : ''}" style="animation-delay:${delay}s">
        <td class="rank-num">${i + 1}</td>
        <td class="td-num">#${String(p.numero).padStart(4,'0')}</td>
        <td class="td-name">
          <div style="display:flex;align-items:center;gap:5px">
            ${p.sprite ? `<img src="/static/pokemon_icons/${p.sprite}" alt="${pname(p)}" class="row-sprite fav-sprite-pick" data-num="${p.numero}" data-name="${pname(p).replace(/"/g,'&quot;')}" data-sprite="/static/pokemon_icons/${p.sprite}" title="Cliquer pour sélectionner comme pokémon du signet" />` : ''}
            <div>
              <a href="/pokemon/${p.numero}">${pname(p)}</a>
              ${p.forme_regionale ? `<span class="badge-forme-reg" style="color:${p.forme_regionale.color};border-color:${p.forme_regionale.color}44;background:${p.forme_regionale.color}18">🌏 ${p.forme_regionale.short}</span>` : ''}
              ${isSource ? '<span class="badge badge-grey" style="margin-left:6px">source</span>' : ''}
            </div>
          </div>
        </td>
        <td style="white-space:nowrap;width:1%;vertical-align:middle;padding-left:3px;padding-right:3px">
          ${(p.types||[]).length
            ? `<div class="type-badges">${(p.types||[]).map(t=>`<span class="type-badge" style="background:${TYPE_COLORS[t]||'#8a8a8a'}">${t}</span>`).join('')}</div>`
            : '<span style="color:var(--muted);font-size:0.7rem">—</span>'}
        </td>
        <td><span class="badge ${bClass}">${bLabel}</span></td>
        <td>
          <div style="display:flex;align-items:flex-end;gap:4px">
            <div class="ev-bars">${renderEVBars(p.ev)}</div>
          </div>
        </td>

        <td><div class="contextes-list">${contextesHtml}</div></td>
        <td style="width:1%;white-space:nowrap">${presetsHtml}</td>
        <td style="width:1%;white-space:nowrap">${condTagsHtml}</td>
        <td style="width:1%;white-space:nowrap">${antiTagsHtml}</td>
        <td class="td-time">${timeHtml}</td>
        <td class="td-weather">${weatherHtml}</td>
        <td class="td-poids">${p.poids || '—'}</td>
        <td class="td-height ${p.hitbox_height ? '' : 'unknown'}">
          ${p.hitbox_height
            ? `<div class="height-bar-wrap">
                <div class="height-bar" style="width:${Math.round((p.hitbox_height/HEIGHT_PAGE_MAX_M)*60)}px"></div>
                <span class="height-val">${p.hitbox_height.toFixed(2)} m</span>
               </div>`
            : '—'}
        </td>
      </tr>`;
  }).join('');
}

// Sort on column header click
document.querySelectorAll('thead th[data-col]').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.col;
    if (currentSort.col === col) {
      currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
    } else {
      currentSort.col = col;
      currentSort.dir = col === 'ev_total' || col === 'poids' ? 'desc' : 'asc';
    }
    // Update headers
    document.querySelectorAll('thead th').forEach(h => {
      h.classList.remove('sorted');
      const arrow = h.querySelector('.sort-arrow');
      if (arrow) arrow.textContent = '';
    });
    th.classList.add('sorted');
    const arrow = th.querySelector('.sort-arrow');
    if (arrow) arrow.textContent = currentSort.dir === 'asc' ? '↑' : '↓';
    render();
  });
});

let debounce;
document.getElementById('search').addEventListener('input', () => {
  clearTimeout(debounce);
  debounce = setTimeout(render, 200);
});
// Sliders : mise à jour de l'affichage en temps réel, render() seulement au relâchement
document.getElementById('y-min-slider').addEventListener('input', () => updateYDisplay());
document.getElementById('y-max-slider').addEventListener('input', () => updateYDisplay());
document.getElementById('y-min-slider').addEventListener('change', () => render());
document.getElementById('y-max-slider').addEventListener('change', () => render());

document.getElementById('height-min-slider').addEventListener('input', () => updateHeightDisplay());
document.getElementById('height-max-slider').addEventListener('input', () => updateHeightDisplay());
document.getElementById('height-min-slider').addEventListener('change', () => render());
document.getElementById('height-max-slider').addEventListener('change', () => render());

render();
initHeightSlider();

// Scroll to source pokemon after render
setTimeout(() => {
  const sourceRow = document.querySelector('tr.is-source');
  if (sourceRow) sourceRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
}, 300);

// ── Populate structure filter dynamically (after filterState/toggleOpt are defined) ──
(function buildStructureFilter() {
  const allStructures = new Set();
  data.forEach(p => {
    if (p.structure_ids) p.structure_ids.forEach(s => allStructures.add(s));
  });

  const container = document.getElementById('structure-options-list');
  if (allStructures.size === 0) {
    container.innerHTML = '<div style="padding:0.6rem 0.75rem;font-family:\'Geist\',monospace;font-size:0.72rem;color:var(--muted)">Aucune structure dans ces données</div>';
    return;
  }

  const sorted = [...allStructures].sort((a, b) => a.localeCompare(b));

  sorted.forEach(name => {
    const safeId = name.replace(/[^a-zA-Z0-9]/g, '_');
    const div = document.createElement('div');
    div.className = 'ms-option';
    div.id = `opt-structure-${safeId}`;
    div.dataset.structureName = name;
    div.innerHTML = `
      <span class="ms-option-label">🏗️ ${name}</span>
      <button class="ms-toggle incl">+</button>
      <button class="ms-toggle excl">−</button>`;
    div.querySelector('.ms-toggle.incl').addEventListener('click', () => toggleOpt('structure', name, 'incl'));
    div.querySelector('.ms-toggle.excl').addEventListener('click', () => toggleOpt('structure', name, 'excl'));
    container.appendChild(div);
  });
})();

// ── Populate egg_group filter dynamically ──
(function buildEggGroupFilter() {
  const EGG_LABELS = {
    monster:      '🦕 Monster',
    water_1:      '💧 Water 1',
    water_2:      '🐟 Water 2',
    water_3:      '🦀 Water 3',
    bug:          '🐛 Insecte',
    flying:       '🦅 Vol',
    field:        '🌿 Sol',
    fairy:        '✨ Fée',
    grass:        '🌱 Plante',
    human_like:   '🧑 Humanoïde',
    mineral:      '🪨 Minéral',
    amorphous:    '🫧 Amorphe',
    dragon:       '🐉 Dragon',
    ditto:        '🟣 Ditto',
    undiscovered: '❓ Non découvert',
    unknown:      '— Inconnu',
  };

  const presentGroups = new Set();
  data.forEach(p => {
    if (p.egg_groups && p.egg_groups.length > 0) {
      p.egg_groups.forEach(g => presentGroups.add(g));
    } else {
      presentGroups.add('unknown');
    }
  });

  const container = document.getElementById('egg-group-options-list');
  if (presentGroups.size === 0) {
    container.innerHTML = '<div style="padding:0.6rem 0.75rem;font-family:\'Geist\',monospace;font-size:0.72rem;color:var(--muted)">Aucun groupe d\'œuf dans ces données</div>';
    return;
  }

  // Trier dans l'ordre canonique, puis alphabétique pour ce qui reste
  const ORDER = ['monster','field','flying','water_1','water_2','water_3','bug','fairy','grass',
                 'human_like','mineral','amorphous','dragon','ditto','undiscovered','unknown'];
  const sorted = [...presentGroups].sort((a, b) => {
    const ia = ORDER.indexOf(a); const ib = ORDER.indexOf(b);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1;
    if (ib !== -1) return 1;
    return a.localeCompare(b);
  });

  sorted.forEach(group => {
    const label = EGG_LABELS[group] || ('🥚 ' + group);
    const div = document.createElement('div');
    div.className = 'ms-option';
    div.id = `opt-egg_group-${group}`;
    div.innerHTML = `
      <span class="ms-option-label">${label}</span>
      <button class="ms-toggle incl">+</button>
      <button class="ms-toggle excl">−</button>`;
    div.querySelector('.ms-toggle.incl').addEventListener('click', () => toggleOpt('egg_group', group, 'incl'));
    div.querySelector('.ms-toggle.excl').addEventListener('click', () => toggleOpt('egg_group', group, 'excl'));
    container.appendChild(div);
  });
})();

// ── Pré-application des filtres Oracle (depuis URL) ──────────────────────────
// Placé APRÈS buildStructureFilter pour que les divs structure existent dans le DOM.
// On mute directement filterState sans passer par toggleOpt (qui appelle render() à chaque fois),
// puis on fait un seul updateFilterUI + render() à la fin.
(function applyOracleFilters() {
  const p = new URLSearchParams(window.location.search);
  if (!p.toString()) return;

  // Helper : muter filterState sans déclencher render
  function setFilter(filter, value, mode) {
    const state = filterState[filter];
    const opposite = mode === 'incl' ? 'exclude' : 'include';
    const current  = mode === 'incl' ? 'include' : 'exclude';
    state[opposite].delete(value);
    state[current].add(value);
  }

  let dirty = false;

  // Contexte inclus
  if (p.has('ctx')) { setFilter('contexte', p.get('ctx'), 'incl'); dirty = true; }

  // EV stats incluses
  (p.get('ev') || '').split(',').filter(Boolean).forEach(s => { setFilter('ev', s, 'incl'); dirty = true; });

  // Moment : exclure les créneaux opposés au créneau de farm
  if (p.has('time')) {
    const farm = p.get('time');
    ['day','night','dusk'].filter(t => t !== farm).forEach(t => { setFilter('time', t, 'excl'); });
    dirty = true;
  }

  // Météo exclue
  if (p.has('excl_weather')) { setFilter('weather', p.get('excl_weather'), 'excl'); dirty = true; }

  // Structures à exclure
  // excl_structures = liste pipe-séparée de labels FR à exclure
  if (p.has('excl_structures')) {
    p.get('excl_structures').split('|').filter(Boolean).forEach(lbl => {
      setFilter('structure', lbl, 'excl');
    });
    dirty = true;
  }
  // incl_structures = liste pipe-séparée de labels FR à INCLURE (logique OR)
  // Un spawn passe s'il a AU MOINS UN des labels → parfait pour spawns multi-structures
  // (ex: Monorpale [Forteresse Nether, Vestige bastion] passe avec incl_structures=Forteresse+Nether)
  if (p.has('incl_structures')) {
    p.get('incl_structures').split('|').filter(Boolean).forEach(lbl => {
      setFilter('structure', lbl, 'incl');
    });
    dirty = true;
  }
  // struct_keep = label FR à garder → exclure tout le reste présent dans ces données
  if (p.has('struct_keep')) {
    const keepLabel = p.get('struct_keep');
    const allStructsHere = new Set();
    data.forEach(row => {
      if (row.structure_ids) row.structure_ids.forEach(s => allStructsHere.add(s));
    });
    allStructsHere.forEach(lbl => {
      if (lbl !== keepLabel) setFilter('structure', lbl, 'excl');
    });
    dirty = true;
  }

  // Special inclus
  (p.get('incl_special') || '').split(',').filter(Boolean).forEach(v => { setFilter('special', v, 'incl'); dirty = true; });

  // Special exclus
  (p.get('excl_special') || '').split(',').filter(Boolean).forEach(v => { setFilter('special', v, 'excl'); dirty = true; });

  // Preset inclus (ex: incl_preset=none → seulement les spawns sans preset)
  (p.get('incl_preset') || '').split(',').filter(Boolean).forEach(v => { setFilter('preset_filter', v, 'incl'); dirty = true; });

  // Preset exclus (ex: excl_preset=treetop,foliage)
  (p.get('excl_preset') || '').split(',').filter(Boolean).forEach(v => { setFilter('preset_filter', v, 'excl'); dirty = true; });

  // Hauteur max
  if (p.has('hmax')) {
    const hmaxCm = Math.round(parseFloat(p.get('hmax')) * 100);
    const el = document.getElementById('height-max-slider');
    if (el) {
      el.value = Math.min(hmaxCm, parseInt(el.max));
      heightMaxCm = Math.min(hmaxCm, parseInt(el.max));
      updateHeightDisplay();
      dirty = true;
    }
  }

  // Y sliders
  if (p.has('y_min')) {
    const el = document.getElementById('y-min-slider');
    if (el) { el.value = p.get('y_min'); updateYDisplay(); dirty = true; }
  }
  if (p.has('y_max')) {
    const el = document.getElementById('y-max-slider');
    if (el) { el.value = p.get('y_max'); updateYDisplay(); dirty = true; }
  }

  if (dirty) {
    // Mettre à jour l'UI de tous les filtres modifiés en une seule passe
    FILTERS.forEach(f => updateFilterUI(f));
    render();
  }
})();

// ── Favoris depuis biome_spawns ──
function serializeCurrentFilters() {
  // Reconstruit les params URL depuis l'état actuel des filtres
  const p = new URLSearchParams();
  p.set('biome', PAGE_BIOME_NAME);
  p.set('mod', PAGE_BIOME_MOD);

  const ctx = [...filterState['contexte'].include];
  if (ctx.length) p.set('ctx', ctx[0]);

  const evs = [...filterState['ev'].include];
  if (evs.length) p.set('ev', evs.join(','));

  // Time : si on a exclu certains temps, on inclut le temps gardé
  const timeExcl = [...filterState['time'].exclude];
  if (timeExcl.length) {
    const kept = ['day','night','dusk'].filter(t => !timeExcl.includes(t));
    if (kept.length === 1) p.set('time', kept[0]);
  }

  const wExcl = [...filterState['weather'].exclude];
  if (wExcl.length) p.set('excl_weather', wExcl[0]);

  const spExcl = [...filterState['special'].exclude];
  if (spExcl.length) p.set('excl_special', spExcl.join(','));

  const spIncl = [...filterState['special'].include];
  if (spIncl.length) p.set('incl_special', spIncl.join(','));

  const structExcl = [...filterState['structure'].exclude];
  if (structExcl.length) p.set('excl_structures', structExcl.join('|'));

  if (heightMaxCm < HEIGHT_PAGE_MAX) p.set('hmax', (heightMaxCm / 100).toFixed(2));
  if (yMinFilter > -64) p.set('y_min', yMinFilter);
  if (yMaxFilter < 320) p.set('y_max', yMaxFilter);

  return p;
}

// ── Tooltips preset ──
const _ptip = document.createElement('div');
_ptip.className = 'preset-tooltip-box';
_ptip.style.display = 'none';
document.body.appendChild(_ptip);

document.addEventListener('mouseover', e => {
  const el = e.target.closest('.badge-preset.has-tooltip');
  if (!el) return;
  _ptip.textContent = el.dataset.tooltip;
  _ptip.style.display = 'block';
});
document.addEventListener('mousemove', e => {
  if (_ptip.style.display === 'none') return;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + 310 > window.innerWidth)  x = e.clientX - 320;
  if (y + 120 > window.innerHeight) y = e.clientY - 90;
  _ptip.style.left = x + 'px';
  _ptip.style.top  = y + 'px';
});
document.addEventListener('mouseout', e => {
  if (e.target.closest('.badge-preset.has-tooltip')) _ptip.style.display = 'none';
});

// ── Partage via URL ──
function shareFilters() {
  const p = serializeCurrentFilters();
  const url = window.location.origin + window.location.pathname + '?' + p.toString();
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.getElementById('btn-share');
    const orig = btn.textContent;
    btn.textContent = '✅ Copié !';
    btn.style.color = 'var(--accent)';
    btn.style.borderColor = 'var(--accent)';
    setTimeout(() => { btn.textContent = orig; btn.style.color = ''; btn.style.borderColor = ''; }, 2000);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = url; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy');
    document.body.removeChild(ta);
    showBiomeToast('🔗 Lien copié !');
  });
}

// ── Sélection du pokémon pour le signet ──
let selectedFavNum  = null;
let selectedFavName = null;

function selectFavPokemon(num, name, spriteUrl) {
  // Désélectionner l'ancien
  document.querySelectorAll('.row-sprite.fav-selected').forEach(el => el.classList.remove('fav-selected'));

  if (selectedFavNum === num) {
    // Deuxième clic = désélectionner
    selectedFavNum  = null;
    selectedFavName = null;
    document.getElementById('fav-selection-bar').classList.remove('visible');
    return;
  }

  selectedFavNum  = num;
  selectedFavName = name;

  // Sélectionner le sprite cliqué
  document.querySelectorAll('.fav-sprite-pick').forEach(img => {
    if (parseInt(img.dataset.num) === num) {
      img.classList.add('fav-selected');
    }
  });

  // Afficher la barre flottante
  const bar = document.getElementById('fav-selection-bar');
  document.getElementById('fav-sel-sprite').src  = spriteUrl;
  document.getElementById('fav-sel-name').textContent = name;
  bar.classList.add('visible');

  // Animation coeur
  const heart = document.createElement('span');
  heart.textContent = '♥';
  heart.style.cssText = 'position:fixed;font-size:1.2rem;color:#f9ca24;pointer-events:none;z-index:9999;transition:transform .6s,opacity .6s;animation:heartFloat .6s ease-out forwards';
  const imgs = document.querySelectorAll('.row-sprite');
  let targetImg = null;
  document.querySelectorAll('.fav-sprite-pick').forEach(img => { if (parseInt(img.dataset.num) === num) targetImg = img; });
  if (targetImg) {
    const r = targetImg.getBoundingClientRect();
    heart.style.left = (r.left + r.width/2 - 8) + 'px';
    heart.style.top  = (r.top  - 10) + 'px';
    document.body.appendChild(heart);
    heart.style.transform = 'translateY(-30px) scale(1.5)';
    heart.style.opacity   = '0';
    setTimeout(() => heart.remove(), 700);
  }
}

function clearFavSelection() {
  selectedFavNum  = null;
  selectedFavName = null;
  document.querySelectorAll('.row-sprite.fav-selected').forEach(el => el.classList.remove('fav-selected'));
  document.getElementById('fav-selection-bar').classList.remove('visible');
}

function openSaveFavModal() {
  const defaultLabel = PAGE_BIOME_NAME;
  const label = prompt('Nom du signet (biome + tes filtres actifs seront sauvegardés) :', defaultLabel);
  if (label === null) return;

  // Priorité : sprite sélectionné > source_pokemon > premier visible
  let pokeNum, pokeName;
  if (selectedFavNum && selectedFavName) {
    pokeNum  = selectedFavNum;
    pokeName = selectedFavName;
  } else if (SOURCE_NUM && SOURCE_NAME) {
    pokeNum  = SOURCE_NUM;
    pokeName = SOURCE_NAME;
  } else {
    const visible = getFilteredData();
    const firstPoke = visible[0];
    pokeNum  = firstPoke ? firstPoke.numero : 0;
    pokeName = firstPoke ? pname(firstPoke) : '';
  }

  // Sérialiser TOUS les filtres actifs
  const structIncl = [...filterState['structure'].include];
  const structExcl = [...filterState['structure'].exclude];
  const urlParams = {
    ctx:              [...filterState['contexte'].include][0]  || null,
    ctx_excl:         [...filterState['contexte'].exclude],
    ev:               [...filterState['ev'].include].join(',') || null,
    ev_excl:          [...filterState['ev'].exclude],
    excl_special:     [...filterState['special'].exclude],
    incl_special:     [...filterState['special'].include],
    excl_weather:     [...filterState['weather'].exclude],
    incl_weather:     [...filterState['weather'].include],
    excl_time:        [...filterState['time'].exclude],
    incl_time:        [...filterState['time'].include],
    excl_bucket:      [...filterState['bucket'].exclude],
    incl_bucket:      [...filterState['bucket'].include],
    excl_type:        [...filterState['type'].exclude],
    incl_type:        [...filterState['type'].include],
    excl_structures:  structExcl,
    struct_keep:      structIncl.length ? structIncl[0] : null,
    hmax:             heightMaxCm < HEIGHT_PAGE_MAX ? heightMaxCm / 100 : null,
    hmin:             heightMinCm > HEIGHT_PAGE_MIN ? heightMinCm / 100 : null,
    y_min:            yMinFilter > -64  ? yMinFilter : null,
    y_max:            yMaxFilter < 320  ? yMaxFilter : null,
    removed: buildRemovedList(),
  };

  fetch('/api/favorites', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      label:        (label || defaultLabel).trim(),
      pokemon_num:  pokeNum,
      pokemon_name: pokeName,
      biome_name:   PAGE_BIOME_NAME,
      mod:          PAGE_BIOME_MOD,
      url_params:   urlParams,
    }),
  })
  .then(r => r.json())
  .then(data => {
    if (data.ok) {
      const btn = document.getElementById('btn-save-fav');
      if (btn) { btn.textContent = '✅ Sauvegardé'; btn.style.color = 'var(--accent)'; btn.style.borderColor = 'var(--accent)'; }
      clearFavSelection();
      showBiomeToast('⭐ Signet enregistré !');
    } else {
      showBiomeToast('Erreur : ' + (data.error || '?'), false);
    }
  })
  .catch(() => showBiomeToast('Erreur réseau', false));
}

function buildRemovedList() {
  const items = [];

  const CTX_FR  = { grounded:'Sol', fishing:'Pêche', submerged:'Submerged', surface:'Surface', seafloor:'Fond marin' };
  const EV_FR   = { hp:'PV', atk:'Attaque', def:'Défense', spa:'Att. Spé', spd:'Déf. Spé', spe:'Vitesse' };
  const TIME_FR = { day:'Jour', dusk:'Crépuscule', night:'Nuit', always:'Sans contrainte horaire' };
  const WTHR_FR = { clear:'Beau temps', rain:'Pluie', any:'Sans contrainte météo' };
  const BKFR    = { common:'Commun', uncommon:'Peu commun', rare:'Rare', 'ultra-rare':'Ultra-rare', filler:'Filler' };
  const SP_INCL_FR = {
    sky:'Ciel visible requis', no_sky:'Sans ciel requis', dark:'Obscurité requise',
    bright:'Luminosité requise', water:'Blocs eau requis', block:'Blocs requis',
    base_block:'Blocs sol requis', depth:'Contrainte Y requise', height:'Contrainte hauteur requise',
    slime:'Chunk Slime requis', fishing:'Condition pêche requise', bait:'Appât requis',
    moon:'Phase de lune requise', structure:'Structure requise', no_structure:'Hors structure requis',
    treetop:"Cimes d'arbres requises", none:'Sans condition spéciale',
  };
  const SP_EXCL_FR = {
    sky:'Ciel visible exclu', no_sky:'Sans ciel exclu', dark:'Obscurité exclue',
    bright:'Luminosité exclue', water:'Blocs eau exclus', block:'Blocs requis exclus',
    base_block:'Blocs sol exclus', depth:'Contrainte Y exclue', height:'Contrainte hauteur exclue',
    slime:'Chunk Slime exclu', fishing:'Condition pêche exclue', bait:'Appât exclu',
    moon:'Phase de lune exclue', structure:'Structure exclue', no_structure:'Hors structure exclu',
    treetop:"Cimes d'arbres exclues", none:'Sans condition spéciale exclu',
  };

  // Contexte et EV déjà affichés comme tags obligatoires dans le signet → pas de doublon

  // Temps
  const timeIncl = [...filterState['time'].include];
  const timeExcl = [...filterState['time'].exclude];
  timeIncl.forEach(v => items.push('Moment : ' + (TIME_FR[v]||v) + ' seulement'));
  timeExcl.forEach(v => items.push('Moment exclu : ' + (TIME_FR[v]||v)));

  // Météo
  const wthrIncl = [...filterState['weather'].include];
  const wthrExcl = [...filterState['weather'].exclude];
  wthrIncl.forEach(v => items.push('Météo : ' + (WTHR_FR[v]||v) + ' seulement'));
  wthrExcl.forEach(v => items.push('Météo exclue : ' + (WTHR_FR[v]||v)));

  // Bucket
  const bkIncl = [...filterState['bucket'].include];
  const bkExcl = [...filterState['bucket'].exclude];
  bkIncl.forEach(v => items.push('Rareté : ' + (BKFR[v]||v) + ' seulement'));
  bkExcl.forEach(v => items.push('Rareté exclue : ' + (BKFR[v]||v)));

  // Type
  const tyIncl = [...filterState['type'].include];
  const tyExcl = [...filterState['type'].exclude];
  tyIncl.forEach(v => items.push('Type : ' + v + ' seulement'));
  tyExcl.forEach(v => items.push('Type exclu : ' + v));

  // Special inclus/exclus
  const spIncl = [...filterState['special'].include];
  const spExcl = [...filterState['special'].exclude];
  spIncl.forEach(v => { if (SP_INCL_FR[v]) items.push(SP_INCL_FR[v]); });
  spExcl.forEach(v => { if (SP_EXCL_FR[v]) items.push(SP_EXCL_FR[v]); });

  // Structure incluse (garder seulement)
  const structIncl = [...filterState['structure'].include];
  structIncl.forEach(s => items.push('Structure gardée : ' + s + ' seulement'));

  // Structure exclue (par nom)
  const structExcl = [...filterState['structure'].exclude];
  structExcl.forEach(s => items.push('Structure exclue : ' + s));

  // Hauteur
  if (heightMinCm > HEIGHT_PAGE_MIN) items.push('Hauteur ≥ ' + (heightMinCm/100).toFixed(1) + 'm');
  if (heightMaxCm < HEIGHT_PAGE_MAX) items.push('Hauteur ≤ ' + (heightMaxCm/100).toFixed(1) + 'm');

  // Y
  if (yMinFilter > -64) items.push('Y > ' + yMinFilter);
  if (yMaxFilter < 320) items.push('Y < ' + yMaxFilter);

  // Groupes d'œufs
  const EGG_FR = {
    monster:'Monster', water_1:'Water 1', water_2:'Water 2', water_3:'Water 3',
    bug:'Insecte', flying:'Vol', field:'Sol', fairy:'Fée', grass:'Plante',
    human_like:'Humanoïde', mineral:'Minéral', amorphous:'Amorphe',
    dragon:'Dragon', ditto:'Ditto', undiscovered:'Non découvert', unknown:'Inconnu',
  };
  const egIncl = [...filterState['egg_group'].include];
  const egExcl = [...filterState['egg_group'].exclude];
  egIncl.forEach(v => items.push('Œuf : ' + (EGG_FR[v]||v) + ' seulement'));
  egExcl.forEach(v => items.push('Œuf exclu : ' + (EGG_FR[v]||v)));

  return items;
}

function getFilteredData() {
  return RAW_DATA.filter(p => {
    const ctx = [...filterState['contexte'].include];
    if (ctx.length && !ctx.some(c => p.contextes.includes(c))) return false;
    return true;
  });
}

function showBiomeToast(msg, ok = true) {
  let toast = document.getElementById('biome-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'biome-toast';
    toast.style.cssText = 'position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%) translateY(3rem);background:#0f0f0f;border:1px solid #252525;border-radius:8px;padding:.7rem 1.4rem;font-family:Geist,monospace;font-size:.78rem;color:#e7e7e7;z-index:9999;transition:transform .3s,opacity .3s;opacity:0;pointer-events:none';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.borderColor = ok ? 'rgba(85,239,196,.3)' : 'rgba(255,71,87,.3)';
  toast.style.transform = 'translateX(-50%) translateY(0)';
  toast.style.opacity   = '1';
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    toast.style.transform = 'translateX(-50%) translateY(3rem)';
    toast.style.opacity   = '0';
  }, 2500);
}

// ── bouton scroll-top ──
// Le script est chargé avant l'élément bouton dans le HTML : on attend le DOM.
function _initScrollTop() {
  const _scrollBtn = document.getElementById('scroll-top-btn');
  if (!_scrollBtn) return;
  window.addEventListener('scroll', () => {
    _scrollBtn.style.display = window.scrollY > 400 ? 'flex' : 'none';
    _scrollBtn.style.alignItems = 'center';
    _scrollBtn.style.justifyContent = 'center';
  }, { passive: true });
  _scrollBtn.addEventListener('mouseover', () => { _scrollBtn.style.borderColor='var(--accent)'; _scrollBtn.style.color='var(--accent)'; });
  _scrollBtn.addEventListener('mouseout',  () => { _scrollBtn.style.borderColor='var(--border)'; _scrollBtn.style.color='var(--muted)'; });
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _initScrollTop);
} else {
  _initScrollTop();
}
