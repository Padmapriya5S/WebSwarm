@echo off
echo ===================================================
echo   WebSwarm Autonomous AI Testing Platform - Boot Sequence
echo ===================================================

echo.
echo [1/3] Setting up Backend Environment...
cd backend
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing backend dependencies...
pip install -r requirements.txt
echo Installing Playwright browsers...
playwright install chromium
echo Starting FastAPI server...
start "WebSwarm Backend" cmd /k "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo.
echo [2/3] Setting up Frontend Environment...
cd ../frontend
echo Installing frontend dependencies...
call npm install
echo Starting Vite Dev Server...
start "WebSwarm Frontend" cmd /k "npm run dev -- --port 5173"

echo.
echo [3/3] System Boot Complete!
echo ===================================================
echo The WebSwarm UI is available at: http://localhost:5173
echo The API Backend is running at:   http://localhost:8000
echo ===================================================
cd ..
