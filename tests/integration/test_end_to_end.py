"""End-to-end integration tests for the Incident Agent."""

import sys
import os
import json
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.processing.preprocessor import LogPreprocessor
from src.rag.vector_store import VectorStore
from src.rag.retriever import IncidentRetriever
from src.rag.indexer import IncidentIndexer
from src.inference.response_parser import ResponseParser
from audit_log import AuditLogger


class TestPreprocessorIntegration(unittest.TestCase):
    """Integration tests for the preprocessor."""

    def setUp(self):
        self.preprocessor = LogPreprocessor()

    def test_full_preprocessing_pipeline(self):
        raw_log = (
            "2025-06-15T14:23:11.456Z ERROR [payment-processor-v2] "
            "Redis connection pool exhausted: pool_size=10, active=10, "
            "waiting=12, timeout=2000ms"
        )
        result = self.preprocessor.preprocess(raw_log)
        self.assertIn('cleaned_log', result)
        self.assertIn('service', result)
        self.assertIn('error_type', result)
        # Check cleaned log doesn't have the timestamp
        self.assertNotIn('2025-06-15', result['cleaned_log'])

    def test_validation_edge_cases(self):
        self.assertFalse(self.preprocessor.validate_input(""))
        self.assertFalse(self.preprocessor.validate_input("short"))
        self.assertTrue(self.preprocessor.validate_input("A" * 50))


class TestVectorStoreIntegration(unittest.TestCase):
    """Integration tests for the vector store."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.temp_dir, "test_store.json")
        self.store = VectorStore(storage_path=self.store_path)

    def tearDown(self):
        if os.path.exists(self.store_path):
            os.remove(self.store_path)
        os.rmdir(self.temp_dir)

    def test_store_and_search_local(self):
        # Store some incidents
        self.store.store(
            content="Redis connection pool exhausted",
            metadata={'root_cause': 'Pool exhausted', 'service': 'payment'},
        )
        self.store.store(
            content="Database max connections reached",
            metadata={'root_cause': 'DB full', 'service': 'postgres'},
        )

        # Search for similar
        results = self.store.search("Redis pool connection exhausted", top_k=3)
        self.assertGreater(len(results), 0)
        # The first result should be about Redis
        top_result = results[0]
        self.assertIn('content', top_result)
        self.assertIn('similarity', top_result)

    def test_empty_store_search(self):
        results = self.store.search("anything")
        self.assertEqual(len(results), 0)


class TestRetrieverIndexerIntegration(unittest.TestCase):
    """Integration tests for retriever + indexer."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = os.path.join(self.temp_dir, "test_store.json")
        self.store = VectorStore(storage_path=self.store_path)
        self.retriever = IncidentRetriever(self.store)
        self.indexer = IncidentIndexer(self.store)

    def tearDown(self):
        if os.path.exists(self.store_path):
            os.remove(self.store_path)
        os.rmdir(self.temp_dir)

    def test_full_cycle(self):
        # Store a resolved incident
        self.indexer.store_resolved(
            cleaned_log="Redis pool exhausted error",
            diagnosis={
                'root_cause': 'Connection pool exhausted',
                'confidence': 'High',
                'fix_steps': ['Increase pool size'],
                'notes': 'Standard fix',
            },
            fix_applied="Increased pool size to 25",
            service="payment",
            resolution_time_minutes=10,
        )

        # Retrieve similar
        result = self.retriever.retrieve("Redis connection pool exhausted")
        self.assertGreaterEqual(len(result['matches']), 0)
        self.assertIn('incident_type', result)
        self.assertIn('memory_context', result)

    def test_novel_incident_detection(self):
        result = self.retriever.retrieve("Something completely different and new")
        self.assertEqual(result['incident_type'], 'NOVEL')


class TestResponseParserIntegration(unittest.TestCase):
    """Integration tests for response parser."""

    def test_parse_realistic_diagnosis(self):
        parser = ResponseParser()
        response = """ROOT CAUSE: Redis connection pool exhausted due to payment spike
CONFIDENCE: High
FIX STEPS:
1. kubectl rollout restart deploy/payment-processor-v2
2. Set CONNECTION_POOL_SIZE=25 in ConfigMap
3. Monitor redis-03 connections for 5 minutes
NOTES: This exact issue occurred on INC-003. Consider implementing connection pooling retry with exponential backoff."""
        
        result = parser.parse_diagnosis(response)
        self.assertEqual(result['root_cause'], "Redis connection pool exhausted due to payment spike")
        self.assertEqual(result['confidence'], "High")
        self.assertEqual(len(result['fix_steps']), 3)


class TestAuditLoggerIntegration(unittest.TestCase):
    """Integration tests for audit logger."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.temp_dir, "test_audit.json")
        self.logger = AuditLogger(log_path=self.log_path)

    def tearDown(self):
        if os.path.exists(self.log_path):
            os.remove(self.log_path)
        os.rmdir(self.temp_dir)

    def test_log_and_stats(self):
        self.logger.log({
            'incident_id': 'test-001',
            'timestamp': '2025-01-01T00:00:00',
            'similarity_score': 0.95,
            'incident_type': 'KNOWN',
            'model_used': 'llama3-8b',
            'cost_usd': 0.001,
            'cumulative_cost_usd': 0.001,
            'latency_seconds': 0.5,
            'resolved': False,
        })

        self.logger.log({
            'incident_id': 'test-002',
            'timestamp': '2025-01-01T00:01:00',
            'similarity_score': 0.3,
            'incident_type': 'NOVEL',
            'model_used': 'qwen-32b',
            'cost_usd': 0.031,
            'cumulative_cost_usd': 0.032,
            'latency_seconds': 2.5,
            'resolved': True,
        })

        entries = self.logger.get_all()
        self.assertEqual(len(entries), 2)

        stats = self.logger.get_stats()
        self.assertEqual(stats['total_incidents'], 2)
        self.assertAlmostEqual(stats['total_cost'], 0.032, places=4)
        self.assertEqual(stats['resolved_count'], 1)

    def test_mark_resolved(self):
        self.logger.log({
            'incident_id': 'test-003',
            'resolved': False,
        })
        self.logger.mark_resolved('test-003')
        entries = self.logger.get_all()
        self.assertTrue(entries[0]['resolved'])


if __name__ == '__main__':
    unittest.main()
