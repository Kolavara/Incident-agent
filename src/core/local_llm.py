"""Ollama local LLM client for fallback when budget cap is hit."""

import os
import time
import logging
import requests
from typing import Dict, Optional

from src.core.base_llm import BaseLLMClient, LLMResponse

logger = logging.getLogger('incident_agent.local_llm')


class LocalLLMClient(BaseLLMClient):
    """Client for local Ollama models as budget fallback."""

    def __init__(self, model_name: str = "llama3",
                 base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = os.getenv('OLLAMA_BASE_URL', base_url)

    def generate(self, system_prompt: str, user_prompt: str,
                 max_tokens: Optional[int] = None,
                 temperature: float = 0.3) -> LLMResponse:
        """Generate a response using Ollama."""
        start_time = time.time()

        try:
            # Check if Ollama is running
            health_url = f"{self.base_url}/api/tags"
            try:
                resp = requests.get(health_url, timeout=5)
                resp.raise_for_status()
            except requests.RequestException:
                raise RuntimeError(
                    "Ollama is not running. Start it with 'ollama serve' and "
                    f"ensure the model '{self.model_name}' is pulled."
                )

            # Generate response
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            payload = {
                "model": self.model_name,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                }
            }
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            latency = time.time() - start_time
            content = data.get('response', '')

            # Rough token estimation for Ollama
            input_tokens = len(full_prompt) // 4
            output_tokens = len(content) // 4

            logger.info(
                f"Ollama call successful: model={self.model_name}, "
                f"latency={latency:.2f}s, cost=$0.0 (local)"
            )

            return LLMResponse(
                content=content,
                model_used=f"ollama/{self.model_name}",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=0.0,
                latency_seconds=latency,
            )

        except requests.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise RuntimeError(
                f"Failed to reach Ollama at {self.base_url}. "
                f"Error: {e}"
            )

    def get_model_name(self) -> str:
        return f"ollama/{self.model_name}"

    def get_cost_info(self) -> Dict[str, float]:
        return {
            'cost_per_1k_input': 0.0,
            'cost_per_1k_output': 0.0,
            'model': f"ollama/{self.model_name}",
        }

    def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get('models', [])
                model_names = [m.get('name', '') for m in models]
                return any(self.model_name in m for m in model_names)
            return False
        except requests.RequestException:
            return False
