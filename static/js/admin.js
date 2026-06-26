// ── Modal date ────────────────────────────────────────────────────────────
  function openDateModal(uid, username, currentExpiry) {
    document.getElementById('date-uid').value = uid;
    document.getElementById('date-modal-user').textContent = '🎮 ' + username;
    document.getElementById('date-picker').value = currentExpiry || '';
    document.getElementById('date-value').value = '';
    document.getElementById('btn-apply').disabled = true;
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    setPreview(null);

    // Si expiry existant → pré-afficher
    if (currentExpiry) onDateInput(currentExpiry, false);

    document.getElementById('modal-date').classList.add('open');
  }

  function closeDateModal() {
    document.getElementById('modal-date').classList.remove('open');
  }

  function applyPreset(btn, val) {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    if (val === 'permanent') {
      document.getElementById('date-picker').value = '';
      document.getElementById('date-value').value  = 'permanent';
      setPreview('permanent');
    } else {
      const d = new Date();
      d.setDate(d.getDate() + val);
      const iso = toISO(d);
      document.getElementById('date-picker').value = iso;
      document.getElementById('date-value').value  = iso;
      setPreview(iso);
    }
    document.getElementById('btn-apply').disabled = false;
  }

  function onDateInput(val, enableApply = true) {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    if (!val) {
      setPreview(null);
      document.getElementById('date-value').value = '';
      document.getElementById('btn-apply').disabled = true;
      return;
    }
    document.getElementById('date-value').value = val;
    if (enableApply) document.getElementById('btn-apply').disabled = false;
    setPreview(val);
  }

  function setPreview(val) {
    const el = document.getElementById('date-preview');
    if (!val) { el.className = 'date-preview'; el.innerHTML = ''; return; }

    if (val === 'permanent') {
      el.className = 'date-preview show perm';
      el.innerHTML = '♾️ Accès permanent — aucune date d\'expiration';
      return;
    }

    const target = new Date(val + 'T00:00:00');
    const today  = new Date(); today.setHours(0,0,0,0);
    const diff   = Math.round((target - today) / 86400000);
    const fmt    = target.toLocaleDateString('fr-FR', { weekday:'long', year:'numeric', month:'long', day:'numeric' });

    let cls = 'date-preview show';
    let txt = '';

    if (diff < 0) {
      cls += ' danger';
      txt = `⛔ ${fmt} — cette date est dans le passé (${Math.abs(diff)} jour${Math.abs(diff)>1?'s':''})`;
    } else if (diff === 0) {
      cls += ' warn';
      txt = `⚠️ ${fmt} — expire aujourd'hui`;
    } else if (diff <= 7) {
      cls += ' warn';
      txt = `⚠️ ${fmt} — dans ${diff} jour${diff>1?'s':''}`;
    } else {
      txt = `✅ ${fmt} — dans ${diff} jour${diff>1?'s':''}`;
    }

    el.className = cls;
    el.innerHTML = txt;
  }

  function toISO(d) {
    return d.getFullYear() + '-'
      + String(d.getMonth()+1).padStart(2,'0') + '-'
      + String(d.getDate()).padStart(2,'0');
  }

  // ── Modal refus ──────────────────────────────────────────────────────────
  function confirmRefuse(uid, email) {
    document.getElementById('refuse-uid').value = uid;
    document.getElementById('modal-email-label').textContent = email || uid;
    document.getElementById('modal-refuse').classList.add('open');
  }
  function closeRefuseModal() {
    document.getElementById('modal-refuse').classList.remove('open');
  }

  // Fermer en cliquant à l'extérieur
  ['modal-date','modal-refuse'].forEach(id => {
    document.getElementById(id).addEventListener('click', function(e) {
      if (e.target === this) this.classList.remove('open');
    });
  });
