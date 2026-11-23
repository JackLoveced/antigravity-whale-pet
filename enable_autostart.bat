@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\agy-pet.exe" (
    "%~dp0.venv\Scripts\agy-pet.exe" enable-autostart --assets-dir "%~dp0assets"
    ping -n 3 127.0.0.1 >nul
    "%~dp0.venv\Scripts\agy-pet.exe" status
) else (
    agy-pet enable-autostart
    ping -n 3 127.0.0.1 >nul
    agy-pet status
)
echo.
pause
