@echo off
rem Double-clique sur ce fichier pour lancer Mes recettes sur Windows.
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python est introuvable.
  echo Installe Python 3.12 depuis https://www.python.org/downloads/windows/
  echo puis relance ce fichier.
  pause
  exit /b 1
)

rem Choisit une version de Python compatible avec tous les outils de l'appli.
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  echo.
  echo Aucune version compatible de Python n'est installee.
  echo Versions trouvees sur ce PC :
  py --list
  echo.
  echo Installe Python 3.12 : https://www.python.org/downloads/windows/
  echo Cherche "Python 3.12" et prends "Windows installer (64-bit)".
  echo Puis relance ce fichier.
  pause
  exit /b 1
)

rem Une installation interrompue laisse un dossier .venv incomplet : on repart de zero.
if exist .venv if not exist .venv\installation-ok (
  echo Nettoyage d'une installation incomplete...
  rmdir /s /q .venv
)

if not exist .venv\installation-ok (
  echo Premiere installation avec %PY%, compte 2 a 5 minutes...
  echo Le detail s'ecrit dans le fichier installation.log
  %PY% -m venv .venv > installation.log 2>&1
  if errorlevel 1 goto echec
  .venv\Scripts\python.exe -m pip install --disable-pip-version-check --upgrade pip >> installation.log 2>&1
  .venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt >> installation.log 2>&1
  if errorlevel 1 goto echec
  echo ok > .venv\installation-ok
)

echo.
echo Mes recettes tourne sur http://localhost:8000
echo Garde cette fenetre ouverte. Ferme-la pour arreter l'appli.
start "" cmd /c "timeout /t 4 >nul & start http://localhost:8000"
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo L'appli s'est arretee. Fais une capture de cette fenetre si c'est inattendu.
pause
exit /b 0

:echec
echo.
echo ===== Installation echouee. Dernieres lignes du journal : =====
powershell -NoProfile -Command "Get-Content -Tail 25 installation.log"
echo ================================================================
echo Fais une capture de cette fenetre et envoie-la.
echo Le journal complet est dans le fichier installation.log du dossier recettes.
if exist .venv rmdir /s /q .venv
pause
exit /b 1
