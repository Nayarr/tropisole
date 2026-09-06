# -*- coding: utf-8 -*-
"""Importe les données de spawn Cobblemon 1.8 dans pokemon_spawns.

Trois sources, fusionnées dans la même table (colonne `spawn_kind`) :
  - world    : spawn_pool_world/*.json          (spawns classiques)
  - herd     : spawn_pool_world/herds/*.json    (hordes et alphas, aplaties)
  - habitat  : habitat_pools/*.json             (pools de Habitat Block)

Remplace intégralement le contenu 1.7. Une sauvegarde de l'ancienne table est
conservée dans pokemon_spawns_17 (écrasée à chaque exécution).

Usage :
    python import_spawns_18.py --dry-run     # analyse sans rien écrire
    python import_spawns_18.py               # importe
"""
import sys, io, os, json, glob, sqlite3, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

DRY = "--dry-run" in sys.argv

DL = "C:/Users/rayan/Downloads"
SP = DL + "/cobblemon-1.8.0-common-src-main-resources-data-cobblemon-spawn_pool_world/common/src/main/resources/data/cobblemon/spawn_pool_world"
HP = DL + "/cobblemon-1.8.0-common-src-main-resources-data-cobblemon-habitat_pools/common/src/main/resources/data/cobblemon/habitat_pools"
JAR = "C:/Users/rayan/AppData/Roaming/ModrinthApp/profiles/Cobblemon 1.8 Creator Day 1.0.1/mods/Promo-Cobblemon-fabric-1.8.0b16092+1.21.1-HEAD-844c03b.jar"

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cobbledex.db")

# Conditions extraites vers des colonnes dédiées : à ne pas redupliquer dans le JSON
COND_EXTRAITES = {"biomes", "timeRange", "minSkyLight", "maxSkyLight",
                  "isRaining", "canSeeSky", "structures", "moonPhase"}
ANTI_EXTRAITES = {"biomes", "structures"}


# ── Référentiels ──────────────────────────────────────────────────────────────

def charger_noms_fr():
    """pokemon_en -> nom FR. Priorité à la BD existante (cohérence des favoris),
    complétée par le lang fr_fr de Cobblemon pour les nouvelles espèces."""
    noms = {}
    conn = sqlite3.connect(DB)
    for en, fr in conn.execute(
            "SELECT DISTINCT lower(pokemon_en), pokemon FROM pokemon_spawns "
            "WHERE pokemon_en IS NOT NULL AND pokemon IS NOT NULL"):
        noms.setdefault(en, fr)
    conn.close()
    avant = len(noms)
    try:
        import zipfile
        z = zipfile.ZipFile(JAR)
        lang = json.loads(z.read("assets/cobblemon/lang/fr_fr.json"))
        for k, v in lang.items():
            if k.startswith("cobblemon.species.") and k.endswith(".name"):
                noms.setdefault(k[len("cobblemon.species."):-len(".name")].lower(), v)
    except Exception as e:
        print("  (lang fr_fr indisponible : %s)" % e)
    print("noms FR : %d depuis la BD, %d au total" % (avant, len(noms)))
    return noms


def charger_numeros():
    """pokemon_en -> numéro national, depuis les noms de fichiers puis la BD."""
    num = {}
    for f in glob.glob(SP + "/*.json"):
        b = os.path.basename(f)[:-5]          # 0001_bulbasaur
        if "_" in b and b.split("_")[0].isdigit():
            n, _, nom = b.partition("_")
            num[nom.lower()] = int(n)
    conn = sqlite3.connect(DB)
    for en, n in conn.execute(
            "SELECT DISTINCT lower(pokemon_en), numero FROM pokemon_spawns"):
        if en:
            num.setdefault(en, n)
    conn.close()
    return num


# ── Utilitaires de conversion ─────────────────────────────────────────────────

def split_espece(champ, connus=None):
    """'venusaur held_item=x alpha=true' -> ('venusaur', 'held_item=x alpha=true')

    Tolère deux anomalies présentes dans les données Cobblemon :
      - un id préfixé par son namespace ('cobblemon:geodude') ;
      - une espèce collée à son aspect, espace manquant
        ('pangoroheld_item=cobblemon:fighting_gem') — on retrouve alors
        l'espèce comme le plus long préfixe connu.
    """
    if not champ:
        return None, None
    parties = champ.strip().split(" ")
    tete = parties[0].lower()
    if tete.startswith("cobblemon:"):
        tete = tete[len("cobblemon:"):]
    reste = " ".join(parties[1:]) or None
    if connus and tete not in connus and "=" in tete:
        for i in range(len(tete) - 1, 2, -1):
            if tete[:i] in connus:
                suffixe = tete[i:]
                reste = (suffixe + (" " + reste if reste else "")).strip()
                tete = tete[:i]
                break
    return tete, reste


def split_niveau(txt):
    if not txt:
        return None, None
    txt = str(txt)
    if "-" in txt:
        a, _, b = txt.partition("-")
        try:
            return int(a), int(b)
        except ValueError:
            return None, None
    try:
        v = int(txt)
        return v, v
    except ValueError:
        return None, None


