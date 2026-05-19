#!/usr/bin/env bash
# Incident Agent Web App — Start both backend and frontend
# Usage: bash start.sh

set -e

echo "========================================"
echo "  🛡️  Incident Response Agent Web App"
echo "========================================"
echo ""

# Check Python
if ! command -v python &> /dev/null; then
    echo "❌ Python not found. Please install Python 3.11+"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 18+"
    exit 1
fi

# Install backend deps if needed
echo "📦 Installing backend dependencies..."
pip install -r requirements.txt -q 2>/dev/null
pip install fastapi uvicorn sse-starlette -q 2>/dev/null

# Install frontend deps if needed
echo "📦 Installing frontend dependencies..."
cd frontend
npm install --silent 2>/dev/null
cd ..

# Start backend in background
echo "🚀 Starting backend on http://localhost:8000..."
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Wait for backend to be ready
sleep 2

# Start frontend
echo "🚀 Starting frontend on http://localhost:5173..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Web App is running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo "   API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Trap Ctrl+C and kill both processes
trap "echo ''; echo '🛑 Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# Wait for either to exit
wait
