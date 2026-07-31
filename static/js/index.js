let currentPage = 1;
  let currentOrder = 'asc';
  let debounceTimer;
  let totalPages = 1;

  let activeType = '';

  const BUCKET_CLASS = {
    'filler': 'badge-filler',
    'common': 'badge-common',
    'uncommon': 'badge-uncommon',
    'rare': 'badge-rare',
    'ultra-rare': 'badge-ultra-rare',
  };

  async function loadStats() {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('stat-total-pokemon').textContent = data.total_pokemon.toLocaleString('fr');
    document.getElementById('stat-total-spawns').textContent = data.total_spawns.toLocaleString('fr');
  }

  function getParams() {
    return new URLSearchParams({
      q:      document.getElementById('search').value,
      bucket: document.getElementById('filter-bucket').value,
      type:   activeType,
      sort:   document.getElementById('sort').value,
      order: currentOrder,
      page: currentPage,
      per_page: 40,
    });
  }

  function bucketClass(bucket) {
    return BUCKET_CLASS[bucket] || 'badge-grey';
  }

  function renderSkeletons() {
    const grid = document.getElementById('grid');
    grid.innerHTML = Array(12).fill(0).map(() => `
      <div class="skeleton-card">
        <div class="skeleton" style="height:12px;width:40px"></div>
        <div class="skeleton" style="height:18px;width:80%"></div>
        <div style="display:flex;gap:6px;margin-top:6px">
          <div class="skeleton" style="height:20px;width:60px;border-radius:4px"></div>
        </div>
        <div class="skeleton" style="height:10px;width:60%;margin-top:6px"></div>
      </div>
    `).join('');
  }

  async function loadPokemon() {
    renderSkeletons();
    const res = await fetch('/api/pokemon?' + getParams());
    const data = await res.json();
    totalPages = data.pages;
    document.getElementById('results-count').textContent =
      `${data.total.toLocaleString('fr')} résultat${data.total !== 1 ? 's' : ''}`;

    const grid = document.getElementById('grid');

    if (data.data.length === 0) {
      grid.innerHTML = `
        <div class="empty">
          <span class="icon">◯</span>
          <h3>Aucun Pokémon trouvé</h3>
          <p>Essayez de modifier vos filtres.</p>
        </div>`;
      document.getElementById('pagination').innerHTML = '';
      return;
    }

    grid.innerHTML = data.data.map((p, i) => {
      const cls = bucketClass(p.bucket);
      const num = String(p.numero).padStart(4, '0');
      return `
        <a class="poke-card" href="/pokemon/${p.numero}" style="animation-delay:${i * 0.025}s">
          <span class="poke-entries">${p.nb_entrees} spawn${p.nb_entrees > 1 ? 's' : ''}</span>
          <div class="poke-num">#${num}</div>
          <div class="poke-name">${p.pokemon}</div>
          <div class="poke-meta">
            ${p.bucket ? `<span class="badge ${cls}">${p.bucket_fr}</span>` : ''}
          </div>
          ${p.types && p.types.length ? `<div class="poke-types">${p.types.map(t => `<span class="type-badge" style="background:${TYPE_COLORS[t]||'#8a8a8a'}">${t}</span>`).join('')}</div>` : ''}
          <div class="poke-lvl">Niv. ${p.niveau_min || '?'} – ${p.niveau_max || '?'}</div>
          ${p.sprite ? `<img class="poke-card-sprite" src="/static/pokemon_icons/${p.sprite}" alt="${p.pokemon}" />` : ''}
        </a>`;
    }).join('');

    renderPagination(data.page, data.pages);
  }

  function renderPagination(page, pages) {
    const container = document.getElementById('pagination');
    if (pages <= 1) { container.innerHTML = ''; return; }

    let buttons = [];
    buttons.push(`<button class="page-btn" onclick="goPage(${page-1})" ${page===1?'disabled':''}>←</button>`);

    const range = [];
    for (let i = 1; i <= pages; i++) {
      if (i === 1 || i === pages || (i >= page - 2 && i <= page + 2)) {
        range.push(i);
      } else if (range[range.length - 1] !== '…') {
        range.push('…');
      }
    }

    range.forEach(r => {
      if (r === '…') {
        buttons.push(`<span class="page-btn" style="cursor:default;opacity:0.4">…</span>`);
      } else {
        buttons.push(`<button class="page-btn ${r===page?'active':''}" onclick="goPage(${r})">${r}</button>`);
      }
    });

    buttons.push(`<button class="page-btn" onclick="goPage(${page+1})" ${page===pages?'disabled':''}>→</button>`);
    container.innerHTML = buttons.join('');
  }

  function goPage(p) {
    if (p < 1 || p > totalPages) return;
    currentPage = p;
    loadPokemon();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function resetPage() {
    currentPage = 1;
  }

  function toggleType(t) {
    activeType = (activeType === t) ? '' : t;
    document.querySelectorAll('.type-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.type === activeType);
    });
    resetPage();
    loadPokemon();
  }

  ['filter-bucket', 'sort'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => { resetPage(); loadPokemon(); });
  });

  document.getElementById('search').addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { resetPage(); loadPokemon(); }, 300);
  });

  document.getElementById('btn-order').addEventListener('click', () => {
    currentOrder = currentOrder === 'asc' ? 'desc' : 'asc';
    document.getElementById('btn-order').textContent = currentOrder === 'asc' ? '↑' : '↓';
    resetPage();
    loadPokemon();
  });

  loadStats();
  loadPokemon();

  // ── BIOME NAV ──────────────────────────────────────────────────────
  (function() {
    var cats    = Array.from(document.querySelectorAll('.biome-cat'));
    var panels  = Array.from(document.querySelectorAll('.biome-panel'));
    var buttons = Array.from(document.querySelectorAll('.biome-cat-btn'));
    var hideTimer = null;
    var subTimer   = null;
    var sub2Timer  = null;
    var current    = null;  // L1 ouvert
    var currentSub  = null; // L2 ouvert { item, sub }
    var currentSub2 = null; // L3 ouvert { item, sub }
    var mouseOverSub  = false;
    var mouseOverSub2 = false;

    panels.forEach(function(p) { document.body.appendChild(p); });

    /* ── Positioning ── */
    function positionPanel(btn, panel) {
      var r = btn.getBoundingClientRect();
      panel.style.top  = r.bottom + 'px';
      panel.style.left = r.left   + 'px';
    }
    function positionSub(item, sub) {
      var r    = item.getBoundingClientRect();
      var subW = sub.offsetWidth || 220;
      sub.style.left = (window.innerWidth - r.right >= subW) ? r.right + 'px' : (r.left - subW) + 'px';
      var top = r.top;
      sub.style.top = Math.max(0, Math.min(top, window.innerHeight - (sub.offsetHeight || 300))) + 'px';
    }
    function positionSub2(item, sub2) {
      var r     = item.getBoundingClientRect();
      var sub2W = sub2.offsetWidth || 210;
      sub2.style.left = (window.innerWidth - r.right >= sub2W) ? r.right + 'px' : (r.left - sub2W) + 'px';
      var top = r.top;
      sub2.style.top = Math.max(0, Math.min(top, window.innerHeight - (sub2.offsetHeight || 280))) + 'px';
    }

    /* ── L3 ── */
    function closeSub2() {
      if (currentSub2) {
        currentSub2.sub.classList.remove('is-open');
        currentSub2.item.classList.remove('sub2-open');
        currentSub2 = null;
      }
      mouseOverSub2 = false;
    }
    function openSub2(item, sub2El) {
      clearTimeout(sub2Timer);
      clearTimeout(subTimer);
      clearTimeout(hideTimer);
      if (currentSub2 && currentSub2.sub !== sub2El) closeSub2();
      if (sub2El.parentNode !== document.body) document.body.appendChild(sub2El);
      positionSub2(item, sub2El);
      sub2El.classList.add('is-open');
      item.classList.add('sub2-open');
      currentSub2 = { item: item, sub: sub2El };
    }
    function scheduleCloseSub2() {
      if (mouseOverSub2) return;
      sub2Timer = setTimeout(function() { if (!mouseOverSub2) closeSub2(); }, 300);
    }

    /* ── L2 ── */
    function closeSub() {
      closeSub2();
      if (currentSub) {
        currentSub.sub.classList.remove('is-open');
        currentSub.item.classList.remove('sub-open');
        currentSub = null;
      }
      mouseOverSub = false;
    }
    function openSub(item, subEl) {
      clearTimeout(subTimer);
      clearTimeout(hideTimer);
      if (currentSub && currentSub.sub !== subEl) closeSub();
      if (subEl.parentNode !== document.body) document.body.appendChild(subEl);
      positionSub(item, subEl);
      subEl.classList.add('is-open');
      item.classList.add('sub-open');
      currentSub = { item: item, sub: subEl };
    }
    function scheduleCloseSub() {
      if (mouseOverSub) return;
      subTimer = setTimeout(function() { if (!mouseOverSub) closeSub(); }, 300);
    }

    /* ── Init L3 sur les items d'un L2 ── */
    function initSub2Items(subEl) {
      subEl.querySelectorAll('.bp-sub2-item').forEach(function(item) {
        var sub2El = item.querySelector('.bp-sub2');
        if (!sub2El) return;
        item.addEventListener('mouseenter', function() {
          mouseOverSub2 = false;
          mouseOverSub  = true;
          clearTimeout(subTimer);
          openSub2(item, sub2El);
        });
        item.addEventListener('mouseleave', function(e) {
          var to = e.relatedTarget;
          if (to && (sub2El.contains(to) || sub2El === to)) return;
          scheduleCloseSub2();
        });
        sub2El.addEventListener('mouseenter', function() {
          mouseOverSub2 = true;
          mouseOverSub  = true;
          clearTimeout(sub2Timer);
          clearTimeout(subTimer);
          clearTimeout(hideTimer);
        });
        sub2El.addEventListener('mouseleave', function(e) {
          mouseOverSub2 = false;
          var to = e.relatedTarget;
          if (to && (item.contains(to) || item === to)) return;
          scheduleCloseSub2();
        });
      });
    }

    /* ── Init L2 sur les items d'un L1 ── */
    function initSubMenus(panel) {
      panel.querySelectorAll('.bp-item').forEach(function(item) {
        var subEl = item.querySelector('.bp-sub');
        if (!subEl) return;
        initSub2Items(subEl);
        item.addEventListener('mouseenter', function() {
          mouseOverSub = false;
          openSub(item, subEl);
        });
        item.addEventListener('mouseleave', function(e) {
          var to = e.relatedTarget;
          if (to && (subEl.contains(to) || subEl === to)) return;
          scheduleCloseSub();
        });
        subEl.addEventListener('mouseenter', function() {
          mouseOverSub = true;
          clearTimeout(subTimer);
          clearTimeout(hideTimer);
        });
        subEl.addEventListener('mouseleave', function(e) {
          mouseOverSub = false;
          var to = e.relatedTarget;
          if (to && (currentSub2 && currentSub2.sub.contains(to))) return;
          if (to && (item.contains(to) || item === to)) return;
          scheduleCloseSub();
        });
      });
    }

    /* ── L1 ── */
    function openPanel(i) {
      clearTimeout(hideTimer);
      if (current && current.i !== i) {
        current.panel.classList.remove('is-open');
        current.btn.classList.remove('is-active');
        closeSub();
      }
      var panel = panels[i], btn = buttons[i];
      positionPanel(btn, panel);
      panel.classList.add('is-open');
      btn.classList.add('is-active');
      current = { i: i, panel: panel, btn: btn };
    }
    function scheduleClose() {
      if (mouseOverSub || mouseOverSub2) return;
      hideTimer = setTimeout(function() {
        if (mouseOverSub || mouseOverSub2) return;
        if (current) {
          current.panel.classList.remove('is-open');
          current.btn.classList.remove('is-active');
          current = null; closeSub();
        }
      }, 300);
    }
    function cancelClose() { clearTimeout(hideTimer); }

    panels.forEach(function(panel) { initSubMenus(panel); });

    cats.forEach(function(cat, i) {
      buttons[i].addEventListener('mouseenter', function() { openPanel(i); });
      buttons[i].addEventListener('mouseleave', function(e) {
        if (e.relatedTarget && panels[i].contains(e.relatedTarget)) return;
        scheduleClose();
      });
      panels[i].addEventListener('mouseenter', cancelClose);
      panels[i].addEventListener('mouseleave', function(e) {
        var to = e.relatedTarget;
        if (to && currentSub  && currentSub.sub.contains(to))  return;
        if (to && currentSub2 && currentSub2.sub.contains(to)) return;
        scheduleClose();
      });
    });

    document.addEventListener('click', function(e) {
      if (!current) return;
      var inPanel = current.panel.contains(e.target);
      var inSub   = currentSub  && currentSub.sub.contains(e.target);
      var inSub2  = currentSub2 && currentSub2.sub.contains(e.target);
      if (!inPanel && !inSub && !inSub2 && !current.btn.contains(e.target)) {
        current.panel.classList.remove('is-open');
        current.btn.classList.remove('is-active');
        current = null; closeSub();
      }
    });

    window.addEventListener('scroll', function() {
      if (current)    positionPanel(current.btn, current.panel);
      if (currentSub) positionSub(currentSub.item, currentSub.sub);
      if (currentSub2) positionSub2(currentSub2.item, currentSub2.sub);
    }, { passive: true });
    window.addEventListener('resize', function() {
      if (current)    positionPanel(current.btn, current.panel);
      if (currentSub) positionSub(currentSub.item, currentSub.sub);
      if (currentSub2) positionSub2(currentSub2.item, currentSub2.sub);
    });
  })();

// ── Expiration abonnement ──
(function() {
  const el = document.getElementById('expiry-text');
  if (!el) return;
  const raw = el.textContent.trim(); // YYYY-MM-DD
  if (!raw) return;
  const exp = new Date(raw + 'T23:59:59');
  const now = new Date();
  const diffMs = exp - now;
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  const badge = el.closest('.expiry-badge');
  if (diffDays <= 0) {
    el.textContent = 'Expiré';
    badge.classList.add('expired');
    badge.title = 'Votre accès a expiré';
  } else if (diffDays <= 7) {
    el.textContent = `Expire dans ${diffDays}j`;
    badge.classList.add('expiring-soon');
    badge.title = `Expire le ${raw}`;
  } else {
    el.textContent = `Expire le ${raw}`;
    badge.title = `${diffDays} jours restants`;
  }
})();
