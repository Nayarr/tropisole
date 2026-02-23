"""
fetch_ev_data.py
================
Lance ce script DEPUIS ton propre PC (connexion internet requise).
Il va récupérer les EVs de tous les Pokémon présents dans la BDD,
puis réécrire ev_yields.py avec les données exactes de PokéAPI.

Usage :
    pip install requests
    python3 fetch_ev_data.py
"""

import sqlite3
import requests
import time
import os
import re

DB_PATH = os.path.join(os.path.dirname(__file__), "cobbledex.db")
OUT_PATH = os.path.join(os.path.dirname(__file__), "ev_yields.py")
POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon/"

EV_STAT_MAP = {
    "hp":              "hp",
    "attack":          "atk",
    "defense":         "def",
    "special-attack":  "spa",
    "special-defense": "spd",
    "speed":           "spe",
}

STAT_LABELS = {
    "hp": "PV", "atk": "Attaque", "def": "Défense",
    "spa": "Att. Spé", "spd": "Déf. Spé", "spe": "Vitesse",
}

STAT_COLORS = {
    "hp":  "#ff6b81", "atk": "#ffa07a", "def": "#74b9ff",
    "spa": "#a29bfe", "spd": "#55efc4", "spe": "#e8ff47",
}


def get_all_pokemon_numbers():
    """Récupère tous les numéros uniques dans la BDD."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT DISTINCT numero FROM pokemon_spawns ORDER BY numero").fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def fetch_ev(numero):
    """Récupère les EVs d'un Pokémon depuis PokéAPI via son numéro."""
    try:
        url = f"{POKEAPI_BASE}{numero}"
        r = requests.get(url, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        ev = {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
        for stat in data["stats"]:
            key = EV_STAT_MAP.get(stat["stat"]["name"])
            if key:
                ev[key] = stat["effort"]
        return ev
    except Exception as e:
        print(f"  ⚠️  Erreur pour #{numero}: {e}")
        return None


def generate_ev_yields_py(ev_dict):
    lines = []
    lines.append('# EV yields par numéro de Pokédex')
    lines.append('# Données récupérées automatiquement depuis PokéAPI')
    lines.append('')
    lines.append('EV_YIELDS = {')
    for num in sorted(ev_dict.keys()):
        ev = ev_dict[num]
        lines.append(
            f'    {num}: {{"hp":{ev["hp"]},"atk":{ev["atk"]},"def":{ev["def"]},'
            f'"spa":{ev["spa"]},"spd":{ev["spd"]},"spe":{ev["spe"]}}},'
        )
    lines.append('}')
    lines.append('')
    lines.append('''
def get_ev(numero):
    """Retourne les EVs d\'un Pokémon par son numéro, avec total calculé."""
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
''')
    return '\n'.join(lines)


def main():
    print("🔵 Cobbledex — Récupération des EVs depuis PokéAPI")
    print("=" * 50)

    numbers = get_all_pokemon_numbers()
    print(f"📋 {len(numbers)} numéros de Pokémon à traiter\n")

    ev_dict = {}
    not_found = []
    zero_ev = []

    for i, num in enumerate(numbers):
        ev = fetch_ev(num)
        if ev is None:
            not_found.append(num)
            ev = {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}

        ev_dict[num] = ev
        total = sum(ev.values())
        stats_str = " + ".join(
            f"{v} {EV_STAT_MAP.get(k, k)}" for k, v in {
                "hp": ev["hp"], "atk": ev["atk"], "def": ev["def"],
                "spa": ev["spa"], "spd": ev["spd"], "spe": ev["spe"]
            }.items() if v > 0
        ) or "aucun"

        if total == 0:
            zero_ev.append(num)

        print(f"  [{i+1:03d}/{len(numbers)}] #{num:04d} → {stats_str} (total={total})")

        # Petite pause pour respecter l'API
        time.sleep(0.15)

    print(f"\n✅ Récupéré : {len(ev_dict)} Pokémon")
    if not_found:
        print(f"⚠️  Introuvables sur PokéAPI : {not_found}")
    if zero_ev:
        print(f"ℹ️  Pokémon sans EV : {len(zero_ev)} (Métamorph, Magicarpe, etc.)")

    # Écrire ev_yields.py
    content = generate_ev_yields_py(ev_dict)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n💾 Fichier écrit : {OUT_PATH}")
    print("🚀 Relance app.py — les EVs sont maintenant corrects !")


if __name__ == "__main__":
    main()