"""Réglages de l'application, lus depuis les variables d'environnement ou le fichier .env."""
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _charger_env() -> None:
    fichier = RACINE / ".env"
    if not fichier.exists():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


_charger_env()

DOSSIER_DONNEES = Path(os.environ.get("RECETTES_DONNEES", RACINE / "data"))
DOSSIER_IMAGES = DOSSIER_DONNEES / "images"
BASE_SQLITE = DOSSIER_DONNEES / "recettes.db"

# Modèle Whisper local : tiny, base, small, medium. "small" donne un bon français sur un CPU.
MODELE_WHISPER = os.environ.get("MODELE_WHISPER", "small")
# Fichier de cookies (format Netscape) pour Instagram ou les posts privés. Optionnel.
COOKIES = os.environ.get("COOKIES_FICHIER") or None

MODELE_CLAUDE = os.environ.get("MODELE_CLAUDE", "claude-opus-5-5")


def cle_claude_presente() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
