const firebaseConfig = {
    apiKey: "AIzaSyD1xoheh3BPkb8ApvVmP2HXcVN42MiU5Ag",
    authDomain: "tropisole-e9cc2.firebaseapp.com",
    projectId: "tropisole-e9cc2",
    storageBucket: "tropisole-e9cc2.appspot.com",
    messagingSenderId: "103939448578976402291",
    appId: "1:581420986357:web:5023cb93d4befa2a893abc"
  };
  firebase.initializeApp(firebaseConfig);

  // ── TAB SWITCH ────────────────────────────────────────────────────────────
  function switchTab(name) {
    ['login', 'register'].forEach(t => {
      document.getElementById('tab-' + t).classList.toggle('active', t === name);
      document.getElementById('panel-' + t).classList.toggle('active', t === name);
    });
    // clear alerts on switch
    ['alert-login', 'alert-register'].forEach(id => {
      const el = document.getElementById(id);
      el.className = 'alert';
      el.textContent = '';
    });
  }

  // ── Enter to submit ───────────────────────────────────────────────────────
  document.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    if (document.getElementById('panel-login').classList.contains('active')) login();
    else register();
  });

  // ── UTILS ─────────────────────────────────────────────────────────────────
  function setLoading(btnId, on) {
    const btn = document.getElementById(btnId);
    btn.disabled = on;
    btn.classList.toggle('loading', on);
  }

  function showAlert(alertId, msg, type) {
    const el = document.getElementById(alertId);
    el.textContent = msg;
    el.className = 'alert' + (msg ? ' ' + type : '');
  }

  const FIREBASE_ERRORS = {
    'auth/user-not-found':         'Aucun compte trouvé pour cet email.',
    'auth/wrong-password':         'Mot de passe incorrect.',
    'auth/invalid-email':          'Adresse e-mail invalide.',
    'auth/invalid-credential':     'Identifiants invalides.',
    'auth/email-already-in-use':   'Un compte existe déjà avec cet email.',
    'auth/weak-password':          'Mot de passe trop faible (8 caractères min.).',
    'auth/too-many-requests':      'Trop de tentatives. Réessayez dans quelques minutes.',
    'auth/network-request-failed': 'Erreur réseau. Vérifiez votre connexion.',
  };

  // ── PASSWORD STRENGTH ─────────────────────────────────────────────────────
  function updateStrength(val) {
    const wrap  = document.getElementById('strength-wrap');
    const fill  = document.getElementById('strength-fill');
    const label = document.getElementById('strength-label');

    if (!val) { wrap.classList.remove('visible'); return; }
    wrap.classList.add('visible');

    let score = 0;
    if (val.length >= 8)  score++;
    if (val.length >= 12) score++;
    if (/[A-Z]/.test(val)) score++;
    if (/[0-9]/.test(val)) score++;
    if (/[^A-Za-z0-9]/.test(val)) score++;

    const levels = [
      { pct: '20%',  color: '#ff4757', text: 'Très faible' },
      { pct: '40%',  color: '#ff6b35', text: 'Faible' },
      { pct: '60%',  color: '#ffa07a', text: 'Moyen' },
      { pct: '80%',  color: '#55efc4', text: 'Fort' },
      { pct: '100%', color: '#C9A24B', text: 'Très fort' },
    ];
    const lvl = levels[Math.max(0, score - 1)] || levels[0];
    fill.style.width      = lvl.pct;
    fill.style.background = lvl.color;
    label.textContent     = lvl.text;
    label.style.color     = lvl.color;
  }

  // ── DEVICE FINGERPRINT ────────────────────────────────────────────────────
  async function getDeviceFingerprint() {
    const components = [];

    // CPU / mémoire (stables, liés au matériel)
    components.push('cores:' + (navigator.hardwareConcurrency || 0));
    components.push('mem:'   + (navigator.deviceMemory       || 0));

    // OS / plateforme / timezone (stables, liés au système)
    components.push('plat:' + (navigator.platform || ''));
    components.push('tz:'   + Intl.DateTimeFormat().resolvedOptions().timeZone);
    components.push('lang:' + navigator.language);

    // Tactile (stable, lié au matériel)
    components.push('touch:' + navigator.maxTouchPoints);

    // WebGL renderer (nom du GPU — stable, lié au matériel)
    try {
      const gl  = document.createElement('canvas').getContext('webgl');
      const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
      if (ext) {
        components.push('gpu:' + gl.getParameter(ext.UNMASKED_RENDERER_WEBGL));
        components.push('gvnd:' + gl.getParameter(ext.UNMASKED_VENDOR_WEBGL));
      } else {
        components.push('gpu:n/a');
      }
    } catch (e) {
      components.push('gpu:err');
    }

    // Hash SHA-256 côté client (TextEncoder + SubtleCrypto)
    const raw = components.join('|');
    try {
      const buf    = new TextEncoder().encode(raw);
      const digest = await crypto.subtle.digest('SHA-256', buf);
      const hex    = Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2,'0')).join('');
      return hex;
    } catch (e) {
      // Fallback : simple hash maison si SubtleCrypto indisponible (très rare)
      let h = 0;
      for (let i = 0; i < raw.length; i++) { h = Math.imul(31, h) + raw.charCodeAt(i) | 0; }
      return 'fb_' + Math.abs(h).toString(16).padStart(8, '0');
    }
  }

  // ── LOGIN ─────────────────────────────────────────────────────────────────
  async function login() {
    showAlert('alert-login', '', '');
    const email    = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    if (!email || !password) {
      showAlert('alert-login', 'Veuillez renseigner votre email et mot de passe.', 'error');
      return;
    }

    setLoading('btn-login', true);
    try {
      const cred    = await firebase.auth().signInWithEmailAndPassword(email, password);
      const idToken = await cred.user.getIdToken();

      const deviceFingerprint = await getDeviceFingerprint();
      const res = await fetch('/firebase-auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken, deviceFingerprint })
      });

      if (res.status === 202) {
        const data = await res.json();
        showAlert('alert-login', '⏳ ' + (data.message || 'Compte en attente de validation.'), 'success');
        setLoading('btn-login', false);
      } else if (res.ok) {
        showAlert('alert-login', 'Connexion réussie — redirection…', 'success');
        setTimeout(() => { window.location.href = '/'; }, 700);
      } else {
        const err = await res.json();
        showAlert('alert-login', 'Erreur serveur : ' + (err.message || 'inconnue'), 'error');
        setLoading('btn-login', false);
      }
    } catch (e) {
      showAlert('alert-login', FIREBASE_ERRORS[e.code] || 'Erreur : ' + e.message, 'error');
      setLoading('btn-login', false);
    }
  }

  // ── REGISTER ──────────────────────────────────────────────────────────────
  async function register() {
    showAlert('alert-register', '', '');
    const email    = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;
    const confirm  = document.getElementById('reg-confirm').value;

    const username = document.getElementById('reg-username').value.trim();
    if (!username) {
      showAlert('alert-register', 'Veuillez entrer votre nom en jeu.', 'error');
      return;
    }
    if (!email || !password || !confirm) {
      showAlert('alert-register', 'Veuillez remplir tous les champs.', 'error');
      return;
    }
    if (password.length < 8) {
      showAlert('alert-register', 'Le mot de passe doit contenir au moins 8 caractères.', 'error');
      return;
    }
    if (password !== confirm) {
      showAlert('alert-register', 'Les mots de passe ne correspondent pas.', 'error');
      return;
    }

    setLoading('btn-register', true);
    try {
      const cred    = await firebase.auth().createUserWithEmailAndPassword(email, password);
      const idToken = await cred.user.getIdToken();

      // On connecte directement après création
      const deviceFingerprint = await getDeviceFingerprint();
      const res = await fetch('/firebase-auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken, username, deviceFingerprint })
      });

      if (res.status === 202) {
        showAlert('alert-register', '✅ Compte créé ! Votre accès est en attente de validation par un administrateur.', 'success');
        setLoading('btn-register', false);
      } else if (res.ok) {
        showAlert('alert-register', 'Compte créé — redirection…', 'success');
        setTimeout(() => { window.location.href = '/'; }, 700);
      } else {
        const err = await res.json();
        showAlert('alert-register', 'Erreur serveur : ' + (err.message || 'inconnue'), 'error');
        setLoading('btn-register', false);
      }
    } catch (e) {
      showAlert('alert-register', FIREBASE_ERRORS[e.code] || 'Erreur : ' + e.message, 'error');
      setLoading('btn-register', false);
    }
  }

  const params = new URLSearchParams(window.location.search);
  if (params.get('pending') === '1') {
    document.getElementById('pending-notice').style.display = 'block';
  }
  if (params.get('expired') === '1') {
    document.getElementById('expired-notice').style.display = 'block';
  }
