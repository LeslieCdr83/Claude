"""Serveur web : API des recettes et interface."""
import re
import shutil
import tempfile
import traceback
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, extraction, structuration

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Mes recettes")
db.initialiser()


def _etat_claude() -> str:
    mode = config.mode_claude()
    if mode == "manuel":
        return "Claude : mode manuel (copier-coller avec l'appli Claude)"
    if mode == "abonnement":
        return ("Claude : abonnement via Claude Code" if config.cle_claude_presente() else
                "Claude : Claude Code introuvable. Installe-le (voir le README).")
    return ("Claude : clé API enregistrée (payante)" if config.cle_claude_presente() else
            "Claude : aucune clé API. Ouvre la page Réglages de l'appli.")


print("", flush=True)
print(_etat_claude(), flush=True)


class Import(BaseModel):
    url: str


class Ingredient(BaseModel):
    quantite: str = ""
    unite: str = ""
    nom: str = ""


class Reglages(BaseModel):
    mode: str | None = None
    cle_api: str | None = None
    effacer_cle: bool = False


class ReponseManuelle(BaseModel):
    type: str
    texte: str


class Modification(BaseModel):
    titre: str | None = None
    portions: str | None = None
    temps_preparation: str | None = None
    temps_cuisson: str | None = None
    ingredients: list[Ingredient] | None = None
    etapes: list[str] | None = None
    tags: list[str] | None = None
    notes: str | None = None
    favori: bool | None = None


def extraire_url(texte: str) -> str | None:
    """Trouve le lien dans un texte partagé (TikTok ajoute souvent une phrase autour)."""
    trouve = re.search(r"https?://\S+", texte or "")
    return trouve.group(0).rstrip(").,;!?\"'") if trouve else None


def _appliquer_fiche(recette_id: int, fiche: dict, titre_defaut: str) -> None:
    if not fiche.get("est_une_recette", True):
        db.mettre_a_jour(recette_id, statut="brouillon", titre=titre_defaut or "Sans titre",
                         erreur="Claude n'a pas trouvé de recette dans cette vidéo.", progression="")
        return
    db.mettre_a_jour(
        recette_id,
        titre=fiche.get("titre") or titre_defaut or "Sans titre",
        portions=fiche.get("portions", ""),
        temps_preparation=fiche.get("temps_preparation", ""),
        temps_cuisson=fiche.get("temps_cuisson", ""),
        ingredients=fiche.get("ingredients", []),
        etapes=fiche.get("etapes", []),
        tags=[t.lower() for t in fiche.get("tags", [])],
        notes=fiche.get("notes", ""),
        statut="pret", erreur="", progression="",
    )


def traiter(recette_id: int, url: str) -> None:
    """Chaîne complète : téléchargement, captures, transcription, puis fiche par Claude."""
    dossier_images = config.DOSSIER_IMAGES / str(recette_id)
    dossier_images.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db.mettre_a_jour(recette_id, progression="Téléchargement de la vidéo")
            video = extraction.telecharger(url, tmp)
            db.mettre_a_jour(recette_id, titre=video.titre[:120], auteur=video.auteur,
                             plateforme=video.plateforme, legende=video.legende)

            captures: list[Path] = []
            transcription = ""
            if video.fichier:
                db.mettre_a_jour(recette_id, progression="Capture du texte affiché à l'écran")
                captures = extraction.extraire_images(video.fichier, video.duree, tmp)
                db.mettre_a_jour(recette_id, progression="Transcription de la voix")
                try:
                    transcription = extraction.transcrire(video.fichier)
                except Exception:
                    traceback.print_exc()  # on continue avec la légende et les captures
            else:
                captures = video.images_carrousel

            # Copie durable des images pour l'affichage et pour une analyse plus tard.
            gardees = []
            for i, image in enumerate(captures):
                cible = dossier_images / f"capture_{i:02d}{image.suffix.lower()}"
                shutil.copy(image, cible)
                gardees.append(f"{recette_id}/{cible.name}")
            miniature = None
            if video.miniature:
                cible = dossier_images / f"miniature{video.miniature.suffix.lower()}"
                shutil.copy(video.miniature, cible)
                miniature = f"{recette_id}/{cible.name}"
            elif gardees:
                miniature = gardees[-1]
            db.mettre_a_jour(recette_id, transcription=transcription, images=gardees, miniature=miniature)

        if not config.cle_claude_presente():
            if config.mode_claude() == "manuel":
                message = ("Vidéo importée. Clique sur « Analyser avec l'appli Claude » "
                           "pour obtenir la fiche.")
            else:
                message = ("Claude n'est pas connecté : légende et transcription enregistrées. "
                           "Connecte Claude dans Réglages puis clique sur Analyser.")
            db.mettre_a_jour(recette_id, statut="brouillon", progression="", erreur=message)
            return
        analyser(recette_id)
    except Exception as exc:
        traceback.print_exc()
        db.mettre_a_jour(recette_id, statut="erreur", progression="", erreur=str(exc)[:500])


