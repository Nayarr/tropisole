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

def enrich_spawn_conditions(spawn_dict):
    """Add parsed condition fields to a spawn dict for easy template use."""
    cond = parse_conditions(spawn_dict.get("conditions"))
    anticond = parse_conditions(spawn_dict.get("anticonditions"))
    spawn_dict["cond_parsed"] = cond
    spawn_dict["anticond_parsed"] = anticond
    # Ne pas écraser y_min/y_max s'ils ont déjà été calculés par agrégation
    if "y_min" not in spawn_dict:
        spawn_dict["y_min"] = cond.get("minY")
    if "y_max" not in spawn_dict:
        spawn_dict["y_max"] = cond.get("maxY")
    spawn_dict["needed_blocks"] = cond.get("neededNearbyBlocks", [])
    spawn_dict["base_blocks"] = cond.get("neededBaseBlocks", [])
    spawn_dict["min_lure"] = cond.get("minLureLevel")
    spawn_dict["max_lure"] = cond.get("maxLureLevel")
    spawn_dict["rod_type"] = cond.get("rodType")
    spawn_dict["bait"] = cond.get("bait")
    spawn_dict["is_slime_chunk"] = cond.get("isSlimeChunk", False)
    spawn_dict["max_light"] = cond.get("maxLight")
    spawn_dict["min_x"] = cond.get("minX")
    spawn_dict["max_x"] = cond.get("maxX")
    tags = []
    blocks = spawn_dict["needed_blocks"]
    if spawn_dict["y_max"] is not None and spawn_dict["y_max"] <= 0:
        tags.append({"icon": "⛏️", "label": f"Sous terre (Y ≤ {spawn_dict['y_max']})", "type": "depth"})
    elif spawn_dict["y_min"] is not None and spawn_dict["y_min"] > 50:
        tags.append({"icon": "🏔️", "label": f"En hauteur (Y ≥ {spawn_dict['y_min']})", "type": "height"})
    elif spawn_dict["y_min"] is not None or spawn_dict["y_max"] is not None:
        label = f"Y : {spawn_dict['y_min'] if spawn_dict['y_min'] is not None else '?'} → {spawn_dict['y_max'] if spawn_dict['y_max'] is not None else '?'}"
        tags.append({"icon": "📍", "label": label, "type": "y_range"})
    water_blocks = ["minecraft:water", "minecraft:water_source"]
    if any(b in water_blocks for b in blocks):
        tags.append({"icon": "🌊", "label": "Nécessite eau à proximité", "type": "water"})
    elif blocks:
        clean = [b.replace("minecraft:", "").replace("cobblemon:", "").replace("#", "").replace("_", " ") for b in blocks[:2]]
        tags.append({"icon": "🧱", "label": f"Blocs requis : {', '.join(clean)}", "type": "block"})
    if spawn_dict["base_blocks"]:
        clean = [b.replace("minecraft:", "").replace("#", "").replace("_", " ") for b in spawn_dict["base_blocks"][:2]]
        tags.append({"icon": "🪨", "label": f"Sol requis : {', '.join(clean)}", "type": "base_block"})
    if spawn_dict.get("is_slime_chunk"):
        tags.append({"icon": "🟩", "label": "Chunk à Slime requis", "type": "slime"})
    if spawn_dict.get("rod_type"):
        rod_name = spawn_dict["rod_type"].replace("cobblemon:", "").replace("_rod", " rod").replace("_", " ")
        tags.append({"icon": "🎣", "label": f"Canne : {rod_name}", "type": "fishing"})
    elif spawn_dict.get("min_lure") is not None:
        tags.append({"icon": "🎣", "label": f"Appât Niv.{spawn_dict['min_lure']}+ requis", "type": "fishing"})
    if spawn_dict.get("bait"):
        bait_name = spawn_dict["bait"].replace("cobblemon:", "").replace("_", " ")
        tags.append({"icon": "🪱", "label": f"Appât : {bait_name}", "type": "bait"})
    if spawn_dict.get("max_light") is not None:
        tags.append({"icon": "🌑", "label": f"Lumière ≤ {spawn_dict['max_light']}", "type": "dark"})
    if spawn_dict.get("min_x") == 0 and spawn_dict.get("max_x") == 0:
        tags.append({"icon": "🗺️", "label": "Centre du monde uniquement", "type": "x_zone"})
    spawn_dict["condition_tags"] = tags
    return spawn_dict


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

    # Source pokemon info
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

    # ── Résolution hiérarchique des tags Cobblemon ────────────────────────────
    # Pour chaque tag FR reçu, on remonte tous les tags parents Cobblemon.
    # Ex: 'Île tropicale' -> is_tropical_island + is_coast + is_ocean + is_overworld
    # Ainsi un pokemon tagué 'is_ocean' apparaît bien en 'Île tropicale'.
    cobblemon_tags = get_cobblemon_tags_for_fr_biomes(biomes_list)

    # Fallback : si aucun tag cobblemon connu, on reste sur le LIKE FR classique
    if cobblemon_tags:
        where_parts = " OR ".join(["biomes_tags LIKE ?" for _ in cobblemon_tags])
        params = [f"%{t}%" for t in cobblemon_tags]
    else:
        where_parts = " OR ".join(["biomes LIKE ?" for _ in biomes_list])
        params = [f"%{b}%" for b in biomes_list]
    # ─────────────────────────────────────────────────────────────────────────

    rows = conn.execute(f"""
        SELECT numero, pokemon, bucket, poids, niveau_min, niveau_max, biomes, biomes_exclus,
               biomes_exclus_tags, time, weather, contexte, lumiere_min, lumiere_max,
               peut_voir_ciel, conditions, anticonditions, lune, structures
        FROM pokemon_spawns
        WHERE {where_parts}
        ORDER BY numero
    """, params).fetchall()
    conn.close()

    # ── FILTRE biomes_exclus ──────────────────────────────────────────────────
    # On retire les Pokémon dont l'entrée exclut TOUS les biomes recherchés.
    # Ex: Carapuce en Eau douce EXCLU Glacial → on l'enlève si on cherche Glacial.
    def is_excluded_by_biomes(row, searched_tags, searched_biomes_fr):
        excl_tags = row["biomes_exclus_tags"] or ""
        excl_fr   = row["biomes_exclus"] or ""
        for tag in searched_tags:
            if tag and tag in excl_tags:
                return True
        for bio in searched_biomes_fr:
            if bio and bio in excl_fr:
                return True
        return False

    filtered_rows = [r for r in rows
                     if not is_excluded_by_biomes(r, cobblemon_tags, biomes_list)]
    # ─────────────────────────────────────────────────────────────────────────

    # Group by numero : garder le poids max, collecter contextes, time, weather, Y, conditions
    seen = {}
    for r in filtered_rows:
        key = r["numero"]
        cond = parse_conditions(r["conditions"])
        if key not in seen:
            seen[key] = dict(r)
            seen[key]["contextes"] = set()
            seen[key]["times"] = set()
            seen[key]["weathers"] = set()
            seen[key]["lumiere_profils"] = set()
            seen[key]["y_min_vals"] = []
            seen[key]["y_max_vals"] = []
            seen[key]["has_unrestricted_y"] = False
        else:
            if (r["poids"] or 0) > (seen[key]["poids"] or 0):
                d = dict(r)
                d["contextes"] = seen[key]["contextes"]
                d["times"] = seen[key]["times"]
                d["weathers"] = seen[key]["weathers"]
                d["lumiere_profils"] = seen[key]["lumiere_profils"]
                d["y_min_vals"] = seen[key]["y_min_vals"]
                d["y_max_vals"] = seen[key]["y_max_vals"]
                d["has_unrestricted_y"] = seen[key]["has_unrestricted_y"]
                seen[key] = d
        if r["contexte"]:
            seen[key]["contextes"].add(r["contexte"])
        if r["time"]:
            seen[key]["times"].add(r["time"])
        if r["weather"]:
            seen[key]["weathers"].add(r["weather"])
        lmin = r["lumiere_min"]
        lmax = r["lumiere_max"]
        sky  = r["peut_voir_ciel"]
        if lmin is not None or lmax is not None or (sky and sky not in ("any", None)):
            seen[key]["lumiere_profils"].add((lmin, lmax, sky))
        if "minY" in cond or "maxY" in cond:
            if "minY" in cond:
                seen[key]["y_min_vals"].append(cond["minY"])
            if "maxY" in cond:
                seen[key]["y_max_vals"].append(cond["maxY"])
        else:
            # Cette entrée n'a aucune contrainte Y → Pokémon accessible partout
            seen[key]["has_unrestricted_y"] = True

    pokemon_list = list(seen.values())
    for p in pokemon_list:
        p["contextes"] = sorted(p["contextes"])
        p["times"] = sorted(p["times"])
        p["weathers"] = sorted(p["weathers"])
        p["lumiere_profils"] = sorted(p["lumiere_profils"], key=lambda x: (x[0] or 0))
        # Si au moins une entrée n'a pas de contrainte Y → accessible à toute hauteur
        if p.get("has_unrestricted_y"):
            p["y_min"] = None
            p["y_max"] = None
        else:
            # Toutes les entrées ont des contraintes Y → range le plus permissif
            p["y_min"] = min(p["y_min_vals"]) if p["y_min_vals"] else None
            p["y_max"] = max(p["y_max_vals"]) if p["y_max_vals"] else None
        # Enrich conditions for display
        enrich_spawn_conditions(p)

    # Enrich with EV data
    for p in pokemon_list:
        ev = get_ev(p["numero"])
        p["ev"] = ev
        p["ev_total"] = ev["total"]
        parts = []
        for stat in ["hp","atk","def","spa","spd","spe"]:
            if ev[stat] > 0:
                parts.append(f"{ev[stat]} {EV_STAT_LABELS[stat]}")
        p["ev_str"] = " + ".join(parts) if parts else "—"

    # Sort by total EV descending
    pokemon_list.sort(key=lambda x: (-x["ev_total"], x["numero"]))

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
    """
    Filtre par biome réel (ex: 'Frozen Cliffs' de Terralith).
    Utilise REVERSE_BIOME_MAP pour retrouver les tags FR, puis filtre en BDD.
    """
    real_biome = request.args.get("biome", "").strip()
    mod = request.args.get("mod", "").strip()
    source_num = request.args.get("from", type=int)
    source_entry = request.args.get("entry", type=int)

    if not real_biome:
        abort(400)

    # Retrouver les tags FR qui contiennent ce biome réel
    tags_fr = get_tags_for_biome(real_biome)
    if not tags_fr:
        # Biome inconnu → on essaie quand même un LIKE direct sur le nom
        tags_fr = [real_biome]

    conn = get_db()

    # Source pokemon info
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

    # Résolution hiérarchique : tags FR -> tags Cobblemon bruts + parents
    cobblemon_tags_reel = get_cobblemon_tags_for_fr_biomes(tags_fr)
    if cobblemon_tags_reel:
        where_parts = " OR ".join(["biomes_tags LIKE ?" for _ in cobblemon_tags_reel])
        params = [f"%{t}%" for t in cobblemon_tags_reel]
    else:
        where_parts = " OR ".join(["biomes LIKE ?" for _ in tags_fr])
        params = [f"%{t}%" for t in tags_fr]

    rows = conn.execute(f"""
        SELECT numero, pokemon, bucket, poids, niveau_min, niveau_max, biomes, biomes_exclus,
               biomes_exclus_tags, time, weather, contexte, lumiere_min, lumiere_max,
               peut_voir_ciel, conditions, anticonditions, lune, structures
        FROM pokemon_spawns
        WHERE {where_parts}
        ORDER BY numero
    """, params).fetchall()
    conn.close()

    # ── FILTRE biomes_exclus ──────────────────────────────────────────────────
    def is_excluded_by_biomes(row, searched_tags, searched_biomes_fr):
        excl_tags = row["biomes_exclus_tags"] or ""
        excl_fr   = row["biomes_exclus"] or ""
        for tag in searched_tags:
            if tag and tag in excl_tags:
                return True
        for bio in searched_biomes_fr:
            if bio and bio in excl_fr:
                return True
        return False

    filtered_rows = [r for r in rows
                     if not is_excluded_by_biomes(r, cobblemon_tags_reel, tags_fr)]
    # ─────────────────────────────────────────────────────────────────────────

    seen = {}
    for r in filtered_rows:
        key = r["numero"]
        cond = parse_conditions(r["conditions"])
        if key not in seen:
            seen[key] = dict(r)
            seen[key]["contextes"] = set()
            seen[key]["times"] = set()
            seen[key]["weathers"] = set()
            seen[key]["lumiere_profils"] = set()
            seen[key]["y_min_vals"] = []
            seen[key]["y_max_vals"] = []
            seen[key]["has_unrestricted_y"] = False
        else:
            if (r["poids"] or 0) > (seen[key]["poids"] or 0):
                d = dict(r)
                d["contextes"] = seen[key]["contextes"]
                d["times"] = seen[key]["times"]
                d["weathers"] = seen[key]["weathers"]
                d["lumiere_profils"] = seen[key]["lumiere_profils"]
                d["y_min_vals"] = seen[key]["y_min_vals"]
                d["y_max_vals"] = seen[key]["y_max_vals"]
                d["has_unrestricted_y"] = seen[key]["has_unrestricted_y"]
                seen[key] = d
        if r["contexte"]:
            seen[key]["contextes"].add(r["contexte"])
        if r["time"]:
            seen[key]["times"].add(r["time"])
        if r["weather"]:
            seen[key]["weathers"].add(r["weather"])
        lmin = r["lumiere_min"]
        lmax = r["lumiere_max"]
        sky  = r["peut_voir_ciel"]
        if lmin is not None or lmax is not None or (sky and sky not in ("any", None)):
            seen[key]["lumiere_profils"].add((lmin, lmax, sky))
        if "minY" in cond or "maxY" in cond:
            if "minY" in cond:
                seen[key]["y_min_vals"].append(cond["minY"])
            if "maxY" in cond:
                seen[key]["y_max_vals"].append(cond["maxY"])
        else:
            seen[key]["has_unrestricted_y"] = True

    pokemon_list = list(seen.values())
    for p in pokemon_list:
        p["contextes"] = sorted(p["contextes"])
        p["times"] = sorted(p["times"])
        p["weathers"] = sorted(p["weathers"])
        p["lumiere_profils"] = sorted(p["lumiere_profils"], key=lambda x: (x[0] or 0))
        if p.get("has_unrestricted_y"):
            p["y_min"] = None
            p["y_max"] = None
        else:
            p["y_min"] = min(p["y_min_vals"]) if p["y_min_vals"] else None
            p["y_max"] = max(p["y_max_vals"]) if p["y_max_vals"] else None
        enrich_spawn_conditions(p)

    # Enrichir avec les EVs
    for p in pokemon_list:
        ev = get_ev(p["numero"])
        p["ev"] = ev
        p["ev_total"] = ev["total"]
        parts = []
        for stat in ["hp", "atk", "def", "spa", "spd", "spe"]:
            if ev[stat] > 0:
                parts.append(f"{ev[stat]} {EV_STAT_LABELS[stat]}")
        p["ev_str"] = " + ".join(parts) if parts else "—"

    pokemon_list.sort(key=lambda x: (-x["ev_total"], x["numero"]))

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