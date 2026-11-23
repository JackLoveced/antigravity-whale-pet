@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\agy-pet.exe" (
    "%~dp0.venv\Scripts\agy-pet.exe" disable-autostart
    ping -n 2 127.0.0.1 >nul
    "%~dp0.venv\Scripts\agy-pet.exe" status
) else (
    agy-pet disable-autostart
    ping -n 2 127.0.0.1 >nul
    agy-pet status
)
echo.
pause
