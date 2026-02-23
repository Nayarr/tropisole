"""
create_db.py — reconstruit cobbledex.db depuis les fichiers JSON de spawn
Source de vérité : spawn_pool_world/*.json  (numéros pokédex nationaux corrects)
Noms FR          : Cobblemon_Spawns_1_7_1_FR.xlsx (avec fallback nom anglais)
"""

import sqlite3
import json
import os
import re
import glob
import pandas as pd

# ── Chemins ───────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(SCRIPT_DIR, "cobbledex.db")
JSON_DIR    = os.path.join(SCRIPT_DIR, "spawn_json", "spawn_pool_world")
XLSX_PATH   = os.path.join(SCRIPT_DIR, "Cobblemon_Spawns_1_7_1_FR.xlsx")

# ── Mapping tag Cobblemon -> tag FR (pour stocker les biomes en FR dans la BDD) ──
COBBLEMON_TAG_TO_FR = {
    "#cobblemon:is_arid":             "Aride",
    "#cobblemon:is_sandy":            "Aride",
    "#cobblemon:is_badlands":         "Terres arides",
    "#cobblemon:is_beach":            "Plage",
    "#cobblemon:is_coast":            "Côte",
    "#cobblemon:is_cold":             "Froid",
    "#cobblemon:is_cold_ocean":       "Océan froid",
    "#cobblemon:is_deep_dark":        "Abysses sombres",
    "#cobblemon:is_deep_ocean":       "Grand océan",
    "#cobblemon:is_desert":           "Désert",
    "#cobblemon:is_dripstone":        "Stalactites",
    "#cobblemon:is_end":              "Fin",
    "#cobblemon:is_floral":           "Floral",
    "#cobblemon:is_forest":           "Forêt",
    "#cobblemon:is_freezing":         "Glacial",
    "#cobblemon:is_freshwater":       "Eau douce",
    "#cobblemon:is_frozen_ocean":     "Océan gelé",
    "#cobblemon:is_glacial":          "Glaciaire",
    "#cobblemon:is_grassland":        "Prairie",
    "#cobblemon:is_highlands":        "Hautes terres",
    "#cobblemon:is_hills":            "Collines",
    "#cobblemon:is_island":           "Île",
    "#cobblemon:is_jungle":           "Jungle",
    "#cobblemon:is_lukewarm_ocean":   "Océan tiède",
    "#cobblemon:is_lush":             "Luxuriant",
    "#cobblemon:is_magical":          "Magique",
    "#cobblemon:is_mountain":         "Montagne",
    "#cobblemon:is_mushroom":         "Champignon",
    "#cobblemon:is_ocean":            "Océan",
    "#cobblemon:is_overworld":        "Monde de surface",
    "#cobblemon:is_peak":             "Sommet",
    "#cobblemon:is_plains":           "Plaines",
    "#cobblemon:is_plateau":          "Plateau",
    "#cobblemon:is_river":            "Rivière",
    "#cobblemon:is_savanna":          "Savane",
    "#cobblemon:is_shrubland":        "Maquis",
    "#cobblemon:is_sky":              "Ciel",
    "#cobblemon:is_snowy":            "Enneigé",
    "#cobblemon:is_snowy_forest":     "Forêt enneigée",
    "#cobblemon:is_snowy_taiga":      "Taïga enneigée",
    "#cobblemon:is_spooky":           "Effrayant",
    "#cobblemon:is_swamp":            "Marais",
    "#cobblemon:is_taiga":            "Taïga",
    "#cobblemon:is_temperate":        "Tempéré",
    "#cobblemon:is_temperate_ocean":  "Océan",
    "#cobblemon:is_thermal":          "Thermal",
    "#cobblemon:is_tropical_island":  "Île tropicale",
    "#cobblemon:is_tundra":           "Toundra",
    "#cobblemon:is_volcanic":         "Volcanique",
    "#cobblemon:is_warm_ocean":       "Océan chaud",
    "#cobblemon:nether/is_basalt":    "Nether basaltique",
    "#cobblemon:nether/is_crimson":   "Nether cramoisi",
    "#cobblemon:nether/is_desert":    "Désert du Nether",
    "#cobblemon:nether/is_forest":    "Forêt du Nether",
    "#cobblemon:nether/is_frozen":    "Nether gelé",
    "#cobblemon:nether/is_fungus":    "Nether fongique",
    "#cobblemon:nether/is_mountain":  "Montagne du Nether",
    "#cobblemon:nether/is_overgrowth":"Végétation du Nether",
    "#cobblemon:nether/is_quartz":    "Quartz du Nether",
    "#cobblemon:nether/is_soul_fire": "Nether feu de l'Âme",
    "#cobblemon:nether/is_soul_sand": "Nether sable de l'Âme",
    "#cobblemon:nether/is_toxic":     "Nether toxique",
    "#cobblemon:nether/is_warped":    "Nether distordu",
    "#cobblemon:nether/is_wasteland": "Terres dévastées du Nether",
    # Tags spéciaux mods
    "#aether:is_aether":              "Éther",
    "#minecraft:is_nether":           "Nether",
    "#the_bumblezone:the_bumblezone": "Bumblezone",
    # Biomes directs (non-tag)
    "aether:skyroot_forest":          "Éther",
    "aether:skyroot_grove":           "Éther",
    "aether:skyroot_meadow":          "Éther",
    "aether:skyroot_woodland":        "Éther",
    "biomesoplenty:crystalline_chasm":"Canyon de cristal",
    "byg:warped_desert":              "Désert distordu",
    "minecraft:frozen_river":         "Rivière gelée",
    "minecraft:mushroom_fields":      "Champs de champignons",
    "minecraft:snowy_beach":          "Plage enneigée",
    "minecraft:sunflower_plains":     "Plaines de tournesols",
    "the_bumblezone:crystal_canyon":  "Bumblezone",
    "the_bumblezone:floral_meadow":   "Bumblezone",
    "the_bumblezone:howling_constructs": "Constructions hurlantes",
    "the_bumblezone:pollinated_fields": "Champs pollinisés",
    "#cobblemon:has_block/mud":       "Boueux",
}

