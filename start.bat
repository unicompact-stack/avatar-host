@echo off
title Avatar-host

echo ===================================
echo   Avatar-host v4.2.0
echo ===================================
echo.

REM --- Firewall rule: phones need port 8000 open ---
net session >nul 2>&1
if %errorlevel% equ 0 (
    netsh advfirewall firewall show rule name="Avatar-host 8000" >nul 2>&1
    if errorlevel 1 (
        echo Opening port 8000 in Windows Firewall...
        netsh advfirewall firewall add rule name="Avatar-host 8000" dir=in action=allow protocol=TCP localport=8000 >nul
        echo Done.
    ) else (
        echo Firewall rule already exists.
    )
) else (
    echo WARNING: no admin rights.
    echo If phones cannot connect, right-click start.bat and Run as Administrator.
)
echo.

echo Installing dependencies...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip install failed. Check Python is installed and in PATH.
    pause
    exit /b 1
)
echo.

REM Set your own PIN (uncomment and change):
REM set ADMIN_PIN=1234

python server.py
pause
