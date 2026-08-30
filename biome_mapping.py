# Données de référence chargées depuis biomes.json (source unique de vérité).
# Pour modifier les biomes/tags/mods : éditer biomes.json, pas ce fichier.
import json as _json, os as _os

_DATA = _json.load(open(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "biomes.json"),
    encoding="utf-8"))

# Mapping exact des tags Cobblemon → biomes réels
# Source : Wiki officiel Cobblemon (données vérifiées)
# Clés = tags FR utilisés dans la BDD / Valeurs = biomes réels par mod

BIOME_MAP = _DATA["biome_map"]

MOD_COLORS = _DATA["mod_colors"]

# Traductions EN des tags FR (les noms réels de biomes sont déjà en anglais)
TAG_EN = _DATA.get("tag_en", {})


def tr_tag(fr_tag, lang="en"):
    """Traduit un tag FR en EN si lang == 'en'. Gère les tags dédiés « X (MOD) »
    et laisse passer tel quel ce qui n'a pas de traduction (noms réels EN inclus)."""
    if lang != "en" or not fr_tag:
        return fr_tag
    if fr_tag.endswith(")") and " (" in fr_tag:
        base, _sep, suffix = fr_tag.rpartition(" (")
        return "%s (%s" % (TAG_EN.get(base, base), suffix)
    return TAG_EN.get(fr_tag, fr_tag)

def get_real_biomes(tag_fr):
    """Retourne la liste des biomes réels pour un tag FR.
    Si tag_fr est un tag Cobblemon brut (#cobblemon:is_xxx), on le résout
    en tag FR d'abord via COBBLEMON_TAG_TO_FR.
    """
    if tag_fr in BIOME_MAP:
        return BIOME_MAP[tag_fr]
    # Tags cobblemon bruts (#cobblemon:is_bamboo, etc.)
    if tag_fr.startswith("#"):
        fr_tag = COBBLEMON_TAG_TO_FR.get(tag_fr)
        if fr_tag and fr_tag in BIOME_MAP:
            return BIOME_MAP[fr_tag]
        # Alias minecraft (#minecraft:is_nether → #cobblemon:is_nether → Nether)
        cobblemon_tag = MINECRAFT_TAG_ALIASES.get(tag_fr)
        if cobblemon_tag:
            fr_tag = COBBLEMON_TAG_TO_FR.get(cobblemon_tag)
            if fr_tag and fr_tag in BIOME_MAP:
                return BIOME_MAP[fr_tag]
    # Raw biome ID (minecraft:frozen_river, aether:skyroot_forest, etc.)
    fr_tags = RAW_ID_TO_FR_TAG.get(tag_fr)
    if fr_tags:
        for fr_tag in fr_tags:
            if fr_tag in BIOME_MAP:
                return BIOME_MAP[fr_tag]
    return [{"biome": tag_fr, "mod": "Tag Cobblemon"}]

def expand_spawn_biomes(biomes_str):
    """Transforme 'Océan froid, Océan gelé, Toundra' en liste de dicts par tag.
    Si un tag est un tag Cobblemon brut (#cobblemon:is_xxx), il est résolu en tag FR.
    """
    if not biomes_str:
        return []
    result = []
    for t in biomes_str.split(","):
        t = t.strip()
        if not t:
            continue
        # Résoudre en tag FR d'affichage
        display_tag = t
        if t.startswith("#"):
            if t in COBBLEMON_TAG_TO_FR:
                display_tag = COBBLEMON_TAG_TO_FR[t]
            elif t in MINECRAFT_TAG_ALIASES:
                cobblemon_tag = MINECRAFT_TAG_ALIASES[t]
                display_tag = COBBLEMON_TAG_TO_FR.get(cobblemon_tag, t)
        elif t in RAW_ID_TO_FR_TAG:
            display_tag = RAW_ID_TO_FR_TAG[t][0]  # premier tag = principal
        result.append({"tag": display_tag, "biomes": get_real_biomes(t)})
    return result

def get_mod_color(mod):
    return MOD_COLORS.get(mod, "#6a6a88")

# ------------------------------------------------------------------
# Carte inversée : biome réel → liste de tags FR qui le contiennent
# Utilisée pour filtrer par biome réel depuis l'index
# ------------------------------------------------------------------
def _build_reverse_map():
    reverse = {}
    for tag, biomes in BIOME_MAP.items():
        for b in biomes:
            key = b["biome"].lower()
            lst = reverse.setdefault(key, [])
            if tag not in lst:          # dédoublonner (noms de biome partagés entre mods)
                lst.append(tag)
    return reverse

