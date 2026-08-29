const SPRITE_BASE = '/static/pokemon_icons/';

let selectedNum = null;
let focusMode = false;

function toggleFocus() {
  focusMode = !focusMode;
  const btn = document.getElementById('btn-focus');
  const hint = document.getElementById('focus-hint');
  if (focusMode) {
    btn.textContent = '🎯 Focus';
    btn.classList.add('active');
    hint.textContent = 'Mode focus : optimise uniquement pour le Pokémon sélectionné (ignore l\'évolution)';
  } else {
    btn.textContent = '🎯 Chaîne';
    btn.classList.remove('active');
    hint.textContent = 'Mode chaîne : optimise pour toute la lignée évolutive';
  }
}

// ── Autocomplete ──
const searchInput = document.getElementById('poke-input');
const acList = document.getElementById('ac-list');
let acIndex = -1;

searchInput.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase().trim();
  selectedNum = null;
  document.getElementById('btn-analyze').disabled = true;

  if (!q) { acList.classList.remove('open'); return; }

  const matches = POKEMON_LIST.filter(p =>
    p.name.toLowerCase().includes(q) ||
    String(p.numero).padStart(4,'0').includes(q)
  ).slice(0, 12);

  if (!matches.length) { acList.classList.remove('open'); return; }

  acList.innerHTML = matches.map((p, i) => {
    const num = String(p.numero).padStart(4,'0');
    const sprite = `${SPRITE_BASE}icon${num}_f00_s0.png`;
    const FORME_COLORS = { Alola:'#00b4d8', Galar:'#9b5de5', Hisui:'#e9c46a', Paldea:'#f4a261', Valencia:'#2dc653' };
    const formeMatch = p.name.match(/\(([^)]+)\)$/);
    const formeBadge = formeMatch
      ? `<span style="font-size:.58rem;padding:.1rem .4rem;border-radius:10px;background:${(FORME_COLORS[formeMatch[1]]||'#8a8a8a')}22;border:1px solid ${(FORME_COLORS[formeMatch[1]]||'#8a8a8a')}55;color:${(FORME_COLORS[formeMatch[1]]||'#8a8a8a')}">${formeMatch[1]}</span>`
      : '';
    const baseName = formeMatch ? p.name.replace(/\s*\([^)]+\)$/, '') : p.name;
    return `<div class="ac-item" data-num="${p.numero}" data-name="${p.name}">
      <span class="ac-num">#${num}</span>
      <img class="ac-sprite" src="${sprite}" onerror="this.style.display='none'" />
      <span>${baseName}</span>${formeBadge}
    </div>`;
  }).join('');
  acList.querySelectorAll('.ac-item').forEach(el => {
    el.addEventListener('click', () => selectPokemon(
      parseInt(el.dataset.num), el.dataset.name
    ));
  });
  acList.classList.add('open');
  acIndex = -1;
});

