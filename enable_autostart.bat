@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === 开启「随 Antigravity 自动打开 / 自动关闭」 ===
if exist "%~dp0.venv\Scripts\agy-pet.exe" (
    "%~dp0.venv\Scripts\agy-pet.exe" enable-autostart --assets-dir "%~dp0assets"
    "%~dp0.venv\Scripts\agy-pet.exe" status
) else (
    agy-pet enable-autostart
    agy-pet status
)
echo.
echo 设置完成！以后打开 Antigravity 时鲸鱼娘会自动出现，关闭 Antigravity 时自动退出。
echo 如果现在已经开着 Antigravity，2 秒内鲸鱼娘就会自动弹出！
pause
