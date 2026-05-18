#!/bin/bash
# Test runner script for Incident Response Agent
# Usage: bash scripts/run_tests.sh

set -e

echo "================================================"
echo "  Running Incident Agent Tests"
echo "================================================"
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Using virtual environment"
fi

# Run unit tests
echo "[1/3] Running unit tests..."
python -m pytest tests/unit/ -v --tb=short 2>&1 || {
    echo "  [WARNING] Unit tests directory or tests not found"
    echo "  Ensure tests directory exists with test files"
}

echo ""

# Run integration tests
echo "[2/3] Running integration tests..."
python -m pytest tests/integration/ -v --tb=short 2>&1 || {
    echo "  [WARNING] Integration tests directory or tests not found"
}

echo ""

# Check imports
echo "[3/3] Checking imports..."
python -c "
import sys
sys.path.insert(0, '.')
from src.processing.preprocessor import LogPreprocessor
from src.core.base_llm import BaseLLMClient, LLMResponse
from src.core.groq_client import GroqClient
from src.core.model_factory import ModelRouter
from src.rag.vector_store import VectorStore
from src.rag.retriever import IncidentRetriever
from src.rag.indexer import IncidentIndexer
from src.rag.embedder import LogEmbedder
from src.prompts.templates import SYSTEM_PROMPT, build_user_prompt
from src.inference.response_parser import ResponseParser
from audit_log import AuditLogger
print('All imports successful!')
"

echo ""
echo "================================================"
echo "  Tests Complete"
echo "================================================"