def labels_fr(tags, cob_to_fr):
    """['#cobblemon:is_jungle'] -> 'Jungle'"""
    out = []
    for t in tags or []:
        fr = cob_to_fr.get(t)
        if fr is None and t == "#minecraft:is_nether":
            fr = "Nether"
        lbl = fr or t
        if lbl not in out:
            out.append(lbl)
    return ", ".join(out) or None


def ligne_commune(s, cob_to_fr):
    """Champs partagés par les trois sources, extraits d'une entrée de spawn."""
    cond = s.get("condition") or {}
    anti = s.get("anticondition") or {}
    reste_cond = {k: v for k, v in cond.items() if k not in COND_EXTRAITES}
    reste_anti = {k: v for k, v in anti.items() if k not in ANTI_EXTRAITES}
    meteo = None
    if "isRaining" in cond:
        meteo = "rain" if cond["isRaining"] else "clear"
    wm = s.get("weightMultiplier") or s.get("weightMultipliers")
    return {
        "biomes":             labels_fr(cond.get("biomes"), cob_to_fr),
        "biomes_tags":        ",".join(cond.get("biomes") or []) or None,
        "biomes_exclus":      labels_fr(anti.get("biomes"), cob_to_fr),
        "biomes_exclus_tags": ",".join(anti.get("biomes") or []) or None,
        "time":               cond.get("timeRange"),
        "weather":            meteo,
        "multiplicateurs":    json.dumps(wm, ensure_ascii=False) if wm else None,
        "contexte":           s.get("spawnablePositionType"),
        "presets":            ", ".join(s.get("presets") or []) or None,
        "conditions":         json.dumps(reste_cond, ensure_ascii=False) if reste_cond else None,
        "anticonditions":     json.dumps(reste_anti, ensure_ascii=False) if reste_anti else None,
        "lumiere_min":        cond.get("minSkyLight"),
        "lumiere_max":        cond.get("maxSkyLight"),
        "peut_voir_ciel":     None if "canSeeSky" not in cond else ("true" if cond["canSeeSky"] else "false"),
        "structures":         json.dumps(cond.get("structures"), ensure_ascii=False) if cond.get("structures") else None,
        "structures_exclu":   json.dumps(anti.get("structures"), ensure_ascii=False) if anti.get("structures") else None,
        "lune":               str(cond["moonPhase"]) if cond.get("moonPhase") is not None else None,
    }


# ── Collecte ──────────────────────────────────────────────────────────────────

def collecter(noms_fr, numeros, cob_to_fr):
    lignes = []
    inconnus = collections.Counter()

    def ajouter(en, forme, base, extra):
        num = numeros.get(en)
        if num is None:
            inconnus[en] += 1
            return
        r = dict(base)
        r.update(extra)
        r["numero"] = num
        r["pokemon"] = noms_fr.get(en, en.title())
        r["pokemon_en"] = en
        r["forme"] = forme
        lignes.append(r)

    # 1. monde
    for f in sorted(glob.glob(SP + "/*.json")):
        for s in json.load(open(f, encoding="utf-8")).get("spawns", []):
            en, forme = split_espece(s.get("pokemon"), numeros)
            if not en:
                continue
            nmin, nmax = split_niveau(s.get("level") or s.get("levelRange"))
            ajouter(en, forme, ligne_commune(s, cob_to_fr), {
                "bucket": s.get("bucket"), "poids": s.get("weight"),
                "niveau_min": nmin, "niveau_max": nmax,
                "spawn_kind": "world", "habitat": None, "phases": None,
                "herd_id": None, "herd_role": None,
                "herd_max_times": None, "herd_size": None,
            })

    # 2. hordes — une ligne par Pokémon, poids réparti selon la composition
    for f in sorted(glob.glob(SP + "/herds/*.json")):
        for s in json.load(open(f, encoding="utf-8")).get("spawns", []):
            membres = s.get("herdablePokemon") or []
            total = sum(float(h.get("weight") or 0) for h in membres) or 1.0
            base = ligne_commune(s, cob_to_fr)
            for h in membres:
                en, forme = split_espece(h.get("pokemon"), numeros)
                if not en:
                    continue
                nmin, nmax = split_niveau(h.get("levelRange") or s.get("levelRange"))
                # P(la horde sort) x P(c'est cette espèce dans la horde)
                poids = float(s.get("weight") or 0) * (float(h.get("weight") or 0) / total)
                ajouter(en, forme, base, {
                    "bucket": s.get("bucket"), "poids": round(poids, 6),
                    "niveau_min": nmin, "niveau_max": nmax,
                    "spawn_kind": "herd", "habitat": None, "phases": None,
                    "herd_id": s.get("id"),
                    "herd_role": "leader" if h.get("isLeader") else "follower",
                    "herd_max_times": h.get("maxTimes"),
                    "herd_size": s.get("maxHerdSize"),
                })

    # 3. habitats — chaque habitat est un pseudo-biome
    for f in sorted(glob.glob(HP + "/*.json")):
        hid = os.path.basename(f)[:-5]
        libelle = hid.replace("_", " ").title()
        tag = "#habitat:" + hid
        for s in json.load(open(f, encoding="utf-8")).get("spawns", []):
            en, forme = split_espece(s.get("species"), numeros)
            if not en:
                continue
            nmin, nmax = split_niveau(s.get("levelRange"))
            mods = s.get("modifiers")
            ajouter(en, forme or (mods if isinstance(mods, str) else None), {
                "biomes": libelle, "biomes_tags": tag,
                "biomes_exclus": None, "biomes_exclus_tags": None,
                "time": s.get("timeRange"), "weather": None,
                "multiplicateurs": None,
                "contexte": s.get("spawnablePositionType"),
                "presets": None,
                "conditions": json.dumps({"maxLight": s["maxLight"]}, ensure_ascii=False)
                              if s.get("maxLight") is not None else None,
                "anticonditions": None,
                "lumiere_min": None, "lumiere_max": None,
                "peut_voir_ciel": None, "structures": None,
                "structures_exclu": None, "lune": None,
            }, {
                "bucket": s.get("bucket"), "poids": s.get("weight"),
                "niveau_min": nmin, "niveau_max": nmax,
                "spawn_kind": "habitat", "habitat": hid,
                "phases": s.get("phases"),
                "herd_id": None, "herd_role": None,
                "herd_max_times": None, "herd_size": None,
            })

    # numéro d'entrée séquentiel par Pokémon
    compteur = collections.Counter()
    for r in lignes:
        compteur[r["numero"]] += 1
        r["entree"] = compteur[r["numero"]]
    return lignes, inconnus