searchInput.addEventListener('keydown', e => {
  const items = acList.querySelectorAll('.ac-item');
  if (e.key === 'ArrowDown') { acIndex = Math.min(acIndex+1, items.length-1); highlightAC(items); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { acIndex = Math.max(acIndex-1, 0); highlightAC(items); e.preventDefault(); }
  else if (e.key === 'Enter' && acIndex >= 0) { items[acIndex].click(); }
  else if (e.key === 'Escape') { acList.classList.remove('open'); }
});

function highlightAC(items) {
  items.forEach((el, i) => el.classList.toggle('selected', i === acIndex));
}

function selectPokemon(num, name) {
  selectedNum = num;
  searchInput.value = name;
  acList.classList.remove('open');
  document.getElementById('btn-analyze').disabled = false;
}

document.addEventListener('click', e => {
  if (!e.target.closest('.search-input-wrap')) acList.classList.remove('open');
});

// ── Analyse ──
const CTX_LABELS = {
  fishing: "🎣 Pêche", grounded: "🌿 Sol", submerged: "🌊 Sous l'eau",
  surface: '💧 Surface', seafloor: '🪨 Fond marin'
};
const TIME_LABELS = { day: '☀️ Jour', dusk: '🌆 Crépuscule', night: '🌙 Nuit' };
const WTHR_LABELS = { clear: '🌤️ Ensoleillé', rain: '🌧️ Pluie' };

let currentSSE = null;

function analyze() {
  if (!selectedNum) return;
  if (currentSSE) { currentSSE.close(); currentSSE = null; }

  const section = document.getElementById('results-section');
  const loading = document.getElementById('loading');
  loading.classList.add('visible');
  section.style.display = 'none';
  section.innerHTML = '';
  document.getElementById('btn-analyze').disabled = true;

  currentSSE = new EventSource(`/api/oracle/stream?numero=${selectedNum}&focus=${focusMode ? 1 : 0}`);
  let chainHtml = '';

  currentSSE.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === 'init') {
      chainHtml = data.chain.length > 1
        ? `<div class="chain-info">
            <span class="chain-label">Chaîne :</span>
            ${data.chain.map(n => `<span class="chain-pokemon">${n}</span>`).join('<span class="chain-arrow">→</span>')}
           </div>`
        : '';
      document.getElementById('loading').querySelector('span') &&
        (document.getElementById('loading').lastChild.textContent = ` Analyse… 0 / ${data.total_biomes} biomes`);
    }

    if (data.type === 'update') {
      const txt = document.getElementById('loading').childNodes;
      if (txt.length > 1) txt[1].textContent = ` Analyse… ${data.progress} / ${data.total_biomes} biomes`;
      section.style.display = 'flex';
      section.style.flexDirection = 'column';
      section.style.gap = '1rem';
      section.innerHTML = chainHtml + '<div class="results-grid">' + data.results.map((r,i) => renderCard(r,i)).join('') + '</div>';
    }

    if (data.type === 'done') {
      currentSSE.close(); currentSSE = null;
      loading.classList.remove('visible');
      document.getElementById('btn-analyze').disabled = false;
      if (!section.innerHTML.trim()) {
        section.innerHTML = '<div class="empty-state">Aucun résultat trouvé.</div>';
        section.style.display = 'block';
      }
    }
  };

  currentSSE.onerror = () => {
    currentSSE.close(); currentSSE = null;
    loading.classList.remove('visible');
    document.getElementById('btn-analyze').disabled = false;
    section.innerHTML = '<div class="empty-state">❌ Erreur de connexion au serveur.</div>';
    section.style.display = 'block';
  };
}

const PRESET_LABELS = {
  "natural": "🌿 Naturel", "water": "💧 Eau", "treetop": "🌲 Cimes",
  "foliage": "🍃 Feuillage", "wild": "🐾 Sauvage", "urban": "🏙️ Urbain",
  "derelict": "🏚️ Délabré", "lava": "🔥 Lave", "redstone": "⚙️ Redstone",
  "illager_structures": "🏰 Pillards", "mansion": "👻 Manoir",
  "mansion_bedrooms": "🛏️ Manoir (chambres)", "mansion_dining": "🍽️ Manoir (salle)",
  "trail_ruins": "🗺️ Ruines", "webs": "🕷️ Toiles", "salt": "🧂 Sel",
  "ancient_city": "🏛️ Cité ancienne", "stronghold": "🏯 Forteresse",
  "end_city": "🌆 Cité de l'End", "nether_fossil": "🦴 Fossile Nether",
  "nether_structures": "🔮 Structures Nether", "jungle_pyramid": "🛕 Pyramide jungle",
  "desert_pyramid": "⛩️ Pyramide désert", "pillager_outpost": "⚔️ Avant-poste",
  "ruined_portal": "🌀 Portail ruiné", "ocean_ruins": "🌊 Ruines océan",
  "ocean_monument": "🔱 Monument océan",
};