def biomes_to_fr(biome_list):
    """Convertit une liste de tags cobblemon en chaîne de tags FR (dédoublonnés)."""
    if not biome_list:
        return None
    seen = []
    for b in biome_list:
        fr = COBBLEMON_TAG_TO_FR.get(b, b)  # fallback = tag brut
        if fr not in seen:
            seen.append(fr)
    return ", ".join(seen)


def parse_level(level_str):
    """Parse '5-31' -> (5, 31)."""
    if not level_str:
        return None, None
    m = re.match(r"(\d+)-(\d+)", str(level_str))
    if m:
        return int(m.group(1)), int(m.group(2))
    try:
        v = int(level_str)
        return v, v
    except Exception:
        return None, None


# Corrections manuelles : erreurs détectées dans le xlsx
# (numéro national -> nom FR correct)
FR_NAME_CORRECTIONS = {
    342: "Crabagarre",   # Crawdaunt : xlsx avait ce nom sur #692 par erreur
    692: "Flingouste",   # Clauncher : absent du xlsx, nom FR officiel
}

def build_fr_name_map():
    """Construit un mapping num_pokédex -> nom_FR depuis le xlsx + corrections manuelles."""
    if not os.path.exists(XLSX_PATH):
        print(f"  ⚠️  xlsx introuvable ({XLSX_PATH}), noms anglais utilisés comme fallback")
        return dict(FR_NAME_CORRECTIONS)

    df = pd.read_excel(XLSX_PATH)
    mapping = {}
    for _, row in df.iterrows():
        num = row.get("No.")
        name = row.get("Pokémon")
        if pd.notna(num) and pd.notna(name):
            num = int(num)
            if num not in mapping:
                mapping[num] = str(name)

    # Appliquer les corrections manuelles (écrasent les erreurs du xlsx)
    for num, correct_name in FR_NAME_CORRECTIONS.items():
        old = mapping.get(num, "ABSENT")
        mapping[num] = correct_name
        print(f"  🔧 Correction #{num:04d} : '{old}' -> '{correct_name}'")

    return mapping


