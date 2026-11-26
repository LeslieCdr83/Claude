"""Notifications sur téléphone et ordinateur (Web Push), envoyées par le serveur de l'appli.

Chaque appareil qui active les notifications donne un « abonnement » (une adresse fournie
par Apple, Google ou Mozilla). Le serveur y envoie un message signé avec sa propre clé VAPID,
créée au premier lancement et gardée dans data/.
"""
import base64
import json
import threading
import traceback

from . import config

FICHIER_CLE = config.DOSSIER_DONNEES / "vapid_prive.pem"
FICHIER_ABONNEMENTS = config.DOSSIER_DONNEES / "abonnements.json"
# Apple exige un contact dans la signature. Adresse générique : aucune donnée personnelle.
CONTACT = "mailto:mes-recettes@example.com"
_verrou = threading.Lock()


def cle_publique() -> str:
    """Clé publique à donner au navigateur (format base64 URL, point non compressé)."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01

    with _verrou:
        if not FICHIER_CLE.exists():
            vapid = Vapid01()
            vapid.generate_keys()
            vapid.save_key(str(FICHIER_CLE))
    vapid = Vapid01.from_file(str(FICHIER_CLE))
    brut = vapid.public_key.public_bytes(serialization.Encoding.X962,
                                         serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(brut).decode().rstrip("=")


def _lire() -> dict:
    try:
        return json.loads(FICHIER_ABONNEMENTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ecrire(abonnements: dict) -> None:
    FICHIER_ABONNEMENTS.write_text(json.dumps(abonnements, ensure_ascii=False), encoding="utf-8")


def abonner(appareil: str, abonnement: dict) -> None:
    with _verrou:
        abonnements = _lire()
        abonnements[appareil] = abonnement
        _ecrire(abonnements)


def desabonner(appareil: str) -> None:
    with _verrou:
        abonnements = _lire()
        abonnements.pop(appareil, None)
        _ecrire(abonnements)


def est_abonne(appareil: str) -> bool:
    return appareil in _lire()


def envoyer(titre: str, texte: str, lien: str = "/#/menus", sauf: str | None = None) -> None:
    """Envoie la notification à tous les appareils abonnés, sauf celui qui a fait le changement.
    L'envoi se fait en arrière-plan pour ne pas ralentir l'appli."""
    destinataires = {a: ab for a, ab in _lire().items() if a != sauf}
    if destinataires:
        threading.Thread(target=_envoyer, args=(destinataires, titre, texte, lien), daemon=True).start()


def _envoyer(destinataires: dict, titre: str, texte: str, lien: str) -> None:
    from pywebpush import WebPushException, webpush

    message = json.dumps({"titre": titre, "texte": texte, "lien": lien}, ensure_ascii=False)
    for appareil, abonnement in destinataires.items():
        try:
            webpush(abonnement, message, vapid_private_key=str(FICHIER_CLE),
                    vapid_claims={"sub": CONTACT}, ttl=24 * 3600)
        except WebPushException as exc:
            # 404 ou 410 : l'appareil s'est désabonné ou l'appli a été supprimée.
            if exc.response is not None and exc.response.status_code in (404, 410):
                desabonner(appareil)
            else:
                traceback.print_exc()
        except Exception:
            traceback.print_exc()
