import sqlite3 as _sqlite3, os as _os, sys as _sys

def _db_path():
    return _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "cobbledex.db")

# Groupes d'œufs par numéro de Pokédex
# Source : JSONs Cobblemon

def _load_egg_groups():
    out = {}
    try:
        conn = _sqlite3.connect(_db_path())
        for n, g in conn.execute(
                "SELECT numero, egg_group FROM pokemon_egg ORDER BY numero, slot"):
            out.setdefault(n, []).append(g)
        conn.close()
    except Exception as _e:
        print("EGG_GROUPS: lecture BD impossible (%s)" % _e, file=_sys.stderr)
    return out

EGG_GROUPS = _load_egg_groups()

def get_egg_groups(numero):
    return EGG_GROUPS.get(numero, [])