def analyser(recette_id: int) -> None:
    recette = db.lire(recette_id)
    if not recette:
        return
    try:
        db.mettre_a_jour(recette_id, statut="en_cours", progression="Rédaction de la fiche par Claude", erreur="")
        images = [config.DOSSIER_IMAGES / chemin for chemin in recette["images"]]
        fiche = structuration.structurer(recette["titre"] or "", recette["legende"], recette["transcription"], images)
        _appliquer_fiche(recette_id, fiche, recette["titre"] or "")
        recette = db.lire(recette_id)
        if config.ADAPTATION_AUTO and recette["statut"] == "pret":
            db.mettre_a_jour(recette_id, statut="en_cours", progression="Adaptation Thermomix et airfryer")
            try:
                db.mettre_a_jour(recette_id, adaptations=structuration.adapter(recette))
            except Exception:
                traceback.print_exc()  # la fiche reste utilisable, l'encart propose de réessayer
            db.mettre_a_jour(recette_id, statut="pret", progression="")
    except Exception as exc:
        traceback.print_exc()
        db.mettre_a_jour(recette_id, statut="brouillon", progression="", erreur=str(exc)[:500])


@app.get("/api/etat")
def etat():
    return {"cle_claude": config.cle_claude_presente(), "mode": config.mode_claude(),
            "modele_whisper": config.MODELE_WHISPER, "portions_defaut": config.PORTIONS_DEFAUT}


def _masquer(cle: str) -> str:
    return f"{cle[:10]}…{cle[-4:]}" if len(cle) > 16 else ("enregistrée" if cle else "")


@app.get("/api/reglages")
def lire_reglages():
    return {
        "mode": config.mode_claude(),
        "cle_api": _masquer(config.cle_api()),
        "claude_code": config.chemin_claude_code() or "",
        "etat": _etat_claude(),
    }


@app.put("/api/reglages")
def modifier_reglages(donnees: Reglages):
    valeurs = {}
    if donnees.mode is not None:
        if donnees.mode not in config.MODES:
            raise HTTPException(400, "Mode inconnu.")
        valeurs["mode"] = donnees.mode
    if donnees.cle_api:
        cle = donnees.cle_api.strip()
        if not cle.startswith("sk-ant-"):
            raise HTTPException(400, "Une clé API Claude commence par sk-ant-.")
        valeurs["cle_api"] = cle
    if donnees.effacer_cle:
        valeurs["cle_api"] = None
    config.ecrire_reglages(valeurs)
    return lire_reglages()


@app.post("/api/reglages/tester")
def tester_reglages():
    try:
        return {"ok": True, "message": structuration.tester_connexion()}
    except structuration.ErreurStructuration as exc:
        return {"ok": False, "message": str(exc)}


@app.post("/api/importer")
def importer(donnees: Import, taches: BackgroundTasks):
    url = extraire_url(donnees.url)
    if not url:
        raise HTTPException(400, "Aucun lien trouvé dans le texte.")
    for r in db.lister():
        if r["source_url"] == url and r["statut"] != "erreur":
            return {"id": r["id"], "deja_presente": True}
    recette_id = db.creer(source_url=url, titre="Import en cours", statut="en_cours",
                          progression="En attente")
    taches.add_task(traiter, recette_id, url)
    return {"id": recette_id, "deja_presente": False}


@app.post("/api/recettes")
def creer_manuellement(donnees: Modification):
    valeurs = donnees.model_dump(exclude_none=True)
    if "ingredients" in valeurs:
        valeurs["ingredients"] = [dict(i) for i in valeurs["ingredients"]]
    valeurs.setdefault("titre", "Nouvelle recette")
    recette_id = db.creer(statut="pret", plateforme="Manuelle", **valeurs)
    return db.lire(recette_id)


@app.get("/api/recettes")
def lister(q: str = "", tag: str = ""):
    return db.lister(q, tag)


