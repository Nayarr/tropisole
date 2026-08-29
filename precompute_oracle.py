# -*- coding: utf-8 -*-
"""Précalcule l'isolation Oracle de chaque Pokémon et stocke le meilleur résultat
dans la table oracle_ranking (utilisée par la page /oracle/ranking).

Pilote directement l'endpoint /api/oracle/stream (même code que la prod) via le
test client Flask → zéro divergence avec l'Oracle réel.

Usage :
    python precompute_oracle.py            # calcule les manquants
    python precompute_oracle.py --force     # recalcule tout
    python precompute_oracle.py --limit 50  # ne fait que 50 (test)
"""
import sys, io, json, time, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

FORCE = "--force" in sys.argv
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

import app as A
DB = A.DB_PATH

DDL = """
CREATE TABLE IF NOT EXISTS oracle_ranking (
    numero       INTEGER PRIMARY KEY,
    name         TEXT,
    best_pct     REAL,
    raw_pct      REAL,
    biome        TEXT,
    mod          TEXT,
    context      TEXT,
    ev           TEXT,
    filters      TEXT,
    competitors  INTEGER,
    only_ultra   INTEGER,
    computed_at  TEXT
)
"""

def get_session_uid():
    c = sqlite3.connect(DB)
    row = c.execute(
        "SELECT firebase_uid FROM users WHERE validated=1 "
        "AND (expires_at IS NULL OR expires_at > '2099') LIMIT 1"
    ).fetchone()
    c.close()
    return row[0] if row else None

def main():
    conn = sqlite3.connect(DB)
    conn.execute(DDL)
    conn.commit()

    # Liste des Pokémon (un par numéro) + nom FR
    rows = conn.execute(
        "SELECT numero, MIN(pokemon) FROM pokemon_spawns GROUP BY numero ORDER BY numero"
    ).fetchall()
    done = set()
    if not FORCE:
        done = {r[0] for r in conn.execute("SELECT numero FROM oracle_ranking")}

    targets = [(n, nm) for n, nm in rows if FORCE or n not in done]
    if LIMIT:
        targets = targets[:LIMIT]
    conn.close()

    uid = get_session_uid()
    if not uid:
        print("Aucun utilisateur validé en base — impossible d'ouvrir une session de calcul.")
        return

    cl = A.app.test_client()
    with cl.session_transaction() as s:
        s["user_id"] = uid
        s["is_admin"] = True  # has_oracle_access -> True

    total = len(targets)
    print("À calculer : %d Pokémon%s" % (total, " (FORCE)" if FORCE else ""))
    t0 = time.time()

    for idx, (numero, name) in enumerate(targets, 1):
        t = time.time()
        r = cl.get("/api/oracle/stream?numero=%d&focus=1" % numero)
        raw = r.get_data().decode("utf-8", "ignore")
        top = None
        for chunk in raw.split("\n\n"):
            if chunk.startswith("data: "):
                try:
                    o = json.loads(chunk[6:])
                except Exception:
                    continue
                if o.get("type") == "update" and o.get("results"):
                    top = o["results"][0]  # meilleur (déjà trié)

        conn = sqlite3.connect(DB)
        if top:
            combo = top.get("combo", {})
            conn.execute(
                "INSERT OR REPLACE INTO oracle_ranking "
                "(numero,name,best_pct,raw_pct,biome,mod,context,ev,filters,competitors,only_ultra,computed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                (numero, name, top.get("pct"), top.get("raw_pct", top.get("pct")),
                 top.get("biome_fr"), top.get("mod"), combo.get("contexte"),
                 combo.get("ev"), json.dumps(combo.get("removed", []), ensure_ascii=False),
                 len(top.get("competitors_names", [])), int(bool(top.get("only_ultra")))),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO oracle_ranking "
                "(numero,name,best_pct,raw_pct,biome,mod,context,ev,filters,competitors,only_ultra,computed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                (numero, name, None, None, None, None, None, None, "[]", None, None),
            )
        conn.commit()
        conn.close()

        dt = time.time() - t
        pct = top.get("pct") if top else None
        biome = top.get("biome_fr") if top else "—"
        eta = (time.time() - t0) / idx * (total - idx)
        print("[%d/%d] #%04d %-18s %5s%% @ %-22s (%.1fs) ETA %dmin"
              % (idx, total, numero, name[:18], pct, biome[:22], dt, eta / 60))

    print("Terminé en %.1f min." % ((time.time() - t0) / 60))

if __name__ == "__main__":
    main()
