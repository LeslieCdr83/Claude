"""Récupère une vidéo depuis son lien, puis en tire la légende, la voix et des images."""
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import config

EXTENSIONS_VIDEO = (".mp4", ".mkv", ".webm", ".mov")
EXTENSIONS_IMAGE = (".jpg", ".jpeg", ".png", ".webp")


@dataclass
class Video:
    url: str
    titre: str = ""
    legende: str = ""
    auteur: str = ""
    plateforme: str = ""
    duree: float = 0.0
    fichier: Path | None = None
    miniature: Path | None = None
    images_carrousel: list[Path] = field(default_factory=list)


class ErreurTelechargement(Exception):
    pass


def telecharger(url: str, dossier: Path) -> Video:
    """Télécharge la vidéo (720p max) et sa miniature avec yt-dlp."""
    import yt_dlp

    options = {
        "outtmpl": str(dossier / "media.%(autonumber)s.%(ext)s"),
        "format": "bv*[height<=720]+ba/b[height<=720]/b/best",
        "merge_output_format": "mp4",
        "writethumbnail": True,
        # TikTok livre la miniature avec l'extension ".image" : on la convertit en jpg.
        "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}],
        "noplaylist": False,
        "playlistend": 20,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if config.COOKIES:
        options["cookiefile"] = config.COOKIES

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:  # yt-dlp lève plusieurs types d'erreurs
        message = str(exc)
        if "login" in message.lower() or "cookies" in message.lower():
            message += (" | Instagram demande souvent une connexion. Renseigne COOKIES_FICHIER"
                        " dans le fichier .env (voir le README).")
        raise ErreurTelechargement(message) from exc

    # Les carrousels arrivent sous forme de liste : on garde les infos du post parent.
    entrees = info.get("entries") or [info]
    premier = entrees[0] if entrees else info

    video = Video(
        url=url,
        titre=info.get("title") or premier.get("title") or "",
        legende=info.get("description") or premier.get("description") or "",
        auteur=info.get("uploader") or info.get("channel") or premier.get("uploader") or "",
        plateforme=info.get("extractor_key") or premier.get("extractor_key") or "",
        duree=float(premier.get("duration") or 0),
    )

    fichiers = sorted(dossier.iterdir())
    videos = [f for f in fichiers if f.suffix.lower() in EXTENSIONS_VIDEO]
    images = [f for f in fichiers if f.suffix.lower() in EXTENSIONS_IMAGE]
    if videos:
        video.fichier = max(videos, key=lambda f: f.stat().st_size)
        video.miniature = images[0] if images else None
    else:
        # Post photo (carrousel TikTok ou Instagram) : les images portent la recette.
        video.images_carrousel = images[:10]
        video.miniature = images[0] if images else None
    return video


def extraire_images(fichier: Path, duree: float, dossier: Path, nombre: int = 6) -> list[Path]:
    """Capture des images réparties sur la vidéo pour lire le texte affiché à l'écran."""
    if not shutil.which("ffmpeg"):
        return []
    if duree <= 0:
        duree = _duree_ffprobe(fichier)
    if duree <= 0:
        return []
    images = []
    for i in range(nombre):
        instant = duree * (i + 0.5) / nombre
        sortie = dossier / f"capture_{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{instant:.2f}", "-i", str(fichier),
             "-frames:v", "1", "-vf", "scale='min(768,iw)':-2", "-q:v", "4", str(sortie)],
            check=False,
        )
        if sortie.exists():
            images.append(sortie)
    return images


def _duree_ffprobe(fichier: Path) -> float:
    if not shutil.which("ffprobe"):
        return 0.0
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(fichier)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


_modele_whisper = None
_verrou_whisper = threading.Lock()


def transcrire(fichier: Path) -> str:
    """Transcrit la voix en local avec faster-whisper. Gratuit, sans clé."""
    global _modele_whisper
    import numpy as np
    from faster_whisper import WhisperModel

    # ffmpeg extrait la piste audio en 16 kHz mono. Évite les soucis de version de PyAV.
    res = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(fichier), "-vn", "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"],
        capture_output=True, check=False,
    )
    if res.returncode != 0 or not res.stdout:
        return ""  # vidéo sans piste audio
    audio = np.frombuffer(res.stdout, np.int16).astype(np.float32) / 32768.0

    with _verrou_whisper:
        if _modele_whisper is None:
            _modele_whisper = WhisperModel(config.MODELE_WHISPER, device="cpu", compute_type="int8")
        segments, _ = _modele_whisper.transcribe(audio, vad_filter=True, beam_size=5)
        return " ".join(s.text.strip() for s in segments).strip()
