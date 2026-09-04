@echo off
chcp 65001 >nul
title Аватар-хост — интернет-режим (cloudflared)

echo ==========================================
echo   Аватар-хост — режим «через интернет»
echo ==========================================
echo.
echo Этот режим нужен, когда Wi-Fi площадки не пускает
echo телефоны к вашему компьютеру (изоляция клиентов),
echo или гости подключаются с мобильного интернета.
echo.
echo Требуется cloudflared: https://github.com/cloudflare/cloudflared/releases
echo (файл cloudflared.exe положите рядом с этим скриптом или в PATH)
echo.

where cloudflared >nul 2>&1
if errorlevel 1 (
    if not exist "%~dp0cloudflared.exe" (
        echo ОШИБКА: cloudflared не найден.
        echo Скачайте cloudflared-windows-amd64.exe, переименуйте в cloudflared.exe
        echo и положите в папку с этим скриптом.
        pause
        exit /b 1
    )
    set CF="%~dp0cloudflared.exe"
) else (
    set CF=cloudflared
)

pip install -q -r requirements.txt

echo.
echo Запускаю туннель...
echo В открывшемся окне cloudflared найдите адрес вида
echo    https://что-то-случайное.trycloudflare.com
echo Скопируйте его и вставьте ниже.
echo.

start "cloudflared" %CF% tunnel --url http://localhost:8000

set /p PUBLIC_URL="Вставьте https-адрес из окна cloudflared: "
echo.
echo Публичный адрес: %PUBLIC_URL%
echo Теперь QR-код будет вести на него.
echo.

REM Свой PIN пульта (в интернете он особенно важен):
REM set ADMIN_PIN=1234

python server.py
pause
