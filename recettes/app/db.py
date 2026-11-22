"""Stockage des recettes dans une base SQLite locale."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

CHAMPS_JSON = ("ingredients", "etapes", "tags")
CHAMPS_MODIFIABLES = (
    "titre", "portions", "temps_preparation", "temps_cuisson",
    "ingredients", "etapes", "tags", "notes", "favori",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS recettes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT,
    plateforme TEXT,
    auteur TEXT,
    titre TEXT,
    portions TEXT,
    temps_preparation TEXT,
    temps_cuisson TEXT,
    ingredients TEXT DEFAULT '[]',
    etapes TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    legende TEXT DEFAULT '',
    transcription TEXT DEFAULT '',
    miniature TEXT,
    images TEXT DEFAULT '[]',
    adaptations TEXT DEFAULT '{}',
    favori INTEGER DEFAULT 0,
    statut TEXT DEFAULT 'en_cours',
    progression TEXT DEFAULT '',
    erreur TEXT DEFAULT '',
    cree_le TEXT
);
"""


@contextmanager
def connexion():
    con = sqlite3.connect(config.BASE_SQLITE)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def initialiser() -> None:
    config.DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    with connexion() as con:
        con.executescript(SCHEMA)
        # Mise à jour des bases créées avant l'ajout d'une colonne.
        colonnes = {l["name"] for l in con.execute("PRAGMA table_info(recettes)")}
        if "adaptations" not in colonnes:
            con.execute("ALTER TABLE recettes ADD COLUMN adaptations TEXT DEFAULT '{}'")


def _vers_dict(ligne: sqlite3.Row) -> dict:
    d = dict(ligne)
    for champ in CHAMPS_JSON + ("images",):
        d[champ] = json.loads(d[champ] or "[]")
    d["adaptations"] = json.loads(d.get("adaptations") or "{}")
    d["favori"] = bool(d["favori"])
    return d


def _serialiser(valeurs: dict) -> dict:
    sortie = {}
    for cle, val in valeurs.items():
        if cle in CHAMPS_JSON + ("images",):
            val = json.dumps(val or [], ensure_ascii=False)
        elif cle == "adaptations":
            val = json.dumps(val or {}, ensure_ascii=False)
        elif cle == "favori":
            val = int(bool(val))
        sortie[cle] = val
    return sortie


def creer(**valeurs) -> int:
    valeurs.setdefault("cree_le", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    valeurs = _serialiser(valeurs)
    cols = ", ".join(valeurs)
    marques = ", ".join("?" for _ in valeurs)
    with connexion() as con:
        cur = con.execute(f"INSERT INTO recettes ({cols}) VALUES ({marques})", tuple(valeurs.values()))
        return cur.lastrowid


def mettre_a_jour(recette_id: int, **valeurs) -> None:
    if not valeurs:
        return
    valeurs = _serialiser(valeurs)
    affect = ", ".join(f"{c} = ?" for c in valeurs)
    with connexion() as con:
        con.execute(f"UPDATE recettes SET {affect} WHERE id = ?", (*valeurs.values(), recette_id))


def lire(recette_id: int) -> dict | None:
    with connexion() as con:
        ligne = con.execute("SELECT * FROM recettes WHERE id = ?", (recette_id,)).fetchone()
    return _vers_dict(ligne) if ligne else None


def lister(recherche: str = "", tag: str = "") -> list[dict]:
    with connexion() as con:
        lignes = con.execute("SELECT * FROM recettes ORDER BY favori DESC, id DESC").fetchall()
    recettes = [_vers_dict(l) for l in lignes]
    if tag:
        recettes = [r for r in recettes if tag.lower() in (t.lower() for t in r["tags"])]
    if recherche:
        mots = recherche.lower().split()

        def texte(r: dict) -> str:
            ingr = " ".join(i.get("nom", "") for i in r["ingredients"])
            return " ".join([r["titre"] or "", r["auteur"] or "", ingr, " ".join(r["tags"]), r["notes"] or ""]).lower()

        recettes = [r for r in recettes if all(m in texte(r) for m in mots)]
    return recettes


def supprimer(recette_id: int) -> dict | None:
    recette = lire(recette_id)
    if recette:
        with connexion() as con:
            con.execute("DELETE FROM recettes WHERE id = ?", (recette_id,))
    return recette


def tous_les_tags() -> list[str]:
    tags = set()
    for r in lister():
        tags.update(t.lower() for t in r["tags"])
    return sorted(tags)