@app.get("/api/recettes/{recette_id}")
def lire(recette_id: int):
    recette = db.lire(recette_id)
    if not recette:
        raise HTTPException(404, "Recette introuvable.")
    return recette


@app.put("/api/recettes/{recette_id}")
def modifier(recette_id: int, donnees: Modification):
    if not db.lire(recette_id):
        raise HTTPException(404, "Recette introuvable.")
    valeurs = donnees.model_dump(exclude_none=True)
    if "tags" in valeurs:
        valeurs["tags"] = [t.strip().lower() for t in valeurs["tags"] if t.strip()]
    if valeurs.get("ingredients") or valeurs.get("etapes"):
        valeurs.update(statut="pret", erreur="")
    db.mettre_a_jour(recette_id, **valeurs)
    return db.lire(recette_id)


@app.post("/api/recettes/{recette_id}/analyser")
def relancer_analyse(recette_id: int, taches: BackgroundTasks):
    if not db.lire(recette_id):
        raise HTTPException(404, "Recette introuvable.")
    if not config.cle_claude_presente():
        raise HTTPException(400, "Claude n'est pas connecté. Ouvre la page Réglages.")
    db.mettre_a_jour(recette_id, statut="en_cours", progression="En attente", erreur="")
    taches.add_task(analyser, recette_id)
    return {"ok": True}


@app.post("/api/recettes/{recette_id}/adapter")
def adapter_appareils(recette_id: int):
    """Version Thermomix TM7 et airfryer Ninja. Prend 20 à 60 secondes."""
    recette = db.lire(recette_id)
    if not recette:
        raise HTTPException(404, "Recette introuvable.")
    if not config.cle_claude_presente():
        raise HTTPException(400, "Claude n'est pas connecté. Ouvre la page Réglages.")
    try:
        adaptations = structuration.adapter(recette)
    except structuration.ErreurStructuration as exc:
        raise HTTPException(502, str(exc)) from exc
    db.mettre_a_jour(recette_id, adaptations=adaptations)
    return db.lire(recette_id)


@app.get("/api/recettes/{recette_id}/demande")
def demande_manuelle(recette_id: int, type: str = "fiche"):
    """Texte à coller dans l'appli Claude (mode manuel)."""
    recette = db.lire(recette_id)
    if not recette:
        raise HTTPException(404, "Recette introuvable.")
    if type not in structuration.SCHEMAS:
        raise HTTPException(400, "Type de demande inconnu.")
    try:
        texte = structuration.demande_manuelle(type, recette)
    except structuration.ErreurStructuration as exc:
        raise HTTPException(400, str(exc)) from exc
    images = [f"/images/{c}" for c in recette["images"]] if type == "fiche" else []
    return {"texte": texte, "images": images}


@app.post("/api/recettes/{recette_id}/reponse")
def reponse_manuelle(recette_id: int, donnees: ReponseManuelle):
    """Enregistre la réponse JSON collée depuis l'appli Claude."""
    recette = db.lire(recette_id)
    if not recette:
        raise HTTPException(404, "Recette introuvable.")
    if donnees.type not in structuration.SCHEMAS:
        raise HTTPException(400, "Type de réponse inconnu.")
    try:
        resultat = structuration.lire_reponse_manuelle(donnees.type, donnees.texte)
    except structuration.ErreurStructuration as exc:
        raise HTTPException(400, str(exc)) from exc
    if donnees.type == "fiche":
        _appliquer_fiche(recette_id, resultat, recette["titre"] or "")
    else:
        db.mettre_a_jour(recette_id, adaptations=resultat)
    return db.lire(recette_id)


@app.post("/api/recettes/{recette_id}/reimporter")
def reimporter(recette_id: int, taches: BackgroundTasks):
    recette = db.lire(recette_id)
    if not recette or not recette["source_url"]:
        raise HTTPException(404, "Recette introuvable.")
    db.mettre_a_jour(recette_id, statut="en_cours", progression="En attente", erreur="")
    taches.add_task(traiter, recette_id, recette["source_url"])
    return {"ok": True}


@app.delete("/api/recettes/{recette_id}")
def supprimer(recette_id: int):
    if not db.supprimer(recette_id):
        raise HTTPException(404, "Recette introuvable.")
    shutil.rmtree(config.DOSSIER_IMAGES / str(recette_id), ignore_errors=True)
    return {"ok": True}


@app.get("/api/tags")
def tags():
    return db.tous_les_tags()


app.mount("/images", StaticFiles(directory=config.DOSSIER_IMAGES), name="images")


@app.get("/")
def accueil():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
