// Données des favoris

function toast(msg, ok=true) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = ok ? 'rgba(85,239,196,.3)' : 'rgba(255,71,87,.3)';
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2500);
}

function filterCards() {
  const q = document.getElementById('search-input').value.toLowerCase().trim();
  let visible = 0;
  document.querySelectorAll('.fav-card').forEach(card => {
    const match = !q || card.dataset.search.includes(q);
    card.style.display = match ? '' : 'none';
    if (match) visible++;
  });
  document.getElementById('count-label').textContent =
    visible + ' signet' + (visible !== 1 ? 's' : '');
}

async function deleteFav(id, btn) {
  if (!confirm('Supprimer ce signet ?')) return;
  const resp = await fetch(`/api/favorites/${id}`, { method: 'DELETE' });
  if (resp.ok) {
    const card = btn.closest('.fav-card');
    card.style.transition = 'opacity .3s, transform .3s';
    card.style.opacity = '0'; card.style.transform = 'scale(.95)';
    setTimeout(() => { card.remove(); filterCards(); }, 300);
    toast('Signet supprimé');
  } else {
    toast('Erreur lors de la suppression', false);
  }
}

async function renameLabel(input) {
  const id = input.dataset.id;
  const newLabel = input.value.trim();
  if (!newLabel) { input.value = input.defaultValue; return; }
  if (newLabel === input.defaultValue) return;
  const resp = await fetch(`/api/favorites/${id}/rename`, {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ label: newLabel })
  });
  if (resp.ok) {
    input.defaultValue = newLabel;
    const card = input.closest('.fav-card');
    card.dataset.search = card.dataset.search.replace(/^[^|]*/, newLabel.toLowerCase());
    toast('Renommé ✓');
  } else {
    input.value = input.defaultValue;
    toast('Erreur', false);
  }
}
