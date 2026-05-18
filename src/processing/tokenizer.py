"""Token counting utilities for budget management."""

import re
from typing import List


class Tokenizer:
    """Rough token counter for estimating LLM costs.

    Uses a simple approximation: ~4 characters per token for English text.
    For production, use a proper tokenizer like tiktoken.
    """

    CHARS_PER_TOKEN = 4.0

    def count_tokens(self, text: str) -> int:
        """Count approximate tokens in text."""
        if not text:
            return 0
        return max(1, round(len(text) / self.CHARS_PER_TOKEN))

    def count_tokens_batch(self, texts: List[str]) -> int:
        """Count approximate tokens across multiple texts."""
        return sum(self.count_tokens(t) for t in texts)

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within max_tokens."""
        max_chars = max_tokens * int(self.CHARS_PER_TOKEN)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n\n[TRUNCATED]"

    def estimate_cost(self, input_tokens: int, output_tokens: int,
                      cost_per_1k_input: float, cost_per_1k_output: float) -> float:
        """Estimate cost for a given token usage."""
        input_cost = (input_tokens / 1000) * cost_per_1k_input
        output_cost = (output_tokens / 1000) * cost_per_1k_output
        return round(input_cost + output_cost, 6)
