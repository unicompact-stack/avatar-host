@echo off
chcp 65001 >nul
title Аватар-хост

echo ===================================
echo   Аватар-хост — локальная сеть
echo ===================================
echo.

REM --- Правило фаервола: без него телефоны не достучатся до порта 8000 ---
net session >nul 2>&1
if %errorlevel% equ 0 (
    netsh advfirewall firewall show rule name="Avatar-host 8000" >nul 2>&1
    if errorlevel 1 (
        echo Открываю порт 8000 в брандмауэре Windows...
        netsh advfirewall firewall add rule name="Avatar-host 8000" dir=in action=allow protocol=TCP localport=8000 >nul
        echo Готово.
    ) else (
        echo Правило брандмауэра уже есть.
    )
) else (
    echo ВНИМАНИЕ: запущено без прав администратора.
    echo Если телефоны не открывают страницу — закройте это окно и запустите
    echo start.bat правой кнопкой → «Запуск от имени администратора».
)
echo.

echo Устанавливаю зависимости...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ОШИБКА: pip install не выполнился. Проверьте, что Python установлен и есть в PATH.
    pause
    exit /b 1
)
echo.

REM Свой PIN пульта — раскомментируйте и поменяйте:
REM set ADMIN_PIN=1234

python server.py
pause
