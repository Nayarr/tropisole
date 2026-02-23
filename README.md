# 🔵 Cobbledex

Base de données et site web pour les spawns Cobblemon v1.7.1.

## Structure

```
cobbledex/
├── app.py           # Serveur Flask (routes + API REST)
├── create_db.py     # Script de création de la base SQLite
├── cobbledex.db     # Base de données SQLite (générée automatiquement)
├── requirements.txt
├── start.sh         # Script de démarrage (Linux/Mac)
├── templates/
│   ├── index.html   # Page principale (liste + recherche + filtres)
│   └── detail.html  # Page détail d'un Pokémon
└── README.md
```

## Installation et lancement

### Méthode rapide (Linux/Mac)
```bash
chmod +x start.sh
./start.sh
```

### Méthode manuelle
```bash
pip install -r requirements.txt
python3 create_db.py   # Créer la base (une seule fois)
python3 app.py         # Lancer le serveur
```

Ouvrir ensuite : http://localhost:5000

## Base de données SQL

### Table : `pokemon_spawns`

| Colonne         | Type    | Description                        |
|-----------------|---------|------------------------------------|
| id              | INTEGER | Clé primaire auto-incrémentée      |
| numero          | INTEGER | Numéro du Pokédex                  |
| pokemon         | TEXT    | Nom du Pokémon (en français)       |
| entree          | INTEGER | Numéro d'entrée de spawn           |
| bucket          | TEXT    | Rareté (common/uncommon/rare/ultra-rare) |
| poids           | REAL    | Poids de spawn                     |
| niveau_min      | INTEGER | Niveau minimum                     |
| niveau_max      | INTEGER | Niveau maximum                     |
| biomes          | TEXT    | Biomes de spawn (séparés par virgule) |
| biomes_exclus   | TEXT    | Biomes exclus                      |
| moment          | TEXT    | Moment (any/day/night/twilight)    |
| meteo           | TEXT    | Météo (any/clear/rain)             |
| multiplicateurs | TEXT    | Multiplicateurs de spawn           |
| contexte        | TEXT    | Contexte (grounded, etc.)          |
| presets         | TEXT    | Presets appliqués                  |
| conditions      | TEXT    | Conditions spéciales               |
| anticonditions  | TEXT    | Anticonditions                     |
| lumiere_min     | REAL    | Lumière du ciel minimale           |
| lumiere_max     | REAL    | Lumière du ciel maximale           |
| peut_voir_ciel  | TEXT    | Peut voir le ciel (true/false)     |
| pattern         | TEXT    | Pattern clé=valeur                 |

## API REST

| Route                    | Description                              |
|--------------------------|------------------------------------------|
| `GET /`                  | Page principale                          |
| `GET /pokemon/<numero>`  | Page détail d'un Pokémon                 |
| `GET /api/pokemon`       | Liste paginée avec filtres               |
| `GET /api/stats`         | Statistiques globales                    |

### Paramètres de `/api/pokemon`
- `q` — recherche par nom
- `bucket` — filtrer par rareté
- `moment` — filtrer par moment (day/night/etc.)
- `biome` — filtrer par biome
- `sort` — trier par (numero/pokemon/bucket/niveau_min)
- `order` — asc ou desc
- `page` — numéro de page
- `per_page` — résultats par page (défaut: 40)

## Fonctionnalités du site

- 🔍 **Recherche** en temps réel par nom
- 🎛️ **Filtres** : rareté, moment, biome
- ↕️ **Tri** : par numéro, nom, rareté ou niveau
- 📄 **Pagination** avec navigation
- 📊 **Stats** en header (total Pokémon, total spawns)
- 🗂️ **Fiche détaillée** par Pokémon avec toutes ses entrées de spawn
- ⬅️➡️ Navigation précédent/suivant entre Pokémon