function buildBiomeUrl(r) {
  const combo = r.combo || {};
  const p = new URLSearchParams();

  // Biome virtuel (structure ubiquitaire) → URL vers /spawns/biome avec tag de dimension
  if (r.virtual_info) {
    const vi = r.virtual_info;
    // Base : /spawns/biome?biomes=<dim_fr>
    const base = new URLSearchParams();
    base.set('biomes', vi.dim_fr);
    if (vi.struct_labels && vi.struct_labels.length > 0) {
      // incl_structures = inclusion OR : spawn passe s'il a AU MOINS UN de ces labels
      // Parfait pour Monorpale [Forteresse+Bastion] : passe avec incl_structures=Forteresse+Nether
      base.set('incl_structures', vi.struct_labels.join('|'));
      // incl_special=structure : exclure les spawns sans structure
      const existingIncl = base.get('incl_special');
      base.set('incl_special', existingIncl ? existingIncl + ',structure' : 'structure');
    }
    if (combo.contexte) base.set('ctx', combo.contexte);
    if (combo.ev)       base.set('ev',  combo.ev);
    if (combo.farm_time) base.set('time', combo.farm_time);
    if (combo.block_weather_excl) base.set('excl_weather', combo.block_weather_excl);
    const exclSpV = [];
    if (combo.no_struct_filter)    exclSpV.push('structure');
    if (combo.block_needed_blocks) exclSpV.push('water', 'block');
    if (combo.block_base_blocks)   exclSpV.push('base_block');
    if (combo.block_darkness)      exclSpV.push('dark');
    if (combo.block_brightness)    exclSpV.push('bright');
    if (exclSpV.length) base.set('excl_special', [...new Set(exclSpV)].join(','));
    if (combo.h_max !== undefined) base.set('hmax', combo.h_max);
    if (combo.excl_structures_fr?.length) base.set('excl_structures', combo.excl_structures_fr.join('|'));
    if (combo.incl_preset) base.set('incl_preset', combo.incl_preset);
    if (combo.excl_preset_list?.length) base.set('excl_preset', combo.excl_preset_list.join(','));
    return `/spawns/biome?${base.toString()}`;
  }

  p.set('biome', r.biome_name);
  p.set('mod',   r.mod || '');

  // Filtres obligatoires
  if (combo.contexte)      p.set('ctx',  combo.contexte);
  if (combo.ev)            p.set('ev',   combo.ev);          // ex: "spe" ou "atk,spe"

  // Filtres optionnels issus du beam
  if (combo.farm_time)     p.set('time', combo.farm_time);
  if (combo.block_weather_excl) p.set('excl_weather', combo.block_weather_excl);
  else if (combo.block_weather) {
    // Fallback : si pas de clé _excl, inverser manuellement (clear→rain, rain→clear)
    const inv = { clear: 'rain', rain: 'clear' };
    if (inv[combo.block_weather]) p.set('excl_weather', inv[combo.block_weather]);
  }
  if (combo.block_sky) {
    // open = bloquer ciel visible → exclure les spawns sky
    // covered = bloquer ciel absent → exclure les spawns no_sky
    p.set('excl_special', combo.block_sky === 'open' ? 'sky' : 'no_sky');
  }
  // require_preset (treetop/water/lava) → déroulé Preset (et non Conditions, pour éviter le doublon)
  if (combo.require_preset) p.set('incl_preset', combo.require_preset);
  // Preset filter : incl_preset=none ou excl_preset=treetop,foliage,...
  if (combo.incl_preset) p.set('incl_preset', combo.incl_preset);
  if (combo.excl_preset_list?.length) p.set('excl_preset', combo.excl_preset_list.join(','));
  // require_struct : on EXCLUT toutes les autres structures sauf celle choisie
  // → biome_spawns recevra la liste des structures à exclure
  // Structure : struct_keep = label FR de la structure à garder
  // biome_spawns exclut dynamiquement tout le reste
  const structKeep = combo.struct_keep_fr || combo.require_struct_fr;
  if (structKeep) p.set('struct_keep', structKeep);
  // Structures à exclure (excl_structures_fr = liste de labels FR)
  if (combo.excl_structures_fr?.length) {
    p.set('excl_structures', combo.excl_structures_fr.join('|'));
  }
  if (combo.block_presets?.length) {
    const existing = p.get('excl_special');
    const list = [...(existing ? [existing] : []), ...combo.block_presets].join(',');
    p.set('excl_special', list);
  }
  if (combo.h_max  !== undefined) p.set('hmax',  combo.h_max);
  if (combo.y_above !== undefined) p.set('y_min', combo.y_above + 1);
  if (combo.y_below !== undefined) p.set('y_max', combo.y_below - 1);

  // Construire la liste excl_special (NE PAS inclure 'structure' ici — géré via excl_structures)
  const exclSp = (p.get('excl_special') || '').split(',').filter(Boolean);
  if (combo.block_needed_blocks) exclSp.push('water', 'block');
  if (combo.block_base_blocks)   exclSp.push('base_block');
  if (combo.block_darkness)      exclSp.push('dark');
  if (combo.block_brightness)    exclSp.push('bright');
  if (exclSp.length) p.set('excl_special', [...new Set(exclSp)].join(','));

  return `/spawns/biome-reel?${p.toString()}`;
}


