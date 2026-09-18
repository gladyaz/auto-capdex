@echo off
echo ===================================
echo   Auto-Capdex Setup (Windows)
echo ===================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.8+ from https://python.org/downloads
    echo IMPORTANT: during install, check the box "Add python.exe to PATH".
    echo Then run this setup.bat again.
    pause
    exit /b 1
)

echo [OK] Python found.
python --version
echo.

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [WARNING] ffmpeg not found on PATH.
    echo This is required before you can process videos.
    echo Easiest fix: open PowerShell and run:
    echo     winget install ffmpeg
    echo Then close and reopen this folder before running run.bat.
    echo.
) else (
    echo [OK] ffmpeg found.
)

where ffprobe >nul 2>nul
if errorlevel 1 (
    echo [WARNING] ffprobe not found on PATH.
    echo ffprobe ships with ffmpeg and is required to validate videos.
    echo Without it every video will be skipped.
    echo Easiest fix: open PowerShell and run:
    echo     winget install ffmpeg
    echo Then close and reopen this folder before running run.bat.
    echo.
) else (
    echo [OK] ffprobe found.
    echo.
)

echo Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

echo Installing dependencies (this can take a few minutes)...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo ===================================
echo   Setup complete!
echo   Next: put your .mp4 files in the "input" folder,
echo   then double-click run.bat
echo ===================================
pause
