from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for, flash, send_from_directory
import firebase_admin
from firebase_admin import credentials, auth
import json
import sqlite3
import os
import math
import hashlib
from datetime import timedelta, datetime, timezone
from ev_yields import get_ev, EV_STAT_LABELS, EV_STAT_COLORS
from pokemon_types import get_types, ALL_TYPES, TYPE_COLORS
from pokemon_sprites import get_sprite
from pokemon_hitboxes import get_height
from pokemon_evochains import get_evo_chain
from pokemon_egg_groups import get_egg_groups  
from biome_mapping import (expand_spawn_biomes, expand_biomes_by_mod, expand_spawn_biomes_filtered,
                           MINECRAFT_TAG_ALIASES,
                           get_mod_color, BIOME_MAP, MOD_COLORS, get_all_real_biomes_sorted,
                           get_tags_for_biome, get_cobblemon_tags_for_fr_biomes, ALL_BIOMES_TO_FR_TAG,
                           FR_TAG_TO_COBBLEMON, FR_TAG_TO_RAW_IDS, get_parent_cobblemon_tags,
                           COBBLEMON_TAG_TO_FR)

app = Flask(__name__)
app.secret_key = "bfcdc97aed922f455ccac7c0af8833b776446cc8b13466187c0b4c6f6ca8ef33"
app.permanent_session_lifetime = timedelta(hours=2)  # Session valide 2 heures
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cobbledex.db")

