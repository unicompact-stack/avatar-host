@echo off
echo ===================================
echo   Avatar-host v3.0.0
echo ===================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip install failed. Check Python is installed and in PATH.
    pause
    exit /b 1
)
echo.
echo Starting server on port 8000...
echo.
echo   Host screen:   http://localhost:8000/host
echo   Guest connect:  http://localhost:8000/connect
echo   Test mode:      http://localhost:8000/
echo.
python server.py
pause
