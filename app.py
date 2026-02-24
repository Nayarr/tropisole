from flask import Flask, render_template, request, jsonify, abort
import json
import sqlite3
import os
import math
from ev_yields import get_ev, EV_STAT_LABELS, EV_STAT_COLORS
from biome_mapping import (expand_spawn_biomes, expand_biomes_by_mod, get_mod_color,
                           BIOME_MAP, MOD_COLORS, get_all_real_biomes_sorted, get_tags_for_biome,
                           get_cobblemon_tags_for_fr_biomes)

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "cobbledex.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

BUCKET_ORDER = {"common": 1, "uncommon": 2, "rare": 3, "ultra-rare": 4}
BUCKET_FR = {
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
    "minecraft:village":            ("🏘️", "Village"),
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

    return render_template("index.html",
                           buckets=buckets,
                           times=times,
                           weathers=weathers,
                           all_biome_tags=all_biome_tags,
                           bucket_fr=BUCKET_FR,
                           time_fr=TIME_FR,
                           weather_fr=WEATHER_FR)

@app.route("/api/pokemon")
def api_pokemon():
    search = request.args.get("q", "").strip()
    bucket  = request.args.get("bucket", "")
    time    = request.args.get("time", "")
    weather = request.args.get("weather", "")
    biome   = request.args.get("biome", "")
    sort    = request.args.get("sort", "numero")
    order = request.args.get("order", "asc")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 40))

    conn = get_db()

    # Build query on aggregated pokemon view
    having_clauses = []
    params = []

    where_clauses = []
    if search:
        where_clauses.append("pokemon LIKE ?")
        params.append(f"%{search}%")
    if bucket:
        where_clauses.append("bucket = ?")
        params.append(bucket)
    if time:
        where_clauses.append("time = ?")
        params.append(time)
    if weather:
        where_clauses.append("weather = ?")
        params.append(weather)
    if biome:
        where_clauses.append("biomes LIKE ?")
        params.append(f"%{biome}%")

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

    # Count
    count_q = f"SELECT COUNT(*) FROM ({base_query})"
    total = conn.execute(count_q, params).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(base_query + f" LIMIT {per_page} OFFSET {offset}", params).fetchall()
    conn.close()

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
        })

    return jsonify({
        "data": result,
        "total": total,
        "page": page,
        "pages": math.ceil(total / per_page),
        "per_page": per_page,
    })

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
        s["biomes_expanded"] = expand_spawn_biomes(s["biomes"])
        s["biomes_exclus_expanded"] = expand_spawn_biomes(s["biomes_exclus"])
        s["biomes_by_mod"] = expand_biomes_by_mod(s["biomes"])
        s["biomes_exclus_by_mod"] = expand_biomes_by_mod(s["biomes_exclus"])
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

    return render_template("detail.html",
                           name=name,
                           numero=numero,
                           spawns=spawns,
                           prev_num=prev_row[0] if prev_row else None,
                           next_num=next_row[0] if next_row else None,
                           bucket_fr=BUCKET_FR,
                           time_fr=TIME_FR,
                           weather_fr=WEATHER_FR,
                           mod_colors=MOD_COLORS,
                           get_mod_color=get_mod_color)

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
    if cobblemon_tags:
        # On entoure le champ avec des virgules pour éviter les faux positifs de substring
        # (ex: is_cold ne doit pas matcher is_cold_ocean)
        where_parts = " OR ".join(
            ["(',' || biomes_tags || ',') LIKE ?" for _ in cobblemon_tags]
        )
        params = [f"%,{t},%" for t in cobblemon_tags]
    else:
        where_parts = " OR ".join(["biomes LIKE ?" for _ in biomes_list])
        params = [f"%{b}%" for b in biomes_list]

    rows = conn.execute(f"""
        SELECT numero, pokemon, bucket, poids, niveau_min, niveau_max, biomes, biomes_exclus,
               biomes_exclus_tags, time, weather, contexte, lumiere_min, lumiere_max,
               peut_voir_ciel, conditions, anticonditions, lune, structures, structures_exclu
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

        # Les entrées avec une structure requise spawnent uniquement dans cette structure,
        # pas dans n'importe quel biome portant le tag (ex: is_overworld + mansion ≠ partout).
        # On les exclut ici : la page /spawns/biome liste les co-spawns d'un même biome,
        # et les Pokémon de structure n'y apparaissent que s'ils partagent le même biome
        # ET la même structure (géré via la page détail).
        structures_raw = row["structures"]
        if structures_raw:
            import json as _json
            try:
                structs = _json.loads(structures_raw)
            except Exception:
                structs = []
            if structs:
                return True

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
                           get_mod_color=get_mod_color)

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

    cobblemon_tags_reel = get_cobblemon_tags_for_fr_biomes(tags_fr)

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
        SELECT numero, pokemon, bucket, poids, niveau_min, niveau_max, biomes, biomes_exclus,
               biomes_exclus_tags, time, weather, contexte, lumiere_min, lumiere_max,
               peut_voir_ciel, conditions, anticonditions, lune, structures, structures_exclu
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

        # Exclure les entrées qui requièrent une structure spécifique :
        # ces Pokémon ne peuvent pas spawner dans un biome quelconque,
        # sauf si le biome réel est directement dans leurs biomes_tags (ex: minecraft:frozen_river).
        structures_raw = row["structures"]
        if structures_raw:
            import json as _json
            try:
                structs = _json.loads(structures_raw)
            except Exception:
                structs = []
            if structs:
                # Si l'entrée a une structure requise, elle n'est valide pour ce biome réel
                # QUE si le biome ID minecraft littéral figure explicitement dans biomes_tags
                biomes_tags_str = row["biomes_tags"] or ""
                if minecraft_id not in biomes_tags_str:
                    return True

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
                           get_mod_color=get_mod_color)


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

if __name__ == "__main__":
    app.run(debug=True, port=5000)