REVERSE_BIOME_MAP = _build_reverse_map()

def get_tags_for_biome(real_biome_name):
    """Retourne les tags FR associés à un biome réel (recherche insensible à la casse)."""
    return REVERSE_BIOME_MAP.get(real_biome_name.lower(), [])

def get_all_real_biomes_sorted():
    """Retourne tous les biomes réels uniques triés, avec leur mod, sans doublons."""
    seen = {}
    for tag, biomes in BIOME_MAP.items():
        for b in biomes:
            key = b["biome"]
            if key not in seen:
                seen[key] = b["mod"]
    return sorted([{"biome": k, "mod": v} for k, v in seen.items()], key=lambda x: x["biome"])

def expand_biomes_by_mod(biomes_str, biomes_exclus_str=None):
    """
    Comme expand_spawn_biomes mais regroupe les biomes réels PAR MOD.
    Si biomes_exclus_str est fourni, les biomes exclus sont filtrés du résultat.
    Retourne : [{"tag": "...", "by_mod": {"Vanilla Minecraft": [...], "Terralith": [...], ...}}]
    """
    if not biomes_str:
        return []

    # Construire l'ensemble des biomes réels exclus
    excluded_biomes = set()
    if biomes_exclus_str:
        for t in biomes_exclus_str.split(","):
            t = t.strip()
            if t:
                for b in get_real_biomes(t):
                    excluded_biomes.add(b["biome"])

    result = []
    for t in biomes_str.split(","):
        t = t.strip()
        if not t:
            continue
        real_biomes = get_real_biomes(t)
        by_mod = {}
        for b in real_biomes:
            if b["biome"] in excluded_biomes:
                continue
            mod = b["mod"]
            by_mod.setdefault(mod, []).append(b["biome"])
        result.append({"tag": t, "by_mod": by_mod})
    return result


# Reverse map: "All vanilla Jungle biomes" → "Jungle" (tag FR cliquable)
# Construit depuis BIOME_MAP, avec overrides manuels pour les cas ambigus
# (un même "All X biomes" peut apparaître dans plusieurs tags FR)
_ALL_BIOMES_RAW = {
    b["biome"]: tag_fr
    for tag_fr, biomes in BIOME_MAP.items()
    for b in biomes
    if b["biome"].startswith("All ")
}

# Overrides manuels : choisir le tag FR le plus précis qui a un mapping Cobblemon
_ALL_BIOMES_OVERRIDES = _DATA["all_biomes_overrides"]

ALL_BIOMES_TO_FR_TAG = {**_ALL_BIOMES_RAW, **_ALL_BIOMES_OVERRIDES}


def expand_spawn_biomes_filtered(biomes_str, biomes_exclus_str=None):
    """
    Comme expand_spawn_biomes mais filtre les biomes exclus du résultat.
    """
    if not biomes_str:
        return []

    excluded_biomes = set()
    if biomes_exclus_str:
        for t in biomes_exclus_str.split(","):
            t = t.strip()
            if t:
                for b in get_real_biomes(t):
                    excluded_biomes.add(b["biome"])

    result = []
    for t in biomes_str.split(","):
        t = t.strip()
        if not t:
            continue
        real_biomes = [b for b in get_real_biomes(t) if b["biome"] not in excluded_biomes]
        result.append({"tag": t, "biomes": real_biomes})
    return result

# ── Hiérarchie des tags Cobblemon ─────────────────────────────────────────────
# Définit quels tags "parents" incluent quels tags "enfants".
# Ex: is_ocean inclut is_coast, is_warm_ocean, is_tropical_island, etc.
# Source: documentation officielle Cobblemon + wiki
COBBLEMON_TAG_HIERARCHY = _DATA["cobblemon_tag_hierarchy"]

# ── Aliases Minecraft natifs → équivalent Cobblemon ──────────────────────────
# Certains spawn files utilisent #minecraft:is_nether au lieu de #cobblemon:is_nether
MINECRAFT_TAG_ALIASES = _DATA["minecraft_tag_aliases"]

# ── Mapping tag FR -> tag Cobblemon brut ──────────────────────────────────────
FR_TAG_TO_COBBLEMON = _DATA["fr_tag_to_cobblemon"]

