"""API integration tests for external services.

These tests require API keys and are skipped by default.
Run with: pytest tests/integration/test_api_integration.py -x -v --run-api
"""

import sys
import os
import json
import tempfile
import unittest
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.processing.preprocessor import LogPreprocessor
from src.core.model_factory import ModelRouter
from src.inference.response_parser import ResponseParser


# Mark all tests as api
pytestmark = pytest.mark.api


def requires_api_keys():
    """Check if required API keys are available."""
    groq_key = os.getenv('GROQ_API_KEY', '')
    return bool(groq_key) and groq_key != 'your_groq_key'


class TestGroqAPIIntegration(unittest.TestCase):
    """Integration tests requiring Groq API access."""

    @pytest.mark.skipif(not requires_api_keys(), reason="GROQ_API_KEY not set")
    def test_groq_connection(self):
        """Test basic Groq API connectivity."""
        try:
            router = ModelRouter()
            client, tier, _ = router.route(0.9)  # High similarity → cheap model
            response = client.generate(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say 'Hello from Incident Agent!'",
                max_tokens=50,
                temperature=0.0,
            )
            self.assertTrue(len(response.content) > 0)
            self.assertGreater(response.input_tokens, 0)
            print(f"\nGroq API test: model={response.model_used}, tier={tier}, "
                  f"cost=${response.cost_usd:.6f}, latency={response.latency_seconds:.2f}s")
        except Exception as e:
            self.fail(f"Groq API connection failed: {e}")

    @pytest.mark.skipif(not requires_api_keys(), reason="GROQ_API_KEY not set")
    def test_diagnosis_via_groq(self):
        """Test a full diagnosis cycle via Groq API."""
        try:
            import time
            from src.rag.vector_store import VectorStore
            from src.rag.retriever import IncidentRetriever
            from src.rag.indexer import IncidentIndexer
            from src.inference.inference_engine import InferenceEngine
            from audit_log import AuditLogger

            # Setup
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
                store_path = f.name

            store = VectorStore(storage_path=store_path)
            router = ModelRouter()
            retriever = IncidentRetriever(store)
            indexer = IncidentIndexer(store)
            audit_logger = AuditLogger(log_path=store_path.replace('.json', '_audit.json'))
            engine = InferenceEngine(router, retriever, indexer, audit_logger)

            # Test diagnosis
            raw_log = (
                "2025-07-08T13:47:33.456Z ERROR [payment-processor-v2] "
                "Redis connection pool exhausted: pool_size=10, active=10, "
                "waiting=12, timeout=2000ms"
            )
            result = engine.diagnose(raw_log)

            self.assertIn('diagnosis', result)
            self.assertIn('root_cause', result['diagnosis'])
            self.assertIn('cost_usd', result)
            print(f"\nDiagnosis result: {result['diagnosis']['root_cause']}")
            print(f"Cost: ${result['cost_usd']:.6f}")

            # Clean up
            os.unlink(store_path)
            audit_path = store_path.replace('.json', '_audit.json')
            if os.path.exists(audit_path):
                os.unlink(audit_path)

        except Exception as e:
            self.fail(f"Diagnosis test failed: {e}")


if __name__ == '__main__':
    import tempfile
    unittest.main()
