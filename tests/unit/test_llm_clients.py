"""Unit tests for LLM client modules."""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.base_llm import LLMResponse, BaseLLMClient
from src.core.groq_client import GroqClient
from src.core.local_llm import LocalLLMClient


class TestLLMResponse(unittest.TestCase):
    """Test LLMResponse data class."""

    def test_default_values(self):
        response = LLMResponse(content="Test response", model_used="test-model")
        self.assertEqual(response.content, "Test response")
        self.assertEqual(response.model_used, "test-model")
        self.assertEqual(response.input_tokens, 0)
        self.assertEqual(response.output_tokens, 0)
        self.assertEqual(response.cost_usd, 0.0)
        self.assertEqual(response.latency_seconds, 0.0)

    def test_to_dict(self):
        response = LLMResponse(
            content="Test",
            model_used="model-x",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            latency_seconds=1.5,
        )
        d = response.to_dict()
        self.assertEqual(d['content'], "Test")
        self.assertEqual(d['input_tokens'], 100)
        self.assertEqual(d['cost_usd'], 0.01)


class TestGroqClient(unittest.TestCase):
    """Test GroqClient (mocked)."""

    @patch('src.core.groq_client.Groq')
    @patch.dict(os.environ, {'GROQ_API_KEY': 'test-key-123'})
    def test_initialization(self, mock_groq):
        client = GroqClient(
            model_name="test-model",
            cost_per_1k_input=0.00005,
            cost_per_1k_output=0.00008,
        )
        self.assertEqual(client.get_model_name(), "test-model")
        self.assertEqual(client.cost_per_1k_input, 0.00005)

    def test_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                GroqClient(model_name="test-model")


class TestLocalLLMClient(unittest.TestCase):
    """Test LocalLLMClient."""

    def test_initialization(self):
        client = LocalLLMClient(model_name="llama3")
        self.assertIn("llama3", client.get_model_name())
        self.assertEqual(client.get_cost_info()['cost_per_1k_input'], 0.0)

    @patch('src.core.local_llm.requests.get')
    def test_is_available_false(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
        client = LocalLLMClient(model_name="llama3")
        self.assertFalse(client.is_available())


if __name__ == '__main__':
    unittest.main()