# Initialisation de Firebase
cred = credentials.Certificate(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tropisole-e9cc2-firebase-adminsdk-fbsvc-f4fb28a221.json"))
firebase_admin.initialize_app(cred)

def generate_hardware_id(client_fingerprint=None):
    """
    Signature de l'appareil.
    - Si le client envoie un fingerprint JS (canvas + GPU + écran + CPU...),
      on l'utilise directement — il est déjà sha256 côté client.
    - Sinon fallback sur User-Agent + Accept-Language (moins fiable).
    Le fingerprint est indépendant du réseau : WiFi ou 4G -> même valeur.
    """
    if client_fingerprint and len(client_fingerprint) >= 16:
        # Re-hash côté serveur pour éviter qu'un attaquant envoie
        # directement le hash volé d'une autre personne.
        return hashlib.sha256(f"cobbledex_v2:{client_fingerprint}".encode()).hexdigest()
    # Fallback legacy
    user_agent = request.headers.get('User-Agent', '')
    accept_lang = request.headers.get('Accept-Language', '')
    return hashlib.sha256(f"{user_agent}{accept_lang}".encode()).hexdigest()

ADMIN_PASSWORD = os.environ.get("COBBLEDEX_ADMIN_PASSWORD", "tropisole_pokesnap")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for col, definition in [
        ("validated",  "INTEGER NOT NULL DEFAULT 0"),
        ("email",      "TEXT"),
        ("username",   "TEXT"),
        ("created_at", "TEXT"),
        ("expires_at", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS patch_notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            version    TEXT NOT NULL,
            title      TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            category   TEXT NOT NULL DEFAULT 'autre',
            content    TEXT NOT NULL,
            page_url   TEXT,
            username   TEXT,
            status     TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            firebase_uid TEXT NOT NULL,
            label        TEXT NOT NULL,
            pokemon_num  INTEGER NOT NULL,
            pokemon_name TEXT NOT NULL,
            biome_name   TEXT NOT NULL,
            mod          TEXT NOT NULL DEFAULT '',
            url_params   TEXT NOT NULL DEFAULT '{}',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

init_db()

@app.route('/static/pokemon_icons/<path:filename>')
def pokemon_icon(filename):
    icons_dir = os.path.join(os.path.dirname(__file__), 'static', 'pokemon_icons')
    return send_from_directory(icons_dir, filename)

@app.before_request
def security_check():
    public = ['/login', '/firebase-auth', '/logout', '/admin', '/admin/validate', '/admin/refuse',
          '/admin/reset-device', '/admin/logout', '/admin/set-expiry',
          '/admin/patchnote/add', '/admin/patchnote/delete', '/patchnotes',
          '/bugreport', '/bugreport/submit']
    if request.path.startswith('/static') or request.path in public:
        return

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    session_fp = session.get('device_fp')  # fingerprint JS mémorisé au moment du login

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT device_id, validated FROM users WHERE firebase_uid = ?", (user_id,))
    row = cursor.fetchone()

    if row:
        device_id, validated = row
        # On compare uniquement si les deux côtés ont un fingerprint JS robuste.
        # Si session_fp est absent (session legacy ou navigateur sans SubtleCrypto),
        # on skip la vérification matérielle — le token Firebase suffit.
        if session_fp and device_id and device_id.strip() and session_fp != device_id:
            conn.close()
            return "🛑 Cet appareil n'est pas autorisé pour ce compte.", 403
        if not validated:
            conn.close()
            session.clear()
            return redirect('/login?pending=1')
        # Vérifier expiration
        cursor.execute("SELECT expires_at FROM users WHERE firebase_uid = ?", (user_id,))
        exp_row = cursor.fetchone()
        if exp_row and exp_row[0]:
            expires_at = datetime.fromisoformat(exp_row[0].replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                conn.close()
                session.clear()
                return redirect('/login?expired=1')
    else:
        conn.close()
        session.clear()
        return redirect('/login')

    conn.close()

# --- LOGIQUE DE CONNEXION ---

@app.route('/firebase-auth', methods=['POST'])
def firebase_auth():
    id_token = request.json.get('idToken')
    username  = (request.json.get('username') or '').strip()
    client_fp = request.json.get('deviceFingerprint', None)
    try:
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=10)
        uid   = decoded_token['uid']
        email = decoded_token.get('email', '')

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT validated FROM users WHERE firebase_uid = ?", (uid,))
        row = cursor.fetchone()

        if row is None:
            device_id = generate_hardware_id(client_fp)
            expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO users (firebase_uid, device_id, email, username, validated, expires_at) VALUES (?, ?, ?, ?, 0, ?)",
                (uid, device_id, email, username, expires_at)
            )
            conn.commit()
            conn.close()
            return {"status": "pending", "message": "Votre compte est en attente de validation par un administrateur."}, 202

        validated = row[0]

        if not validated:
            conn.close()
            return {"status": "pending", "message": "Votre compte est en attente de validation par un administrateur."}, 202

        # Récupérer le device_id enregistré en DB
        cursor.execute("SELECT device_id FROM users WHERE firebase_uid = ?", (uid,))
        device_row = cursor.fetchone()
        stored_device_id = device_row[0] if device_row else None

        if client_fp:
            incoming_device_id = generate_hardware_id(client_fp)
            if not stored_device_id:
                # Compte legacy sans device_id → on l'enregistre une seule fois, puis verrouillé
                cursor.execute("UPDATE users SET device_id = ? WHERE firebase_uid = ?", (incoming_device_id, uid))
                conn.commit()
                stored_device_id = incoming_device_id
            elif incoming_device_id != stored_device_id:
                conn.close()
                return {"status": "error", "message": "Cet appareil n'est pas autorisé pour ce compte."}, 403

        conn.close()

        session.permanent = True
        session['user_id'] = uid
        session['email']   = email
        if client_fp:
            session['device_fp'] = stored_device_id
        return {"status": "success"}, 200

    except Exception as e:
        return {"status": "error", "message": str(e)}, 401

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

BUCKET_ORDER = {"filler": 1, "common": 2, "uncommon": 3, "rare": 4, "ultra-rare": 5}
BUCKET_FR = {
    "filler": "Fillers",
    "common": "Commun",
    "uncommon": "Peu commun",
    "rare": "Rare",
    "ultra-rare": "Ultra-rare",
    None: "—"
}
TIME_FR = {
    "day":    "Jour",
    "night":  "Nuit",
    "dusk":   "Crépuscule",
    None:     "—"
}
WEATHER_FR = {
    "rain":  "Pluie",
    "clear": "Ensoleillé",
    None:    "—"
}

def parse_conditions(conditions_str):
    """Parse the conditions JSON string into a structured dict."""
    if not conditions_str:
        return {}
    try:
        return json.loads(conditions_str)
    except Exception:
        return {}

STRUCTURE_NAMES_FR = {
    "minecraft:shipwreck":          ("🚢", "Épave"),
    "#minecraft:shipwreck":         ("🚢", "Épave"),
    "minecraft:village":            ("🏘️", "Village"),
    "#minecraft:village":           ("🏘️", "Village"),
    "minecraft:pillager_outpost":   ("🗼", "Avant-poste pillard"),
    "minecraft:ocean_monument":     ("🏛️", "Monument océanique"),
    "minecraft:ocean_ruin":         ("🏚️", "Ruines océaniques"),
    "minecraft:stronghold":         ("🏰", "Forteresse"),
    "minecraft:mineshaft":          ("⛏️", "Mineshaft"),
    "minecraft:jungle_pyramid":     ("🛕", "Temple jungle"),
    "minecraft:desert_pyramid":     ("🏜️", "Pyramide désert"),
    "minecraft:igloo":              ("🏔️", "Igloo"),
    "minecraft:woodland_mansion":   ("🏚️", "Manoir forestier"),
    "minecraft:nether_fortress":    ("🔥", "Forteresse Nether"),
    "minecraft:nether_fossil":      ("🦴", "Fossile Nether"),
    "minecraft:bastion_remnant":    ("🏯", "Vestige bastion"),
    "minecraft:end_city":           ("🌆", "Cité de l'End"),
    "minecraft:buried_treasure":    ("💎", "Trésor enfoui"),
    "minecraft:swamp_hut":          ("🧙", "Cabane sorcière"),
    "minecraft:ruined_portal":      ("🌀", "Portail en ruine"),
    "minecraft:ancient_city":       ("🏛️", "Cité ancienne"),
    "minecraft:trail_ruins":        ("🪨", "Ruines de piste"),
    "minecraft:trial_chambers":     ("⚔️", "Chambres d'épreuve"),
    "cobblemon:shrine":             ("⛩️", "Sanctuaire"),
    "cobblemon:fossil_site":        ("🦴", "Site fossile"),
}

def _structure_label(sid):
    if sid in STRUCTURE_NAMES_FR:
        return STRUCTURE_NAMES_FR[sid]
    clean = sid.replace("minecraft:", "").replace("cobblemon:", "").replace("_", " ").title()
    return ("🏗️", clean)

def _parse_structures(raw):
    """Parse structure JSON (string/list/dict) → list of string IDs."""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, list):
        ids = []
        for item in raw:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                sid = item.get("identifier") or item.get("id") or item.get("structure")
                if sid:
                    ids.append(sid)
        return ids
    if isinstance(raw, dict):
        sid = raw.get("identifier") or raw.get("id")
        return [sid] if sid else []
    return []

def _clean_block(b):
    return (b.replace("minecraft:", "").replace("cobblemon:", "")
             .replace("#cobblemon:", "").replace("#minecraft:", "")
             .replace("#", "").replace("_", " ").strip())

MOON_PHASE_FR = {
    0: "Pleine lune", 1: "Lune décroissante", 2: "Dernier quartier",
    3: "Lune gibbeuse décroissante", 4: "Nouvelle lune",
    5: "Lune gibbeuse croissante", 6: "Premier quartier", 7: "Lune croissante",
}

# Formes régionales reconnues → label FR + couleur badge
FORME_REGIONALE = {
    "alolan":   {"label": "Forme d'Alola",   "short": "Alola",   "color": "#00b4d8"},
    "galarian": {"label": "Forme de Galar",   "short": "Galar",   "color": "#9b5de5"},
    "hisuian":  {"label": "Forme de Hisui",   "short": "Hisui",   "color": "#e9c46a"},
    "paldean":  {"label": "Forme de Paldea",  "short": "Paldea",  "color": "#f4a261"},
    "valencian":{"label": "Forme Valenciana", "short": "Valencia","color": "#2dc653"},
}

def get_forme_regionale(forme_str):
    """Retourne le dict FORME_REGIONALE si la forme est régionale, sinon None."""
    if not forme_str:
        return None
    key = forme_str.strip().lower().split()[0].split("=")[0]
    return FORME_REGIONALE.get(key)

def _make_condition_tags(cond, structures_raw, spawn_dict):
    """Génère la liste complète des tags de condition à partir du dict parsé."""
    tags = []

    # ── Y level ──────────────────────────────────────────────────────────────
    y_min = spawn_dict.get("y_min")
    y_max = spawn_dict.get("y_max")
    if y_max is not None and y_max <= 0:
        tags.append({"icon": "⛏️", "label": f"Sous terre (Y ≤ {y_max})", "type": "depth"})
    elif y_min is not None and y_min > 50:
        tags.append({"icon": "🏔️", "label": f"En hauteur (Y ≥ {y_min})", "type": "height"})
    elif y_min is not None or y_max is not None:
        lo = y_min if y_min is not None else "?"
        hi = y_max if y_max is not None else "?"
        tags.append({"icon": "📍", "label": f"Y : {lo} → {hi}", "type": "y_range"})

    # ── Ciel / Lumière ────────────────────────────────────────────────────────
    # canSeeSky vient de la colonne peut_voir_ciel (déjà dans spawn_dict)
    sky = spawn_dict.get("peut_voir_ciel")
    if sky == "true":
        tags.append({"icon": "☀️", "label": "Doit voir le ciel", "type": "sky"})
    elif sky == "false":
        tags.append({"icon": "🏠", "label": "Ne doit PAS voir le ciel", "type": "no_sky"})

    lmin = spawn_dict.get("lumiere_min")
    lmax = spawn_dict.get("lumiere_max")
    if lmin is not None or lmax is not None:
        lo = int(lmin) if lmin is not None else "?"
        hi = int(lmax) if lmax is not None else "?"
        if lmax is not None and lmax <= 7:
            tags.append({"icon": "🌑", "label": f"Obscurité (lumière {lo}–{hi})", "type": "dark"})
        elif lmin is not None and lmin >= 8:
            tags.append({"icon": "🌕", "label": f"Lumineux (lumière {lo}–{hi})", "type": "bright"})
        else:
            tags.append({"icon": "🌗", "label": f"Lumière {lo}–{hi}", "type": "light"})

    max_light = cond.get("maxLight")
    if max_light is not None:
        tags.append({"icon": "🌑", "label": f"Lumière bloc ≤ {max_light}", "type": "dark"})

    # ── Météo (dans conditions JSON pour les anticond, pas besoin ici car colonne) ──
    # isRaining dans la colonne `weather` mais peut aussi être dans conditions
    is_raining = cond.get("isRaining")
    if is_raining is True:
        tags.append({"icon": "🌧️", "label": "Pluie requise", "type": "weather_rain"})
    elif is_raining is False:
        tags.append({"icon": "🌤️", "label": "Beau temps requis", "type": "weather_clear"})

    # ── Blocs à proximité ─────────────────────────────────────────────────────
    blocks = cond.get("neededNearbyBlocks", [])
    water_blocks = {"minecraft:water", "minecraft:water_source"}
    if blocks:
        if any(b in water_blocks for b in blocks):
            tags.append({"icon": "🌊", "label": "Eau à proximité requise", "type": "water"})
        else:
            clean = [_clean_block(b) for b in blocks[:3]]
            tags.append({"icon": "🧱", "label": f"Blocs requis : {', '.join(clean)}", "type": "block"})

    # ── Sol ───────────────────────────────────────────────────────────────────
    base_blocks = cond.get("neededBaseBlocks", [])
    if base_blocks:
        clean = [_clean_block(b) for b in base_blocks[:3]]
        tags.append({"icon": "🪨", "label": f"Sol requis : {', '.join(clean)}", "type": "base_block"})

    # ── Slime chunk ───────────────────────────────────────────────────────────
    if cond.get("isSlimeChunk"):
        tags.append({"icon": "🟩", "label": "Chunk à Slime requis", "type": "slime"})

    # ── Pêche ─────────────────────────────────────────────────────────────────
    rod_type = cond.get("rodType")
    if rod_type:
        rod_name = rod_type.replace("cobblemon:", "").replace("_rod", " rod").replace("_", " ")
        tags.append({"icon": "🎣", "label": f"Canne : {rod_name}", "type": "fishing"})
    elif cond.get("minLureLevel") is not None:
        tags.append({"icon": "🎣", "label": f"Leurre Niv.{cond['minLureLevel']}+", "type": "fishing"})

    bait = cond.get("bait")
    if bait:
        bait_name = bait.replace("cobblemon:", "").replace("_", " ")
        tags.append({"icon": "🪱", "label": f"Appât : {bait_name}", "type": "bait"})

    # ── Lune ─────────────────────────────────────────────────────────────────
    moon = cond.get("moonPhase")
    if moon is not None:
        moon_name = MOON_PHASE_FR.get(int(moon), f"Phase {moon}")
        tags.append({"icon": "🌙", "label": f"Lune : {moon_name}", "type": "moon"})
    # Aussi depuis la colonne `lune`
    lune_col = spawn_dict.get("lune")
    if lune_col and moon is None:
        phases = [p.strip() for p in str(lune_col).split(",") if p.strip()]
        if len(phases) == 1:
            moon_name = MOON_PHASE_FR.get(int(phases[0]), f"Phase {phases[0]}")
            tags.append({"icon": "🌙", "label": f"Lune : {moon_name}", "type": "moon"})
        else:
            names = [MOON_PHASE_FR.get(int(p), f"Phase {p}") for p in phases]
            tags.append({"icon": "🌙", "label": f"Lune : {', '.join(names)}", "type": "moon"})

    # ── Zone X ───────────────────────────────────────────────────────────────
    min_x = cond.get("minX")
    max_x = cond.get("maxX")
    if min_x == 0 and max_x == 0:
        tags.append({"icon": "🗺️", "label": "Centre du monde uniquement", "type": "x_zone"})
    elif min_x is not None or max_x is not None:
        lo = min_x if min_x is not None else "?"
        hi = max_x if max_x is not None else "?"
        tags.append({"icon": "🗺️", "label": f"Zone X : {lo} → {hi}", "type": "x_zone"})

    # ── Structures requises ───────────────────────────────────────────────────
    for sid in _parse_structures(structures_raw):
        icon, label_fr = _structure_label(sid)
        tags.append({"icon": icon, "label": f"Structure : {label_fr}", "type": "structure"})

    return tags


def _make_anticondition_tags(anticond, structures_exclu_raw):
    """Génère la liste complète des tags d'anti-condition."""
    tags = []

    # ── Y exclu ───────────────────────────────────────────────────────────────
    ay_min = anticond.get("minY")
    ay_max = anticond.get("maxY")
    if ay_min is not None or ay_max is not None:
        lo = ay_min if ay_min is not None else "?"
        hi = ay_max if ay_max is not None else "?"
        tags.append({"icon": "🚫", "label": f"Y exclu : {lo} → {hi}", "type": "anti_y"})

    # ── Ciel / Lumière exclu ──────────────────────────────────────────────────
    asky = anticond.get("canSeeSky")
    if asky is True:
        tags.append({"icon": "🚫", "label": "Pas de ciel visible", "type": "anti_sky"})
    elif asky is False:
        tags.append({"icon": "🚫", "label": "Doit être à ciel ouvert (anticond)", "type": "anti_sky"})

    almin = anticond.get("minSkyLight")
    almax = anticond.get("maxSkyLight")
    if almin is not None or almax is not None:
        lo = int(almin) if almin is not None else "?"
        hi = int(almax) if almax is not None else "?"
        tags.append({"icon": "🚫", "label": f"Lumière exclue : {lo}–{hi}", "type": "anti_light"})

    aml = anticond.get("maxLight")
    if aml is not None:
        tags.append({"icon": "🚫", "label": f"Lumière bloc > {aml} requis", "type": "anti_light"})

    # ── Météo exclue ──────────────────────────────────────────────────────────
    ais_raining = anticond.get("isRaining")
    if ais_raining is True:
        tags.append({"icon": "🚫", "label": "Pas de pluie", "type": "anti_weather"})
    elif ais_raining is False:
        tags.append({"icon": "🚫", "label": "Pas de beau temps", "type": "anti_weather"})

    # ── Blocs interdits à proximité ───────────────────────────────────────────
    ablocks = anticond.get("neededNearbyBlocks", [])
    water_blocks = {"minecraft:water", "minecraft:water_source"}
    if ablocks:
        if any(b in water_blocks for b in ablocks):
            tags.append({"icon": "🚫", "label": "Pas d'eau à proximité", "type": "anti_water"})
        else:
            clean = [_clean_block(b) for b in ablocks[:3]]
            tags.append({"icon": "🚫", "label": f"Blocs interdits : {', '.join(clean)}", "type": "anti_block"})

    # ── Sol interdit ──────────────────────────────────────────────────────────
    abase = anticond.get("neededBaseBlocks", [])
    if abase:
        clean = [_clean_block(b) for b in abase[:3]]
        tags.append({"icon": "🚫", "label": f"Sol interdit : {', '.join(clean)}", "type": "anti_base"})

    # ── Slime chunk exclu ─────────────────────────────────────────────────────
    if anticond.get("isSlimeChunk"):
        tags.append({"icon": "🚫", "label": "Pas dans chunk à Slime", "type": "anti_slime"})

    # ── Lune exclue ───────────────────────────────────────────────────────────
    amoon = anticond.get("moonPhase")
    if amoon is not None:
        moon_name = MOON_PHASE_FR.get(int(amoon), f"Phase {amoon}")
        tags.append({"icon": "🚫", "label": f"Lune exclue : {moon_name}", "type": "anti_moon"})

    # ── Zone X exclue ─────────────────────────────────────────────────────────
    amin_x = anticond.get("minX")
    amax_x = anticond.get("maxX")
    if amin_x is not None or amax_x is not None:
        lo = amin_x if amin_x is not None else "?"
        hi = amax_x if amax_x is not None else "?"
        tags.append({"icon": "🚫", "label": f"Zone X exclue : {lo} → {hi}", "type": "anti_x"})

    # ── Structures exclues ────────────────────────────────────────────────────
    for sid in _parse_structures(structures_exclu_raw):
        _, label_fr = _structure_label(sid)
        tags.append({"icon": "🚫", "label": f"Hors structure : {label_fr}", "type": "no_structure"})

    return tags


def enrich_spawn_conditions(spawn_dict):
    """Add parsed condition fields to a spawn dict for easy template use."""
    cond = parse_conditions(spawn_dict.get("conditions"))
    anticond = parse_conditions(spawn_dict.get("anticonditions"))
    spawn_dict["cond_parsed"] = cond
    spawn_dict["anticond_parsed"] = anticond
    if "y_min" not in spawn_dict:
        spawn_dict["y_min"] = cond.get("minY")
    if "y_max" not in spawn_dict:
        spawn_dict["y_max"] = cond.get("maxY")
    spawn_dict["needed_blocks"] = cond.get("neededNearbyBlocks", [])
    spawn_dict["base_blocks"] = cond.get("neededBaseBlocks", [])
    spawn_dict["min_lure"] = cond.get("minLureLevel")
    spawn_dict["rod_type"] = cond.get("rodType")
    spawn_dict["bait"] = cond.get("bait")
    spawn_dict["is_slime_chunk"] = cond.get("isSlimeChunk", False)
    spawn_dict["condition_tags"] = _make_condition_tags(cond, spawn_dict.get("structures"), spawn_dict)
    spawn_dict["anticondition_tags"] = _make_anticondition_tags(anticond, spawn_dict.get("structures_exclu"))
    return spawn_dict


def _build_spawn_list(filtered_rows):
    """Une ligne DB = une entrée de spawn dans la liste (pas d'agrégation)."""
    ev_cache = {}
    pokemon_list = []
    for r in filtered_rows:
        p = dict(r)
        cond = parse_conditions(p.get("conditions"))
        p["y_min"] = cond.get("minY")
        p["y_max"] = cond.get("maxY")
        p["contextes"] = [p["contexte"]] if p.get("contexte") else []
        # times = [] signifie "spawn toujours" (pas de contrainte horaire)
        p["times"]     = [p["time"]]     if p.get("time")     else []
        # weathers = [] signifie "toute météo"
        p["weathers"]  = [p["weather"]]  if p.get("weather")  else []
        lmin = p.get("lumiere_min")
        lmax = p.get("lumiere_max")
        sky  = p.get("peut_voir_ciel")
        if lmin is not None or lmax is not None or (sky and sky not in ("any", None)):
            p["lumiere_profils"] = [(lmin, lmax, sky)]
        else:
            p["lumiere_profils"] = []
        enrich_spawn_conditions(p)
        raw_presets = p.get("presets") or ""
        p["presets_list"] = [pr.strip() for pr in raw_presets.split(",") if pr.strip()]
        p["forme_regionale"] = get_forme_regionale(p.get("forme"))
        num = p["numero"]
        if num not in ev_cache:
            ev = get_ev(num)
            parts = []
            for stat in ["hp","atk","def","spa","spd","spe"]:
                if ev[stat] > 0:
                    parts.append(f"{ev[stat]} {EV_STAT_LABELS[stat]}")
            ev_cache[num] = (ev, " + ".join(parts) if parts else "—")
        p["ev"], p["ev_str"] = ev_cache[num]
        p["ev_total"] = p["ev"]["total"]
        p["types"] = get_types(num)
        p["egg_groups"] = get_egg_groups(num)
        p["sprite"] = get_sprite(num, p.get("forme"))
        h = get_height(num, p.get("forme"))
        p["hitbox_height"] = round(h, 3) if h else None
        pokemon_list.append(p)
    pokemon_list.sort(key=lambda x: (-x["ev_total"], x["numero"]))
    return pokemon_list


@app.route("/")
def index():
    conn = get_db()

    buckets = [r[0] for r in conn.execute(
        "SELECT DISTINCT bucket FROM pokemon_spawns WHERE bucket IS NOT NULL ORDER BY bucket"
    ).fetchall()]
    times = [r[0] for r in conn.execute(
        "SELECT DISTINCT time FROM pokemon_spawns WHERE time IS NOT NULL ORDER BY time"
    ).fetchall()]
    weathers = [r[0] for r in conn.execute(
        "SELECT DISTINCT weather FROM pokemon_spawns WHERE weather IS NOT NULL ORDER BY weather"
    ).fetchall()]
    conn.close()

    all_biome_tags = sorted(BIOME_MAP.keys())

    # Grandes catégories thématiques → liste de tags Cobblemon
    BIOME_CATEGORIES = {
        "❄️ Froid & Neige": ["Froid", "Glacial", "Glaciaire", "Forêt enneigée", "Enneigé", "Plage enneigée", "Océan gelé", "Toundra", "Hiver"],
        "🏔️ Montagnes & Sommets": ["Montagne", "Sommet", "Hautes terres", "Collines", "Plateau"],
        "🌲 Forêts": ["Forêt", "Forêt enneigée", "Taïga", "Dense", "Bambou", "Fleurs de cerisier"],
        "🌿 Plaines & Prairies": ["Prairie", "Plaines", "Floral", "Printemps", "Été", "Automne", "Clairsemé"],
        "🏜️ Aride & Désert": ["Désert", "Aride", "Terres arides", "Sableux", "Savane"],
        "🌊 Océans & Côtes": ["Océan", "Grand océan", "Océan tiède", "Océan chaud", "Océan gelé", "Côte", "Plage", "Île", "Île tropicale"],
        "🌴 Jungle & Tropical": ["Jungle", "Luxuriant", "Île tropicale", "Chaud"],
        "🌾 Zones humides": ["Marais", "Boueux", "Eau douce", "Rivière", "Thermal"],
        "🍄 Spéciaux": ["Champignon", "Champs de champignons", "Magique", "Effrayant", "Sel", "Volcanique", "Stalactites", "Ciel"],
        "🕳️ Souterrain": ["Grotte", "Abysses sombres"],
        "🔥 Nether": ["Nether", "Nether basaltique", "Nether cramoisi", "Désert du Nether", "Forêt du Nether", "Nether gelé", "Nether fongique", "Montagne du Nether", "Végétation du Nether", "Quartz du Nether", "Nether feu de l'Âme", "Nether sable de l'Âme", "Nether toxique", "Nether distordu", "Terres dévastées du Nether"],
        "🌌 End & Autres": ["Fin", "Éther", "Bumblezone", "Canyon de cristal", "Prairie fleurie", "Champs pollinisés", "Constructions hurlantes"],
    }

    # Pour chaque catégorie, collecter tous les biomes réels uniques
    biomes_by_category = {}
    for cat_name, tags in BIOME_CATEGORIES.items():
        seen = set()
        biomes = []
        for tag in tags:
            if tag not in BIOME_MAP:
                continue
            for entry in BIOME_MAP[tag]:
                b = entry["biome"]
                if b not in seen and not b.startswith("All "):
                    seen.add(b)
                    biomes.append(b)
        if biomes:
            biomes_by_category[cat_name] = sorted(biomes)

    # Récupérer expires_at de l'utilisateur connecté
    user_expires_at = None
    user_id = session.get('user_id')
    if user_id:
        conn2 = sqlite3.connect(DB_PATH)
        row_exp = conn2.execute("SELECT expires_at FROM users WHERE firebase_uid = ?", (user_id,)).fetchone()
        conn2.close()
        if row_exp and row_exp[0]:
            user_expires_at = row_exp[0][:10]  # juste la date YYYY-MM-DD

    return render_template("index.html",
                           buckets=buckets,
                           biomes_by_category=biomes_by_category,
                           bucket_fr=BUCKET_FR,
                           all_types=ALL_TYPES,
                           type_colors=TYPE_COLORS,
                           user_expires_at=user_expires_at)

@app.route("/api/pokemon")
def api_pokemon():
    search      = request.args.get("q", "").strip()
    bucket      = request.args.get("bucket", "")
    type_filter = request.args.get("type", "")
    sort        = request.args.get("sort", "numero")
    order       = request.args.get("order", "asc")
    page        = int(request.args.get("page", 1))
    per_page    = int(request.args.get("per_page", 40))

    conn = get_db()

    where_clauses = []
    params = []

    if bucket:
        where_clauses.append("bucket = ?")
        params.append(bucket)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Get one representative row per pokemon
    allowed_sorts = {"numero": "numero", "pokemon": "pokemon", "bucket": "bucket",
                     "niveau_min": "niveau_min", "poids": "poids"}
    sort_col = allowed_sorts.get(sort, "numero")
    order_dir = "ASC" if order == "asc" else "DESC"

    # Subquery: pick one row per (numero, pokemon) combo
    base_query = f"""
        SELECT numero, pokemon,
               MAX(niveau_min) as niveau_min, MAX(niveau_max) as niveau_max,
               GROUP_CONCAT(DISTINCT bucket) as bucket,
               GROUP_CONCAT(DISTINCT time) as time,
               COUNT(*) as nb_entrees
        FROM pokemon_spawns
        {where_sql}
        GROUP BY numero, pokemon
        ORDER BY {sort_col} {order_dir}
    """

    all_rows = conn.execute(base_query, params).fetchall()
    conn.close()

    # Filtre par nom insensible à la casse ET aux accents
    if search:
        import unicodedata
        def normalize(s):
            return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()
        needle = normalize(search)
        all_rows = [r for r in all_rows if needle in normalize(r["pokemon"])]

    # Filtre par type en Python (les types ne sont pas en BDD)
    if type_filter:
        all_rows = [r for r in all_rows if type_filter in get_types(r["numero"])]

    total = len(all_rows)
    offset = (page - 1) * per_page
    rows = all_rows[offset: offset + per_page]

    result = []
    for r in rows:
        bucket_val = r["bucket"].split(",")[0] if r["bucket"] else None
        result.append({
            "numero": r["numero"],
            "pokemon": r["pokemon"],
            "bucket": bucket_val,
            "bucket_fr": BUCKET_FR.get(bucket_val, bucket_val),
            "niveau_min": r["niveau_min"],
            "niveau_max": r["niveau_max"],
            "nb_entrees": r["nb_entrees"],
            "types": get_types(r["numero"]),
            "sprite": get_sprite(r["numero"]),
        })

    return jsonify({
        "data": result,
        "total": total,
        "page": page,
        "pages": math.ceil(total / per_page),
        "per_page": per_page,
    })

def _biome_spawn_counts(biome_names):
    """
    Retourne {biome_name: nb_lignes_spawn_actives} pour une liste de biomes réels.
    Utilise le même matching tag que l'oracle.
    """
    if not biome_names:
        return {}
    real_biome_map, _ = _oracle_build_real_biome_map()
    conn = get_db()
    rows = conn.execute(
        "SELECT biomes_tags, biomes_exclus_tags FROM pokemon_spawns WHERE est_actif = 1"
    ).fetchall()
    conn.close()

    # Pré-parser les sets de tags une seule fois
    spawn_tag_sets = [
        (
            frozenset(t.strip() for t in (r[0] or '').split(',') if t.strip()),
            frozenset(t.strip() for t in (r[1] or '').split(',') if t.strip()),
        )
        for r in rows
    ]

    counts = {}
    for bname in biome_names:
        all_tags = real_biome_map.get(bname)
        if not all_tags:
            counts[bname] = 0
            continue
        count = sum(
            1 for tag_set, excl_set in spawn_tag_sets
            if all_tags & tag_set and not (all_tags & excl_set)
        )
        counts[bname] = count
    return counts


@app.route("/pokemon/<int:numero>")
def pokemon_detail(numero):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM pokemon_spawns WHERE numero = ? ORDER BY entree",
        (numero,)
    ).fetchall()
    conn.close()

    if not rows:
        abort(404)

    spawns = [dict(r) for r in rows]
    name = spawns[0]["pokemon"]

    # Expand each spawn's biomes into individual real biomes (flat + grouped by mod)
    for s in spawns:
        excl = s.get("biomes_exclus") or None
        s["biomes_expanded"] = expand_spawn_biomes_filtered(s["biomes"], excl)
        s["biomes_exclus_expanded"] = expand_spawn_biomes(s["biomes_exclus"])
        s["biomes_by_mod"] = expand_biomes_by_mod(s["biomes"], excl)
        s["biomes_exclus_by_mod"] = expand_biomes_by_mod(s["biomes_exclus"])
        s["forme_regionale"] = get_forme_regionale(s.get("forme"))
        enrich_spawn_conditions(s)

    # Previous / next
    conn = get_db()
    prev_row = conn.execute(
        "SELECT DISTINCT numero FROM pokemon_spawns WHERE numero < ? ORDER BY numero DESC LIMIT 1",
        (numero,)
    ).fetchone()
    next_row = conn.execute(
        "SELECT DISTINCT numero FROM pokemon_spawns WHERE numero > ? ORDER BY numero ASC LIMIT 1",
        (numero,)
    ).fetchone()
    conn.close()

    # Sprite : on prend la forme de la première entrée de spawn
    first_forme = spawns[0].get("forme") if spawns else None
    sprite_file = get_sprite(numero, first_forme)
    sprite_url  = f"/static/pokemon_icons/{sprite_file}" if sprite_file else None

    # Collecter tous les biomes réels affichés pour calculer leurs counts
    all_real_biomes = set()
    for s in spawns:
        for group in s.get('biomes_by_mod', []):
            for mod, blist in group['by_mod'].items():
                for b in blist:
                    if not b.startswith('All '):
                        all_real_biomes.add(b)
    biome_spawn_counts = _biome_spawn_counts(all_real_biomes)

    return render_template("detail.html",
                           name=name,
                           numero=numero,
                           spawns=spawns,
                           sprite_url=sprite_url,
                           prev_num=prev_row[0] if prev_row else None,
                           next_num=next_row[0] if next_row else None,
                           bucket_fr=BUCKET_FR,
                           time_fr=TIME_FR,
                           weather_fr=WEATHER_FR,
                           mod_colors=MOD_COLORS,
                           get_mod_color=get_mod_color,
                           all_biomes_to_fr=ALL_BIOMES_TO_FR_TAG,
                           all_types=ALL_TYPES,
                           type_colors=TYPE_COLORS,
                           biome_spawn_counts=biome_spawn_counts)

