@echo off
echo.
echo  AeroSense ATC -- 12-Phase Multi-Agent ATC System
echo =====================================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (echo  ERROR: Python 3.10+ required & pause & exit /b 1)

if "%GOOGLE_API_KEY%"=="" (
  echo  ERROR: GOOGLE_API_KEY is not set.
  echo  Set it with:  set GOOGLE_API_KEY=AIza...
  echo  Get a key at: https://aistudio.google.com/app/apikey
  pause & exit /b 1
)

echo  Installing dependencies...
python -m pip install -r requirements.txt -q

echo.
echo  Starting AeroSense ATC at http://localhost:8000
echo  Open dashboard: http://localhost:8000
echo.
python main.py
pause