# Reverse map : tag Cobblemon brut → tag FR (le plus précis)
# Utilisé pour résoudre les tags #cobblemon:is_xxx stockés directement en BDD
# Les tags dédiés "(BWG)" / "(Wythers)" ne doivent pas écraser le tag FR de base
COBBLEMON_TAG_TO_FR = {}
for _k, _v in FR_TAG_TO_COBBLEMON.items():
    if _v in COBBLEMON_TAG_TO_FR and "(" in _k:
        continue
    COBBLEMON_TAG_TO_FR[_v] = _k

# ── Propagation parent → enfant dans BIOME_MAP ───────────────────────────────
# Si is_coast est parent de is_beach, BIOME_MAP["Côte"] doit contenir tous les
# biomes de BIOME_MAP["Plage"]. On itère jusqu'à convergence (chaînes multi-niveaux).
def _propagate_children_to_parents():
    cob_to_fr = {}
    for fr, cob in FR_TAG_TO_COBBLEMON.items():
        cob_to_fr.setdefault(cob, []).append(fr)

    for _ in range(20):  # max profondeur hiérarchie
        changed = False
        for parent_cob, children_cob in COBBLEMON_TAG_HIERARCHY.items():
            if not children_cob:
                continue
            parent_frs = cob_to_fr.get(parent_cob, [])
            if not parent_frs:
                continue
            for child_cob in children_cob:
                child_frs = cob_to_fr.get(child_cob, [])
                for parent_fr in parent_frs:
                    if parent_fr not in BIOME_MAP:
                        continue
                    parent_entries = BIOME_MAP[parent_fr]
                    parent_keys = {(e["mod"], e["biome"]) for e in parent_entries}
                    for child_fr in child_frs:
                        if child_fr not in BIOME_MAP:
                            continue
                        for entry in BIOME_MAP[child_fr]:
                            key = (entry["mod"], entry["biome"])
                            if key not in parent_keys:
                                parent_entries.append(entry)
                                parent_keys.add(key)
                                changed = True
        if not changed:
            break

# DÉSACTIVÉ depuis la régénération de biomes.json depuis le registre serveur.
# Le dump (/dumpbiometags) utilise streamTags(), qui renvoie déjà TOUS les tags
# d'un biome, imbrications de tags résolues par Minecraft. Propager en plus la
# hiérarchie fabriquait des appartenances inexistantes : les biomes de l'End
# (is_cold) se retrouvaient dans « Monde de surface », Sommet passait de 20 à 56
# biomes, etc. — d'où de faux spawns et de fausses isolations dans l'Oracle.
# _propagate_children_to_parents()

# ── Mapping raw biome IDs (minecraft:, aether:, etc.) → liste de tags FR ────
# Un biome peut appartenir à plusieurs tags (ex: is_forest + is_taiga).
# Le premier élément est le tag principal d'affichage.
RAW_ID_TO_FR_TAG = _DATA["raw_id_to_fr_tag"]

# ── Reverse : tag FR → liste de raw IDs bruts ────────────────────────────────
FR_TAG_TO_RAW_IDS = {}
for _raw_id, _fr_tags in RAW_ID_TO_FR_TAG.items():
    for _fr_tag in _fr_tags:
        FR_TAG_TO_RAW_IDS.setdefault(_fr_tag, []).append(_raw_id)

# Utilisé dans les requêtes SQL pour inclure les pokémon qui ont un ID littéral
# en plus du tag cobblemon (ex: aether:skyroot_forest en sus de #aether:is_aether).

def get_parent_cobblemon_tags(cobblemon_tag):
    """
    Retourne tous les tags parents Cobblemon qui incluent cobblemon_tag (récursivement).
    Ex: get_parent_cobblemon_tags('#cobblemon:is_tropical_island')
        -> {'#cobblemon:is_coast', '#cobblemon:is_ocean', '#cobblemon:is_overworld'}
    """
    if not cobblemon_tag:
        return set()

    parents = set()
    stack = [cobblemon_tag]
    visited = set()

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)

        for parent, children in COBBLEMON_TAG_HIERARCHY.items():
            if current in children and parent not in parents:
                parents.add(parent)
                stack.append(parent)

    return parents


def get_children_cobblemon_tags(cobblemon_tag):
    """Retourne récursivement tous les tags enfants d'un tag donné."""
    if not cobblemon_tag:
        return set()

    children = set()
    stack = [cobblemon_tag]
    visited = set()

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)

        for child in COBBLEMON_TAG_HIERARCHY.get(current, []):
            if child not in children:
                children.add(child)
                stack.append(child)

    return children


