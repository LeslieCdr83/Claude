#!/bin/bash
# Double-clique sur ce fichier pour lancer Mes recettes sur Mac.
cd "$(dirname "$0")"

PYTHON=""
for candidat in python3.12 python3.13 python3.11 python3.10 python3; do
  if command -v "$candidat" >/dev/null 2>&1 && "$candidat" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PYTHON="$candidat"; break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.10 ou plus récent est introuvable."
  echo "Installe-le depuis https://www.python.org/downloads/ puis relance ce fichier."
  read -r -p "Appuie sur Entrée pour fermer."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Première installation, compte 2 à 5 minutes..."
  "$PYTHON" -m venv .venv || exit 1
fi
source .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements.txt || { read -r -p "Installation échouée. Entrée pour fermer."; exit 1; }

echo ""
echo "Mes recettes tourne sur http://localhost:8000"
echo "Garde cette fenêtre ouverte. Ferme-la pour arrêter l'appli."
(sleep 3 && open http://localhost:8000) &
uvicorn app.main:app --host 127.0.0.1 --port 8000
