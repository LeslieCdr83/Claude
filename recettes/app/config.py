"""Réglages de l'application, lus depuis les variables d'environnement ou le fichier reglages.txt."""
import json
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
# Nombre de personnes affiché par défaut sur chaque fiche.
try:
    PORTIONS_DEFAUT = max(1, int(os.environ.get("PORTIONS_DEFAUT") or 4))
except ValueError:
    PORTIONS_DEFAUT = 4
# Rédige automatiquement les versions Thermomix et airfryer après chaque import.
ADAPTATION_AUTO = (os.environ.get("ADAPTATION_AUTO") or "oui").strip().lower() not in ("non", "0", "false")
# Modèle exact de ton airfryer, pour des réglages plus précis (ex. "Ninja Foodi Dual Zone AF400EU").
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


# ---------- Réglages modifiables depuis l'appli (page Réglages) ----------
# Ils priment sur reglages.txt et sont gardés dans data/reglages.json.
FICHIER_REGLAGES = DOSSIER_DONNEES / "reglages.json"
MODES = ("api", "abonnement", "manuel")


def lire_reglages() -> dict:
    try:
        return json.loads(FICHIER_REGLAGES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire_reglages(valeurs: dict) -> None:
    reglages = lire_reglages()
    reglages.update(valeurs)
    reglages = {k: v for k, v in reglages.items() if v not in (None, "")}
    FICHIER_REGLAGES.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_REGLAGES.write_text(json.dumps(reglages, ensure_ascii=False, indent=2), encoding="utf-8")


def cle_api() -> str:
    return (lire_reglages().get("cle_api") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def cle_api_presente() -> bool:
    return bool(cle_api())


def chemin_claude_code() -> str | None:
    """Trouve la commande claude (Claude Code), y compris à son emplacement d'installation habituel."""
    import shutil
    # L'installation officielle place claude.exe dans ~/.local/bin : on la préfère à un éventuel claude.cmd.
    for candidat in (Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"):
        if candidat.exists():
            return str(candidat)
    return shutil.which("claude")


def mode_claude() -> str:
    """"api" (clé payante), "abonnement" (Claude Code connecté à ton compte Claude)
    ou "manuel" (copier-coller avec l'appli Claude)."""
    choix = (lire_reglages().get("mode") or os.environ.get("MODE_CLAUDE") or "").strip().lower()
    if choix in MODES:
        return choix
    if cle_api_presente():
        return "api"
    return "abonnement" if chemin_claude_code() else "api"


def disponible(mode: str | None) -> bool:
    """Vrai si ce mode peut fonctionner tout de suite sur cet ordinateur."""
    if mode == "api":
        return cle_api_presente()
    if mode == "abonnement":
        return chemin_claude_code() is not None
    return False


def cle_claude_presente() -> bool:
    """Vrai si Claude est utilisable automatiquement, par la clé API ou par l'abonnement."""
    if mode_claude() == "manuel":
        return False
    if mode_claude() == "abonnement":
        return chemin_claude_code() is not None
    return cle_api_presente()


DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
