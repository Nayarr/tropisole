from flask import Flask, render_template, request, jsonify, abort
import sqlite3
import os
import math
from ev_yields import get_ev, EV_STAT_LABELS, EV_STAT_COLORS
from biome_mapping import (expand_spawn_biomes, expand_biomes_by_mod, get_mod_color,
                           BIOME_MAP, MOD_COLORS, get_all_real_biomes_sorted, get_tags_for_biome)

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
MOMENT_FR = {
    "any": "Tout moment",
    "day": "Jour",
    "night": "Nuit",
    "twilight": "Crépuscule",
    None: "—"
}
METEO_FR = {
    "any": "Tout temps",
    "clear": "Ensoleillé",
    "rain": "Pluie",
    None: "—"
}

@app.route("/")
def index():
    conn = get_db()

    buckets = [r[0] for r in conn.execute(
        "SELECT DISTINCT bucket FROM pokemon_spawns WHERE bucket IS NOT NULL ORDER BY bucket"
    ).fetchall()]
    moments = [r[0] for r in conn.execute(
        "SELECT DISTINCT moment FROM pokemon_spawns WHERE moment IS NOT NULL ORDER BY moment"
    ).fetchall()]
    conn.close()

    # Utilise les tags FR du BIOME_MAP comme options de filtre (triés alphabétiquement)
    all_biome_tags = sorted(BIOME_MAP.keys())

    return render_template("index.html",
                           buckets=buckets,
                           moments=moments,
                           all_biome_tags=all_biome_tags,
                           bucket_fr=BUCKET_FR,
                           moment_fr=MOMENT_FR)

@app.route("/api/pokemon")
def api_pokemon():
    search = request.args.get("q", "").strip()
    bucket = request.args.get("bucket", "")
    moment = request.args.get("moment", "")
    biome = request.args.get("biome", "")
    sort = request.args.get("sort", "numero")
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
    if moment:
        where_clauses.append("moment = ?")
        params.append(moment)
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
               GROUP_CONCAT(DISTINCT moment) as moment,
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
                           moment_fr=MOMENT_FR,
                           meteo_fr=METEO_FR,
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

    # Find all pokemon that spawn in ANY of the given biomes
    # Build LIKE conditions
    where_parts = " OR ".join(["biomes LIKE ?" for _ in biomes_list])
    params = [f"%{b}%" for b in biomes_list]

    rows = conn.execute(f"""
        SELECT numero, pokemon, bucket, poids, niveau_min, niveau_max, biomes, moment,
               contexte, lumiere_min, lumiere_max, peut_voir_ciel
        FROM pokemon_spawns
        WHERE {where_parts}
        ORDER BY numero
    """, params).fetchall()
    conn.close()

    # Group by numero : garder le poids max, collecter tous les contextes et profils de lumière uniques
    seen = {}
    for r in rows:
        key = r["numero"]
        if key not in seen:
            seen[key] = dict(r)
            seen[key]["contextes"] = set()
            seen[key]["lumiere_profils"] = set()
        else:
            if (r["poids"] or 0) > (seen[key]["poids"] or 0):
                d = dict(r)
                d["contextes"] = seen[key]["contextes"]
                d["lumiere_profils"] = seen[key]["lumiere_profils"]
                seen[key] = d
        if r["contexte"]:
            seen[key]["contextes"].add(r["contexte"])
        # Enregistrer ce profil lumière si non-trivial
        lmin = r["lumiere_min"]
        lmax = r["lumiere_max"]
        sky  = r["peut_voir_ciel"]
        if lmin is not None or lmax is not None or (sky and sky not in ("any", None)):
            seen[key]["lumiere_profils"].add((lmin, lmax, sky))

    pokemon_list = list(seen.values())
    for p in pokemon_list:
        p["contextes"] = sorted(p["contextes"])
        p["lumiere_profils"] = sorted(p["lumiere_profils"], key=lambda x: (x[0] or 0))

    # Enrich with EV data
    for p in pokemon_list:
        ev = get_ev(p["numero"])
        p["ev"] = ev
        p["ev_total"] = ev["total"]
        # Build EV string
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
                           moment_fr=MOMENT_FR,
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

    # Chercher tous les pokémon dont le champ biomes contient AU MOINS UN des tags FR
    where_parts = " OR ".join(["biomes LIKE ?" for _ in tags_fr])
    params = [f"%{t}%" for t in tags_fr]

    rows = conn.execute(f"""
        SELECT numero, pokemon, bucket, poids, niveau_min, niveau_max, biomes, moment,
               contexte, lumiere_min, lumiere_max, peut_voir_ciel
        FROM pokemon_spawns
        WHERE {where_parts}
        ORDER BY numero
    """, params).fetchall()
    conn.close()

    # Dédoublonner par numero, garder le poids le plus élevé, collecter contextes + profils lumière
    seen = {}
    for r in rows:
        key = r["numero"]
        if key not in seen:
            seen[key] = dict(r)
            seen[key]["contextes"] = set()
            seen[key]["lumiere_profils"] = set()
        else:
            if (r["poids"] or 0) > (seen[key]["poids"] or 0):
                d = dict(r)
                d["contextes"] = seen[key]["contextes"]
                d["lumiere_profils"] = seen[key]["lumiere_profils"]
                seen[key] = d
        if r["contexte"]:
            seen[key]["contextes"].add(r["contexte"])
        lmin = r["lumiere_min"]
        lmax = r["lumiere_max"]
        sky  = r["peut_voir_ciel"]
        if lmin is not None or lmax is not None or (sky and sky not in ("any", None)):
            seen[key]["lumiere_profils"].add((lmin, lmax, sky))

    pokemon_list = list(seen.values())
    for p in pokemon_list:
        p["contextes"] = sorted(p["contextes"])
        p["lumiere_profils"] = sorted(p["lumiere_profils"], key=lambda x: (x[0] or 0))

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
                           moment_fr=MOMENT_FR,
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