def parse_pokemon_field(raw):
    """
    Parse le champ 'pokemon' du JSON.
    Ex: 'squirtle'                          -> ('squirtle', None)
        'rattata'                           -> ('rattata', None)
        'corsola galarian'                  -> ('corsola', 'galarian')
        'dudunsparce landsnake_form=two-segment' -> ('dudunsparce', 'landsnake_form=two-segment')
    Retourne (nom_base, forme_str|None)
    """
    raw = raw.strip()
    parts = raw.split(" ", 1)
    base = parts[0]
    forme = parts[1] if len(parts) > 1 else None
    return base, forme


def create_database():
    print("🔵 Reconstruction de cobbledex.db depuis les JSON de spawn")
    print("=" * 60)

    # Noms FR depuis xlsx
    fr_map = build_fr_name_map()
    print(f"  📖 {len(fr_map)} noms FR chargés depuis le xlsx")

    # Fichiers JSON
    json_files = sorted(glob.glob(os.path.join(JSON_DIR, "*.json")))
    print(f"  📂 {len(json_files)} fichiers JSON trouvés")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS pokemon_spawns")
    c.execute("""
        CREATE TABLE pokemon_spawns (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            numero           INTEGER,
            pokemon          TEXT,
            pokemon_en       TEXT,
            forme            TEXT,
            entree           INTEGER,
            bucket           TEXT,
            poids            REAL,
            niveau_min       INTEGER,
            niveau_max       INTEGER,
            biomes           TEXT,
            biomes_tags      TEXT,
            biomes_exclus    TEXT,
            biomes_exclus_tags TEXT,
            time             TEXT,
            weather          TEXT,
            multiplicateurs  TEXT,
            contexte         TEXT,
            presets          TEXT,
            conditions       TEXT,
            anticonditions   TEXT,
            lumiere_min      REAL,
            lumiere_max      REAL,
            peut_voir_ciel   TEXT,
            pattern          TEXT,
            structures       TEXT,
            structures_exclu TEXT,
            lune             TEXT,
            est_actif        INTEGER DEFAULT 1
        )
    """)
    conn.commit()

    total_rows = 0
    skipped_files = 0
    name_fallbacks = []

    for fpath in json_files:
        fname = os.path.basename(fpath).replace(".json", "")
        m = re.match(r"^(\d+)_(.+)$", fname)
        if not m:
            skipped_files += 1
            continue

        numero = int(m.group(1))
        if numero == 0:
            # Fichiers spéciaux type pidgey_herd etc., on skip
            skipped_files += 1
            continue

        with open(fpath, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"  ⚠️  JSON invalide : {fname} ({e})")
                skipped_files += 1
                continue

        if not data.get("enabled", True):
            continue

        spawns = data.get("spawns", [])
        entree = 0

        for s in spawns:
            if s.get("type") != "pokemon":
                continue

            entree += 1
            pokemon_raw = s.get("pokemon", "")
            name_base, forme = parse_pokemon_field(pokemon_raw)

            # Nom FR
            nom_fr = fr_map.get(numero)
            if nom_fr is None:
                nom_fr = name_base  # fallback anglais
                name_fallbacks.append((numero, name_base))

            # Nettoyage nom FR si forme régionale (ex: "Rattata [Alolan]" dans xlsx)
            # On garde le nom de base FR sans la forme car la forme est dans la colonne dédiée
            nom_fr_base = nom_fr.split(" [")[0].split(" (")[0]

            cond   = s.get("condition", {})
            acond  = s.get("anticondition", {})

            niveau_min, niveau_max = parse_level(s.get("level"))

            biomes_fr       = biomes_to_fr(cond.get("biomes", []))
            biomes_excl_fr  = biomes_to_fr(acond.get("biomes", []))
            # Tags bruts (pour la résolution hiérarchique dans les requêtes)
            biomes_tags_raw      = ",".join(cond.get("biomes", [])) or None
            biomes_excl_tags_raw = ",".join(acond.get("biomes", [])) or None

            moment = cond.get("timeRange")
            meteo  = None
            if cond.get("isRaining") is True:
                meteo = "rain"
            elif cond.get("isRaining") is False:
                meteo = "clear"

            # Multiplicateurs (stocker en JSON string)
            mult = s.get("weightMultipliers") or s.get("weightMultiplier")
            mult_str = json.dumps(mult, ensure_ascii=False) if mult else None

            # presets
            presets = s.get("presets", [])
            presets_str = ", ".join(presets) if presets else None

            # Conditions supplémentaires (blocs, Y, lure...)
            extra_cond = {k: v for k, v in cond.items()
                          if k not in ("biomes", "timeRange", "isRaining",
                                       "canSeeSky", "minSkyLight", "maxSkyLight",
                                       "structures", "moonPhase")}
            extra_acond = {k: v for k, v in acond.items()
                           if k not in ("biomes", "structures")}
            cond_str  = json.dumps(extra_cond,  ensure_ascii=False) if extra_cond  else None
            acond_str = json.dumps(extra_acond, ensure_ascii=False) if extra_acond else None

            # Structures
            structures      = cond.get("structures")
            structures_excl = acond.get("structures")
            structures_str      = json.dumps(structures,      ensure_ascii=False) if structures      else None
            structures_excl_str = json.dumps(structures_excl, ensure_ascii=False) if structures_excl else None

            lune = cond.get("moonPhase")
            lune_str = str(lune) if lune is not None else None

            peut_voir_ciel = cond.get("canSeeSky")
            if peut_voir_ciel is True:
                pvc_str = "true"
            elif peut_voir_ciel is False:
                pvc_str = "false"
            else:
                pvc_str = None

            c.execute("""
                INSERT INTO pokemon_spawns (
                    numero, pokemon, pokemon_en, forme, entree,
                    bucket, poids, niveau_min, niveau_max,
                    biomes, biomes_tags, biomes_exclus, biomes_exclus_tags,
                    time, weather,
                    multiplicateurs, contexte, presets,
                    conditions, anticonditions,
                    lumiere_min, lumiere_max, peut_voir_ciel,
                    structures, structures_exclu, lune, est_actif
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                numero,
                nom_fr_base,
                name_base,
                forme,
                entree,
                s.get("bucket"),
                s.get("weight"),
                niveau_min,
                niveau_max,
                biomes_fr,
                biomes_tags_raw,
                biomes_excl_fr,
                biomes_excl_tags_raw,
                moment,       # -> colonne time
                meteo,        # -> colonne weather
                mult_str,
                s.get("spawnablePositionType"),
                presets_str,
                cond_str,
                acond_str,
                cond.get("minSkyLight"),
                cond.get("maxSkyLight"),
                pvc_str,
                structures_str,
                structures_excl_str,
                lune_str,
                1,
            ))
            total_rows += 1

    conn.commit()

    # Index
    c.execute("CREATE INDEX idx_numero  ON pokemon_spawns(numero)")
    c.execute("CREATE INDEX idx_pokemon ON pokemon_spawns(pokemon)")
    c.execute("CREATE INDEX idx_bucket  ON pokemon_spawns(bucket)")
    c.execute("CREATE INDEX idx_context ON pokemon_spawns(contexte)")
    conn.commit()
    conn.close()

    unique_pokemon = len(set())
    print(f"\n✅ Base reconstruite :")
    print(f"   {total_rows} entrées de spawn insérées")
    print(f"   {skipped_files} fichiers ignorés (désactivés / format spécial)")
    if name_fallbacks:
        unique_fallbacks = list(dict.fromkeys(name_fallbacks))
        print(f"   ⚠️  {len(unique_fallbacks)} pokémon sans nom FR (nom anglais utilisé) :")
        for num, en in unique_fallbacks:
            print(f"      #{num:04d} {en}")


if __name__ == "__main__":
    create_database()