function renderCard(r, i) {
  const pct     = r.pct;       // score pondéré (tri)
  const rawPct  = r.raw_pct ?? r.pct;  // % affiché
  const onlyUltra  = r.only_ultra || false;
  const fillerNames = r.filler_names || [];
  const isGold  = rawPct === 100 && r.competitors_names.length === 0 && fillerNames.length === 0;
  const pctClass = isGold ? 'pgold' : rawPct === 100 ? 'p100' : onlyUltra ? 'ponly' : rawPct >= 75 ? 'p75' : rawPct >= 50 ? 'p50' : 'plow';
  const cardClass = isGold ? 'gold' : rawPct === 100 ? 'perfect' : onlyUltra ? 'great' : rawPct >= 75 ? 'great' : '';
  const barColor  = isGold ? '#ffc439' : rawPct === 100 ? '#55efc4' : onlyUltra ? '#a29bfe' : rawPct >= 75 ? '#C9A24B' : rawPct >= 50 ? '#ffab40' : '#8a8a8a';

  const combo = r.combo || {};

  // Conditions OBLIGATOIRES
  const mandatoryTags = [];
  if (combo.contexte) mandatoryTags.push(`<span class="filter-tag ctx">${CTX_LABELS[combo.contexte] || combo.contexte}</span>`);
  if (combo.ev_label) mandatoryTags.push(`<span class="filter-tag lume">⚡ EV ${combo.ev_label}</span>`);
  if (combo.structure) mandatoryTags.push(`<span class="filter-tag lume">🏗️ ${combo.structure.replace(/.*[:/]/, '')}</span>`);
  if (combo.require_preset) {
    const PRESET_LABELS_CARD = { 'treetop': '🌲 Cimes d\'arbres', 'water': '💧 Eau', 'lava': '🌋 Lave' };
    mandatoryTags.push(`<span class="filter-tag ctx">${PRESET_LABELS_CARD[combo.require_preset] || combo.require_preset}</span>`);
  }
  if (combo.incl_preset === 'none') {
    mandatoryTags.push(`<span class="filter-tag lume">∅ Preset vide uniquement</span>`);
  }
  if (combo.require_struct_label) {
    mandatoryTags.push(`<span class="filter-tag ctx">${combo.require_struct_label}</span>`);
  }

  // Conditions SUPPRIMÉES pour isoler (envoyées directement par le serveur)
  const removedTags = (combo.removed || []).map(msg =>
    `<span class="filter-tag removed">🚫 ${msg}</span>`
  );
  // Structures exclues → afficher dans "À bloquer"
  if (combo.excl_structures_fr?.length) {
    combo.excl_structures_fr.forEach(lbl =>
      removedTags.push(`<span class="filter-tag removed">🏗️ ${lbl} exclu</span>`)
    );
  }

  const filtersHtml = `
    <div class="filters-row">
      <span class="filter-label">Obligatoire</span>${mandatoryTags.join('')}
    </div>
    ${removedTags.length
      ? `<div class="filters-row"><span class="filter-label">À bloquer</span>${removedTags.join('')}</div>`
      : `<div class="filters-row"><span class="filter-label" style="color:var(--green)">Aucun blocage supplémentaire ✓</span></div>`
    }`;


  const BUCKET_COLORS = { 'ultra-rare': '#a29bfe', 'rare': '#C9A24B', 'uncommon': '#55efc4', 'common': '#8a8a8a' };
  const compHtml = r.competitors_names.length === 0
    ? `<span class="no-competitors">✅ Isolation parfaite avec la chaîne</span>`
    : `<div class="competitors-wrap">
        <span class="filter-label">Concurrents</span>
        ${r.competitors_names.slice(0, 8).map((n, i) => {
          const bkt = (r.competitors_buckets || [])[i];
          const col = BUCKET_COLORS[bkt] || '#8a8a8a';
          return `<span class="competitor-chip" style="border-color:${col}44;color:${col}">${n}</span>`;
        }).join('')}
        ${r.competitors_names.length > 8 ? `<span class="competitor-chip">+${r.competitors_names.length - 8}</span>` : ''}
       </div>`;

  const totalBase = r.total_base || r.total_spawns;
  const totalFilt = r.total_filtered || r.total_spawns;

  const modColor = {
    "Vanilla Minecraft": "#74b9ff", "Terralith": "#55efc4",
    "Wythers\' Overhauled Overworld": "#fd79a8", "Oh The Biomes We\'ve Gone": "#6ab04c",
    "BetterNether": "#ff7675", "Cobblemon": "#C9A24B",
  }[r.mod] || "#8a8a8a";

  const reductPct = totalBase > 0 ? ((totalBase - totalFilt) / totalBase * 100).toFixed(1) : '0.0';

  const fillerHtml = fillerNames.length === 0 ? '' :
    `<div class="fillers-wrap">
      <span class="filter-label" style="color:var(--muted)">Fillers inévitables</span>
      ${fillerNames.slice(0, 6).map(n => `<span class="filler-chip">⚠ ${n}</span>`).join('')}
      ${fillerNames.length > 6 ? `<span class="filler-chip">+${fillerNames.length - 6}</span>` : ''}
    </div>`;

  return `
    <div class="result-card ${cardClass}">
      <div class="result-top">
        <span class="result-rank">#${i+1}</span>
        <div style="flex:1">
          <a class="result-biome"
             href="${buildBiomeUrl(r)}"
             target="_blank"
             style="text-decoration:none;color:inherit;cursor:pointer"
             onmouseover="this.style.color='var(--accent)'" onmouseout="this.style.color='inherit'">
            ${r.biome_name || r.biome_fr} ↗
          </a>
          <div style="font-family:'Geist',monospace;font-size:.6rem;margin-top:2px;color:${modColor}">${r.mod || ""}</div>
        </div>
        <div style="text-align:right">
          <span class="result-pct ${pctClass}">−${reductPct}%</span>
          <div class="result-pct-sub">pureté <span>${rawPct}%</span></div>
          ${isGold ? '<div class="badge-gold" style="margin-top:.3rem">✦ Isolation totale</div>' : onlyUltra ? '<div class="badge-ultra-only" style="margin-top:.3rem">⭐ Ultra-rares</div>' : ''}
        </div>
      </div>
      <div class="pct-bar-wrap">
        <div class="pct-bar" style="width:${parseFloat(reductPct)}%;background:${barColor}"></div>
      </div>
      ${filtersHtml}
      ${compHtml}
      ${fillerHtml}
      <div class="result-stat">
        <span>${r.target_spawns}</span> spawn${r.target_spawns > 1 ? 's' : ''} cibles
        sur <span>${totalFilt}</span> restants
        <span style="color:var(--muted)">·</span> ${totalBase} total dans le biome
      </div>
    </div>`;
}

// ── Auto-lancement depuis l'URL (/oracle?numero=X&focus=1) ──
// Utilisé par le Classement d'isolation : clic sur un Pokémon → relance la simu.
(function autorunFromURL() {
  const p = new URLSearchParams(location.search);
  const num = parseInt(p.get('numero'), 10);
  if (!num) return;
  const entry = POKEMON_LIST.find(x => x.numero === num);
  if (!entry) return;
  if (p.get('focus') === '1' && !focusMode) toggleFocus();
  selectPokemon(num, entry.name);
  analyze();
})();
