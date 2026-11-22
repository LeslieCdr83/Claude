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
                    "estimee": {"type": "boolean"},
                },
                "required": ["quantite", "unite", "nom", "estimee"],
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
- Chaque ingrédient a une quantité et une unité utilisables pour la liste de courses. \
"quantite" contient seulement un nombre ("200", "1/2", "1,5"), "unite" une unité simple \
("g", "kg", "ml", "cl", "l", "c. à soupe", "c. à café", "gousse", "tranche"), ou rien pour \
un ingrédient qui se compte à la pièce (œufs, citrons, oignons).
- Quand la vidéo ne donne pas une quantité, estime-la : part habituelle pour une personne \
(par exemple 80 à 100 g de pâtes ou de riz sec, 120 à 150 g de viande ou de poisson, 200 g de légumes, \
1 œuf), multipliée par le nombre de portions. Mets alors "estimee" à true. Sinon "estimee" vaut false.
- Exception : sel, poivre, épices, herbes séchées en pincée, huile ou beurre de cuisson en petite \
quantité, eau de cuisson. Pour ceux-là, laisse "quantite" et "unite" vides et "estimee" à false.
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


def texte_fiche(titre: str, legende: str, transcription: str) -> str:
    return (f"{CONSIGNES}\n\n<titre>{titre}</titre>\n\n<legende>\n{legende or '(vide)'}\n</legende>\n\n"
            f"<transcription>\n{transcription or '(aucune voix détectée)'}\n</transcription>")


def texte_complet(titre: str, legende: str, transcription: str) -> str:
    """Fiche et versions TM7 / Ninja dans la même demande : un seul appel à Claude."""
    return (texte_fiche(titre, legende, transcription)
            + "\n\nEnsuite, à partir de la fiche que tu viens de rédiger, remplis \"adaptations\".\n"
            + consignes_adaptation())


def structurer(titre: str, legende: str, transcription: str, images: list[Path], mode: str | None = None,
               avec_adaptations: bool = False) -> dict:
    """Appelle Claude et renvoie la fiche. Avec avec_adaptations, la fiche contient aussi
    "adaptations" (versions Thermomix et airfryer), obtenues dans le même appel."""
    if avec_adaptations:
        return _appeler_claude(texte_complet(titre, legende, transcription), SCHEMA_COMPLET, images[:10], mode)
    return _appeler_claude(texte_fiche(titre, legende, transcription), SCHEMA_RECETTE, images[:10], mode)


def _appeler_claude(texte: str, schema: dict, images: list[Path] = (), mode: str | None = None) -> dict:
    """Passe par l'abonnement Claude (Claude Code) ou par l'API, selon MODE_CLAUDE."""
    images = [c for c in images if c.suffix.lower() in TYPES_IMAGE and c.exists()]
    if (mode or config.mode_claude()) == "abonnement":
        return _appeler_abonnement(texte, schema, images)
    return _appeler_api(texte, schema, images)


def _appeler_api(texte: str, schema: dict, images: list[Path]) -> dict:
    import anthropic

    if not config.cle_api_presente():
        raise ErreurStructuration("Aucune clé ANTHROPIC_API_KEY configurée.")

    contenu = [b for b in (_bloc_image(c) for c in images) if b]
    contenu.append({"type": "text", "text": texte})
    client = anthropic.Anthropic(api_key=config.cle_api())
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

    sortie = next((b.text for b in reponse.content if b.type == "text"), "")
    try:
        return json.loads(sortie)
    except json.JSONDecodeError as exc:
        raise ErreurStructuration("Réponse de Claude illisible.") from exc


