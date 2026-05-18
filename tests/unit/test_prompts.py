"""Unit tests for prompt templates and response parser."""

import sys
import os
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.prompts.templates import SYSTEM_PROMPT, build_user_prompt
from src.inference.response_parser import ResponseParser


class TestSystemPrompt(unittest.TestCase):
    """Test the system prompt template."""

    def test_system_prompt_contains_key_elements(self):
        self.assertIn("Site Reliability Engineer", SYSTEM_PROMPT)
        self.assertIn("ROOT CAUSE", SYSTEM_PROMPT)
        self.assertIn("CONFIDENCE", SYSTEM_PROMPT)
        self.assertIn("FIX STEPS", SYSTEM_PROMPT)
        self.assertIn("NOTES", SYSTEM_PROMPT)


class TestBuildUserPrompt(unittest.TestCase):
    """Test user prompt construction."""

    def test_basic_prompt(self):
        result = build_user_prompt(
            cleaned_log="Error: connection timeout",
            memory_context="No past incidents found.",
        )
        self.assertIn("Error: connection timeout", result)
        self.assertIn("No past incidents found.", result)
        self.assertIn("ERROR LOG", result)
        self.assertIn("PAST SIMILAR INCIDENTS", result)

    def test_prompt_with_fields(self):
        result = build_user_prompt(
            cleaned_log="Error occurred",
            memory_context="No past incidents.",
            extracted_fields={
                'service': 'api-gateway',
                'error_type': 'timeout',
                'error_code': 'ERR502',
                'host': 'prod-01',
            },
        )
        self.assertIn("api-gateway", result)
        self.assertIn("timeout", result)
        self.assertIn("ERR502", result)
        self.assertIn("prod-01", result)


class TestResponseParser(unittest.TestCase):
    """Test the response parser."""

    def setUp(self):
        self.parser = ResponseParser()

    def test_parse_valid_response(self):
        response = """ROOT CAUSE: Database connection pool exhausted due to connection leak
CONFIDENCE: High
FIX STEPS:
1. Increase max_connections to 300
2. Restart the database service
3. Add connection pool monitoring
NOTES: This affects write operations only"""
        
        result = self.parser.parse_diagnosis(response)
        self.assertEqual(result['root_cause'], "Database connection pool exhausted due to connection leak")
        self.assertEqual(result['confidence'], "High")
        self.assertEqual(len(result['fix_steps']), 3)
        self.assertIn("Increase max_connections", result['fix_steps'][0])

    def test_parse_empty_response(self):
        result = self.parser.parse_diagnosis("")
        self.assertFalse(result['parse_success'])

    def test_parse_malformed_response(self):
        result = self.parser.parse_diagnosis("This is a random response without the expected format.")
        self.assertEqual(result['root_cause'], '')
        self.assertEqual(result['confidence'], 'Low')

    def test_parse_partial_response(self):
        response = """ROOT CAUSE: Redis connection timeout
CONFIDENCE: Medium
FIX STEPS:
1. Increase timeout
NOTES: No further info"""
        
        result = self.parser.parse_diagnosis(response)
        self.assertEqual(result['root_cause'], "Redis connection timeout")
        self.assertEqual(result['confidence'], "Medium")
        self.assertEqual(len(result['fix_steps']), 1)

    def test_format_for_display(self):
        diagnosis = {
            'root_cause': 'Disk full',
            'confidence': 'High',
            'fix_steps': ['Free up space', 'Add monitoring'],
            'notes': 'Act fast',
        }
        display = self.parser.format_for_display(diagnosis)
        self.assertIn("Disk full", display)
        self.assertIn("Free up space", display)
        self.assertIn("Add monitoring", display)


if __name__ == '__main__':
    unittest.main()
