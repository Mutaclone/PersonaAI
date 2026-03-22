@echo off
setlocal enabledelayedexpansion
title Persona — EEL Compiler

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║       PERSONA — EEL COMPILER  v1.6           ║
echo  ║  Drop an HTML file onto this bat to compile  ║
echo  ║  (Single-file mode: one .exe, no extras)     ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: ── Check an HTML file was dragged in ────────────────────────
if "%~1"=="" (
    echo  [ERROR] No file provided.
    echo  Drag and drop your HTML file onto this .bat to compile.
    echo.
    pause
    exit /b 1
)

set "HTML_PATH=%~1"
set "HTML_NAME=%~n1"
set "HTML_EXT=%~x1"
set "HTML_DIR=%~dp1"

if /i not "%HTML_EXT%"==".html" (
    echo  [ERROR] "%HTML_NAME%%HTML_EXT%" is not an HTML file.
    echo  Please drag a .html file onto this bat.
    echo.
    pause
    exit /b 1
)

:: ── Locate main.py and app.py next to this bat ───────────────
set "BAT_DIR=%~dp0"
set "MAIN_PY=%BAT_DIR%main.py"
set "APP_PY=%BAT_DIR%app.py"

if not exist "%MAIN_PY%" (
    echo  [ERROR] main.py not found at: %MAIN_PY%
    echo  Make sure main.py is in the same folder as this .bat
    echo.
    pause
    exit /b 1
)
if not exist "%APP_PY%" (
    echo  [ERROR] app.py not found at: %APP_PY%
    echo  Make sure app.py is in the same folder as this .bat
    echo.
    pause
    exit /b 1
)

echo  Input HTML : %HTML_PATH%
echo  App name   : %HTML_NAME%
echo  Project dir: %BAT_DIR%
echo.

:: ── Find Python ───────────────────────────────────────────────
echo  [1/7] Locating Python installation...
set "PYTHON="

python --version >nul 2>&1
if not errorlevel 1 ( set "PYTHON=python" & goto :python_found )

py --version >nul 2>&1
if not errorlevel 1 ( set "PYTHON=py" & goto :python_found )

for %%B in (
    "%LOCALAPPDATA%\Programs\Python"
    "%PROGRAMFILES%\Python"
    "%PROGRAMFILES(X86)%\Python"
    "%APPDATA%\Programs\Python"
    "%SYSTEMDRIVE%\Python"
    "%USERPROFILE%\AppData\Local\Programs\Python"
) do (
    if exist "%%~B" (
        for /d %%D in ("%%~B\Python3*") do (
            if exist "%%D\python.exe" ( set "PYTHON=%%D\python.exe" & goto :python_found )
        )
        for /d %%D in ("%%~B\Python*") do (
            if exist "%%D\python.exe" ( set "PYTHON=%%D\python.exe" & goto :python_found )
        )
    )
)

echo.
echo  [WARN] Python was not found in any standard location.
echo  A deep disk search has been skipped to protect your system.
echo.
echo  Please do one of the following:
echo    1. Install Python from https://python.org
echo       (check "Add Python to PATH" during setup)
echo    2. If Python is already installed, add its folder to your PATH
echo.

echo  [ERROR] Could not locate Python on this machine.
echo  Install from https://python.org — check "Add Python to PATH" during setup.
echo.
pause
exit /b 1

:python_found
for /f "tokens=*" %%v in ('"%PYTHON%" --version 2^>^&1') do echo         %%v
echo         Path: %PYTHON%

:: ── Install dependencies ──────────────────────────────────────
echo.
echo  [2/7] Installing dependencies...
echo         (eel, pyinstaller, Pillow — first run may take a minute)
echo.

"%PYTHON%" -m pip install --quiet --upgrade pip >nul 2>&1
"%PYTHON%" -m pip install --quiet --upgrade eel pyinstaller Pillow

if errorlevel 1 (
    echo  [ERROR] pip install failed. Check internet or run as Administrator.
    echo.
    pause
    exit /b 1
)
echo         All dependencies ready.

:: ── Locate and convert icon ───────────────────────────────────
echo.
echo  [3/7] Locating icon...

set "ICON_ARG="
set "ICO_PATH=%BAT_DIR%icon.ico"

:: Priority order: icon.ico > icon.png > PersonaIcon.png > *.ico > *.png
if exist "%BAT_DIR%icon.ico" (
    set "ICON_ARG=--icon \"%BAT_DIR%icon.ico\""
    echo         Found: icon.ico
    goto :icon_done
)

:: Convert PNG to ICO using Pillow
set "PNG_TO_CONVERT="

if exist "%BAT_DIR%icon.png" (
    set "PNG_TO_CONVERT=%BAT_DIR%icon.png"
    echo         Found: icon.png — converting to icon.ico...
    goto :do_convert
)

if exist "%BAT_DIR%PersonaIcon.png" (
    set "PNG_TO_CONVERT=%BAT_DIR%PersonaIcon.png"
    echo         Found: PersonaIcon.png — converting to icon.ico...
    goto :do_convert
)

