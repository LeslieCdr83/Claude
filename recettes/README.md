# Mes recettes

Application web personnelle qui sauvegarde des recettes depuis une vidéo TikTok, Instagram, Facebook ou YouTube.

Tu colles le lien de la vidéo. L'application :

1. télécharge la vidéo avec yt-dlp ;
2. capture 6 images pour lire le texte affiché à l'écran ;
3. transcrit la voix sur ton ordinateur avec faster-whisper, gratuitement et sans clé ;
4. envoie légende, transcription et captures à Claude, qui rédige la fiche : titre, portions, temps, ingrédients, étapes, tags.

Tu retrouves ensuite tes recettes avec une recherche, des tags, des favoris, un ajusteur de portions, une liste de courses et l'impression.

## Installation

1. Installe Python 3.12 depuis https://www.python.org/downloads/. Sur Windows, coche « Add python.exe to PATH » au début de l'installation.
2. Télécharge le dossier de l'appli et décompresse-le où tu veux, par exemple dans Documents.
3. Ouvre le dossier `recettes`.

## Lancement

Sur Mac, double-clique sur `lancer-mac.command`. La première fois, macOS bloque le fichier : fais clic droit, « Ouvrir », puis confirme.

Sur Windows, double-clique sur `lancer-windows.bat`. Si Windows affiche « Windows a protégé votre ordinateur », clique sur « Informations complémentaires » puis « Exécuter quand même ».

Le premier lancement installe tout, en 2 à 5 minutes. Le navigateur s'ouvre ensuite sur http://localhost:8000. Garde la fenêtre noire ouverte tant que tu utilises l'appli.

Le premier import télécharge aussi le modèle de transcription (environ 500 Mo). Les imports suivants prennent 30 secondes à 2 minutes.

## Ajouter la clé Claude

1. Crée un compte sur https://console.anthropic.com et ajoute quelques dollars de crédit.
2. Crée une clé API.
3. Dans le dossier `recettes`, fais une copie de `reglages-exemple.txt` et renomme-la `reglages.txt`.
4. Ouvre `reglages.txt` avec un éditeur de texte et colle ta clé après `ANTHROPIC_API_KEY=`.
5. Ferme la fenêtre noire et relance l'appli.

Sans clé, l'import marche déjà. La recette reste en brouillon avec la légende, la transcription et les captures. Une fois la clé ajoutée, ouvre le brouillon et clique sur « Analyser avec Claude ».

Coût estimé : 3 à 8 centimes par recette avec le modèle Claude Opus 5.5 (4 $ par million de jetons en entrée, 20 $ en sortie, d'après la grille tarifaire d'Anthropic). Pour réduire le coût, ajoute la ligne `MODELE_CLAUDE=claude-haiku-5-5` dans `reglages.txt`.

## Portions et appareils

Chaque fiche affiche les quantités pour 4 personnes. Les boutons + et − changent le nombre, et la recette d'origine reste indiquée. Pour un autre nombre par défaut, ajoute `PORTIONS_DEFAUT=2` dans `reglages.txt`.

Après chaque import, Claude rédige aussi une version Thermomix TM7 et une version airfryer Ninja pour 4 personnes, avec les réglages de chaque étape. L'encart indique si la recette se fait entièrement, en partie ou pas du tout avec l'appareil. Pour des réglages plus précis, indique le modèle de ton airfryer : `MODELE_AIRFRYER=Ninja Foodi Dual Zone AF400EU`. Pour ne générer ces versions qu'à la demande, mets `ADAPTATION_AUTO=non`.

## Instagram et Facebook

Instagram et Facebook bloquent souvent le téléchargement sans connexion. Dans ce cas :

1. Installe l'extension « Get cookies.txt LOCALLY » dans ton navigateur.
2. Connecte-toi à Instagram et à Facebook dans le même navigateur, puis exporte les cookies de chaque site.
3. Regroupe-les dans un seul fichier `cookies.txt` en collant le contenu de l'un à la suite de l'autre.
4. Indique son chemin dans `reglages.txt` : `COOKIES_FICHIER=/chemin/vers/cookies.txt`.

## Sur ton téléphone, avec Tailscale

Tailscale relie ton téléphone à ton ordinateur par une adresse HTTPS privée. Personne d'autre n'y a accès. C'est gratuit pour un usage personnel.

1. Crée un compte sur https://tailscale.com et installe Tailscale sur ton ordinateur.
2. Installe l'appli Tailscale sur ton téléphone et connecte-toi avec le même compte.
3. Lance Mes recettes sur l'ordinateur.
4. Ouvre un terminal (Terminal sur Mac, PowerShell sur Windows) et tape la commande ci-dessous.

Sur Mac :

```bash
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg 8000
```

Sur Windows :

```bash
tailscale serve --bg 8000
```

La première fois, la commande affiche un lien pour activer HTTPS. Ouvre-le, valide, puis relance la commande. Elle affiche ensuite ton adresse, du type `https://nom-de-ton-ordi.tail1234.ts.net`. Cette commande reste active même après un redémarrage.

5. Sur ton téléphone, Tailscale activé, ouvre cette adresse.
6. Installe l'appli : sur Android, menu du navigateur puis « Installer l'application ». Sur iPhone, bouton Partager de Safari puis « Sur l'écran d'accueil ».

Sur Android, « Mes recettes » apparaît ensuite dans le menu Partager de TikTok et Instagram. Sur iPhone, copie le lien de la vidéo et colle-le dans l'appli.

L'ordinateur doit être allumé, avec Mes recettes lancé, pour que le téléphone y accède.

## Données

Les recettes vivent dans `data/recettes.db` et les images dans `data/images`. Sauvegarde ce dossier pour garder ta bibliothèque.

## Tests

```bash
python -m pytest tests
```
