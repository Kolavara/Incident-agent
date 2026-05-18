#!/bin/bash
# Environment setup script for Incident Response Agent
# Usage: bash scripts/setup_env.sh

set -e

echo "================================================"
echo "  Incident Response Agent - Setup"
echo "================================================"
echo ""

# Check Python version
echo "[1/5] Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+\.\d+' | head -1)
if [ -z "$PYTHON_VERSION" ]; then
    echo "  [ERROR] Python 3 not found. Please install Python 3.11+"
    exit 1
fi
echo "  Found Python $PYTHON_VERSION"

# Create virtual environment
echo "[2/5] Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  Virtual environment created"
else
    echo "  Virtual environment already exists"
fi

# Activate and install dependencies
echo "[3/5] Installing dependencies..."
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "  Dependencies installed"

# Create .env if it doesn't exist
echo "[4/5] Setting up environment variables..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  Created .env file from .env.example"
    echo "  [!!] Please edit .env and add your API keys:"
    echo "       - GROQ_API_KEY (required for LLM calls)"
    echo "       - HINDSIGHT_API_KEY (optional, for memory)"
    echo "       - HINDSIGHT_PIPELINE_ID (optional, for memory)"
else
    echo "  .env file already exists"
fi

# Validate environment variables
echo "[5/5] Validating environment variables..."
source .env 2>/dev/null || true

HAS_GROQ=true
HAS_HINDSIGHT=true

if [ -z "$GROQ_API_KEY" ] || [ "$GROQ_API_KEY" = "your_groq_key" ]; then
    echo "  [WARNING] GROQ_API_KEY is not set. LLM calls will fail."
    echo "            Get a free key at: https://console.groq.com/keys"
    HAS_GROQ=false
else
    echo "  [OK] GROQ_API_KEY is set"
fi

if [ -z "$HINDSIGHT_API_KEY" ] || [ "$HINDSIGHT_API_KEY" = "your_hindsight_key" ]; then
    echo "  [INFO] HINDSIGHT_API_KEY not set. Using local file memory (no Hindsight)."
    HAS_HINDSIGHT=false
else
    echo "  [OK] HINDSIGHT_API_KEY is set"
fi

echo ""
echo "================================================"
echo "  Setup Complete!"
echo "================================================"
if [ "$HAS_GROQ" = false ]; then
    echo ""
    echo "  To run with LLM support:"
    echo "    1. Get a Groq API key: https://console.groq.com/keys"
    echo "    2. Edit .env and set GROQ_API_KEY"
    echo "    3. Run: python main.py demo"
    echo ""
fi
echo "  Quick start (offline demo):"
echo "    python main.py demo-offline"
echo ""
echo "  Quick start (live demo - requires API key):"
echo "    python main.py demo"
echo ""

# Deactivate virtual environment
deactivate 2>/dev/null || true
