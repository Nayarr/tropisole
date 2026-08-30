# -*- coding: utf-8 -*-
"""Précalcule l'isolation Oracle de chaque Pokémon et stocke le meilleur résultat
dans la table oracle_ranking (utilisée par la page /oracle/ranking).

Pilote directement l'endpoint /api/oracle/stream (même code que la prod) via le
test client Flask → zéro divergence avec l'Oracle réel.

Calcule les DEUX modes pour chaque Pokémon :
  - "chain" : optimise pour toute la lignée évolutive (focus=0)
  - "focus" : optimise pour le Pokémon seul (focus=1)

Usage :
    python precompute_oracle.py            # calcule les manquants
    python precompute_oracle.py --force     # recalcule tout
    python precompute_oracle.py --limit 50  # ne fait que 50 Pokémon (test)
"""
import sys, io, json, time, sqlite3
# line_buffering=True : la progression s'affiche en direct dans la console
# (sinon la sortie est bufferisée et on ne voit rien pendant tout le calcul).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

FORCE = "--force" in sys.argv
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

import app as A
DB = A.DB_PATH

MODES = [("chain", 0), ("focus", 1)]

DDL = """
CREATE TABLE IF NOT EXISTS oracle_ranking (
    numero       INTEGER,
    mode         TEXT,
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
    bucket       TEXT,
    buckets      TEXT,
    computed_at  TEXT,
    PRIMARY KEY (numero, mode)
)
"""

def make_client():
    """Client de test avec l'accès Oracle, sans dépendre d'une session.

    Ce script tourne hors ligne et ne sert aucune requête réelle :
      - on neutralise les hooks before_request (session / appareil / expiration) ;
      - on force has_oracle_access() à True.
    On ne s'appuie PAS sur un cookie de session : Flask relit le cookie signé avec
    max_age = permanent_session_lifetime (2 h), donc un calcul de plus de 2 h
    verrait sa session expirer en cours de route (403 au milieu du run).
    """
    A.app.before_request_funcs[None] = []
    A.has_oracle_access = lambda: True
    return A.app.test_client()

def main():
    print("Base : %s" % DB)
    conn = sqlite3.connect(DB)
    conn.execute(DDL)
    conn.commit()

    # Liste des Pokémon (un par numéro) + nom FR
    rows = conn.execute(
        "SELECT numero, MIN(pokemon) FROM pokemon_spawns GROUP BY numero ORDER BY numero"
    ).fetchall()
    done = set()
    if not FORCE:
        done = {(r[0], r[1]) for r in conn.execute("SELECT numero, mode FROM oracle_ranking")}
    conn.close()

    if LIMIT:
        rows = rows[:LIMIT]
    targets = [(n, nm, mode, fo) for n, nm in rows for mode, fo in MODES
               if FORCE or (n, mode) not in done]

    cl = make_client()

    total = len(targets)
    print("À calculer : %d entrées (%d Pokémon x %d modes)%s"
          % (total, len(rows), len(MODES), " (FORCE)" if FORCE else ""))
    t0 = time.time()

    for idx, (numero, name, mode, focus) in enumerate(targets, 1):
        t = time.time()
        r = cl.get("/api/oracle/stream?numero=%d&focus=%d" % (numero, focus))
        if r.status_code != 200:
            print("ERREUR : /api/oracle/stream a répondu %s (attendu 200). "
                  "Calcul interrompu." % r.status_code)
            return
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
                "(numero,mode,name,best_pct,raw_pct,biome,mod,context,ev,filters,competitors,only_ultra,bucket,buckets,computed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                (numero, mode, name, top.get("pct"), top.get("raw_pct", top.get("pct")),
                 top.get("biome_fr"), top.get("mod"), combo.get("contexte"),
                 combo.get("ev"), json.dumps(combo.get("removed", []), ensure_ascii=False),
                 len(top.get("competitors_names", [])), int(bool(top.get("only_ultra"))),
                 (top.get("target_buckets") or [None])[0],
                 ",".join(top.get("target_buckets") or [])),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO oracle_ranking "
                "(numero,mode,name,best_pct,raw_pct,biome,mod,context,ev,filters,competitors,only_ultra,bucket,buckets,computed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                (numero, mode, name, None, None, None, None, None, None, "[]", None, None, None, None),
            )
        conn.commit()
        conn.close()

        dt = time.time() - t
        pct = top.get("pct") if top else None
        biome = top.get("biome_fr") if top else "—"
        eta = (time.time() - t0) / idx * (total - idx)
        print("[%d/%d] #%04d %-16s %-5s %5s%% @ %-20s (%.1fs) ETA %dmin"
              % (idx, total, numero, name[:16], mode, pct, biome[:20], dt, eta / 60))

    print("Terminé en %.1f min." % ((time.time() - t0) / 60))

if __name__ == "__main__":
    main()
