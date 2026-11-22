"""Transforme la légende, la transcription et les captures en fiche recette avec Claude."""
import base64
import json
from pathlib import Path

from . import config

TYPES_IMAGE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

SCHEMA_RECETTE = {
    "type": "object",
    "properties": {
        "est_une_recette": {"type": "boolean"},
        "titre": {"type": "string"},
        "portions": {"type": "string"},
        "temps_preparation": {"type": "string"},
        "temps_cuisson": {"type": "string"},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quantite": {"type": "string"},
                    "unite": {"type": "string"},
                    "nom": {"type": "string"},
                },
                "required": ["quantite", "unite", "nom"],
                "additionalProperties": False,
            },
        },
        "etapes": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["est_une_recette", "titre", "portions", "temps_preparation", "temps_cuisson",
                 "ingredients", "etapes", "tags", "notes"],
    "additionalProperties": False,
}

CONSIGNES = """Tu reçois les éléments d'une vidéo de cuisine publiée sur un réseau social : \
la légende du post, la transcription de la voix, et des captures d'écran prises à intervalles réguliers.

Rédige la fiche recette en français.
- Croise les trois sources. Les quantités apparaissent souvent seulement dans le texte affiché \
à l'écran ou dans la légende.
- Garde les quantités et unités telles que la vidéo les donne. Convertis les unités américaines \
(cups, oz, °F) en unités métriques et indique la valeur d'origine entre parenthèses.
- Laisse "quantite" et "unite" vides quand l'information manque. N'invente aucune quantité.
- Écris des étapes courtes, dans l'ordre, une action principale par étape.
- Propose 2 à 5 tags en minuscules : type de plat, régime, difficulté, temps.
- Mets dans "notes" les astuces du créateur et ce qui reste incertain.
- Laisse vides les champs que la vidéo ne permet pas de remplir.
- Si la vidéo ne contient pas de recette, mets "est_une_recette" à false."""


class ErreurStructuration(Exception):
    pass


def _bloc_image(chemin: Path) -> dict | None:
    type_media = TYPES_IMAGE.get(chemin.suffix.lower())
    if not type_media or not chemin.exists():
        return None
    donnees = base64.standard_b64encode(chemin.read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": type_media, "data": donnees}}


def structurer(titre: str, legende: str, transcription: str, images: list[Path]) -> dict:
    """Appelle Claude et renvoie un dictionnaire conforme à SCHEMA_RECETTE."""
    import anthropic

    if not config.cle_claude_presente():
        raise ErreurStructuration("Aucune clé ANTHROPIC_API_KEY configurée.")

    contenu: list[dict] = []
    for chemin in images[:10]:
        bloc = _bloc_image(chemin)
        if bloc:
            contenu.append(bloc)
    contenu.append({
        "type": "text",
        "text": (f"{CONSIGNES}\n\n<titre>{titre}</titre>\n\n<legende>\n{legende or '(vide)'}\n</legende>\n\n"
                 f"<transcription>\n{transcription or '(aucune voix détectée)'}\n</transcription>"),
    })

    client = anthropic.Anthropic()
    try:
        reponse = client.beta.messages.create(
            model=config.MODELE_CLAUDE,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"format": {"type": "json_schema", "schema": SCHEMA_RECETTE}},
            messages=[{"role": "user", "content": contenu}],
        )
    except anthropic.AuthenticationError as exc:
        raise ErreurStructuration("Clé API refusée. Vérifie ANTHROPIC_API_KEY.") from exc
    except anthropic.RateLimitError as exc:
        raise ErreurStructuration("Trop de requêtes. Réessaie dans une minute.") from exc
    except anthropic.APIStatusError as exc:
        raise ErreurStructuration(f"Erreur de l'API Claude ({exc.status_code}) : {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ErreurStructuration("Impossible de joindre l'API Claude.") from exc

    if reponse.stop_reason == "refusal":
        raise ErreurStructuration("Claude a refusé d'analyser ce contenu.")
    if reponse.stop_reason == "max_tokens":
        raise ErreurStructuration("Réponse coupée : la recette est trop longue.")

    texte = next((b.text for b in reponse.content if b.type == "text"), "")
    try:
        return json.loads(texte)
    except json.JSONDecodeError as exc:
        raise ErreurStructuration("Réponse de Claude illisible.") from exc