def get_cobblemon_tags_for_fr_biomes(fr_biomes_list):
    """
    Convertit une liste de tags FR en ensemble de tags Cobblemon bruts.
    Inclut le tag direct + ses enfants + les tags "frères" qui partagent
    les mêmes virtual biomes (ex: 'All Wythers Dark Forest' → is_spooky ET is_magical).
    N'inclut PAS les tags parents larges (is_overworld, is_nether) qui causeraient
    des faux positifs massifs.

    Ex: ['Île tropicale'] -> {'#cobblemon:is_tropical_island',
                               '#cobblemon:is_coast', '#cobblemon:is_ocean'}
    Ex: ['Forêt sombre (Wythers)'] -> {'#cobblemon:is_spooky', '#cobblemon:is_magical'}
    """
    # Tags trop larges à exclure (couvrent presque tout le jeu)
    OVERLY_BROAD = {
        '#cobblemon:is_overworld',
        '#cobblemon:is_nether',
        '#cobblemon:is_end',
        '#cobblemon:is_arid',
        '#cobblemon:is_cold',
        '#cobblemon:is_grassland',
        '#cobblemon:is_sandy',
        '#cobblemon:is_temperate',
        '#cobblemon:is_sparse',
        '#cobblemon:is_dense',
        '#cobblemon:is_ocean',
        '#cobblemon:is_mountain',
        '#cobblemon:is_freshwater',
    }

    # Pré-calcul : virtual biome (ex: "All Wythers' Dark Forest biomes") → set de cobblemon tags
    virtual_to_cob_tags = {}
    for fr, biomes in BIOME_MAP.items():
        cob = FR_TAG_TO_COBBLEMON.get(fr)
        if not cob:
            continue
        for entry in biomes:
            if entry['biome'].startswith('All '):
                virtual_to_cob_tags.setdefault(entry['biome'], set()).add(cob)

    all_cobblemon_tags = set()
    for fr_tag in fr_biomes_list:
        cobblemon_tag = FR_TAG_TO_COBBLEMON.get(fr_tag)
        if cobblemon_tag:
            all_cobblemon_tags.add(cobblemon_tag)
            # Enfants directs seulement (pas les parents larges)
            all_cobblemon_tags |= get_children_cobblemon_tags(cobblemon_tag)
            # Parents proches (exclure les trop larges)
            for parent in get_parent_cobblemon_tags(cobblemon_tag):
                if parent not in OVERLY_BROAD:
                    all_cobblemon_tags.add(parent)
            # Tags frères partageant les mêmes virtual biomes
            for entry in BIOME_MAP.get(fr_tag, []):
                if entry['biome'].startswith('All '):
                    sibling_tags = virtual_to_cob_tags.get(entry['biome'], set()) - OVERLY_BROAD
                    all_cobblemon_tags |= sibling_tags

    return all_cobblemon_tags

def build_biome_menu():
    """Construit la structure du menu de navigation depuis biomes.json.

    Retourne une liste d'onglets (un par mod, ordonnés), chacun groupé par
    thème puis par tag FR de base, avec la liste des biomes réels du mod.
    Le menu d'index.html est rendu à partir de cette structure (boucle Jinja),
    il n'y a donc plus de HTML de menu à maintenir à la main.
    """
    mod_meta  = _DATA["mod_meta"]
    themes    = _DATA["menu_themes"]
    tag_icons = _DATA["tag_icons"]

    menu = []
    for mod_name, meta in sorted(mod_meta.items(), key=lambda kv: kv[1]["order"]):
        theme_blocks = []
        for th in themes:
            tag_blocks = []
            for tag in th["tags"]:
                seen = set()
                biomes = []
                for e in BIOME_MAP.get(tag, []):
                    if e["mod"] == mod_name and e["biome"] not in seen:
                        seen.add(e["biome"])
                        biomes.append(e["biome"])
                if biomes:
                    tag_blocks.append({
                        "tag": tag,
                        "icon": tag_icons.get(tag, "🔹"),
                        "biomes": biomes,
                    })
            if tag_blocks:
                theme_blocks.append({
                    "label": th["label"],
                    "label_en": th.get("label_en", th["label"]),
                    "icon": th["icon"],
                    "tags": tag_blocks,
                })
        if theme_blocks:
            menu.append({
                "mod": mod_name,
                "color": MOD_COLORS.get(mod_name, "#888888"),
                "emoji": meta["emoji"],
                "themes": theme_blocks,
            })
    return menu
