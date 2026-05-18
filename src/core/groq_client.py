"""Groq API client wrapper with retry and error handling."""

import os
import time
import logging
from typing import Dict, Optional, Tuple

from groq import Groq
from groq import APIStatusError, APIConnectionError, RateLimitError

from src.core.base_llm import BaseLLMClient, LLMResponse

logger = logging.getLogger('incident_agent.groq_client')

# Maximum safe interval to keep under free tier rate limits
MIN_REQUEST_INTERVAL = 12.0  # Conservative delay between requests

_last_request_time: float = 0.0


def _rate_limit_throttle():
    """Throttle requests to stay under Groq free tier rate limits."""
    global _last_request_time
    if _last_request_time > 0:
        elapsed = time.time() - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            delay = MIN_REQUEST_INTERVAL - elapsed
            logger.info(f"Rate limiting: waiting {delay:.1f}s before next request...")
            time.sleep(delay)
    _last_request_time = time.time()


class GroqClient(BaseLLMClient):
    """Client for Groq API with exponential backoff retry logic."""

    MAX_RETRIES = 3
    BASE_DELAY = 2  # seconds

    def __init__(self, model_name: str,
                 cost_per_1k_input: float = 0.00005,
                 cost_per_1k_output: float = 0.00008,
                 api_key: Optional[str] = None,
                 max_tokens: int = 1024):
        self.model_name = model_name
        self.cost_per_1k_input = cost_per_1k_input
        self.cost_per_1k_output = cost_per_1k_output
        self.max_tokens = min(max_tokens, 2048)  # Cap response tokens for free tier

        api_key = api_key or os.getenv('GROQ_API_KEY')
        if not api_key or api_key == 'your_groq_key':
            raise ValueError(
                "GROQ_API_KEY not set. Set it in your .env file or environment variables."
            )

        self.client = Groq(api_key=api_key)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return len(text) // 4

    def _truncate_prompt(self, system_prompt: str, user_prompt: str,
                         max_output_tokens: int) -> Tuple[str, str, int]:
        """Truncate prompts to stay under rate limits.

        Groq free tier allows ~6000 TPM. To be safe, we target ~4000
        total tokens per request (input + output).
        """
        target_total = 4000
        system_tokens = self._estimate_tokens(system_prompt)
        user_tokens = self._estimate_tokens(user_prompt)
        total_estimated = system_tokens + user_tokens + max_output_tokens

        if total_estimated <= target_total:
            return system_prompt, user_prompt, max_output_tokens

        # Need to truncate - start with user_prompt
        overflow = total_estimated - target_total
        max_user_chars = len(user_prompt) - (overflow * 4)
        if max_user_chars < 200:
            max_user_chars = 200  # Keep at least 200 chars of context

        truncated_user = user_prompt[:max_user_chars]
        if truncated_user != user_prompt:
            logger.info(
                f"Truncated user prompt from {len(user_prompt)} chars to {len(truncated_user)} chars "
                f"to stay under token limit (estimated {total_estimated} > {target_total})"
            )

        return system_prompt, truncated_user, min(max_output_tokens, 1024)

    def generate(self, system_prompt: str, user_prompt: str,
                 max_tokens: Optional[int] = None,
                 temperature: float = 0.3) -> LLMResponse:
        """Generate a response with retry logic."""
        max_tokens = min(max_tokens or self.max_tokens, 2048)
        start_time = time.time()
        last_error = None

        # Truncate prompts to stay under rate limits
        system_prompt, user_prompt, max_tokens = self._truncate_prompt(
            system_prompt, user_prompt, max_tokens
        )

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Throttle to stay under rate limits
                _rate_limit_throttle()

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                latency = time.time() - start_time
                content = response.choices[0].message.content or ""
                input_tokens = response.usage.prompt_tokens if response.usage else 0
                output_tokens = response.usage.completion_tokens if response.usage else 0
                cost = self._calculate_cost(input_tokens, output_tokens)

                logger.info(
                    f"Groq API call successful: model={self.model_name}, "
                    f"input_tokens={input_tokens}, output_tokens={output_tokens}, "
                    f"cost=${cost:.6f}, latency={latency:.2f}s"
                )

                return LLMResponse(
                    content=content,
                    model_used=self.model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    latency_seconds=latency,
                )

            except RateLimitError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    delay = self.BASE_DELAY * (4 ** attempt)  # More aggressive backoff
                    logger.warning(
                        f"Rate limit hit (attempt {attempt + 1}/{self.MAX_RETRIES + 1}). "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error("Rate limit exceeded all retry attempts.")
                    raise

            except APIConnectionError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    delay = self.BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{self.MAX_RETRIES + 1}). "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error("Connection failed after all retries.")
                    raise

            except APIStatusError as e:
                logger.error(f"Groq API error: {e.status_code} - {e.message}")
                raise

        # Should not reach here
        raise RuntimeError(f"Groq API call failed after {self.MAX_RETRIES + 1} attempts. "
                          f"Last error: {last_error}")

    def get_model_name(self) -> str:
        return self.model_name

    def get_cost_info(self) -> Dict[str, float]:
        return {
            'cost_per_1k_input': self.cost_per_1k_input,
            'cost_per_1k_output': self.cost_per_1k_output,
            'model': self.model_name,
        }

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate the cost for a given token usage."""
        input_cost = (input_tokens / 1000) * self.cost_per_1k_input
        output_cost = (output_tokens / 1000) * self.cost_per_1k_output
        return round(input_cost + output_cost, 6)
