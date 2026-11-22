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

## Mettre à jour l'appli

Ferme la fenêtre noire, puis double-clique sur `mettre-a-jour.bat` dans le dossier `recettes`. Le script télécharge la dernière version et remplace les fichiers de l'appli. Il ne touche ni à `data` (tes recettes, ta liste, tes réglages) ni à `reglages.txt`.

## Connecter Claude

L'appli a besoin de Claude pour rédiger les fiches. Tu choisis à chaque fois : l'encart d'import, la fiche et l'encart Thermomix et airfryer ont un bouton par mode. L'appli met en avant le dernier mode utilisé. Un bouton grisé indique un mode pas encore configuré. La page Réglages (icône ⚙) sert à enregistrer la clé API et à tester chaque mode.

| Mode | Coût | Fonctionnement |
|---|---|---|
| Abonnement Claude (Claude Code) | Inclus dans Pro ou Max | Automatique |
| Clé API | 5 à 12 centimes par recette | Automatique |
| Manuel, avec l'appli Claude | Gratuit, tout compte Claude | Copier-coller |

### Mode manuel

Importe la vidéo avec « Sans analyse », puis clique sur « Appli Claude (copier-coller) » sur la fiche. L'appli prépare la demande :

1. Clique sur « Copier la demande ».
2. Colle-la dans une nouvelle conversation de l'appli Claude ou de claude.ai. Joins les captures de la vidéo pour que Claude lise les quantités affichées à l'écran.
3. Copie la réponse de Claude, colle-la dans l'appli et clique sur « Enregistrer la réponse ».

L'appli vérifie la réponse avant de l'enregistrer. Le même principe sert pour les versions Thermomix et airfryer.

### Avec ton abonnement Claude (sans payer de jetons)

Il faut un abonnement Claude Pro ou Max. Les analyses comptent dans les limites d'utilisation de ton abonnement, sans facture en plus.

1. Installe Claude Code. Sur Windows, ouvre PowerShell et tape :

```bash
irm https://claude.ai/install.ps1 | iex
```

Sur Mac, ouvre Terminal et tape :

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

2. Ferme le terminal, ouvre-en un nouveau et tape `claude`. Choisis la connexion avec ton compte Claude et valide dans le navigateur. Tape ensuite `/exit`.
3. Relance l'appli. Le bouton « Claude Code » devient actif. Réglages propose « Tester Claude Code ».

Une analyse complète (fiche, TM7 et Ninja) prend 30 à 60 secondes.

### Avec une clé API (payante)

1. Crée un compte sur https://console.anthropic.com et ajoute quelques dollars de crédit.
2. Crée une clé API.
3. Dans Réglages, colle la clé et clique sur « Enregistrer ». Le bouton « API Claude » devient actif.

Coût estimé : 3 à 8 centimes par recette avec Claude Opus 5.5 (4 $ par million de jetons en entrée, 20 $ en sortie, d'après la grille tarifaire d'Anthropic), plus 2 à 4 centimes pour l'adaptation aux appareils. Pour réduire le coût, ajoute la ligne `MODELE_CLAUDE=claude-haiku-5-5` dans `reglages.txt`.

### Sans Claude

Le bouton « Sans analyse » importe la vidéo en brouillon, avec la légende, la transcription et les captures. Tu choisis plus tard comment rédiger la fiche.

## Portions et appareils

Quand la vidéo ne donne pas une quantité, Claude l'estime à partir d'une part habituelle par personne (par exemple 80 à 100 g de pâtes sèches), multipliée par le nombre de portions. Ces quantités portent le signe ≈ sur la fiche et dans la liste de courses. Le sel, le poivre et les épices restent sans quantité. Une quantité corrigée à la main perd le signe ≈.

Chaque fiche affiche les quantités pour 4 personnes. Les boutons + et − changent le nombre, et la recette d'origine reste indiquée. Pour un autre nombre par défaut, ajoute `PORTIONS_DEFAUT=2` dans `reglages.txt`.

Après chaque import, Claude rédige aussi, dans la même demande que la fiche, une version Thermomix TM7 et une version airfryer Ninja pour 4 personnes, avec les réglages de chaque étape. L'encart indique si la recette se fait entièrement, en partie ou pas du tout avec l'appareil. Pour des réglages plus précis, indique le modèle de ton airfryer : `MODELE_AIRFRYER=Ninja Foodi Dual Zone AF400EU`. Pour ne générer ces versions qu'à la demande, mets `ADAPTATION_AUTO=non`.

## Menus de la semaine

La page Menus tire 5 plats au hasard parmi tes recettes rédigées, du lundi au vendredi. Elle écarte les desserts, boissons et sauces, et évite que deux plats partagent la même base (pâtes, riz, poulet, poisson, légumineuses...) ou les mêmes tags. Un nouveau tirage évite aussi les plats du tirage précédent.

- 🔒 garde un plat lors du prochain tirage.
- ↻ change seulement le plat de ce jour.
- « Tout ajouter aux courses » ajoute les 5 plats à la liste de courses, pour 4 personnes.

Le tirage se fait dans l'appli, sans Claude : il est gratuit et immédiat.

## Mettre à jour une recette avec un JSON Claude

Sur une fiche, le bouton « Coller un JSON Claude » accepte une fiche complète ou une version TM7 et Ninja. L'appli reconnaît le type. Les champs absents gardent leur valeur : tu peux coller seulement les ingrédients ou seulement les étapes. La page « + » (nouvelle recette) permet aussi de créer une recette à partir d'un JSON.

Pour créer une recette à partir d'un simple titre avec ChatGPT (ou Claude), copie le texte de `prompts/chatgpt-recette-depuis-titre.txt`, remplace `[ÉCRIS LE TITRE ICI]` par le nom du plat, puis colle la réponse dans la page « + », section « Créer à partir d'un JSON Claude ».

## Leclerc Drive

Leclerc Drive ne permet pas à une autre appli de remplir ton panier. L'appli t'aide autrement : dans la liste de courses, 🛒 ouvre la recherche du produit dans ton magasin, et la ligne se coche. Tu choisis le produit et tu l'ajoutes au panier.

Pour l'activer, cherche un produit dans ton drive (par exemple « farine »), copie l'adresse de la page de résultats et colle-la dans Réglages, section Leclerc Drive.

Le bouton « Partager » de la liste de courses envoie la liste en texte vers Notes, Rappels, SMS ou WhatsApp.

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

Les recettes vivent dans `data/recettes.db` et les images dans `data/images`. La liste de courses et le menu de la semaine sont dans `data/partage.json` : le PC et le téléphone partagent les mêmes. Sauvegarde ce dossier pour garder ta bibliothèque.

## Tests

```bash
python -m pytest tests
```
