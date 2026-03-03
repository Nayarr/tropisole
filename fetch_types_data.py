"""
fetch_types_data.py
===================
Lance ce script DEPUIS ton propre PC (connexion internet requise).
Il récupère les types de tous les Pokémon présents dans la BDD
via PokéAPI, puis génère pokemon_types.py.

Usage :
    pip install requests
    python3 fetch_types_data.py
"""

import sqlite3
import requests
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cobbledex.db")
OUT_PATH = os.path.join(os.path.dirname(__file__), "pokemon_types.py")
POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon/"

# Mapping PokéAPI (anglais) → français
TYPE_FR = {
    "normal":   "Normal",
    "fire":     "Feu",
    "water":    "Eau",
    "electric": "Électrik",
    "grass":    "Plante",
    "ice":      "Glace",
    "fighting": "Combat",
    "poison":   "Poison",
    "ground":   "Sol",
    "flying":   "Vol",
    "psychic":  "Psy",
    "bug":      "Insecte",
    "rock":     "Roche",
    "ghost":    "Spectre",
    "dragon":   "Dragon",
    "dark":     "Ténèbres",
    "steel":    "Acier",
    "fairy":    "Fée",
}

def get_all_pokemon_numbers():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT DISTINCT numero FROM pokemon_spawns ORDER BY numero"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def fetch_types(numero):
    try:
        r = requests.get(f"{POKEAPI_BASE}{numero}", timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        types = sorted(data["types"], key=lambda t: t["slot"])
        return [TYPE_FR.get(t["type"]["name"], t["type"]["name"].capitalize()) for t in types]
    except Exception as e:
        print(f"  ⚠️  Erreur pour #{numero}: {e}")
        return None


def generate_pokemon_types_py(types_dict):
    lines = [
        "# Types par numéro de Pokédex",
        "# Données récupérées automatiquement depuis PokéAPI",
        "",
        "POKEMON_TYPES = {",
    ]
    for num in sorted(types_dict.keys()):
        t = types_dict[num]
        lines.append(f"    {num}: {t!r},")
    lines.append("}")
    lines.append("")
    lines.append("""
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
    \"\"\"Retourne la liste des types FR d'un Pokémon par son numéro.\"\"\"
    return POKEMON_TYPES.get(numero, [])


def get_type_color(type_fr):
    \"\"\"Retourne la couleur hex associée à un type FR.\"\"\"
    return TYPE_COLORS.get(type_fr, "#6a6a88")
""")
    return "\n".join(lines)


def main():
    print("🔵 Cobbledex — Récupération des types depuis PokéAPI")
    print("=" * 50)

    numbers = get_all_pokemon_numbers()
    print(f"📋 {len(numbers)} Pokémon à traiter\n")

    types_dict = {}
    not_found = []

    for i, num in enumerate(numbers):
        types = fetch_types(num)
        if types is None:
            not_found.append(num)
            types = []
        types_dict[num] = types
        print(f"  [{i+1:03d}/{len(numbers)}] #{num:04d} → {' / '.join(types) or '—'}")
        time.sleep(0.15)

    print(f"\n✅ Récupéré : {len(types_dict)} Pokémon")
    if not_found:
        print(f"⚠️  Introuvables : {not_found}")

    content = generate_pokemon_types_py(types_dict)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n💾 Fichier écrit : {OUT_PATH}")
    print("🚀 Relance app.py — le filtre par type est maintenant actif !")


if __name__ == "__main__":
    main()