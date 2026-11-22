@echo off
rem Double-clique sur ce fichier pour installer la derniere version de Mes recettes.
rem Tes recettes (dossier data), ta cle et tes reglages ne sont pas touches.
chcp 65001 >nul
cd /d "%~dp0"

echo Mise a jour de Mes recettes
echo.
echo Ferme d'abord la fenetre noire de l'appli si elle est ouverte.
pause

set "ZIP=%TEMP%\mes-recettes.zip"
set "DEST=%TEMP%\mes-recettes-maj"
set "SOURCE="

echo Telechargement de la derniere version...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/LeslieCdr83/Claude/archive/refs/heads/claude/bold-allen-uyn3k7.zip' -OutFile $env:ZIP; if (Test-Path $env:DEST) { Remove-Item -Recurse -Force $env:DEST }; Expand-Archive -Path $env:ZIP -DestinationPath $env:DEST"
if errorlevel 1 goto echec

for /d %%D in ("%DEST%\*") do set "SOURCE=%%D\recettes"
if not defined SOURCE goto echec
if not exist "%SOURCE%\app\main.py" goto echec

rem Un dossier app\app reste parfois apres une copie a la main : il ne sert a rien.
if exist "app\app" rmdir /s /q "app\app"

echo Copie des nouveaux fichiers...
robocopy "%SOURCE%\app" "app" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto echec
for %%F in (requirements.txt lancer-windows.bat lancer-mac.command README.md reglages-exemple.txt) do (
  if exist "%SOURCE%\%%F" copy /y "%SOURCE%\%%F" "%%F" >nul
)
rem Le script de mise a jour lui-meme est remplace a la fin, quand il ne tourne plus.
set "NOUVEAU_SCRIPT=%SOURCE%\mettre-a-jour.bat"

if exist .venv\Scripts\python.exe (
  echo Verification des outils...
  .venv\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements.txt
)

echo.
echo Mise a jour terminee.
choice /m "Lancer l'appli maintenant"
if errorlevel 2 goto fin
start "" "%~dp0lancer-windows.bat"

:fin
if exist "%NOUVEAU_SCRIPT%" (copy /y "%NOUVEAU_SCRIPT%" "%~f0" >nul & exit /b 0)
exit /b 0

:echec
echo.
echo La mise a jour a echoue. Verifie ta connexion internet, puis relance ce fichier.
echo Si le probleme continue, fais une capture de cette fenetre et envoie-la.
pause
exit /b 1