@app.route("/spawns/biome")
def spawns_by_biome():
    """Page listant tous les Pokémon qui partagent les mêmes biomes, triés par EVs lâchés."""
    biomes_param = request.args.get("biomes", "")
    source_num = request.args.get("from", type=int)
    source_entry = request.args.get("entry", type=int)

    if not biomes_param:
        abort(400)

    biomes_list = [b.strip() for b in biomes_param.split(",") if b.strip()]
    conn = get_db()

    source_pokemon = None
    if source_num:
        row = conn.execute(
            "SELECT * FROM pokemon_spawns WHERE numero=? AND entree=?",
            (source_num, source_entry or 1)
        ).fetchone()
        if not row:
            row = conn.execute("SELECT * FROM pokemon_spawns WHERE numero=?", (source_num,)).fetchone()
        if row:
            source_pokemon = dict(row)

    cobblemon_tags = get_cobblemon_tags_for_fr_biomes(biomes_list)
    # Ajouter les raw IDs (ex: aether:skyroot_forest, minecraft:frozen_river)
    # qui correspondent aux mêmes tags FR mais ne sont pas des tags cobblemon
    raw_ids = set()
    for fr_tag in biomes_list:
        raw_ids |= set(FR_TAG_TO_RAW_IDS.get(fr_tag, []))
    all_ids = cobblemon_tags | raw_ids
    if all_ids:
        # On entoure le champ avec des virgules pour éviter les faux positifs de substring
        # (ex: is_cold ne doit pas matcher is_cold_ocean)
        where_parts = " OR ".join(
            ["(',' || biomes_tags || ',') LIKE ?" for _ in all_ids]
        )
        params = [f"%,{t},%" for t in all_ids]
    else:
        where_parts = " OR ".join(["biomes LIKE ?" for _ in biomes_list])
        params = [f"%{b}%" for b in biomes_list]

    rows = conn.execute(f"""
        SELECT numero, pokemon, forme, bucket, poids, niveau_min, niveau_max, biomes, biomes_exclus,
               biomes_exclus_tags, time, weather, contexte, lumiere_min, lumiere_max,
               peut_voir_ciel, conditions, anticonditions, lune, structures, structures_exclu,
               presets
        FROM pokemon_spawns
        WHERE {where_parts}
        ORDER BY numero, entree
    """, params).fetchall()
    conn.close()

    def is_excluded_by_biomes(row, searched_tags, searched_biomes_fr):
        # Découpe en ensembles pour éviter les faux positifs de substring
        excl_tags_set = {t.strip() for t in (row["biomes_exclus_tags"] or "").split(",") if t.strip()}
        excl_fr_set   = {b.strip() for b in (row["biomes_exclus"] or "").split(",") if b.strip()}
        for tag in searched_tags:
            if tag and tag in excl_tags_set:
                return True
        for bio in searched_biomes_fr:
            if bio and bio in excl_fr_set:
                return True

        # Les Pokémon avec structure requise sont affichés avec leur tag condition
        # (ex: "⛩️ Structure : Temple jungle") — on ne les masque plus.
        return False

    filtered_rows = [r for r in rows if not is_excluded_by_biomes(r, cobblemon_tags, biomes_list)]
    pokemon_list = _build_spawn_list(filtered_rows)

    return render_template("biome_spawns.html",
                           biomes=biomes_list,
                           biomes_expanded=expand_spawn_biomes(biomes_param),
                           pokemon_list=pokemon_list,
                           source_pokemon=source_pokemon,
                           bucket_fr=BUCKET_FR,
                           time_fr=TIME_FR,
                           ev_stat_labels=EV_STAT_LABELS,
                           ev_stat_colors=EV_STAT_COLORS,
                           mod_colors=MOD_COLORS,
                           get_mod_color=get_mod_color,
                           all_biomes_to_fr=ALL_BIOMES_TO_FR_TAG,
                           all_types=ALL_TYPES,
                           type_colors=TYPE_COLORS)

