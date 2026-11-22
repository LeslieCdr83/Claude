import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

DOSSIER_TEST = tempfile.mkdtemp()
os.environ["RECETTES_DONNEES"] = DOSSIER_TEST
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["MODE_CLAUDE"] = "api"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import extraction, main, structuration  # noqa: E402

client = TestClient(main.app)

FICHE = {
    "est_une_recette": True,
    "titre": "Pâtes au citron",
    "portions": "2 personnes",
    "temps_preparation": "5 min",
    "temps_cuisson": "10 min",
    "ingredients": [{"quantite": "200", "unite": "g", "nom": "spaghetti"},
                    {"quantite": "1", "unite": "", "nom": "citron"}],
    "etapes": ["Cuire les pâtes.", "Ajouter le citron."],
    "tags": ["Rapide", "végétarien"],
    "notes": "",
}


APPAREIL = {"faisable": "oui", "explication": "", "resume": "15 min", "conseils": "",
            "etapes": [{"instruction": "Mets l'eau", "mode": "", "temps": "10 min", "temperature": "100 °C", "vitesse": "1"}]}
ADAPTATIONS = {"portions": 4, "ingredients": [{"quantite": "400", "unite": "g", "nom": "spaghetti"}],
               "thermomix": APPAREIL, "airfryer": {**APPAREIL, "faisable": "non", "etapes": []}}


def faux_telechargement(url, dossier):
    video = dossier / "media.00001.mp4"
    video.write_bytes(b"x")
    miniature = dossier / "media.00001.jpg"
    miniature.write_bytes(b"jpg")
    return extraction.Video(url=url, titre="Pasta", legende="200 g de spaghetti, 1 citron",
                            auteur="chef", plateforme="TikTok", duree=30, fichier=video, miniature=miniature)


def preparer_faux(monkeypatch):
    monkeypatch.setattr(extraction, "telecharger", faux_telechargement)
    monkeypatch.setattr(extraction, "extraire_images", lambda f, d, dossier, nombre=6: [])
    monkeypatch.setattr(extraction, "transcrire", lambda f: "on fait cuire les pâtes")


def test_extraire_url():
    assert main.extraire_url("Regarde https://vm.tiktok.com/ZMabc/ trop bon !") == "https://vm.tiktok.com/ZMabc/"
    assert main.extraire_url("pas de lien") is None


def test_import_sans_cle_donne_un_brouillon(monkeypatch):
    preparer_faux(monkeypatch)
    rep = client.post("/api/importer", json={"url": "https://www.tiktok.com/@chef/video/1"})
    assert rep.status_code == 200
    recette = client.get(f"/api/recettes/{rep.json()['id']}").json()
    assert recette["statut"] == "brouillon"
    assert recette["transcription"] == "on fait cuire les pâtes"
    assert recette["legende"].startswith("200 g")
    assert recette["miniature"].endswith("miniature.jpg")

    doublon = client.post("/api/importer", json={"url": "https://www.tiktok.com/@chef/video/1"}).json()
    assert doublon["deja_presente"] is True


def test_import_avec_cle_remplit_la_fiche(monkeypatch):
    preparer_faux(monkeypatch)
    monkeypatch.setattr(main.config, "cle_claude_presente", lambda: True)
    monkeypatch.setattr(main.structuration, "structurer", lambda *a: FICHE)
    monkeypatch.setattr(main.structuration, "adapter", lambda r: ADAPTATIONS)
    rep = client.post("/api/importer", json={"url": "https://www.tiktok.com/@chef/video/2"})
    recette = client.get(f"/api/recettes/{rep.json()['id']}").json()
    assert recette["statut"] == "pret"
    assert recette["adaptations"]["thermomix"]["faisable"] == "oui"
    assert recette["titre"] == "Pâtes au citron"
    assert recette["tags"] == ["rapide", "végétarien"]
    assert len(recette["ingredients"]) == 2


def test_echec_de_telechargement(monkeypatch):
    def echec(url, dossier):
        raise extraction.ErreurTelechargement("vidéo privée")
    monkeypatch.setattr(extraction, "telecharger", echec)
    rep = client.post("/api/importer", json={"url": "https://www.instagram.com/reel/abc/"})
    recette = client.get(f"/api/recettes/{rep.json()['id']}").json()
    assert recette["statut"] == "erreur"
    assert "privée" in recette["erreur"]


def test_creation_modification_recherche_suppression():
    r = client.post("/api/recettes", json={"titre": "Crêpes", "tags": ["dessert"],
                                           "ingredients": [{"quantite": "250", "unite": "g", "nom": "farine"}]}).json()
    assert r["statut"] == "pret"
    client.put(f"/api/recettes/{r['id']}", json={"favori": True, "tags": [" Dessert ", ""]})
    modifiee = client.get(f"/api/recettes/{r['id']}").json()
    assert modifiee["favori"] is True and modifiee["tags"] == ["dessert"]

    assert any(x["id"] == r["id"] for x in client.get("/api/recettes", params={"q": "farine"}).json())
    assert not client.get("/api/recettes", params={"q": "chocolat"}).json()
    assert "dessert" in client.get("/api/tags").json()

    assert client.delete(f"/api/recettes/{r['id']}").status_code == 200
    assert client.get(f"/api/recettes/{r['id']}").status_code == 404


