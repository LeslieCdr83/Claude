@echo off
rem Double-clique sur ce fichier pour lancer Mes recettes sur Windows.
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python est introuvable.
  echo Installe-le depuis https://www.python.org/downloads/ puis relance ce fichier.
  pause
  exit /b 1
)

if not exist .venv (
  echo Premiere installation, compte 2 a 5 minutes...
  py -3 -m venv .venv || (pause & exit /b 1)
)
call .venv\Scripts\activate.bat
pip install -q --disable-pip-version-check -r requirements.txt || (echo Installation echouee. & pause & exit /b 1)

echo.
echo Mes recettes tourne sur http://localhost:8000
echo Garde cette fenetre ouverte. Ferme-la pour arreter l'appli.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
