@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (py -3 -m venv .venv)
echo Installing requirements (first run takes a few minutes)...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (echo Install failed. Check your internet connection. & pause & exit /b 1)
start "Drukyul website and login" ".venv\Scripts\python.exe" Auth.py
start "Drukyul dashboard" ".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true
timeout /t 5 >nul
start http://127.0.0.1:5000
