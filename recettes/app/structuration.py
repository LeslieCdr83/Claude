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
- "portions" commence par un nombre, par exemple "2 personnes". Si la vidéo ne le dit pas, \
estime-le d'après les quantités et signale l'estimation dans "notes".
- Laisse vides les autres champs que la vidéo ne permet pas de remplir.
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

    return _appeler_claude(contenu, SCHEMA_RECETTE)


def _appeler_claude(contenu: list[dict], schema: dict) -> dict:
    import anthropic

    if not config.cle_claude_presente():
        raise ErreurStructuration("Aucune clé ANTHROPIC_API_KEY configurée.")

    client = anthropic.Anthropic()
    try:
        reponse = client.beta.messages.create(
            model=config.MODELE_CLAUDE,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"format": {"type": "json_schema", "schema": schema}},
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


# ---------- Adaptation aux appareils ----------

def _schema_appareil() -> dict:
    return {
        "type": "object",
        "properties": {
            "faisable": {"type": "string", "enum": ["oui", "partiel", "non"]},
            "explication": {"type": "string"},
            "resume": {"type": "string"},
            "etapes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "instruction": {"type": "string"},
                        "mode": {"type": "string"},
                        "temps": {"type": "string"},
                        "temperature": {"type": "string"},
                        "vitesse": {"type": "string"},
                    },
                    "required": ["instruction", "mode", "temps", "temperature", "vitesse"],
                    "additionalProperties": False,
                },
            },
            "conseils": {"type": "string"},
        },
        "required": ["faisable", "explication", "resume", "etapes", "conseils"],
        "additionalProperties": False,
    }


SCHEMA_ADAPTATIONS = {
    "type": "object",
    "properties": {
        "portions": {"type": "integer"},
        "ingredients": SCHEMA_RECETTE["properties"]["ingredients"],
        "thermomix": _schema_appareil(),
        "airfryer": _schema_appareil(),
    },
    "required": ["portions", "ingredients", "thermomix", "airfryer"],
    "additionalProperties": False,
}

CONSIGNES_ADAPTATION = """Adapte cette recette pour {personnes} personnes et pour deux appareils, en français. \
Écris au tutoiement.

Quantités :
- Recalcule chaque quantité pour {personnes} personnes à partir des portions d'origine. \
Si les portions d'origine manquent, estime-les d'après les quantités et dis-le dans les conseils.
- Arrondis de façon pratique : œufs entiers, cuillères au demi près, grammes à 5 g près.
- Mets cette liste dans "ingredients" et "portions" = {personnes}. Les étapes des deux appareils \
utilisent ces quantités.

1. Thermomix TM7 (Vorwerk).
- Bol de 2,2 litres. Vérifie que les quantités tiennent. Sinon, indique de diviser en plusieurs fournées.
- Réglages au format Thermomix : temps (ex. "5 min", "30 s"), température (37 à 160 °C, ou "Varoma"), \
vitesse ("cuillère", 1 à 10, "Turbo") avec "sens inverse" quand il faut préserver les morceaux.
- Utilise les modes du TM7 quand ils conviennent : Rissoler, Pétrin, Turbo, Cuisson lente, Sous-vide, \
Fermentation, Épaissir, Cuisson du riz, Vapeur avec le Varoma. Laisse "mode" vide pour une étape classique.
- Précise quand utiliser le fouet (papillon), le panier de cuisson ou le Varoma.
- Une étape par réglage : l'instruction dit quoi mettre dans le bol, les champs donnent le réglage.

2. Airfryer Ninja (\
{modele}).
- Modes Ninja : Air Fry, Max Crisp, Roast, Bake, Reheat, Dehydrate. Température en °C, temps en minutes.
- Indique quand secouer ou retourner, quand huiler, et si une fournée unique suffit.
- Pour un modèle double zone, précise ce qui va dans chaque bac et l'usage de Sync ou Match.
- Laisse "vitesse" vide.

Pour chaque appareil :
- "faisable" : "oui" si tout se fait dans l'appareil, "partiel" si une partie demande un autre ustensile \
(dis lequel et à quelle étape), "non" si l'appareil n'apporte rien (dis pourquoi dans "explication", etapes vide).
- "resume" : une ligne avec le temps total et les réglages clés.
- "conseils" : les écarts avec la recette d'origine (texture, temps de cuisson, quantités ajustées).
- N'invente pas de fonction qui n'existe pas sur l'appareil."""


def adapter(recette: dict) -> dict:
    """Renvoie {"thermomix": {...}, "airfryer": {...}} pour une recette déjà structurée."""
    ingredients = "\n".join(
        "- " + " ".join(x for x in (i.get("quantite", ""), i.get("unite", ""), i.get("nom", "")) if x)
        for i in recette.get("ingredients", [])
    )
    etapes = "\n".join(f"{n}. {e}" for n, e in enumerate(recette.get("etapes", []), 1))
    if not ingredients and not etapes:
        raise ErreurStructuration("La recette n'a ni ingrédients ni étapes à adapter.")
    texte = (
        CONSIGNES_ADAPTATION.replace("{modele}", config.MODELE_AIRFRYER)
        .replace("{personnes}", str(config.PORTIONS_DEFAUT))
        + f"\n\n<recette>\nTitre : {recette.get('titre') or ''}\nPortions : {recette.get('portions') or ''}\n"
        + f"Ingrédients :\n{ingredients}\n\nÉtapes :\n{etapes}\n\nNotes : {recette.get('notes') or ''}\n</recette>"
    )
    return _appeler_claude([{"type": "text", "text": texte}], SCHEMA_ADAPTATIONS)
