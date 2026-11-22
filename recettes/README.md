# Mes recettes

Application web personnelle qui sauvegarde des recettes depuis une vidéo TikTok, Instagram ou YouTube.

Tu colles le lien de la vidéo. L'application :

1. télécharge la vidéo avec yt-dlp ;
2. capture 6 images pour lire le texte affiché à l'écran ;
3. transcrit la voix sur ton ordinateur avec faster-whisper, gratuitement et sans clé ;
4. envoie légende, transcription et captures à Claude, qui rédige la fiche : titre, portions, temps, ingrédients, étapes, tags.

Tu retrouves ensuite tes recettes avec une recherche, des tags, des favoris, un ajusteur de portions, une liste de courses et l'impression.

## Installation

Il te faut Python 3.10 ou plus récent et ffmpeg.

Sur Mac :

```bash
brew install python ffmpeg
```

Sur Windows, installe Python depuis python.org puis ffmpeg :

```bash
winget install ffmpeg
```

Dans le dossier `recettes`, crée l'environnement et installe les dépendances :

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

Sous Windows, la commande d'activation est `.venv\Scripts\activate`.

```bash
pip install -r requirements.txt
```

## Lancement

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ouvre http://localhost:8000 dans ton navigateur.

Le premier import télécharge le modèle de transcription (environ 500 Mo pour `small`). Les imports suivants prennent 30 secondes à 2 minutes.

## Ajouter la clé Claude

1. Crée un compte sur https://console.anthropic.com et ajoute quelques dollars de crédit.
2. Crée une clé API.
3. Copie `.env.exemple` sous le nom `.env` et colle ta clé après `ANTHROPIC_API_KEY=`.
4. Redémarre le serveur.

Sans clé, l'import marche déjà. La recette reste en brouillon avec la légende, la transcription et les captures. Une fois la clé ajoutée, ouvre le brouillon et clique sur « Analyser avec Claude ».

Coût estimé : 3 à 8 centimes par recette avec le modèle Claude Opus 5.5 (4 $ par million de jetons en entrée, 20 $ en sortie, d'après la grille tarifaire d'Anthropic). Pour réduire le coût, mets `MODELE_CLAUDE=claude-haiku-5-5` dans `.env`.

## Instagram

Instagram bloque souvent le téléchargement sans connexion. Dans ce cas :

1. Installe l'extension « Get cookies.txt LOCALLY » dans ton navigateur.
2. Connecte-toi à Instagram et exporte les cookies dans un fichier `cookies.txt`.
3. Indique son chemin dans `.env` : `COOKIES_FICHIER=/chemin/vers/cookies.txt`.

## Sur ton téléphone

Le serveur tourne sur ton ordinateur. Ton téléphone y accède s'il est sur le même Wi-Fi : ouvre `http://IP-DE-TON-ORDI:8000`.

Pour voir l'appli dans le menu « Partager » de TikTok et Instagram, il faut l'installer comme application. Android et iOS l'exigent en HTTPS. La solution la plus simple est Tailscale (gratuit) : la commande `tailscale serve 8000` donne une adresse HTTPS privée, accessible seulement depuis tes appareils. Ouvre cette adresse sur ton téléphone puis choisis « Ajouter à l'écran d'accueil ».

Sur Android, l'appli apparaît alors dans le menu Partager. Sur iPhone, Safari ne gère pas ce menu pour les applis web : copie le lien et colle-le dans l'appli.

## Données

Les recettes vivent dans `data/recettes.db` et les images dans `data/images`. Sauvegarde ce dossier pour garder ta bibliothèque.

## Tests

```bash
python -m pytest tests
```
