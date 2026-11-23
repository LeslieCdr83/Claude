"""Serveur web : API des recettes et interface."""
import json
import re
import shutil
import threading
import tempfile
import traceback
from pathlib import Path

from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, extraction, notifications, structuration

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Mes recettes")


@app.middleware("http")
async def sans_cache(request, call_next):
    """Le navigateur revérifie l'interface à chaque ouverture : une mise à jour de l'appli
    s'affiche sans Ctrl + F5, y compris dans l'appli installée sur le téléphone."""
    reponse = await call_next(request)
    if not request.url.path.startswith("/images/"):
        reponse.headers["Cache-Control"] = "no-cache"
    return reponse
db.initialiser()


def _etat_claude() -> str:
    api = "enregistrée" if config.disponible("api") else "absente (page Réglages)"
    code = "trouvé" if config.disponible("abonnement") else "introuvable (voir le README)"
    return f"Clé API Claude : {api}. Claude Code : {code}."


def _mode_valide(mode: str | None) -> str:
    if mode not in ("api", "abonnement"):
        raise HTTPException(400, "Choisis API Claude ou Claude Code.")
    if not config.disponible(mode):
        raise HTTPException(400, "Enregistre d'abord ta clé API dans Réglages." if mode == "api"
                            else "Claude Code est introuvable sur cet ordinateur. Voir le README.")
    return mode


print("", flush=True)
print(_etat_claude(), flush=True)


class Import(BaseModel):
    url: str
    mode: str | None = None  # "api", "abonnement" ou rien (brouillon à analyser plus tard)


class Ingredient(BaseModel):
    quantite: str = ""
    unite: str = ""
    nom: str = ""
    estimee: bool = False
    achat: str = ""  # produit à chercher en magasin, sans préparation


class Reglages(BaseModel):
    cle_api: str | None = None
    effacer_cle: bool = False
    drive: str | None = None  # lien d'une recherche dans ton Leclerc Drive


PARAMETRES_RECHERCHE = ("TexteRecherche", "texteRecherche", "q", "query", "search", "recherche")


def modele_drive(url: str) -> str:
    """Transforme le lien d'une recherche (ex. ...recherche.aspx?TexteRecherche=farine)
    en modèle où {q} remplace le produit cherché."""
    url = url.strip()
    if not url.startswith("https://"):
        raise HTTPException(400, "Colle un lien qui commence par https://")
    for nom in PARAMETRES_RECHERCHE:
        if re.search(rf"[?&]{nom}=", url):
            return re.sub(rf"([?&]{nom}=)[^&#]*", r"\g<1>{q}", url, count=1)
    raise HTTPException(400, "Ce lien ne contient pas de recherche. Cherche un produit sur ton drive, puis copie l'adresse.")


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


def traiter(recette_id: int, url: str, mode: str | None = None) -> None:
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

        if not config.disponible(mode):
            db.mettre_a_jour(recette_id, statut="brouillon", progression="",
                             erreur="Vidéo importée. Choisis comment rédiger la fiche ci-dessous.")
            return
        analyser(recette_id, mode)
    except Exception as exc:
        traceback.print_exc()
        db.mettre_a_jour(recette_id, statut="erreur", progression="", erreur=str(exc)[:500])


def analyser(recette_id: int, mode: str | None = None) -> None:
    recette = db.lire(recette_id)
    if not recette:
        return
    try:
        db.mettre_a_jour(recette_id, statut="en_cours", progression="Rédaction de la fiche par Claude", erreur="")
        images = [config.DOSSIER_IMAGES / chemin for chemin in recette["images"]]
        if config.ADAPTATION_AUTO:
            db.mettre_a_jour(recette_id, progression="Rédaction de la fiche et des versions TM7 et Ninja")
        # Un seul appel : la fiche et, si ADAPTATION_AUTO, les versions Thermomix et airfryer.
        fiche = structuration.structurer(recette["titre"] or "", recette["legende"], recette["transcription"],
                                         images, mode, avec_adaptations=config.ADAPTATION_AUTO)
        adaptations = fiche.pop("adaptations", None)
        _appliquer_fiche(recette_id, fiche, recette["titre"] or "")
        if adaptations and fiche.get("est_une_recette", True):
            db.mettre_a_jour(recette_id, adaptations=adaptations)
    except Exception as exc:
        traceback.print_exc()
        db.mettre_a_jour(recette_id, statut="brouillon", progression="", erreur=str(exc)[:500])


