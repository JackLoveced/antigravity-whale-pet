@echo off
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\agy-petw.exe" (
    start "" "%~dp0.venv\Scripts\agy-petw.exe"
) else if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" -m antigravity_whale_pet
) else (
    start "" agy-petw
)