:: Search for any .ico in the folder
for %%F in ("%BAT_DIR%*.ico") do (
    set "ICON_ARG=--icon \"%%F\""
    echo         Found: %%~nxF
    goto :icon_done
)

:: Search for any .png in the folder
for %%F in ("%BAT_DIR%*.png") do (
    set "PNG_TO_CONVERT=%%F"
    echo         Found: %%~nxF — converting to icon.ico...
    goto :do_convert
)

echo         No icon found — building without a custom icon.
echo         (Place icon.png or icon.ico next to this bat to add one)
goto :icon_done

:do_convert
"%PYTHON%" -c "from PIL import Image; img=Image.open(r'%PNG_TO_CONVERT%').convert('RGBA'); img.save(r'%ICO_PATH%', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
if errorlevel 1 (
    echo         [WARN] Icon conversion failed — building without icon.
    goto :icon_done
)
echo         Converted to: icon.ico
set "ICON_ARG=--icon \"%ICO_PATH%\""

:icon_done

:: ── Copy HTML into web\ folder ────────────────────────────────
echo.
echo  [4/7] Copying HTML into web\ folder...

set "WEB_DIR=%BAT_DIR%web"
if not exist "%WEB_DIR%" mkdir "%WEB_DIR%"

copy /y "%HTML_PATH%" "%WEB_DIR%\index.html" >nul
echo         Copied to: %WEB_DIR%\index.html

:: ── Run PyInstaller ───────────────────────────────────────────
:: v1.6: switched back to --onefile for single-exe distribution.
:: The web/ folder is bundled inside the exe and extracted at runtime
:: via sys._MEIPASS (handled in app.py).
::
:: NOTE: --onefile uses 2-4 GB RAM during build (compression step).
::       If your machine has less than 8 GB RAM, the build may be slow
::       or fail. In that case, change --onefile to --onedir below.
echo.
echo  [5/7] Running PyInstaller (single-file mode)...
echo         Building self-contained exe with all assets bundled inside.
echo         This may use 2-4 GB RAM during compression.
echo.

cd /d "%BAT_DIR%"

if defined ICON_ARG (
    echo         Using icon: %ICO_PATH%
    "%PYTHON%" -m PyInstaller ^
        --onefile ^
        --windowed ^
        --name "%HTML_NAME%" ^
        --add-data "web;web" ^
        --add-data "server.py;." ^
        --icon "%ICO_PATH%" ^
        --hidden-import "bottle" ^
        --hidden-import "bottle_websocket" ^
        --hidden-import "geventwebsocket" ^
        --hidden-import "PIL" ^
        --hidden-import "PIL.Image" ^
        --hidden-import "PIL.PngImagePlugin" ^
        --noconfirm ^
        main.py
) else (
    "%PYTHON%" -m PyInstaller ^
        --onefile ^
        --windowed ^
        --name "%HTML_NAME%" ^
        --add-data "web;web" ^
        --add-data "server.py;." ^
        --hidden-import "bottle" ^
        --hidden-import "bottle_websocket" ^
        --hidden-import "geventwebsocket" ^
        --hidden-import "PIL" ^
        --hidden-import "PIL.Image" ^
        --hidden-import "PIL.PngImagePlugin" ^
        --noconfirm ^
        main.py
)

if errorlevel 1 (
    echo.
    echo  [ERROR] PyInstaller failed. See output above.
    echo  Common fixes:
    echo    - Right-click this .bat and "Run as administrator"
    echo    - Temporarily disable antivirus
    echo    - If out of RAM, edit this bat and change --onefile to --onedir
    echo.
    pause
    exit /b 1
)

:: ── Copy output exe to same folder as HTML ───────────────────
echo.
echo  [6/7] Copying output...

set "EXE_SRC=%BAT_DIR%dist\%HTML_NAME%.exe"
set "EXE_DEST=%HTML_DIR%%HTML_NAME%.exe"

if not exist "%EXE_SRC%" (
    echo  [ERROR] Built exe not found at: %EXE_SRC%
    echo  The build may have failed. Check the output above.
    pause
    exit /b 1
)

copy /y "%EXE_SRC%" "%EXE_DEST%" >nul
echo         Copied to: %EXE_DEST%

:: ── Clean up build artifacts ──────────────────────────────────
:: NOTE: We keep build/ and dist/ as cache for faster rebuilds.
::       Only __pycache__ and .spec files are cleaned.
echo  [7/7] Cleaning temporary files...
if exist "%BAT_DIR%__pycache__" rd /s /q "%BAT_DIR%__pycache__"
for %%F in ("%BAT_DIR%*.spec") do del /q "%%F"
echo         Done. (build/ and dist/ kept as cache for faster rebuilds)

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║               BUILD COMPLETE!                ║
echo  ╚══════════════════════════════════════════════╝
echo.
echo   Output : %EXE_DEST%
echo.
echo   This is a single self-contained .exe — just
echo   share the file. No folders or dependencies needed.
echo.
echo   On first launch, a "characters\" folder and
echo   "settings.config" will be created next to the exe.
echo.
echo   [TIP] If your antivirus flags the exe:
echo         Add an exclusion for: %EXE_DEST%
echo.

explorer /select,"%EXE_DEST%"
pause
exit /b 0