@app.get("/api/etat")
def etat():
    return {"api": config.disponible("api"), "claude_code": config.disponible("abonnement"),
            "modele_whisper": config.MODELE_WHISPER, "portions_defaut": config.PORTIONS_DEFAUT,
            "drive": config.lire_reglages().get("drive", "")}


def _masquer(cle: str) -> str:
    return f"{cle[:10]}…{cle[-4:]}" if len(cle) > 16 else ("enregistrée" if cle else "")


@app.get("/api/reglages")
def lire_reglages():
    return {
        "cle_api": _masquer(config.cle_api()),
        "claude_code": config.chemin_claude_code() or "",
        "etat": _etat_claude(),
        "drive": config.lire_reglages().get("drive", ""),
    }


@app.put("/api/reglages")
def modifier_reglages(donnees: Reglages):
    valeurs = {}
    if donnees.cle_api:
        cle = donnees.cle_api.strip()
        if not cle.startswith("sk-ant-"):
            raise HTTPException(400, "Une clé API Claude commence par sk-ant-.")
        valeurs["cle_api"] = cle
    if donnees.effacer_cle:
        valeurs["cle_api"] = None
    if donnees.drive is not None:
        valeurs["drive"] = modele_drive(donnees.drive) if donnees.drive.strip() else None
    config.ecrire_reglages(valeurs)
    return lire_reglages()


@app.post("/api/reglages/tester")
def tester_reglages(mode: str):
    try:
        return {"ok": True, "message": structuration.tester_connexion(mode)}
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
    mode = _mode_valide(donnees.mode) if donnees.mode else None
    taches.add_task(traiter, recette_id, url, mode)
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
def relancer_analyse(recette_id: int, taches: BackgroundTasks, mode: str = ""):
    if not db.lire(recette_id):
        raise HTTPException(404, "Recette introuvable.")
    mode = _mode_valide(mode)
    db.mettre_a_jour(recette_id, statut="en_cours", progression="En attente", erreur="")
    taches.add_task(analyser, recette_id, mode)
    return {"ok": True}


@app.post("/api/recettes/{recette_id}/adapter")
def adapter_appareils(recette_id: int, mode: str = ""):
    """Version Thermomix TM7 et airfryer Ninja. Prend 20 à 60 secondes."""
    recette = db.lire(recette_id)
    if not recette:
        raise HTTPException(404, "Recette introuvable.")
    mode = _mode_valide(mode)
    try:
        adaptations = structuration.adapter(recette, mode)
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
    if donnees.type not in (*structuration.SCHEMAS, "auto"):
        raise HTTPException(400, "Type de réponse inconnu.")
    defauts = {
        "fiche": {"est_une_recette": True, **{c: recette[c] or ([] if c in ("ingredients", "etapes", "tags") else "")
                  for c in ("titre", "portions", "temps_preparation", "temps_cuisson",
                            "ingredients", "etapes", "tags", "notes")}},
        "adaptation": recette["adaptations"] or {},
    }
    try:
        type_reponse, resultat = structuration.lire_reponse_manuelle(donnees.type, donnees.texte, defauts)
    except structuration.ErreurStructuration as exc:
        raise HTTPException(400, str(exc)) from exc
    if type_reponse == "fiche":
        adaptations = resultat.pop("adaptations", None)
        _appliquer_fiche(recette_id, resultat, recette["titre"] or "")
        if adaptations:
            db.mettre_a_jour(recette_id, adaptations=adaptations)
    else:
        db.mettre_a_jour(recette_id, adaptations=resultat)
    return db.lire(recette_id)


