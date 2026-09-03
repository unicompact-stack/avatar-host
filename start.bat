@echo off
chcp 65001 >nul
echo Запуск аватар-хоста...
cd /d "%~dp0"
pip install -r requirements.txt
python server.py
pause
