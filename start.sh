#!/bin/bash

echo "==================================================="
echo "  WebSwarm Autonomous AI Testing Platform - Boot Sequence"
echo "==================================================="
echo ""

echo "[1/3] Setting up Backend Environment..."
cd backend || exit

BACKEND_STATE=1
if curl -fsS --max-time 2 http://127.0.0.1:8000/openapi.json >/dev/null 2>&1; then
    BACKEND_STATE=0
elif command -v ss >/dev/null 2>&1 && ss -ltn '( sport = :8000 )' | tail -n +2 | grep -q .; then
    echo "Port 8000 is occupied by an unhealthy or unrelated process. Stop that process explicitly, then retry."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "Installing backend dependencies..."
pip install -r requirements.txt
echo "Installing Playwright browsers..."
playwright install chromium

if [ "$BACKEND_STATE" -eq 0 ]; then
    echo "Reusing healthy FastAPI server on port 8000."
    BACKEND_PID=""
else
    echo "Starting FastAPI server in the background..."
    python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
fi

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
trap 'echo "Shutting down..."; if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi; exit' INT TERM EXIT

npm run dev -- --port 5173
