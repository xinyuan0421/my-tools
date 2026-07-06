@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ==============================================
echo   msg_send GUI - Build Windows EXE
echo ==============================================
echo.

:: Change to the directory where this bat file lives
cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)
echo [1/3] Python found: OK

:: Install PyInstaller
echo [2/3] Installing PyInstaller...
python -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller
    pause
    exit /b 1
)
echo       PyInstaller: OK

:: Clean old build
if exist "dist\msgsend_gui.exe" del /f /q "dist\msgsend_gui.exe"
if exist "build" rmdir /s /q "build"

:: Build EXE
echo [3/3] Building EXE...
python -m PyInstaller msgsend_gui.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check errors above.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   Build SUCCESS!
echo   EXE: %~dp0dist\msgsend_gui.exe
echo ==============================================
echo.
echo   Usage:
echo   - Copy dist\msgsend_gui.exe to any Windows PC
echo   - Double-click to run (no Python needed)
echo   - Click [folder] button to point to clustermw root
echo.
start "" "%~dp0dist\msgsend_gui.exe"
pause
