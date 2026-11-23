@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === 关闭「随 Antigravity 自动打开 / 自动关闭」 ===
if exist "%~dp0.venv\Scripts\agy-pet.exe" (
    "%~dp0.venv\Scripts\agy-pet.exe" disable-autostart
    "%~dp0.venv\Scripts\agy-pet.exe" status
) else (
    agy-pet disable-autostart
    agy-pet status
)
echo.
pause