@app.route("/spawns/biome-reel")
def spawns_by_real_biome():
    real_biome = request.args.get("biome", "").strip()
    mod = request.args.get("mod", "").strip()
    source_num = request.args.get("from", type=int)
    source_entry = request.args.get("entry", type=int)

    if not real_biome:
        abort(400)

    tags_fr = get_tags_for_biome(real_biome)
    if not tags_fr:
        tags_fr = [real_biome]

    conn = get_db()

    source_pokemon = None
    if source_num:
        row = conn.execute(
            "SELECT * FROM pokemon_spawns WHERE numero=? AND entree=?",
            (source_num, source_entry or 1)
        ).fetchone()
        if not row:
            row = conn.execute("SELECT * FROM pokemon_spawns WHERE numero=?", (source_num,)).fetchone()
        if row:
            source_pokemon = dict(row)

    # Pour un biome réel précis : tags directs + leurs parents (is_lush → is_cave → is_overworld)
    # mais PAS les enfants. Sans les parents, les Pokémon avec des tags larges (is_overworld)
    # n'apparaissent pas. Sans les enfants, on évite les faux positifs (Nether Wastes → is_nether
    # → is_frozen → Stalgamin qui ne spawn qu'en Nether gelé).
    cobblemon_tags_reel = set()
    for fr_tag in tags_fr:
        cobblemon_tag = FR_TAG_TO_COBBLEMON.get(fr_tag)
        if cobblemon_tag:
            cobblemon_tags_reel.add(cobblemon_tag)
            cobblemon_tags_reel |= get_parent_cobblemon_tags(cobblemon_tag)
            # Inclure les aliases Minecraft natifs (ex: #minecraft:is_nether)
            for mc_alias, cob_tag in MINECRAFT_TAG_ALIASES.items():
                if cob_tag == cobblemon_tag:
                    cobblemon_tags_reel.add(mc_alias)

    # Dériver l'ID Minecraft littéral (ex: "Frozen River" → "minecraft:frozen_river")
    # pour trouver les Pokémon qui l'ont en dur dans leurs biomes_tags
    minecraft_id = "minecraft:" + real_biome.lower().replace(" ", "_")

    if cobblemon_tags_reel:
        # On entoure le champ avec des virgules pour éviter les faux positifs de substring
        # (ex: is_cold ne doit pas matcher is_cold_ocean)
        tag_conditions = " OR ".join(
            ["(',' || biomes_tags || ',') LIKE ?" for _ in cobblemon_tags_reel]
        )
        params = [f"%,{t},%" for t in cobblemon_tags_reel]
        # On cherche aussi l'ID littéral minecraft au cas où il est présent directement
        where_parts = f"({tag_conditions}) OR (',' || biomes_tags || ',') LIKE ?"
        params.append(f"%,{minecraft_id},%")
    else:
        where_parts = " OR ".join(["biomes LIKE ?" for _ in tags_fr])
        params = [f"%{t}%" for t in tags_fr]

    rows = conn.execute(f"""
        SELECT numero, pokemon, forme, bucket, poids, niveau_min, niveau_max, biomes, biomes_exclus,
               biomes_exclus_tags, biomes_tags, time, weather, contexte, lumiere_min, lumiere_max,
               peut_voir_ciel, conditions, anticonditions, lune, structures, structures_exclu,
               presets
        FROM pokemon_spawns
        WHERE {where_parts}
        ORDER BY numero, entree
    """, params).fetchall()
    conn.close()

    def is_excluded_by_biomes(row, searched_tags, searched_biomes_fr):
        # Découpe en ensembles pour éviter les faux positifs de substring
        excl_tags_set = {t.strip() for t in (row["biomes_exclus_tags"] or "").split(",") if t.strip()}
        excl_fr_set   = {b.strip() for b in (row["biomes_exclus"] or "").split(",") if b.strip()}
        for tag in searched_tags:
            if tag and tag in excl_tags_set:
                return True
        for bio in searched_biomes_fr:
            if bio and bio in excl_fr_set:
                return True

        # Les Pokémon avec structure requise sont affichés avec leur tag condition
        # (ex: "⛩️ Structure : Temple jungle") — on ne les masque plus.
        return False

    filtered_rows = [r for r in rows if not is_excluded_by_biomes(r, cobblemon_tags_reel, tags_fr)]
    pokemon_list = _build_spawn_list(filtered_rows)

    return render_template("biome_spawns.html",
                           biomes=tags_fr,
                           biomes_expanded=expand_spawn_biomes(",".join(tags_fr)),
                           real_biome_name=real_biome,
                           real_biome_mod=mod,
                           pokemon_list=pokemon_list,
                           source_pokemon=source_pokemon,
                           bucket_fr=BUCKET_FR,
                           time_fr=TIME_FR,
                           ev_stat_labels=EV_STAT_LABELS,
                           ev_stat_colors=EV_STAT_COLORS,
                           mod_colors=MOD_COLORS,
                           get_mod_color=get_mod_color,
                           all_biomes_to_fr=ALL_BIOMES_TO_FR_TAG,
                           all_types=ALL_TYPES,
                           type_colors=TYPE_COLORS)


@app.route("/api/stats")
def api_stats():
    conn = get_db()
    total_spawns = conn.execute("SELECT COUNT(*) FROM pokemon_spawns").fetchone()[0]
    total_pokemon = conn.execute("SELECT COUNT(DISTINCT numero) FROM pokemon_spawns").fetchone()[0]
    buckets = conn.execute(
        "SELECT bucket, COUNT(DISTINCT numero) as n FROM pokemon_spawns GROUP BY bucket"
    ).fetchall()
    conn.close()
    return jsonify({
        "total_spawns": total_spawns,
        "total_pokemon": total_pokemon,
        "par_bucket": {(r["bucket"] or "inconnu"): r["n"] for r in buckets}
    })



# ── ADMIN ──────────────────────────────────────────────────────────────────

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    error = None
    if request.method == 'POST' and 'password' in request.form:
        if request.form['password'] == ADMIN_PASSWORD:
            session['is_admin'] = True
        else:
            error = "Mot de passe incorrect."

    if not session.get('is_admin'):
        return render_template('admin_login.html', error=error)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    pending    = [dict(r) for r in conn.execute("SELECT * FROM users WHERE validated = 0 ORDER BY created_at DESC").fetchall()]
    validated  = [dict(r) for r in conn.execute("SELECT * FROM users WHERE validated = 1 ORDER BY created_at DESC").fetchall()]
    patchnotes = [dict(r) for r in conn.execute("SELECT * FROM patch_notes ORDER BY created_at DESC").fetchall()]  # ← ajouter
    bug_reports = [dict(r) for r in conn.execute("SELECT * FROM bug_reports ORDER BY created_at DESC").fetchall()]
    conn.close()

    # Enrichir avec les emails Firebase si manquants
    for u in pending + validated:
        if not u.get('email'):
            try:
                fb_user = auth.get_user(u['firebase_uid'])
                u['email'] = fb_user.email
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE users SET email = ? WHERE firebase_uid = ?", (fb_user.email, u['firebase_uid']))
                conn.commit()
                conn.close()
            except Exception:
                u['email'] = None

    now = datetime.now(timezone.utc)
    now_date  = now.strftime("%Y-%m-%d")
    warn_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    return render_template('admin.html', pending=pending, validated=validated,
                           now_date=now_date, warn_date=warn_date, patchnotes=patchnotes,
                           bug_reports=bug_reports)


@app.route('/admin/validate', methods=['POST'])
def admin_validate():
    if not session.get('is_admin'):
        return redirect('/admin')
    uid = request.form.get('uid')
    if uid:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE users SET validated = 1 WHERE firebase_uid = ?", (uid,))
        conn.commit()
        conn.close()
    return redirect('/admin')


@app.route('/admin/reset-device', methods=['POST'])
def admin_reset_device():
    if not session.get('is_admin'):
        return redirect('/admin')
    uid = request.form.get('uid')
    if uid:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE users SET device_id = '' WHERE firebase_uid = ?", (uid,))
        conn.commit()
        conn.close()
    return redirect('/admin')


@app.route('/admin/refuse', methods=['POST'])
def admin_refuse():
    if not session.get('is_admin'):
        return redirect('/admin')
    uid = request.form.get('uid')
    if uid:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM users WHERE firebase_uid = ?", (uid,))
        conn.commit()
        conn.close()
        try:
            auth.revoke_refresh_tokens(uid)
            auth.delete_user(uid)
        except Exception:
            pass
    return redirect('/admin')


