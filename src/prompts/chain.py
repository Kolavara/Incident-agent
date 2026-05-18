"""Multi-step reasoning chain for complex incident diagnosis."""

from typing import Dict, List, Optional

from src.core.base_llm import BaseLLMClient, LLMResponse
from src.prompts.templates import SYSTEM_PROMPT, build_user_prompt


class ReasoningChain:
    """Reasoning chain for incident diagnosis.

    For novel/complex incidents, we use a single focused prompt
    with lower max_tokens to stay within free tier rate limits.
    """

    COMPLEX_SYSTEM_PROMPT = """You are an expert Site Reliability Engineer with 10 years of experience at a high-growth fintech company. You specialize in diagnosing novel production incidents.

This is a NOVEL incident (no similar past incidents found). Analyze carefully:
1. First, identify what service/component is failing
2. Determine the likely root cause based on available evidence
3. Identify patterns from the error message and stack trace
4. Propose the most actionable fix steps

Be concise. Focus on the most likely root cause and the fastest remediation.

Respond in this exact format:
ROOT CAUSE: [one sentence]
CONFIDENCE: [High / Medium / Low]
FIX STEPS:
1. [step]
2. [step]
3. [step]
NOTES: [caveats or warnings]"""

    def __init__(self):
        pass

    def run_simple(self, client: BaseLLMClient, cleaned_log: str,
                   memory_context: str, extracted_fields: Optional[Dict] = None) -> LLMResponse:
        """Simple single-step diagnosis for known/partial incidents."""
        user_prompt = build_user_prompt(cleaned_log, memory_context, extracted_fields)
        return client.generate(SYSTEM_PROMPT, user_prompt, max_tokens=512, temperature=0.3)

    def run_complex(self, client: BaseLLMClient, cleaned_log: str,
                    memory_context: str,
                    extracted_fields: Optional[Dict] = None) -> LLMResponse:
        """Single-step diagnosis for novel/complex incidents with focused prompt."""
        # Truncate memory context for novel incidents - we don't need it as much
        if len(memory_context) > 300:
            memory_context = memory_context[:300] + "..."

        user_prompt = build_user_prompt(cleaned_log, memory_context, extracted_fields)
        # Use 1024 tokens for the powerful model — it needs room for
        # chain-of-thought reasoning (<think> blocks) AND the structured output
        return client.generate(
            self.COMPLEX_SYSTEM_PROMPT,
            user_prompt,
            max_tokens=1024,
            temperature=0.4,
        )
