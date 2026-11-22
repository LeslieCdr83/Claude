"""Réglages de l'application, lus depuis les variables d'environnement ou le fichier reglages.txt."""
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _charger_env() -> None:
    # Windows masque les extensions : "reglages.txt" devient souvent "reglages.txt.txt".
    for nom in ("reglages.txt", "reglages.txt.txt", "reglages", ".env"):
        fichier = RACINE / nom
        if fichier.exists():
            _lire(fichier)


def _lire(fichier: Path) -> None:
    for ligne in fichier.read_text(encoding="utf-8-sig").splitlines():
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
# Modèle exact de ton airfryer, pour des réglages plus précis (ex. "Ninja Foodi Dual Zone AF400EU").
# Nombre de personnes affiché par défaut sur chaque fiche.
try:
    PORTIONS_DEFAUT = max(1, int(os.environ.get("PORTIONS_DEFAUT") or 4))
except ValueError:
    PORTIONS_DEFAUT = 4
# Rédige automatiquement les versions Thermomix et airfryer après chaque import.
ADAPTATION_AUTO = (os.environ.get("ADAPTATION_AUTO") or "oui").strip().lower() not in ("non", "0", "false")
MODELE_AIRFRYER = os.environ.get("MODELE_AIRFRYER") or "modèle non précisé, réglages valables pour la gamme Ninja"


def _trouver_ffmpeg() -> str:
    """ffmpeg est fourni par le paquet imageio-ffmpeg : rien à installer à part."""
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = _trouver_ffmpeg()


def cle_claude_presente() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