@app.route('/admin/extend', methods=['POST'])
def admin_extend():
    if not session.get('is_admin'):
        return redirect('/admin')
    uid = request.form.get('uid')
    days = int(request.form.get('days', 7))
    if uid:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT expires_at FROM users WHERE firebase_uid = ?", (uid,)).fetchone()
        # Prolonger depuis maintenant ou depuis l'expiration actuelle si future
        if row and row[0]:
            try:
                current_exp = datetime.fromisoformat(row[0])
                if current_exp.tzinfo is None:
                    current_exp = current_exp.replace(tzinfo=timezone.utc)
                base = max(current_exp, datetime.now(timezone.utc))
            except Exception:
                base = datetime.now(timezone.utc)
        else:
            base = datetime.now(timezone.utc)
        new_exp = (base + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE users SET expires_at = ? WHERE firebase_uid = ?", (new_exp, uid))
        conn.commit()
        conn.close()
    return redirect('/admin')


@app.route('/admin/set-expiry', methods=['POST'])
def admin_set_expiry():
    if not session.get('is_admin'):
        return redirect('/admin')
    uid     = request.form.get('uid')
    expires = request.form.get('expires', '').strip()  # 'permanent' | 'YYYY-MM-DD'
    if not uid:
        return redirect('/admin')

    conn = sqlite3.connect(DB_PATH)
    if expires == 'permanent':
        # Accès permanent : on met expires_at à NULL
        conn.execute("UPDATE users SET expires_at = NULL WHERE firebase_uid = ?", (uid,))
    elif expires:
        # Date précise fournie par le datepicker (format YYYY-MM-DD)
        # On la stocke au format datetime avec heure de fin de journée
        new_exp = expires + " 23:59:59"
        conn.execute("UPDATE users SET expires_at = ? WHERE firebase_uid = ?", (new_exp, uid))
    conn.commit()
    conn.close()
    return redirect('/admin')


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/admin')

# ── Patch Notes (public) ─────────────────────────────────────────────────────
@app.route("/patchnotes")
def patchnotes():
    conn = get_db()
    notes = conn.execute(
        "SELECT * FROM patch_notes ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("patchnotes.html", notes=notes)


# ── Admin : créer un patch note ───────────────────────────────────────────────
@app.route("/admin/patchnote/add", methods=["POST"])
def admin_add_patch_note():
    if not session.get("is_admin"):
        return redirect("/admin")
    version = request.form.get("version", "").strip()
    title   = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if version and title and content:
        conn = get_db()
        conn.execute(
            "INSERT INTO patch_notes (version, title, content) VALUES (?, ?, ?)",
            (version, title, content)
        )
        conn.commit()
        conn.close()
    return redirect("/admin")


# ── Admin : supprimer un patch note ──────────────────────────────────────────
@app.route("/admin/patchnote/delete", methods=["POST"])
def admin_delete_patch_note():
    if not session.get("is_admin"):
        return redirect("/admin")
    note_id = request.form.get("id", type=int)
    if note_id:
        conn = get_db()
        conn.execute("DELETE FROM patch_notes WHERE id = ?", (note_id,))
        conn.commit()
        conn.close()
    return redirect("/admin")

# ── Bug Reports (public) ─────────────────────────────────────────────────────
@app.route("/bugreport")
def bugreport():
    return render_template("bugreport.html")


@app.route("/bugreport/submit", methods=["POST"])
def bugreport_submit():
    title    = request.form.get("title", "").strip()
    category = request.form.get("category", "autre").strip()
    content  = request.form.get("content", "").strip()
    page_url = request.form.get("page_url", "").strip()
    username = request.form.get("username", "").strip()
    if title and content:
        conn = get_db()
        conn.execute(
            "INSERT INTO bug_reports (title, category, content, page_url, username) VALUES (?, ?, ?, ?, ?)",
            (title, category, content, page_url or None, username or None)
        )
        conn.commit()
        conn.close()
    return render_template("bugreport.html", submitted=True)


# ── Admin : bug reports ───────────────────────────────────────────────────────
@app.route("/admin/bugreport/status", methods=["POST"])
def admin_bugreport_status():
    if not session.get("is_admin"):
        return redirect("/admin")
    report_id = request.form.get("id", type=int)
    status    = request.form.get("status", "open")
    if report_id and status in ("open", "in_progress", "resolved"):
        conn = get_db()
        conn.execute("UPDATE bug_reports SET status = ? WHERE id = ?", (status, report_id))
        conn.commit()
        conn.close()
    return redirect("/admin#bugreports")


@app.route("/admin/bugreport/delete", methods=["POST"])
def admin_bugreport_delete():
    if not session.get("is_admin"):
        return redirect("/admin")
    report_id = request.form.get("id", type=int)
    if report_id:
        conn = get_db()
        conn.execute("DELETE FROM bug_reports WHERE id = ?", (report_id,))
        conn.commit()
        conn.close()
    return redirect("/admin#bugreports")


# ──────────────────────────────────────────────────────────────────────────────
# ORACLE D'ISOLATION
# ──────────────────────────────────────────────────────────────────────────────

import numpy as _np
import math as _math

EV_LABELS_ORACLE = {
    'hp': 'PV', 'atk': 'Attaque', 'def': 'Defense',
    'spa': 'Att. Spe', 'spd': 'Def. Spe', 'spe': 'Vitesse'
}

def _oracle_build_real_biome_map():
    """
    Construit {biome_reel: set_de_TOUS_les_tags_cobblemon_qui_le_couvrent} depuis BIOME_MAP.
    Inclut les tags broad (is_overworld, is_arid...) pour avoir le vrai pool de concurrents.
    """
    mapping = {}
    mods    = {}
    for fr_tag, biomes in BIOME_MAP.items():
        cob_tag = FR_TAG_TO_COBBLEMON.get(fr_tag)
        if not cob_tag:
            continue
        for entry in biomes:
            bname = entry['biome']
            mapping.setdefault(bname, set()).add(cob_tag)
            mods[bname] = entry['mod']
    return mapping, mods


def _oracle_load_spawns():
    conn = get_db()
    rows = conn.execute("""
        SELECT numero, pokemon, biomes_tags, biomes_exclus_tags,
               contexte, time, weather, conditions, peut_voir_ciel,
               structures, lune, presets, bucket, lumiere_min, lumiere_max
        FROM pokemon_spawns WHERE est_actif = 1
    """).fetchall()
    conn.close()
    COLS = ['numero','pokemon','biomes_tags','biomes_exclus_tags',
            'contexte','time','weather','conditions','peut_voir_ciel',
            'structures','lune','presets','bucket','lumiere_min','lumiere_max']
    spawns = []
    for r in rows:
        s = dict(zip(COLS, r))
        s['ev'] = get_ev(s['numero'])
        s['hitbox_height'] = get_height(s['numero'])
        cond = json.loads(s['conditions']) if s['conditions'] else {}
        s['minY']     = cond.get('minY')
        s['maxY']     = cond.get('maxY')
        s['maxLight']     = cond.get('maxLight')
        needed_nearby           = cond.get('neededNearbyBlocks', [])
        s['needed_blocks']      = bool(needed_nearby)
        s['needed_blocks_list'] = needed_nearby if isinstance(needed_nearby, list) else ([needed_nearby] if needed_nearby else [])
        s['needed_base_blocks'] = bool(cond.get('neededBaseBlocks'))
        s['lumiere_min']   = s.get('lumiere_min')   # None si pas de contrainte
        s['lumiere_max']   = s.get('lumiere_max')   # None si pas de contrainte
        s['preset_set'] = set(p.strip() for p in (s['presets'] or '').split(',') if p.strip())
        try:
            s['struct_list'] = json.loads(s['structures']) if s['structures'] else []
        except Exception:
            s['struct_list'] = []
        s['has_required_struct'] = len(s['struct_list']) > 0
        # Manoir = spawn strictement interne, pas de mélange avec biome général
        s['is_mansion'] = any('woodland_mansion' in st for st in s['struct_list'])
        s['is_filler']      = s.get('bucket') == 'filler'
        s['is_ultra_rare']  = s.get('bucket') == 'ultra-rare'
        # Normaliser #minecraft:is_nether → #cobblemon:is_nether
        # (Cobblemon utilise son propre namespace mais certains spawns utilisent minecraft:)
        _MC_TO_COB = {'#minecraft:is_nether': '#cobblemon:is_nether',
                      '#minecraft:is_overworld': '#cobblemon:is_overworld',
                      '#minecraft:is_end': '#cobblemon:is_end'}
        def _norm_tags(raw):
            tags = set(t.strip() for t in (raw or '').split(',') if t.strip())
            return {_MC_TO_COB.get(t, t) for t in tags}
        s['tag_set']  = _norm_tags(s['biomes_tags'])
        s['excl_set'] = _norm_tags(s['biomes_exclus_tags'])
        spawns.append(s)
    return spawns


def _oracle_beam_refine(subset, base_combo, chain, skip_hmax=False, ctx=None, chain_lum_min=None, chain_lum_max=None, skip_struct=False):
    """
    Affine une sous-liste avec beam search sur les filtres optionnels.
    Contexte et EV déjà appliqués — ici : weather, preset, sky, Y, light, time, hmax.
    """
    ns = len(subset)
    if ns == 0:
        return 0, ns, base_combo, subset
    is_t = _np.array([s['numero'] in chain for s in subset])
    if is_t.sum() == 0:
        return 0, ns, base_combo, subset

    # ── Chaque filtre = BLOQUER une condition = ÉLIMINER les spawns qui la requièrent ──
    # Les spawns sans contrainte (None) restent dans le pool dans TOUS les cas.
    # ORDRE de test : structures → lumière → ciel → blocs requis → Y → hitbox → preset → temps → météo
    fc_struct  = {}   # 1. structures
    fc_light   = {}   # 2. lumière / obscurité
    fc_sky     = {}   # 3. ciel
    fc_blocks  = {}   # 4. blocs requis
    fc_y       = {}   # 5. Y
    fc_hmax    = {}   # 6. hitbox (rempli plus bas)
    fc_preset  = {}   # 7. presets
    fc_time    = {}   # 8. temps
    fc_weather = {}   # 9. météo

    # MÉTÉO
    all_weathers = sorted({s['weather'] for s in subset if s['weather']})
    for w in all_weathers:
        other = [x for x in all_weathers if x != w]
        if other:
            fc_weather['block_weather:' + w] = _np.array(
                [s['weather'] is None or s['weather'] == w for s in subset]
            )

    # PRESET : bloquer l'absence d'un preset = éliminer spawns qui ONT ce preset
    # Ex: "pas de treetop" → éliminer spawns avec 'treetop' dans preset_set
    # PRESETS : un spawn peut avoir plusieurs presets (ex: 'natural, treetop')
    # Bloquer 'treetop' n'exclut un spawn QUE si tous ses presets sont bloqués
    # On crée un filtre par preset p : exclure les spawns dont preset_set ⊆ {p}
    # (= ils n'ont que p comme preset, donc sans p ils ne peuvent plus spawner)
    all_presets = set()
    for s in subset: all_presets |= s['preset_set']
    # 'natural' et 'wild' sont des presets omniprésents qu'on ne peut pas bloquer
    UNBLOCABLE_PRESETS = {'natural', 'wild'}
    # Seuls ces presets sont des emplacements physiquement exclusifs :
    # on peut se limiter strictement a treetop (sur feuilles), water (dans l'eau)
    # ou lava (pres de lave) sans ambiguite avec natural/wild.
    # Tous les autres presets (foliage, urban, derelict...) coexistent avec
    # natural/wild et ne peuvent pas etre "requis" sans faux positifs.
    REQUIREABLE_PRESETS = {'treetop', 'water', 'lava'}
    for p in sorted(all_presets):
        if p in UNBLOCABLE_PRESETS:
            continue
        # Exclure uniquement les spawns qui n'ont QUE ce preset (pas d'autre preset alternatif)
        # ex: block_preset:treetop exclut {treetop} mais garde {natural, treetop}
        fc_preset['block_preset:' + p] = _np.array(
            [(p not in s['preset_set']) or (len(s['preset_set']) > 1) for s in subset]
        )
        # REQUIRE PRESET : se limiter strictement a un emplacement exclusif.
        # Uniquement pour treetop/water/lava car ce sont des locations mutuellement
        # exclusives avec natural/wild — les autres presets se chevauchent.
        if p in REQUIREABLE_PRESETS and any(p in s['preset_set'] for s in subset if s['numero'] in chain):
            fc_preset['require_preset:' + p] = _np.array(
                [p in s['preset_set'] for s in subset]
            )

    if not skip_struct:
        # STRUCTURE — deux types de filtres :
        # 1. block_struct:X  → exclure les structures QUE UNIQUEMENT les concurrents utilisent
        # 2. require_struct:X → se limiter à UNE structure que la chaîne utilise (élimine les autres,
        #    y compris d'autres structures de la chaîne — ex: village plutôt que manoir pour Évoli)
        all_struct_ids = set()
        for s in subset:
            all_struct_ids |= set(s['struct_list'])
        def _struct_canonical(sid):
            return sid.lstrip('#').replace('cobblemon:', 'mc:').replace('minecraft:', 'mc:')
        struct_groups = {}  # canonical → set of raw IDs
        for sid in all_struct_ids:
            c = _struct_canonical(sid)
            struct_groups.setdefault(c, set()).add(sid)

        # Structures utilisées par la chaîne
        chain_struct_canons = set()
        for s in subset:
            if s['numero'] in chain:
                for sid in s['struct_list']:
                    chain_struct_canons.add(_struct_canonical(sid))

        for canon, raw_ids in struct_groups.items():
            if canon in chain_struct_canons:
                # La chaîne utilise cette structure → propose require_struct pour s'y limiter
                fc_struct['require_struct:' + canon] = _np.array([
                    not s['has_required_struct'] or bool(set(_struct_canonical(sid) for sid in s['struct_list']) & {canon})
                    for s in subset
                ])
            else:
                # Uniquement des concurrents → propose block_struct pour les exclure
                fc_struct['block_struct:' + canon] = _np.array([
                    not s['has_required_struct'] or bool(set(_struct_canonical(sid) for sid in s['struct_list']) & chain_struct_canons)
                    for s in subset
                ])

    # CIEL : bloquer ciel visible → éliminer peut_voir_ciel='true', garder false+None
    #        bloquer ciel absent  → éliminer peut_voir_ciel='false', garder true+None
    fc_sky['block_sky:open']    = _np.array([s['peut_voir_ciel'] != 'true'  for s in subset])
    fc_sky['block_sky:covered'] = _np.array([s['peut_voir_ciel'] != 'false' for s in subset])

    # Y : "au-dessus de Y=v" → éliminer spawns dont maxY <= v
    for ym in sorted({s['maxY'] for s in subset if s['maxY'] is not None}):
        fc_y['block_ybelow:' + str(ym)] = _np.array([s['maxY'] is None or s['maxY'] > ym for s in subset])
    # Y : "en-dessous de Y=v" → éliminer spawns dont minY >= v
    for ym in sorted({s['minY'] for s in subset if s['minY'] is not None}):
        fc_y['block_yabove:' + str(ym)] = _np.array([s['minY'] is None or s['minY'] < ym for s in subset])

    # LUMIÈRE : bloquer lumière forte → éliminer spawns avec maxLight > seuil
    for ml in sorted({s['maxLight'] for s in subset if s['maxLight'] is not None}):
        fc_light['block_light:' + str(ml)] = _np.array(
            [s['maxLight'] is None or s['maxLight'] <= ml for s in subset]
        )
    # Bloquer les spawns qui nécessitent des blocs proches spécifiques (nénuphars, eau, etc.)
    if any(s['needed_blocks'] for s in subset):
        fc_blocks['block_neededBlocks:1'] = _np.array([not s['needed_blocks'] for s in subset])
    # Bloquer les spawns qui nécessitent un sol spécifique (herbe, pierre, etc.)
    if any(s['needed_base_blocks'] for s in subset):
        fc_blocks['block_baseBlocks:1'] = _np.array([not s['needed_base_blocks'] for s in subset])
    # Filtres luminosité basés sur la plage de lumière de la CIBLE
    # block_darkness : si la cible a besoin de lumière (lum_min>0), exclure les spawns d'obscurité
    if chain_lum_min is not None and chain_lum_min > 0:
        fc_light['block_darkness:1'] = _np.array(
            [s['lumiere_max'] is None or s['lumiere_max'] >= chain_lum_min for s in subset]
        )
    # block_brightness : si la cible a besoin d'obscurité (lum_max<15), exclure les spawns lumineux
    if chain_lum_max is not None and chain_lum_max < 15:
        fc_light['block_brightness:1'] = _np.array(
            [s['lumiere_min'] is None or s['lumiere_min'] <= chain_lum_max for s in subset]
        )
    # Filtres luminosité généraux : même si la cible n'a pas de contrainte lumière,
    # on peut CHOISIR de farmer en lumière ou dans l'obscurité pour exclure des concurrents.
    # "block_darkness_gen" = farmer en lumière → exclure les spawns dark-only (lum_max <= 7)
    # "block_brightness_gen" = farmer dans le noir → exclure les spawns bright-only (lum_min >= 8)
    # Ces filtres ne s'appliquent que si la cible elle-même ne serait pas exclue.
    if 'block_darkness:1' not in fc_light:
        # Cible sans contrainte de luminosité OU avec lum_max > 7 → peut spawner en lumière
        # La chaîne a AU MOINS UN spawn qui tolère la lumière (lum_max > 7 ou sans contrainte)
        # → mettre des torches peut avantager la cible sans l'éliminer
        chain_allows_light = any(
            s['lumiere_max'] is None or s['lumiere_max'] > 7
            for s in subset if s['numero'] in chain
        )
        if chain_allows_light and any(
            s['lumiere_max'] is not None and s['lumiere_max'] <= 7
            for s in subset if s['numero'] not in chain
        ):
            fc_light['block_darkness:1'] = _np.array(
                [s['lumiere_max'] is None or s['lumiere_max'] > 7 for s in subset]
            )
    if 'block_brightness:1' not in fc_light:
        # Cible sans contrainte OU avec lum_min < 8 → peut spawner dans l'obscurité
        # La chaîne a AU MOINS UN spawn qui tolère l'obscurité (lum_min < 8 ou sans contrainte)
        chain_allows_dark = any(
            s['lumiere_min'] is None or s['lumiere_min'] < 8
            for s in subset if s['numero'] in chain
        )
        if chain_allows_dark and any(
            s['lumiere_min'] is not None and s['lumiere_min'] >= 8
            for s in subset if s['numero'] not in chain
        ):
            fc_light['block_brightness:1'] = _np.array(
                [s['lumiere_min'] is None or s['lumiere_min'] < 8 for s in subset]
            )

    # MOMENT : tester les 3 creneaux, meme si non representes dans le subset.
    # farm_time:night -> exclut les spawns jour/crepuscule only
    all_times_in_subset = sorted({s['time'] for s in subset if s['time']})
    if all_times_in_subset:
        for farm_t in ['day', 'night', 'dusk']:
            excluded_by_farm = [s for s in subset if s['time'] and s['time'] != farm_t]
            if excluded_by_farm:
                fc_time['farm_time:' + farm_t] = _np.array(
                    [s['time'] is None or s['time'] == farm_t for s in subset]
                )
    # Pour chaque hauteur unique des membres de la chaine, on cree un filtre hmax.
    # Ex: Ouistempo(0.6)->1.0, Badabouin(1.32)->2.0, Gorythmic(2.185)->3.0
    # IMPORTANT: les membres de la chaine exclus par ce plafond ne sont pas des
    # "cibles perdues" - ils ne peuvent simplement pas spawner dans cet espace.
    # On stocke un is_t local par filtre hmax qui redefinit la chaine effective.
    fc_is_t_override = {}
    if not skip_hmax:
        chain_hs_unique = sorted({
            float(_math.ceil(s['hitbox_height']))
            for s in subset if s['numero'] in chain and s['hitbox_height']
        })
        for h_ceil in chain_hs_unique:
            if ctx in ('submerged', 'seafloor'):
                h_ceil = max(h_ceil, 2.0)
            key = 'hmax:' + str(h_ceil)
            # Garde: hitbox inconnue (None) OU hitbox <= plafond
            fc_hmax[key] = _np.array(
                [s['hitbox_height'] is None or s['hitbox_height'] <= h_ceil for s in subset]
            )
            # is_t local: membres de la chaine qui RENTRENT dans ce plafond
            fc_is_t_override[key] = _np.array([
                s['numero'] in chain and
                (s['hitbox_height'] is None or s['hitbox_height'] <= h_ceil)
                for s in subset
            ])

    # Fusionner dans l'ordre de priorité
    fc = {}
    fc.update(fc_struct)
    fc.update(fc_light)
    fc.update(fc_sky)
    fc.update(fc_blocks)
    fc.update(fc_y)
    fc.update(fc_hmax)
    fc.update(fc_preset)
    fc.update(fc_time)
    fc.update(fc_weather)

    if not fc:
        tgt = int(is_t.sum())
        return round(tgt / ns * 100, 1), ns, base_combo, subset

    fn = list(fc.keys())
    fa = [fc[k] for k in fn]
    is_ultra  = _np.array([s['is_ultra_rare'] for s in subset])
    n_tgt_init  = int(is_t.sum())
    n_ultra_init= int((is_ultra & ~is_t).sum())
    n_norm_init = ns - n_tgt_init - n_ultra_init
    _wd = n_tgt_init + n_norm_init + n_ultra_init * 0.1
    best_pct  = (n_tgt_init / _wd * 100) if _wd > 0 else 0
    best_mask = _np.ones(ns, dtype=bool)
    best_keys = []
    beam = [(_np.ones(ns, dtype=bool), [])]
    is_ultra_arr = _np.array([s['is_ultra_rare'] for s in subset])

    for _d in range(9):
        nb = []
        for mask, active in beam:
            for name, arr in zip(fn, fa):
                if name in active: continue
                # Filtres mutuellement exclusifs : on ne peut pas bloquer les deux côtés en même temps
                cat_name = name.split(':')[0]
                if cat_name == 'block_sky' and any(k.startswith('block_sky:') for k in active): continue
                if cat_name == 'farm_time' and any(k.startswith('farm_time:') for k in active): continue
                if cat_name == 'block_weather' and any(k.startswith('block_weather:') for k in active): continue
                # require_preset et block_preset sont incompatibles entre eux
                if cat_name == 'require_preset' and any(k.startswith('require_preset:') for k in active): continue
                if cat_name == 'require_preset' and any(k.startswith('block_preset:') for k in active): continue
                if cat_name == 'block_preset' and any(k.startswith('require_preset:') for k in active): continue
                # block_darkness et block_brightness sont mutuellement exclusifs
                if name == 'block_darkness:1' and 'block_brightness:1' in active: continue
                if name == 'block_brightness:1' and 'block_darkness:1' in active: continue
                # require_struct : une seule à la fois (on ne peut pas se limiter à deux structures)
                if cat_name == 'require_struct' and any(k.startswith('require_struct:') for k in active): continue
                nm  = mask & arr
                cnt = int(nm.sum())
                if cnt == 0: continue
                # Un filtre n'est utile que s'il élimine au moins un concurrent (non-cible).
                # Pour hmax : utile seulement s'il élimine au moins un concurrent,
                # pas juste des membres de la chaîne (évite hmax:2 quand seule la chaîne est présente).
                curr_non_target = int((mask & ~is_t).sum())
                new_non_target  = int((nm    & ~is_t).sum())
                if new_non_target >= curr_non_target: continue
                # Pour les filtres hmax, la chaine effective = membres qui rentrent dans le plafond.
                # Les membres exclus par la hauteur ne sont pas des cibles perdues.
                new_active_combo = active + [name]
                hmax_in_combo = [k for k in new_active_combo if k.startswith('hmax:')]
                if hmax_in_combo:
                    most_restrictive = min(hmax_in_combo, key=lambda k: float(k[5:]))
                    eff_is_t = fc_is_t_override.get(most_restrictive, is_t)
                else:
                    eff_is_t = is_t
                t2  = int((nm & eff_is_t).sum())
                if t2 == 0: continue
                # Score pondéré : les ultra-rare comptent 0.1 comme concurrent
                n_ultra = int((nm & is_ultra_arr).sum()) - int((nm & eff_is_t & is_ultra_arr).sum())
                n_norm  = cnt - t2 - n_ultra
                weighted_denom = t2 + n_norm + n_ultra * 0.1
                weighted_pct = (t2 / weighted_denom * 100) if weighted_denom > 0 else 0
                nb.append((weighted_pct, cnt, nm, new_active_combo))
        if not nb: break
        nb.sort(key=lambda x: (-x[0], x[1]))
        top = nb[0]
        if top[0] > best_pct or (top[0] == best_pct and top[1] < int(best_mask.sum())):
            best_pct  = top[0]
            best_mask = top[2]
            best_keys = top[3]
        beam = [(m, a) for _, _, m, a in nb[:10]]
        if best_pct == 100.0 and int(best_mask.sum()) <= len(chain):
            break

    # ── Pass final : tenter d'ajouter UN filtre supplémentaire ──
    # On explore le meilleur masque trouvé ET les 5 états finaux du beam.
    # Couvre le cas où 4 filtres sont nécessaires (ex: Ouistempo dans Tropical Beach :
    # require_treetop + farm_time:night + block_neededBlocks + hmax:1.0 → 100%).
    if best_pct < 100.0:
        is_ultra_arr_fp = _np.array([s['is_ultra_rare'] for s in subset])
        # Candidats : meilleur état global + derniers états du beam (peuvent diverger)
        fp_candidates = [(best_mask, best_keys)] + [
            (m, a) for m, a in beam if list(a) != list(best_keys)
        ]
        for fp_mask, fp_keys in fp_candidates:
            if best_pct == 100.0 and int(best_mask.sum()) <= len(chain):
                break
            for name, arr in zip(fn, fa):
                if name in fp_keys:
                    continue
                cat_name = name.split(':')[0]
                if cat_name == 'block_sky'      and any(k.startswith('block_sky:')      for k in fp_keys): continue
                if cat_name == 'farm_time'      and any(k.startswith('farm_time:')      for k in fp_keys): continue
                if cat_name == 'block_weather'  and any(k.startswith('block_weather:')  for k in fp_keys): continue
                if cat_name == 'require_preset' and any(k.startswith('require_preset:') or k.startswith('block_preset:') for k in fp_keys): continue
                if cat_name == 'block_preset'   and any(k.startswith('require_preset:') for k in fp_keys): continue
                if name == 'block_darkness:1'   and 'block_brightness:1' in fp_keys: continue
                if name == 'block_brightness:1' and 'block_darkness:1'   in fp_keys: continue
                if cat_name == 'require_struct'  and any(k.startswith('require_struct:') for k in fp_keys): continue
                if cat_name == 'block_struct': pass  # plusieurs block_struct peuvent se combiner
                nm  = fp_mask & arr
                cnt = int(nm.sum())
                if cnt == 0:
                    continue
                curr_non_target_fp = int((fp_mask & ~is_t).sum())
                new_non_target_fp  = int((nm      & ~is_t).sum())
                if new_non_target_fp >= curr_non_target_fp:
                    continue
                new_keys = list(fp_keys) + [name]
                hmax_in_combo = [k for k in new_keys if k.startswith('hmax:')]
                if hmax_in_combo:
                    most_restrictive = min(hmax_in_combo, key=lambda k: float(k[5:]))
                    eff_is_t_fp = fc_is_t_override.get(most_restrictive, is_t)
                else:
                    eff_is_t_fp = is_t
                t2 = int((nm & eff_is_t_fp).sum())
                if t2 == 0:
                    continue
                n_ultra_fp = int((nm & is_ultra_arr_fp).sum()) - int((nm & eff_is_t_fp & is_ultra_arr_fp).sum())
                n_norm_fp  = cnt - t2 - n_ultra_fp
                wd = t2 + n_norm_fp + n_ultra_fp * 0.1
                wpct = (t2 / wd * 100) if wd > 0 else 0
                if wpct > best_pct or (wpct == best_pct and cnt < int(best_mask.sum())):
                    best_pct  = wpct
                    best_mask = nm
                    best_keys = new_keys
                if best_pct == 100.0 and int(best_mask.sum()) <= len(chain):
                    break

    # ── Pass hmax de réduction ──────────────────────────────────────────────────
    # Après le beam, on tente d'ajouter le meilleur hmax non encore sélectionné.
    # Objectif : réduire total_filtered (pool restant) même si la pureté baisse.
    # Un hmax est accepté si : au moins une cible reste + pool réduit.
    # On choisit le hmax le plus restrictif qui laisse au moins une cible.
    if not skip_hmax and not any(k.startswith('hmax:') for k in best_keys):
        best_hmax_mask = None
        best_hmax_cnt  = int(best_mask.sum())
        best_hmax_key  = None
        for key, arr in zip(fn, fa):
            if not key.startswith('hmax:'): continue
            nm = best_mask & arr
            cnt = int(nm.sum())
            if cnt == 0 or cnt >= best_hmax_cnt: continue
            # Vérifier qu'au moins une cible reste (en utilisant fc_is_t_override si pertinent)
            eff = fc_is_t_override.get(key, is_t)
            if int((nm & eff).sum()) == 0: continue
            best_hmax_mask = nm
            best_hmax_cnt  = cnt
            best_hmax_key  = key
        if best_hmax_key:
            best_mask = best_hmax_mask
            best_keys = best_keys + [best_hmax_key]

    # Construire le combo en termes de conditions BLOQUÉES/SUPPRIMÉES
    EV_LBL = {'hp':'PV','atk':'Attaque','def':'Défense','spa':'Att. Spé','spd':'Déf. Spé','spe':'Vitesse'}
    WTHR_LBL = {'clear':'beau temps', 'rain':'pluie'}
    TIME_LBL  = {'day':'jour', 'night':'nuit', 'dusk':'crépuscule'}
    PRESET_LBL = {
        'treetop':'cimes d\'arbres','foliage':'feuillage','wild':'zones sauvages',
        'urban':'zones urbaines','derelict':'zones délabrées','lava':'lave',
        'redstone':'redstone','mansion':'manoir','illager_structures':'structures pillards',
        'trail_ruins':'ruines de sentier','webs':'toiles','salt':'sel',
        'ancient_city':'cité ancienne','stronghold':'forteresse',
        'end_city':'cité de l\'End','nether_fossil':'fossile Nether',
        'nether_structures':'structures Nether','jungle_pyramid':'pyramide jungle',
        'desert_pyramid':'pyramide désert','pillager_outpost':'avant-poste pillard',
        'ruined_portal':'portail ruiné','ocean_ruins':'ruines océaniques',
        'ocean_monument':'monument océanique',
    }
    combo = dict(base_combo)
    removed = []  # conditions supprimées pour affichage
    # Si on a exclu les spawns en structure du pool, le signaler
    if base_combo.get('no_struct_filter'):
        removed.append('Spawns en structure exclus')
    # Si le pool est limité à une structure spécifique, construire require_struct
    req_struct_canon = base_combo.get('require_struct_canon')
    if req_struct_canon:
        raw_val = req_struct_canon.replace('mc:', 'minecraft:')
        icon, label_fr = _structure_label(raw_val)
        combo['require_struct'] = req_struct_canon
        combo['require_struct_label'] = f"{icon} {label_fr}"
        combo['require_struct_fr']    = label_fr
        combo['struct_keep_fr']       = base_combo.get('struct_keep_fr', label_fr)
        combo['excl_structures_fr']   = base_combo.get('excl_structures_fr', [])
    elif base_combo.get('struct_keep_fr'):
        combo['struct_keep_fr'] = base_combo['struct_keep_fr']
    elif base_combo.get('excl_structures_fr'):
        combo['excl_structures_fr'] = base_combo['excl_structures_fr']
    for key in best_keys:
        # hmax:2.0 → un seul ':' contrairement aux block_xxx:yyy
        if key.startswith('hmax:'):
            hval = key[5:]  # après 'hmax:'
            combo['h_max'] = float(hval)
            removed.append(f"Hauteur > {hval}m bloquée (dalles/blocs)")
            continue
        cat, val = key.split(':', 1)
        if cat == 'block_weather':
            combo['block_weather'] = val
            # val = météo sous laquelle on FARME (le filtre garde val+None, élimine l'autre météo)
            farm_label = WTHR_LBL.get(val, val)
            other_weathers = [w for w in sorted({s['weather'] for s in subset if s['weather']}) if w != val]
            if other_weathers:
                excl_label = ' / '.join(WTHR_LBL.get(w, w) for w in other_weathers)
                # Stocker la météo EXCLUE pour que buildBiomeUrl puisse l'envoyer correctement
                combo['block_weather_excl'] = other_weathers[0] if len(other_weathers) == 1 else None
                removed.append(f"Farmer par {farm_label} (spawns {excl_label} exclus)")
            else:
                removed.append(f"Farmer par {farm_label}")
        elif cat == 'block_preset':
            combo.setdefault('block_presets', []).append(val)
            removed.append('Preset ' + PRESET_LBL.get(val,val) + ' bloqué')
        elif cat == 'require_preset':
            combo['require_preset'] = val
        elif cat == 'require_struct':
            raw_val = val.replace('mc:', 'minecraft:')
            icon, label_fr = _structure_label(raw_val)
            combo['require_struct'] = val
            combo['require_struct_label'] = f"{icon} {label_fr}"
            combo['require_struct_fr']    = label_fr
            # Toutes les autres structures présentes dans le subset → à exclure dans biome_spawns
            other_structs_fr = []
            for other_canon, other_raw_ids in struct_groups.items():
                if other_canon == val:
                    continue
                rep = next((r for r in other_raw_ids if not r.startswith('#')), next(iter(other_raw_ids)))
                _, lbl = _structure_label(rep)
                if lbl not in other_structs_fr:
                    other_structs_fr.append(lbl)
            combo['excl_structures_fr'] = other_structs_fr
        elif cat == 'block_struct':
            # val = canonical struct id (ex: "mc:jungle_pyramid")
            raw_val = val.replace('mc:', 'minecraft:')
            _, label_fr = _structure_label(raw_val)
            combo.setdefault('excl_structures_fr', [])
            if label_fr not in combo['excl_structures_fr']:
                combo['excl_structures_fr'].append(label_fr)
        elif cat == 'block_sky':
            combo['block_sky'] = val
            if val == 'open':    removed.append("Ciel visible bloqué (toit/caverne)")
            else:                removed.append("Ciel absent bloqué (à l\'air libre)")
        elif cat == 'block_ybelow':
            combo['y_above'] = float(val)
            removed.append(f"Spawns sous Y={val} bloqués")
        elif cat == 'block_yabove':
            combo['y_below'] = float(val)
            removed.append(f"Spawns au-dessus Y={val} bloqués")
        elif cat == 'block_light':
            combo['maxLight'] = float(val)
            removed.append(f"Lumière > {val} bloquée")
        elif cat == 'block_neededBlocks':
            combo['block_needed_blocks'] = True
            excl_blocks = set()
            for s in subset:
                if s['needed_blocks']:
                    for b in s.get('needed_blocks_list', []):
                        excl_blocks.add(b)
            water_blocks = {'minecraft:water', 'minecraft:water_source', '#minecraft:water'}
            if excl_blocks & water_blocks:
                removed.append("Eau à proximité exclue — rester loin de l'eau")
            elif excl_blocks:
                clean = [_clean_block(b) for b in list(excl_blocks)[:3]]
                removed.append(f"Blocs requis à proximité exclus : {', '.join(clean)}")
            else:
                removed.append("Blocs requis à proximité exclus")
        elif cat == 'block_baseBlocks':
            combo['block_base_blocks'] = True
            removed.append("Sol spécifique bloqué (herbe, pierre, etc.)")
        elif cat == 'block_darkness':
            combo['block_darkness'] = True
            removed.append("Spawns d'obscurité exclus — farmer en lumière (lumière > 7)")
        elif cat == 'block_brightness':
            combo['block_brightness'] = True
            removed.append("Spawns lumineux exclus — farmer dans l'obscurité (lumière ≤ 7)")
        elif cat == 'farm_time':
            combo['farm_time'] = val
            excluded_times = [t for t in all_times_in_subset if t != val]
            if excluded_times:
                excl_names = ' / '.join(TIME_LBL.get(t, t) for t in excluded_times)
                removed.append(f"Pokémon {excl_names} uniquement exclus (farmer {TIME_LBL.get(val, val)})")

    combo['removed'] = removed

    filtered_final = [s for s, m in zip(subset, best_mask) if m]
    competitors_final = [s for s in filtered_final if s['numero'] not in chain]
    raw_pct = round(sum(1 for s in filtered_final if s['numero'] in chain) / len(filtered_final) * 100, 1) if filtered_final else 0
    only_ultra = len(competitors_final) > 0 and all(s['is_ultra_rare'] for s in competitors_final)
    combo['raw_pct']    = raw_pct
    combo['only_ultra'] = only_ultra
    return round(best_pct, 1), int(best_mask.sum()), combo, filtered_final


def _oracle_best_combo(in_biome, chain, is_virtual_biome=False):
    """
    Calcule la meilleure isolation pour un biome.
    Pool = spawns sans structure requise + spawns de structure non-manoir
           (ils coexistent dans le chunk avec les spawns normaux).
    Exception : manoir = pool strictement les spawns du manoir.
    Filtres obligatoires : contexte + stat EV.
    Filtres optionnels via beam search : sky, météo, preset, Y, lumière, time, hitbox.
    Note : filtre hitbox désactivé pour le contexte fishing.
    """
    # Si la chaîne cible ne spawn jamais en structure → exclure tous les spawns
    # qui nécessitent une structure (ils n'apparaîtront pas dans le biome sans structure)
    chain_has_struct = any(s['has_required_struct'] for s in in_biome if s['numero'] in chain)

    if chain_has_struct:
        # Chaîne avec structure : pool = sans struct + non-manoir (comportement précédent)
        pool_general = [s for s in in_biome
                        if (not s['has_required_struct'] or not s['is_mansion'])
                        and not s['is_filler']]
    else:
        # Chaîne sans structure : pool = UNIQUEMENT spawns sans structure
        pool_general = [s for s in in_biome
                        if not s['has_required_struct']
                        and not s['is_filler']]

    # Pool manoir : strictement les spawns du manoir, fillers exclus
    pool_mansion = [s for s in in_biome if s['is_mansion'] and not s['is_filler']]

    # Pool par structure individuelle : si la chaîne spawn dans plusieurs structures,
    # tester chaque structure séparément pour voir si l'une isole mieux.
    # Ex : Évoli spawn en village ET en manoir → tester village seul vs manoir seul.
    def _struct_canonical_local(sid):
        return sid.lstrip('#').replace('cobblemon:', 'mc:').replace('minecraft:', 'mc:')

    chain_struct_canons_local = set()
    for s in in_biome:
        if s['numero'] in chain and s['has_required_struct']:
            for sid in s['struct_list']:
                chain_struct_canons_local.add(_struct_canonical_local(sid))

    # Grouper les structures de la chaîne par canon
    chain_struct_groups_local = {}
    for s in in_biome:
        if s['numero'] in chain and s['has_required_struct']:
            for sid in s['struct_list']:
                c = _struct_canonical_local(sid)
                chain_struct_groups_local.setdefault(c, set()).add(sid)

    # Les structures sont gérées par les biomes virtuels dans generate()
    # → pas d'extra_pools ici, pool_general = sans structure uniquement
    extra_pools = []

    results = []

    for pool_label, pool in [('general', pool_general), ('mansion', pool_mansion)] + [(lbl, p) for lbl, p, _, _excl in extra_pools]:
        if not pool:
            continue
        if pool_label == 'mansion' and not any(s['numero'] in chain for s in pool):
            continue

        total_base = len(pool)
        ctxs = sorted({s['contexte'] for s in pool if s['contexte']})

        # Collecter toutes les stats EV lâchées par la chaîne cible
        chain_ev_stats = set()
        for s in pool:
            if s['numero'] in chain:
                for stat in ['hp','atk','def','spa','spd','spe']:
                    if s['ev'][stat] > 0:
                        chain_ev_stats.add(stat)

        if not chain_ev_stats:
            continue

        # Tester chaque stat EV individuellement
        ev_combos_to_test = [(stat,) for stat in sorted(chain_ev_stats)]

        for ctx in ctxs:
            ctx_sub = [s for s in pool if s['contexte'] == ctx]
            if not any(s['numero'] in chain for s in ctx_sub):
                continue

            for ev_combo in ev_combos_to_test:
                # Garder les spawns qui ont AU MOINS UNE des stats EV du combo
                # (le joueur filtre par "donne des EVs dans ces stats")
                ev_sub = [s for s in ctx_sub if any(s['ev'][stat] > 0 for stat in ev_combo)]
                if not ev_sub:
                    continue
                if not any(s['numero'] in chain for s in ev_sub):
                    continue

                label = ' + '.join(EV_LABELS_ORACLE.get(s, s) for s in ev_combo)
                base = {'contexte': ctx, 'ev': ','.join(ev_combo), 'ev_label': label}
                if pool_label == 'mansion':
                    base['pool'] = 'mansion'
                elif pool_label.startswith('struct:') or pool_label.startswith('strict:'):
                    prefix = 'struct:' if pool_label.startswith('struct:') else 'strict:'
                    canon_key = pool_label[len(prefix):]
                    # Pour biome_spawns, trouver tous les labels du groupe
                    struct_labels = []
                    for c in canon_key.split('|'):
                        raw_val = c.replace('mc:', 'minecraft:')
                        _, lbl = _structure_label(raw_val)
                        if lbl not in struct_labels:
                            struct_labels.append(lbl)
                    base['require_struct_canon'] = canon_key
                    # struct_keep_fr = premier label du groupe
                    base['struct_keep_fr'] = struct_labels[0] if struct_labels else ''
                    # struct_keep_all = tous les labels pour biome_spawns
                    base['struct_keep_all_fr'] = struct_labels
                    if pool_label.startswith('strict:'):
                        base['pool'] = 'strict_struct'
                elif pool_label == 'general' and chain_has_struct:
                    # pool_general exclut les spawns manoir → indiquer quelle(s) structure(s)
                    # la chaîne utilise pour que biome_spawns exclue tout le reste
                    chain_struct_labels = []
                    for s in in_biome:
                        if s['numero'] in chain and s['has_required_struct']:
                            for sid in s['struct_list']:
                                _, lbl = _structure_label(sid)
                                if lbl not in chain_struct_labels:
                                    chain_struct_labels.append(lbl)
                    # On envoie la première structure de la chaîne comme struct_keep
                    # (manoir exclu du pool_general, donc c'est Village si c'est Évoli)
                    non_mansion_labels = [l for l in chain_struct_labels if l != 'Manoir forestier']
                    if non_mansion_labels:
                        base['struct_keep_fr'] = non_mansion_labels[0]
                if not chain_has_struct:
                    base['no_struct_filter'] = True
                # Lumière min/max de la chaîne pour ce pool (via colonnes DB)
                lum_mins = [s['lumiere_min'] for s in pool if s['numero'] in chain and s['lumiere_min'] is not None]
                lum_maxs = [s['lumiere_max'] for s in pool if s['numero'] in chain and s['lumiere_max'] is not None]
                c_lum_min = min(lum_mins) if lum_mins else None
                c_lum_max = max(lum_maxs) if lum_maxs else None
                pct, tf, combo, filt = _oracle_beam_refine(ev_sub, base, chain,
                                                            skip_hmax=(ctx == 'fishing'),
                                                            skip_struct=(not is_virtual_biome),
                                                            ctx=ctx,
                                                            chain_lum_min=c_lum_min,
                                                            chain_lum_max=c_lum_max)
                results.append((pct, total_base, tf, combo, filt))

    if not results:
        return 0, 0, 0, {}, []

    results.sort(key=lambda x: (-x[0], x[2]))
    return results[0]


@app.route('/oracle')
def oracle():
    conn = get_db()
    pokemon_list = conn.execute(
        "SELECT DISTINCT numero, pokemon FROM pokemon_spawns ORDER BY numero"
    ).fetchall()
    conn.close()
    return render_template('oracle.html', pokemon_list=pokemon_list)


@app.route('/api/oracle/stream')
def api_oracle_stream():
    numero = request.args.get('numero', type=int)
    focus  = request.args.get('focus', '0') == '1'
    if not numero:
        return jsonify({'error': 'numero requis'}), 400

    def generate():
        full_chain = get_evo_chain(numero)
        # Mode focus : uniquement le Pokémon sélectionné, indépendamment de sa chaîne
        chain = frozenset({numero}) if focus else full_chain
        all_spawns = _oracle_load_spawns()
        real_biome_map, biome_mods = _oracle_build_real_biome_map()

        conn = get_db()
        num_to_name = {r[0]: r[1] for r in conn.execute(
            "SELECT DISTINCT numero, pokemon FROM pokemon_spawns"
        ).fetchall()}
        conn.close()

        chain_names = [num_to_name.get(n, '#' + str(n)) for n in sorted(chain)]

        ALLOWED_MODS = {'Vanilla Minecraft', 'Terralith', "Wythers' Overhauled Overworld"}

        # Structures ubiquitaires → traités comme biomes virtuels
        # (stronghold sous tout l'overworld, bastion/fortress dans tout le nether, etc.)
        # Format : (nom_affiché, frozenset_de_tags, mod)
        VIRTUAL_STRUCT_BIOMES = [
            ('Forteresse',            frozenset({'#cobblemon:is_overworld'}),  'Vanilla Minecraft',   frozenset({'mc:stronghold'})),
            ('Ruines',                frozenset({'#cobblemon:is_overworld'}),  'Cobblemon',           frozenset({'mc:ruin'})),
            ('Ruines (Arche)',        frozenset({'#cobblemon:is_overworld'}),  'Cobblemon',           frozenset({'mc:ruins/arch'})),
            ('Ruines (Luna Henge)',   frozenset({'#cobblemon:is_overworld'}),  'Cobblemon',           frozenset({'mc:ruins/luna_henge_ruins'})),
            ('Ruines (Sol Henge)',    frozenset({'#cobblemon:is_overworld'}),  'Cobblemon',           frozenset({'mc:ruins/sol_henge_ruins'})),
            ('Ruines (Stonjourner)',  frozenset({'#cobblemon:is_overworld'}),  'Cobblemon',           frozenset({'mc:ruins/stonjourner_henge_ruins'})),
            ('Forteresse Nether',     frozenset({'#cobblemon:is_nether'}),     'Vanilla Minecraft',   frozenset({'mc:nether_fortress'})),
            ('Vestige de bastion',    frozenset({'#cobblemon:is_nether'}),     'Vanilla Minecraft',   frozenset({'mc:bastion_remnant'})),
            ('Mineshaft',             frozenset({'#cobblemon:is_overworld'}),  'Vanilla Minecraft',   frozenset({'mc:mineshaft'})),
        ]

        def _struct_canonical_check(sid):
            return sid.lstrip('#').replace('cobblemon:', 'mc:').replace('minecraft:', 'mc:')

        # Biomes réels où la chaîne peut spawner
        # — exclure les regroupements "All ..." et les mods non autorisés
        target_biomes = []
        for bname, all_tags in real_biome_map.items():
            if bname.startswith('All '):
                continue
            if biome_mods.get(bname) not in ALLOWED_MODS:
                continue
            for s in all_spawns:
                if s['numero'] in chain and all_tags & s['tag_set'] and not (all_tags & s['excl_set']):
                    target_biomes.append((bname, all_tags))
                    break

        # Ajouter les biomes virtuels de structure si la chaîne y spawn
        for vname, vtags, vmod, vstruct_canons in VIRTUAL_STRUCT_BIOMES:
            # La chaîne doit avoir au moins un spawn avec ces structs dans cette dimension
            chain_has = any(
                s['numero'] in chain
                and vtags & s['tag_set']
                and bool({_struct_canonical_check(sid) for sid in s['struct_list']} & vstruct_canons)
                for s in all_spawns
            )
            if chain_has:
                target_biomes.append((vname, vtags, vmod, vstruct_canons))

        _msg = json.dumps({'type': 'init', 'chain': chain_names, 'total_biomes': len(target_biomes)})
        yield "data: " + _msg + "\n\n"

        results = []

        for i, biome_entry in enumerate(target_biomes):
            bname    = biome_entry[0]
            all_tags = biome_entry[1]
            bmod     = biome_entry[2] if len(biome_entry) > 2 else biome_mods.get(bname, '?')
            vstruct_filter = biome_entry[3] if len(biome_entry) > 3 else None

            if vstruct_filter:
                # Biome virtuel : pool = spawns dans cette dimension ET avec au moins une de ces structures
                in_biome = [s for s in all_spawns
                            if all_tags & s['tag_set']
                            and not (all_tags & s['excl_set'])
                            and s['has_required_struct']
                            and bool({_struct_canonical_check(sid) for sid in s['struct_list']} & vstruct_filter)]
            else:
                in_biome = [s for s in all_spawns
                            if all_tags & s['tag_set'] and not (all_tags & s['excl_set'])]
            if not in_biome: continue

            pct, total_base, total_filt, combo, filtered = _oracle_best_combo(in_biome, chain, is_virtual_biome=vstruct_filter is not None)
            if pct == 0: continue

            competitor_nums = frozenset(s['numero'] for s in filtered if s['numero'] not in chain)
            competitors_names = [num_to_name.get(n, '#' + str(n)) for n in sorted(competitor_nums)]

            # Fillers du biome dans le même contexte ET avec les mêmes EVs que la chaîne :
            # ce sont les seuls fillers inévitables dans ce setup précis.
            best_ctx  = combo.get('contexte')
            best_ev   = set(combo.get('ev', '').split(',')) if combo.get('ev') else set()
            # Tags du biome courant pour détecter Nether / End
            nether_tags = {'#cobblemon:is_nether'}
            end_tags    = {'#cobblemon:is_end'}
            is_nether_biome = bool(all_tags & nether_tags)
            is_end_biome    = bool(all_tags & end_tags)
            require_preset  = combo.get('require_preset')
            filler_nums = frozenset(
                s['numero'] for s in in_biome
                if s['is_filler'] and s['numero'] not in chain
                and (best_ctx is None or s['contexte'] == best_ctx)
                and (not best_ev or any(s['ev'].get(stat, 0) > 0 for stat in best_ev))
                # Les fillers n'apparaissent pas en pêche
                and best_ctx != 'fishing'
                # Les fillers n'apparaissent pas en treetop
                and require_preset != 'treetop'
                # Les fillers (is_overworld) ne spawnet pas dans le Nether ni l'End
                and not is_nether_biome
                and not is_end_biome
            )
            filler_names = [num_to_name.get(n, '#' + str(n)) for n in sorted(filler_nums)]

            # Pour les biomes virtuels, préparer les infos pour l'URL
            virtual_info = None
            if vstruct_filter is not None:
                dim_fr = 'Nether' if '#cobblemon:is_nether' in all_tags else 'Monde de surface'
                # Trouver le premier label FR de la structure
                struct_labels_virt = []
                for c in vstruct_filter:
                    # Essayer cobblemon: avec # en premier, puis minecraft: sans #
                    raw_cob_hash = '#cobblemon:' + c.replace('mc:', '')
                    raw_cob      = 'cobblemon:'  + c.replace('mc:', '')
                    raw_mc       = 'minecraft:'  + c.replace('mc:', '')
                    if raw_cob_hash in STRUCTURE_NAMES_FR:
                        _, lbl = STRUCTURE_NAMES_FR[raw_cob_hash]
                    elif raw_cob in STRUCTURE_NAMES_FR:
                        _, lbl = STRUCTURE_NAMES_FR[raw_cob]
                    elif raw_mc in STRUCTURE_NAMES_FR:
                        _, lbl = STRUCTURE_NAMES_FR[raw_mc]
                    else:
                        _, lbl = _structure_label(raw_mc)
                    if lbl not in struct_labels_virt:
                        struct_labels_virt.append(lbl)
                virtual_info = {
                    'dim_fr': dim_fr,
                    'struct_labels': struct_labels_virt,
                }

            result = {
                'biome_name':      bname,
                'biome_fr':        bname,
                'mod':             bmod,
                'virtual_info':    virtual_info,
                'pct':             pct,
                'raw_pct':         combo.pop('raw_pct', pct),
                'only_ultra':      combo.pop('only_ultra', False),
                'total_base':      total_base,
                'total_filtered':  total_filt,
                'target_spawns':   sum(1 for s in filtered if s['numero'] in chain),
                'combo':           combo,
                'competitors_names': competitors_names,
                'competitors_buckets': [s['bucket'] for s in filtered if s['numero'] not in chain],
                'filler_names':      filler_names,
            }
            results.append(result)
            def _sort_key(x):
                raw = x['raw_pct'] if 'raw_pct' in x else x['pct']
                # Le crépuscule dure ~30s dans Minecraft → pénalité forte sur le score affiché
                if x.get('combo', {}).get('farm_time') == 'dusk':
                    raw = raw * 0.25
                reduct = (x['total_base'] - x['total_filtered']) / x['total_base'] if x['total_base'] > 0 else 0
                return (-raw, -reduct)
            results_sorted = sorted(results, key=_sort_key)

            _msg = json.dumps({
                'type': 'update',
                'results': results_sorted[:50],
                'progress': i + 1,
                'total_biomes': len(target_biomes),
            })
            yield "data: " + _msg + "\n\n"

        yield "data: " + json.dumps({'type': 'done'}) + "\n\n"

    return app.response_class(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )



# ─────────────────────────────────────────────────────────
# FAVORIS
# ─────────────────────────────────────────────────────────

@app.route('/favorites')
def favorites_page():
    user_id = session.get('user_id')
    conn = get_db()
    favs = [dict(r) for r in conn.execute(
        "SELECT * FROM favorites WHERE firebase_uid = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()]
    conn.close()
    for fav in favs:
        try:
            params = json.loads(fav['url_params']) if fav['url_params'] else {}
        except Exception:
            params = {}
        fav['params'] = params
        from urllib.parse import urlencode
        qs = {'biome': fav['biome_name'], 'mod': fav.get('mod', '')}
        if params.get('ctx'):       qs['ctx']   = params['ctx']
        if params.get('ev'):        qs['ev']    = params['ev']
        if params.get('farm_time'): qs['time']  = params['farm_time']
        if params.get('incl_time'):
            it = params['incl_time'] if isinstance(params['incl_time'], list) else [params['incl_time']]
            if it: qs['time'] = it[0]
        if params.get('excl_weather'):
            ew = params['excl_weather']
            qs['excl_weather'] = ew[0] if isinstance(ew, list) else ew
        elif params.get('block_weather_excl'): qs['excl_weather'] = params['block_weather_excl']
        elif params.get('block_weather'):
            inv = {'clear':'rain','rain':'clear'}
            if inv.get(params['block_weather']): qs['excl_weather'] = inv[params['block_weather']]
        if params.get('struct_keep'): qs['struct_keep'] = params['struct_keep']
        excl_sp = []
        if params.get('no_struct_filter'):     excl_sp.append('structure')
        if params.get('block_sky') == 'open':  excl_sp.append('sky')
        elif params.get('block_sky') == 'covered': excl_sp.append('no_sky')
        if params.get('require_preset'): qs['incl_special'] = params['require_preset']
        if params.get('struct_keep_fr') or params.get('require_struct_fr'):
            qs['struct_keep'] = params.get('struct_keep_fr') or params.get('require_struct_fr')
        if params.get('block_presets'):   excl_sp.extend(params['block_presets'])
        if params.get('block_needed_blocks'): excl_sp += ['water','block']
        if params.get('block_base_blocks'):   excl_sp.append('base_block')
        if params.get('block_darkness'):      excl_sp.append('dark')
        if params.get('block_brightness'):    excl_sp.append('bright')
        if params.get('excl_special'):
            for v in (params['excl_special'] if isinstance(params['excl_special'], list) else [params['excl_special']]):
                excl_sp.append(v)
        if params.get('incl_special'):
            qs['incl_special'] = params['incl_special'] if isinstance(params['incl_special'], str) else ','.join(params['incl_special'])
        if params.get('excl_structures'):
            qs['excl_structures'] = '|'.join(params['excl_structures']) if isinstance(params['excl_structures'], list) else params['excl_structures']
        if excl_sp: qs['excl_special'] = ','.join(dict.fromkeys(excl_sp))
        if params.get('h_max') is not None:   qs.setdefault('hmax',  params['h_max'])
        if params.get('y_above') is not None: qs.setdefault('y_min', int(params['y_above']) + 1)
        if params.get('y_below') is not None: qs.setdefault('y_max', int(params['y_below']) - 1)
        if params.get('hmax') is not None:    qs.setdefault('hmax',  params['hmax'])
        if params.get('y_min') is not None:   qs.setdefault('y_min', params['y_min'])
        if params.get('y_max') is not None:   qs.setdefault('y_max', params['y_max'])
        fav['biome_url'] = '/spawns/biome-reel?' + urlencode(qs)
    return render_template('favorites.html', favorites=favs)


@app.route('/api/favorites', methods=['POST'])
def api_favorites_add():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'non connecté'}), 401
    data = request.get_json(force=True)
    label        = (data.get('label') or '').strip()[:120]
    pokemon_num  = int(data.get('pokemon_num', 0))
    pokemon_name = (data.get('pokemon_name') or '').strip()[:80]
    biome_name   = (data.get('biome_name') or '').strip()[:200]
    mod          = (data.get('mod') or '').strip()[:100]
    url_params   = json.dumps(data.get('url_params') or {})
    if not label or not biome_name or not pokemon_num:
        return jsonify({'error': 'données manquantes'}), 400
    conn = get_db()
    conn.execute(
        "INSERT INTO favorites (firebase_uid, label, pokemon_num, pokemon_name, biome_name, mod, url_params) VALUES (?,?,?,?,?,?,?)",
        (user_id, label, pokemon_num, pokemon_name, biome_name, mod, url_params)
    )
    conn.commit()
    fav_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({'ok': True, 'id': fav_id})


@app.route('/api/favorites/<int:fav_id>/rename', methods=['PATCH'])
def api_favorites_rename(fav_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'non connecté'}), 401
    data = request.get_json(force=True)
    label = (data.get('label') or '').strip()[:120]
    if not label:
        return jsonify({'error': 'label vide'}), 400
    conn = get_db()
    conn.execute("UPDATE favorites SET label = ? WHERE id = ? AND firebase_uid = ?",
                 (label, fav_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/favorites/<int:fav_id>', methods=['DELETE'])
def api_favorites_delete(fav_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'non connecté'}), 401
    conn = get_db()
    conn.execute("DELETE FROM favorites WHERE id = ? AND firebase_uid = ?", (fav_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)