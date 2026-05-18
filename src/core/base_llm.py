"""Abstract base class for LLM client implementations."""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple


class LLMResponse:
    """Standardized response from any LLM client."""

    def __init__(self, content: str, model_used: str, input_tokens: int = 0,
                 output_tokens: int = 0, cost_usd: float = 0.0,
                 latency_seconds: float = 0.0):
        self.content = content
        self.model_used = model_used
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd
        self.latency_seconds = latency_seconds

    def to_dict(self) -> Dict:
        return {
            'content': self.content,
            'model_used': self.model_used,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cost_usd': self.cost_usd,
            'latency_seconds': self.latency_seconds,
        }


class BaseLLMClient(ABC):
    """Abstract base class for LLM API clients."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str,
                 max_tokens: Optional[int] = None,
                 temperature: float = 0.3) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            system_prompt: The system-level prompt
            user_prompt: The user's prompt/message
            max_tokens: Maximum tokens in the response
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            LLMResponse with the generated content and metadata
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the name of the model this client uses."""
        pass

    @abstractmethod
    def get_cost_info(self) -> Dict[str, float]:
        """Return cost information for this model."""
        pass