def test_analyser_sans_cle_refuse():
    r = client.post("/api/recettes", json={"titre": "X"}).json()
    assert client.post(f"/api/recettes/{r['id']}/analyser").status_code == 400


def test_structurer_appelle_claude(monkeypatch, tmp_path):
    image = tmp_path / "capture.jpg"
    image.write_bytes(b"\xff\xd8fake")
    appels = {}

    class FauxMessages:
        def create(self, **kwargs):
            appels.update(kwargs)
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=json.dumps(FICHE))])

    class FauxClient:
        def __init__(self, **kwargs):
            self.beta = SimpleNamespace(messages=FauxMessages())

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", FauxClient)
    monkeypatch.setattr(structuration.config, "cle_api_presente", lambda: True)
    monkeypatch.setattr(structuration.config, "mode_claude", lambda: "api")

    fiche = structuration.structurer("Pasta", "légende", "voix", [image])
    assert fiche["titre"] == "Pâtes au citron"
    assert appels["output_config"]["format"]["schema"] is structuration.SCHEMA_RECETTE
    contenu = appels["messages"][0]["content"]
    assert contenu[0]["type"] == "image" and contenu[0]["source"]["media_type"] == "image/jpeg"
    assert "<legende>" in contenu[-1]["text"]


def test_adapter_appareils(monkeypatch):
    r = client.post("/api/recettes", json={"titre": "Pâtes", "portions": "2 personnes",
                                           "ingredients": [{"quantite": "200", "unite": "g", "nom": "spaghetti"}]}).json()
    assert client.post(f"/api/recettes/{r['id']}/adapter").status_code == 400  # pas de clé
    monkeypatch.setattr(main.config, "cle_claude_presente", lambda: True)
    recu = {}
    monkeypatch.setattr(main.structuration, "adapter", lambda rec: recu.update(rec) or ADAPTATIONS)
    maj = client.post(f"/api/recettes/{r['id']}/adapter").json()
    assert recu["titre"] == "Pâtes"
    assert maj["adaptations"]["portions"] == 4
    assert client.get(f"/api/recettes/{r['id']}").json()["adaptations"]["airfryer"]["faisable"] == "non"


def test_consignes_adaptation(monkeypatch):
    envoye = {}
    monkeypatch.setattr(structuration, "_appeler_claude", lambda texte, schema: envoye.update(c=texte, s=schema) or ADAPTATIONS)
    structuration.adapter({"titre": "Pâtes", "portions": "2 personnes", "etapes": ["Cuire"],
                           "ingredients": [{"quantite": "200", "unite": "g", "nom": "spaghetti"}]})
    texte = envoye["c"]
    assert "pour 4 personnes" in texte and "TM7" in texte and "Ninja" in texte
    assert "- 200 g spaghetti" in texte and "{" not in texte.split("<recette>")[0]
    assert envoye["s"] is structuration.SCHEMA_ADAPTATIONS


def test_reglages_depuis_l_appli():
    assert client.get("/api/reglages").json()["mode"] == "api"
    assert client.put("/api/reglages", json={"cle_api": "mauvaise"}).status_code == 400
    r = client.put("/api/reglages", json={"mode": "abonnement", "cle_api": "sk-ant-api03-abcdefghijklmnop1234"}).json()
    assert r["mode"] == "abonnement" and r["cle_api"].startswith("sk-ant-api") and "1234" in r["cle_api"]
    assert main.config.cle_api() == "sk-ant-api03-abcdefghijklmnop1234"
    r = client.put("/api/reglages", json={"mode": "manuel", "effacer_cle": True}).json()
    assert r["mode"] == "manuel" and r["cle_api"] == ""
    assert client.get("/api/etat").json()["cle_claude"] is False
    client.put("/api/reglages", json={"mode": "api"})


def test_mode_manuel_aller_retour():
    r = client.post("/api/recettes", json={"titre": "Brouillon"}).json()
    main.db.mettre_a_jour(r["id"], legende="200 g de riz", transcription="on cuit le riz", statut="brouillon")
    demande = client.get(f"/api/recettes/{r['id']}/demande", params={"type": "fiche"}).json()
    assert "200 g de riz" in demande["texte"] and '"est_une_recette"' in demande["texte"]

    assert client.post(f"/api/recettes/{r['id']}/reponse", json={"type": "fiche", "texte": "désolé"}).status_code == 400
    incomplet = json.dumps({"titre": "Riz"})
    rep = client.post(f"/api/recettes/{r['id']}/reponse", json={"type": "fiche", "texte": incomplet})
    assert rep.status_code == 400 and "manquant" in rep.json()["detail"]

    colle = "Voici la fiche :\n```json\n" + json.dumps({**FICHE, "titre": "Riz nature", "en_trop": 1}) + "\n```"
    fiche = client.post(f"/api/recettes/{r['id']}/reponse", json={"type": "fiche", "texte": colle}).json()
    assert fiche["titre"] == "Riz nature" and fiche["statut"] == "pret"

    demande = client.get(f"/api/recettes/{r['id']}/demande", params={"type": "adaptation"}).json()
    assert "TM7" in demande["texte"]
    maj = client.post(f"/api/recettes/{r['id']}/reponse", json={"type": "adaptation", "texte": json.dumps(ADAPTATIONS)}).json()
    assert maj["adaptations"]["thermomix"]["faisable"] == "oui"
