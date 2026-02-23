import sqlite3
import pandas as pd
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cobbledex.db")
XLSX_PATH = "/home/claude/Cobblemon_Spawns_1_7_1_FR.xlsx"

def create_database():
    df = pd.read_excel(XLSX_PATH)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DROP TABLE IF EXISTS pokemon_spawns")
    c.execute("""
        CREATE TABLE pokemon_spawns (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            numero           INTEGER,
            pokemon          TEXT,
            entree           INTEGER,
            bucket           TEXT,
            poids            REAL,
            niveau_min       INTEGER,
            niveau_max       INTEGER,
            biomes           TEXT,
            biomes_exclus    TEXT,
            moment           TEXT,
            meteo            TEXT,
            multiplicateurs  TEXT,
            contexte         TEXT,
            presets          TEXT,
            conditions       TEXT,
            anticonditions   TEXT,
            lumiere_min      REAL,
            lumiere_max      REAL,
            peut_voir_ciel   TEXT,
            pattern          TEXT
        )
    """)

    for _, row in df.iterrows():
        c.execute("""
            INSERT INTO pokemon_spawns (
                numero, pokemon, entree, bucket, poids,
                niveau_min, niveau_max, biomes, biomes_exclus,
                moment, meteo, multiplicateurs, contexte, presets,
                conditions, anticonditions, lumiere_min, lumiere_max,
                peut_voir_ciel, pattern
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            int(row["No."]) if pd.notna(row["No."]) else None,
            str(row["Pokémon"]) if pd.notna(row["Pokémon"]) else None,
            int(row["Entry"]) if pd.notna(row["Entry"]) else None,
            str(row["Bucket"]) if pd.notna(row["Bucket"]) else None,
            float(row["Weight"]) if pd.notna(row["Weight"]) else None,
            int(row["Lv. Min"]) if pd.notna(row["Lv. Min"]) else None,
            int(row["Lv. Max"]) if pd.notna(row["Lv. Max"]) else None,
            str(row["Biomes"]) if pd.notna(row["Biomes"]) else None,
            str(row["Excluded Biomes"]) if pd.notna(row["Excluded Biomes"]) else None,
            str(row["Time"]) if pd.notna(row["Time"]) else None,
            str(row["Weather"]) if pd.notna(row["Weather"]) else None,
            str(row["Multipliers"]) if pd.notna(row["Multipliers"]) else None,
            str(row["Context"]) if pd.notna(row["Context"]) else None,
            str(row["Presets"]) if pd.notna(row["Presets"]) else None,
            str(row["Conditions"]) if pd.notna(row["Conditions"]) else None,
            str(row["Anticonditions"]) if pd.notna(row["Anticonditions"]) else None,
            float(row["skyLightMin"]) if pd.notna(row["skyLightMin"]) else None,
            float(row["skyLightMax"]) if pd.notna(row["skyLightMax"]) else None,
            str(row["canSeeSky"]) if pd.notna(row["canSeeSky"]) else None,
            str(row["Patternkey=Value"]) if pd.notna(row["Patternkey=Value"]) else None,
        ))

    conn.commit()

    # Create useful indexes
    c.execute("CREATE INDEX idx_pokemon ON pokemon_spawns(pokemon)")
    c.execute("CREATE INDEX idx_numero ON pokemon_spawns(numero)")
    c.execute("CREATE INDEX idx_bucket ON pokemon_spawns(bucket)")
    conn.commit()
    conn.close()

    total = len(df)
    unique = df["Pokémon"].nunique()
    print(f"✅ Base créée : {total} entrées, {unique} Pokémon uniques")

if __name__ == "__main__":
    create_database()