def _appeler_abonnement(texte: str, schema: dict, images: list[Path]) -> dict:
    """Utilise Claude Code connecté à ton abonnement Claude : pas de jetons API facturés."""
    import os
    import subprocess

    executable = config.chemin_claude_code()
    if not executable:
        raise ErreurStructuration("Claude Code est introuvable. Installe-le (voir le README) ou passe MODE_CLAUDE=api.")

    if images:
        texte += ("\n\nCaptures d'écran de la vidéo, à lire avec l'outil Read :\n"
                  + "\n".join(str(c.resolve()) for c in images))
    commande = [executable, "-p", "--output-format", "json", "--json-schema", json.dumps(schema),
                "--max-turns", "15", "--tools", "Read" if images else ""]
    if images:
        commande += ["--allowedTools", "Read"]
    # Sans cette précaution, Claude Code utiliserait la clé API (facturée) au lieu de l'abonnement.
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    dossier = images[0].parent if images else config.DOSSIER_DONNEES
    try:
        res = subprocess.run(commande, input=texte, capture_output=True, text=True, encoding="utf-8",
                             env=env, cwd=dossier, timeout=600, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ErreurStructuration("Claude Code n'a pas répondu en 10 minutes.") from exc

    try:
        resultat = json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        detail = (res.stderr or res.stdout or "").strip()[-300:]
        raise ErreurStructuration(f"Claude Code a échoué : {detail}") from exc

    if resultat.get("is_error") or resultat.get("subtype") != "success":
        message = str(resultat.get("result") or resultat.get("subtype") or "erreur inconnue")
        bas = message.lower()
        if "login" in bas or "api key" in bas or "auth" in bas:
            message = "Claude Code n'est pas connecté. Ouvre un terminal, tape claude puis /login."
        elif "limit" in bas:
            message = "Limite d'utilisation de ton abonnement atteinte. Réessaie plus tard."
        raise ErreurStructuration(message[:400])

    sortie = resultat.get("structured_output")
    if isinstance(sortie, dict):
        return sortie
    try:
        return json.loads(resultat.get("result") or "")
    except json.JSONDecodeError as exc:
        raise ErreurStructuration("Réponse de Claude Code illisible.") from exc


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
- Chaque ingrédient a une quantité et une unité utilisables pour la liste de courses. \
"quantite" contient seulement un nombre ("200", "1/2", "1,5"), "unite" une unité simple \
("g", "kg", "ml", "cl", "l", "c. à soupe", "c. à café", "gousse", "tranche"), ou rien pour \
un ingrédient qui se compte à la pièce (œufs, citrons, oignons).
- Quand la recette ne donne pas une quantité, estime-la : part habituelle pour une personne \
(par exemple 80 à 100 g de pâtes ou de riz sec, 120 à 150 g de viande ou de poisson, 200 g de légumes, \
1 œuf), multipliée par le nombre de portions. Mets alors "estimee" à true. Sinon "estimee" vaut false.
- Exception : sel, poivre, épices, herbes séchées en pincée, huile ou beurre de cuisson en petite \
quantité, eau de cuisson. Pour ceux-là, laisse "quantite" et "unite" vides et "estimee" à false.
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


def adapter(recette: dict, mode: str | None = None) -> dict:
    """Renvoie {"thermomix": {...}, "airfryer": {...}} pour une recette déjà structurée."""
    return _appeler_claude(texte_adaptation(recette), SCHEMA_ADAPTATIONS, mode=mode)


def consignes_adaptation() -> str:
    return (CONSIGNES_ADAPTATION.replace("{modele}", config.MODELE_AIRFRYER)
            .replace("{personnes}", str(config.PORTIONS_DEFAUT)))


def texte_adaptation(recette: dict) -> str:
    ingredients = "\n".join(
        "- " + " ".join(x for x in (i.get("quantite", ""), i.get("unite", ""), i.get("nom", "")) if x)
        for i in recette.get("ingredients", [])
    )
    etapes = "\n".join(f"{n}. {e}" for n, e in enumerate(recette.get("etapes", []), 1))
    if not ingredients and not etapes:
        raise ErreurStructuration("La recette n'a ni ingrédients ni étapes à adapter.")
    texte = (
        consignes_adaptation()
        + f"\n\n<recette>\nTitre : {recette.get('titre') or ''}\nPortions : {recette.get('portions') or ''}\n"
        + f"Ingrédients :\n{ingredients}\n\nÉtapes :\n{etapes}\n\nNotes : {recette.get('notes') or ''}\n</recette>"
    )
    return texte


# ---------- Mode manuel : copier-coller avec l'appli Claude ----------

SCHEMA_COMPLET = {
    **SCHEMA_RECETTE,
    "properties": {**SCHEMA_RECETTE["properties"], "adaptations": SCHEMA_ADAPTATIONS},
    "required": [*SCHEMA_RECETTE["required"], "adaptations"],
}
# Un JSON collé peut contenir ou non les adaptations.
SCHEMAS = {"fiche": {**SCHEMA_COMPLET, "required": SCHEMA_RECETTE["required"]}, "adaptation": SCHEMA_ADAPTATIONS}


def demande_manuelle(type_demande: str, recette: dict) -> str:
    """Texte à coller dans l'appli Claude. La réponse attendue est un JSON conforme au schéma."""
    if type_demande == "fiche":
        construire = texte_complet if config.ADAPTATION_AUTO else texte_fiche
        texte = construire(recette.get("titre") or "", recette.get("legende") or "",
                           recette.get("transcription") or "")
        texte += ("\n\nSi des captures d'écran de la vidéo sont jointes, lis le texte qu'elles affichent "
                  "(quantités, ingrédients).")
        schema = SCHEMA_COMPLET if config.ADAPTATION_AUTO else SCHEMA_RECETTE
    else:
        texte = texte_adaptation(recette)
        schema = SCHEMA_ADAPTATIONS
    schema = json.dumps(schema, ensure_ascii=False)
    return (texte + "\n\nRéponds uniquement avec un objet JSON valide qui respecte ce schéma JSON, "
            f"sans texte avant ni après :\n{schema}")


def extraire_json(texte: str) -> dict:
    """Trouve l'objet JSON dans un texte collé, avec ou sans bloc ```json autour."""
    texte = (texte or "").strip()
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin <= debut:
        raise ErreurStructuration("Aucun objet JSON trouvé dans le texte collé.")
    try:
        donnees = json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError as exc:
        raise ErreurStructuration(f"JSON invalide : {exc.msg}, ligne {exc.lineno}.") from exc
    if not isinstance(donnees, dict):
        raise ErreurStructuration("Le JSON doit être un objet entre accolades { }.")
    return donnees


def detecter_type(donnees: dict) -> str:
    """Un JSON avec "thermomix" ou "airfryer" est une adaptation. Sinon, c'est une fiche."""
    return "adaptation" if ("thermomix" in donnees or "airfryer" in donnees) else "fiche"


def lire_reponse_manuelle(type_demande: str, texte: str, defauts: dict | None = None) -> tuple[str, dict]:
    """Vérifie le JSON collé. Les champs absents reprennent les valeurs actuelles (defauts),
    ce qui permet de ne coller qu'une partie, par exemple seulement les ingrédients."""
    donnees = extraire_json(texte)
    if type_demande == "auto":
        type_demande = detecter_type(donnees)
    tous = defauts or {}
    if type_demande == "fiche" and isinstance(donnees.get("adaptations"), dict):
        # Adaptations partielles (par exemple seulement le Ninja) : le reste est gardé.
        donnees["adaptations"] = {**(tous.get("adaptation") or {}), **donnees["adaptations"]}
    return type_demande, valider({**(tous.get(type_demande) or {}), **donnees}, SCHEMAS[type_demande])


def valider(valeur, schema: dict, chemin: str = "réponse"):
    """Vérifie les types et les champs obligatoires. Ignore les champs en trop."""
    attendu = schema.get("type")
    if attendu == "object":
        if not isinstance(valeur, dict):
            raise ErreurStructuration(f"{chemin} : objet attendu.")
        sortie = {}
        for cle, sous_schema in schema.get("properties", {}).items():
            if cle in valeur:
                sortie[cle] = valider(valeur[cle], sous_schema, f"{chemin}.{cle}")
            elif sous_schema.get("type") == "boolean" and cle == "estimee":
                sortie[cle] = False
            elif cle in schema.get("required", []):
                raise ErreurStructuration(f"Champ manquant : {chemin}.{cle}")
        return sortie
    if attendu == "array":
        if not isinstance(valeur, list):
            raise ErreurStructuration(f"{chemin} : liste attendue.")
        return [valider(v, schema["items"], f"{chemin}[{i}]") for i, v in enumerate(valeur)]
    if attendu == "string":
        if valeur is None:
            return ""
        if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
            valeur = str(valeur)
        if not isinstance(valeur, str):
            raise ErreurStructuration(f"{chemin} : texte attendu.")
        if "enum" in schema and valeur not in schema["enum"]:
            raise ErreurStructuration(f"{chemin} : valeur attendue parmi {', '.join(schema['enum'])}.")
        return valeur
    if attendu == "integer":
        try:
            return int(valeur)
        except (TypeError, ValueError) as exc:
            raise ErreurStructuration(f"{chemin} : nombre entier attendu.") from exc
    if attendu == "boolean":
        if not isinstance(valeur, bool):
            raise ErreurStructuration(f"{chemin} : true ou false attendu.")
        return valeur
    return valeur


# ---------- Test de connexion (page Réglages) ----------

def tester_connexion(mode: str) -> str:
    if mode == "manuel":
        return "Mode manuel : rien à tester. Tu colleras les demandes dans l'appli Claude."
    if mode == "api":
        import anthropic
        if not config.cle_api_presente():
            raise ErreurStructuration("Aucune clé API enregistrée.")
        try:
            anthropic.Anthropic(api_key=config.cle_api()).models.list(limit=1)
        except anthropic.AuthenticationError as exc:
            raise ErreurStructuration("Clé API refusée. Vérifie qu'elle est complète.") from exc
        except anthropic.APIError as exc:
            raise ErreurStructuration(f"Erreur de l'API Claude : {exc}") from exc
        return "Clé API valide."
    resultat = _appeler_abonnement(
        "Réponds avec ok = true.", {"type": "object", "properties": {"ok": {"type": "boolean"}},
                                    "required": ["ok"], "additionalProperties": False}, [])
    if resultat.get("ok") is not True:
        raise ErreurStructuration("Claude Code a répondu, mais pas comme prévu.")
    return "Claude Code répond avec ton abonnement."
