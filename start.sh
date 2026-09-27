#!/bin/bash

echo "==================================================="
echo "  WebSwarm Autonomous AI Testing Platform - Boot Sequence"
echo "==================================================="
echo ""

echo "[1/3] Setting up Backend Environment..."
cd backend || exit

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "Installing backend dependencies..."
pip install -r requirements.txt
echo "Installing Playwright browsers..."
playwright install chromium

echo "Starting FastAPI server in the background..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo ""
echo "[2/3] Setting up Frontend Environment..."
cd ../frontend || exit
echo "Installing frontend dependencies..."
npm install

echo ""
echo "[3/3] System Boot Complete!"
echo "==================================================="
echo "The WebSwarm UI is available at: http://localhost:5173"
echo "The API Backend is running at:   http://localhost:8000"
echo "==================================================="
echo "Press Ctrl+C to stop all servers."

# Trap Ctrl+C and kill background backend process on exit
trap "echo 'Shutting down...'; kill $BACKEND_PID; exit" INT TERM EXIT

npm run dev -- --port 5173