COLS = ["numero", "pokemon", "pokemon_en", "forme", "entree", "bucket", "poids",
        "niveau_min", "niveau_max", "biomes", "biomes_tags", "biomes_exclus",
        "biomes_exclus_tags", "time", "weather", "multiplicateurs", "contexte",
        "presets", "conditions", "anticonditions", "lumiere_min", "lumiere_max",
        "peut_voir_ciel", "pattern", "structures", "structures_exclu", "lune",
        "est_actif", "spawn_kind", "habitat", "phases", "herd_id", "herd_role",
        "herd_max_times", "herd_size"]

DDL = """
CREATE TABLE pokemon_spawns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER, pokemon TEXT, pokemon_en TEXT, forme TEXT, entree INTEGER,
    bucket TEXT, poids REAL, niveau_min INTEGER, niveau_max INTEGER,
    biomes TEXT, biomes_tags TEXT, biomes_exclus TEXT, biomes_exclus_tags TEXT,
    time TEXT, weather TEXT, multiplicateurs TEXT, contexte TEXT, presets TEXT,
    conditions TEXT, anticonditions TEXT, lumiere_min REAL, lumiere_max REAL,
    peut_voir_ciel TEXT, pattern TEXT, structures TEXT, structures_exclu TEXT,
    lune TEXT, est_actif INTEGER DEFAULT 1,
    spawn_kind TEXT, habitat TEXT, phases TEXT,
    herd_id TEXT, herd_role TEXT, herd_max_times INTEGER, herd_size INTEGER
)
"""


def main():
    import biome_mapping as bm
    cob_to_fr = bm.COBBLEMON_TAG_TO_FR

    noms_fr = charger_noms_fr()
    numeros = charger_numeros()
    lignes, inconnus = collecter(noms_fr, numeros, cob_to_fr)

    par_kind = collections.Counter(r["spawn_kind"] for r in lignes)
    print("\nlignes générées : %d" % len(lignes))
    for k, n in par_kind.most_common():
        print("   %-8s %5d" % (k, n))
    print("espèces distinctes : %d" % len({r["pokemon_en"] for r in lignes}))
    print("buckets : %s" % dict(collections.Counter(r["bucket"] for r in lignes)))
    if inconnus:
        print("\n⚠ espèces sans numéro national (ignorées) : %d" % len(inconnus))
        for en, n in inconnus.most_common(20):
            print("     %-24s %d lignes" % (en, n))

    if DRY:
        print("\n--dry-run : rien écrit.")
        return

    conn = sqlite3.connect(DB)
    conn.execute("DROP TABLE IF EXISTS pokemon_spawns_17")
    conn.execute("ALTER TABLE pokemon_spawns RENAME TO pokemon_spawns_17")
    conn.execute(DDL)
    conn.executemany(
        "INSERT INTO pokemon_spawns (%s) VALUES (%s)" % (
            ",".join(COLS), ",".join("?" * len(COLS))),
        [[r.get(c, 1 if c == "est_actif" else None) for c in COLS] for r in lignes])
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM pokemon_spawns").fetchone()[0]
    old = conn.execute("SELECT COUNT(*) FROM pokemon_spawns_17").fetchone()[0]
    conn.close()
    print("\nimporté : %d lignes (ancienne table conservée : pokemon_spawns_17, %d lignes)" % (n, old))


if __name__ == "__main__":
    main()
