import sqlite3 as _sqlite3, os as _os, sys as _sys

def _db_path():
    return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "cobbledex.db")

# EV yields par numéro de Pokédex
# Données récupérées automatiquement depuis PokéAPI

def _load_ev_yields():
    out = {}
    try:
        conn = _sqlite3.connect(_db_path())
        for n, hp, atk, df, spa, spd, spe in conn.execute(
                'SELECT numero, hp, atk, "def", spa, spd, spe FROM pokemon_ev'):
            out[n] = {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": spe}
        conn.close()
    except Exception as _e:
        print("EV_YIELDS: lecture BD impossible (%s)" % _e, file=_sys.stderr)
    return out

EV_YIELDS = _load_ev_yields()


def get_ev(numero):
    """Retourne les EVs d'un Pokémon par son numéro, avec total calculé."""
    if numero not in EV_YIELDS:
        return {"hp":0,"atk":0,"def":0,"spa":0,"spd":0,"spe":0,"total":0}
    ev = EV_YIELDS[numero].copy()
    ev["total"] = ev["hp"] + ev["atk"] + ev["def"] + ev["spa"] + ev["spd"] + ev["spe"]
    return ev

EV_STAT_LABELS = {
    "hp": "PV",
    "atk": "Attaque",
    "def": "Défense",
    "spa": "Att. Spé",
    "spd": "Déf. Spé",
    "spe": "Vitesse",
}

EV_STAT_COLORS = {
    "hp":  "#ff6b81",
    "atk": "#ffa07a",
    "def": "#74b9ff",
    "spa": "#a29bfe",
    "spd": "#55efc4",
    "spe": "#e8ff47",
}