@app.post("/api/recettes/{recette_id}/reimporter")
def reimporter(recette_id: int, taches: BackgroundTasks, mode: str = ""):
    recette = db.lire(recette_id)
    if not recette or not recette["source_url"]:
        raise HTTPException(404, "Recette introuvable.")
    mode = _mode_valide(mode) if mode else None
    db.mettre_a_jour(recette_id, statut="en_cours", progression="En attente", erreur="")
    taches.add_task(traiter, recette_id, recette["source_url"], mode)
    return {"ok": True}


@app.delete("/api/recettes/{recette_id}")
def supprimer(recette_id: int):
    if not db.supprimer(recette_id):
        raise HTTPException(404, "Recette introuvable.")
    shutil.rmtree(config.DOSSIER_IMAGES / str(recette_id), ignore_errors=True)
    return {"ok": True}


# ---------- Données partagées entre appareils (liste de courses, menu de la semaine) ----------
CLES_PARTAGEES = ("courses", "coches-courses", "menu-semaine", "menu-verrous")
FICHIER_PARTAGE = config.DOSSIER_DONNEES / "partage.json"
_verrou_partage = threading.Lock()


def _lire_partage() -> dict:
    try:
        return json.loads(FICHIER_PARTAGE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@app.get("/api/partage")
def lire_partage():
    return _lire_partage()


JOURS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")


@app.put("/api/partage/{cle}")
def ecrire_partage(cle: str, valeur: list = Body(...), x_appareil: str | None = Header(None)):
    if cle not in CLES_PARTAGEES:
        raise HTTPException(404, "Donnée inconnue.")
    if len(json.dumps(valeur)) > 200_000:
        raise HTTPException(413, "Donnée trop grande.")
    with _verrou_partage:
        donnees = _lire_partage()
        ancien = donnees.get(cle) or []
        donnees[cle] = valeur
        FICHIER_PARTAGE.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    if cle == "menu-semaine":
        _annoncer_nouveaux_plats(ancien, valeur, x_appareil)
    return {"ok": True}


def _annoncer_nouveaux_plats(ancien: list, nouveau: list, appareil: str | None) -> None:
    """Notifie les autres appareils des plats qui viennent d'entrer dans le menu."""
    ajouts = []
    for jour, recette_id in enumerate(nouveau[:7]):
        if isinstance(recette_id, int) and recette_id not in ancien:
            recette = db.lire(recette_id)
            if recette:
                ajouts.append(f"{JOURS[jour]} : {recette['titre']}")
    if not ajouts:
        return
    titre = "Nouveau plat au menu" if len(ajouts) == 1 else f"{len(ajouts)} plats ajoutés au menu"
    notifications.envoyer(titre, "\n".join(ajouts), sauf=appareil)


class Abonnement(BaseModel):
    appareil: str
    abonnement: dict


@app.get("/api/notifications")
def etat_notifications(appareil: str = ""):
    try:
        cle = notifications.cle_publique()
    except ImportError as exc:
        raise HTTPException(503, "Outil de notifications manquant : lance mettre-a-jour.bat, puis relance l'appli.") from exc
    return {"cle": cle, "abonne": bool(appareil) and notifications.est_abonne(appareil)}


@app.post("/api/notifications")
def activer_notifications(donnees: Abonnement):
    if not donnees.abonnement.get("endpoint", "").startswith("https://"):
        raise HTTPException(400, "Abonnement invalide.")
    notifications.abonner(donnees.appareil, donnees.abonnement)
    return {"ok": True}


@app.delete("/api/notifications")
def desactiver_notifications(appareil: str):
    notifications.desabonner(appareil)
    return {"ok": True}


@app.post("/api/notifications/test")
def tester_notifications(appareil: str):
    if not notifications.est_abonne(appareil):
        raise HTTPException(400, "Les notifications ne sont pas activées sur cet appareil.")
    abonnement = {appareil: notifications._lire()[appareil]}
    notifications.threading.Thread(target=notifications._envoyer, daemon=True,
                                   args=(abonnement, "Mes recettes", "Les notifications fonctionnent.", "/#/menus")).start()
    return {"ok": True}


@app.get("/api/tags")
def tags():
    return db.tous_les_tags()


app.mount("/images", StaticFiles(directory=config.DOSSIER_IMAGES), name="images")


@app.get("/")
def accueil():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
