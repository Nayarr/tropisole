// Category pills
  document.querySelectorAll('.cat-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      document.getElementById('cat-input').value = pill.dataset.val;
    });
  });

  // Char counters + submit enable
  function updateCount(el, counterId) {
    document.getElementById(counterId).textContent = `${el.value.length} / ${el.maxLength}`;
    checkSubmit();
  }

  function checkSubmit() {
    const title   = document.getElementById('title').value.trim();
    const content = document.getElementById('content').value.trim();
    document.getElementById('btn-submit').disabled = !(title && content);
  }

  // Pre-fill page_url with current referrer if coming from the site
  const ref = document.referrer;
  if (ref && ref.includes(window.location.host)) {
    const urlField = document.getElementById('page_url');
    if (!urlField.value) {
      try {
        urlField.value = new URL(ref).pathname + new URL(ref).search;
      } catch(e) {}
    }
  }
