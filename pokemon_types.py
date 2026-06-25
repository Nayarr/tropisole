import sqlite3 as _sqlite3, os as _os, sys as _sys

def _db_path():
    return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "cobbledex.db")

# Types par numéro de Pokédex
# Données récupérées automatiquement depuis PokéAPI

def _load_pokemon_types():
    out = {}
    try:
        conn = _sqlite3.connect(_db_path())
        for n, t in conn.execute(
                "SELECT numero, type FROM pokemon_types ORDER BY numero, slot"):
            out.setdefault(n, []).append(t)
        conn.close()
    except Exception as _e:
        print("POKEMON_TYPES: lecture BD impossible (%s)" % _e, file=_sys.stderr)
    return out

POKEMON_TYPES = _load_pokemon_types()


TYPE_COLORS = {
    "Normal":   "#9ba0a8",
    "Feu":      "#ff7034",
    "Eau":      "#4d90d5",
    "Électrik": "#f4d23b",
    "Plante":   "#62bb5c",
    "Glace":    "#74cec0",
    "Combat":   "#ce4069",
    "Poison":   "#ab6ac8",
    "Sol":      "#d97846",
    "Vol":      "#8fa9e6",
    "Psy":      "#f97176",
    "Insecte":  "#90c12c",
    "Roche":    "#c9bb8a",
    "Spectre":  "#516aac",
    "Dragon":   "#0a6dc4",
    "Ténèbres": "#595761",
    "Acier":    "#5a8ea2",
    "Fée":      "#ec8fe6",
}

ALL_TYPES = [
    "Normal", "Feu", "Eau", "Électrik", "Plante", "Glace",
    "Combat", "Poison", "Sol", "Vol", "Psy", "Insecte",
    "Roche", "Spectre", "Dragon", "Ténèbres", "Acier", "Fée",
]


def get_types(numero):
    """Retourne la liste des types FR d'un Pokémon par son numéro."""
    return POKEMON_TYPES.get(numero, [])


def get_type_color(type_fr):
    """Retourne la couleur hex associée à un type FR."""
    return TYPE_COLORS.get(type_fr, "#6a6a88")
