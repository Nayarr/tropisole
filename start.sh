#!/bin/bash
# Cobbledex — Script de démarrage

echo "🔵 Cobbledex — Pokédex Cobblemon"
echo "================================="

# Aller dans le dossier du script
cd "$(dirname "$0")"

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 non trouvé. Installez Python 3."
    exit 1
fi

# Installer les dépendances si nécessaire
echo "📦 Vérification des dépendances..."
pip3 install flask pandas openpyxl --quiet 2>/dev/null || pip install flask pandas openpyxl --quiet

# Créer la base de données si elle n'existe pas
if [ ! -f "cobbledex.db" ]; then
    echo "🗄️  Création de la base de données..."
    python3 create_db.py
    if [ $? -ne 0 ]; then
        echo "❌ Erreur lors de la création de la base de données."
        exit 1
    fi
fi

echo ""
echo "✅ Prêt ! Ouvrez votre navigateur sur :"
echo "   http://localhost:5000"
echo ""
echo "Appuyez sur Ctrl+C pour arrêter."
echo ""

python3 app.py
