@echo off
setlocal

set "DOCWEAVE_REPO_DIR=%~dp0"
cd /d "%DOCWEAVE_REPO_DIR%"

set "DOCWEAVE_RUNTIME_LAUNCHER=%APPDATA%\DocWeave\launch-docweave-runtime.cmd"
set "DOCWEAVE_DESKTOP_EXE=%DOCWEAVE_REPO_DIR%.venv\Scripts\docweave-desktop.exe"
set "DOCWEAVE_PYTHON_EXE=%DOCWEAVE_REPO_DIR%.venv\Scripts\python.exe"

if exist "%DOCWEAVE_RUNTIME_LAUNCHER%" (
    start "DocWeave Dashboard" "%DOCWEAVE_RUNTIME_LAUNCHER%"
    exit /b 0
)

if exist "%DOCWEAVE_DESKTOP_EXE%" (
    start "DocWeave Dashboard" "%DOCWEAVE_DESKTOP_EXE%"
    exit /b 0
)

if exist "%DOCWEAVE_PYTHON_EXE%" (
    set "PYTHONPATH=%DOCWEAVE_REPO_DIR%src;%PYTHONPATH%"
    start "DocWeave Dashboard" "%DOCWEAVE_PYTHON_EXE%" -m docweave.desktop.application
    exit /b 0
)

echo DocWeave dashboard could not be started.
echo.
echo Expected a local virtual environment at:
echo   %DOCWEAVE_REPO_DIR%.venv
echo.
echo Create it from this repository with:
echo   python -m venv .venv
echo   .\.venv\Scripts\python -m pip install -r requirements-lock.txt
echo   .\.venv\Scripts\python -m pip install -e . --no-deps
echo.
pause
exit /b 1
