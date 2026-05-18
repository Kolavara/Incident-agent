"""Model factory with intelligent routing using native cascadeflow CascadeAgent.

Uses cascadeflow's CascadeAgent for LLM calls with automatic model routing,
budget enforcement, and audit trail. Falls back to local Ollama when budget
is exhausted or API keys are missing.
"""

import os
import logging
from typing import Dict, Any, Tuple, Optional

from dotenv import load_dotenv

import cascadeflow
from cascadeflow import (
    CascadeAgent,
    ModelConfig,
    cascadeflowError,
)

from src.core.base_llm import BaseLLMClient, LLMResponse
from src.core.groq_client import GroqClient
from src.core.local_llm import LocalLLMClient

logger = logging.getLogger('incident_agent.model_factory')
load_dotenv()


class CascadeAgentWrapper(BaseLLMClient):
    """Wraps cascadeflow's CascadeAgent behind the BaseLLMClient interface.

    Allows the existing inference pipeline to use cascadeflow's intelligent
    routing, budget tracking, and model cascade system without refactoring
    the entire codebase.
    """

    def __init__(self, agent: CascadeAgent, model_name: str, tier: str,
                 cost_per_1k_input: float = 0.0,
                 cost_per_1k_output: float = 0.0):
        self._agent = agent
        self._model_name = model_name
        self._tier = tier
        self._cost_per_1k_input = cost_per_1k_input
        self._cost_per_1k_output = cost_per_1k_output

    def generate(self, system_prompt: str, user_prompt: str,
                 max_tokens: Optional[int] = None,
                 temperature: float = 0.3) -> LLMResponse:
        """Generate response using cascadeflow's CascadeAgent.

        cascadeflow handles model selection, quality verification, and
        cost tracking internally.
        """
        import time
        start = time.time()

        # Build message list for cascadeflow
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = self._agent.run(
                query=user_prompt,
                messages=messages,
                max_tokens=max_tokens or 1024,
                temperature=temperature,
            )

            latency_ms = time.time() - start

            # Extract model info from cascadeflow result
            actual_model = result.model_used or self._model_name
            content = result.content or ""
            cost = result.total_cost if hasattr(result, 'total_cost') else 0.0

            # Estimate tokens if not provided
            input_tokens = len(user_prompt + system_prompt) // 4
            output_tokens = len(content) // 4

            logger.info(
                f"CascadeAgent: model={actual_model}, tier={self._tier}, "
                f"cost=${cost:.6f}, latency={latency_ms:.2f}s, "
                f"cascaded={getattr(result, 'cascaded', False)}"
            )

            return LLMResponse(
                content=content,
                model_used=actual_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_seconds=latency_ms,
            )

        except cascadeflowError as e:
            logger.warning(f"cascadeflow routing error: {e}")
            # Fall back to direct Groq call if cascadeflow fails
            return self._fallback_generate(system_prompt, user_prompt,
                                           max_tokens, temperature)
        except Exception as e:
            logger.error(f"CascadeAgent error: {e}")
            return self._fallback_generate(system_prompt, user_prompt,
                                           max_tokens, temperature)

    def _fallback_generate(self, system_prompt: str, user_prompt: str,
                           max_tokens: Optional[int] = None,
                           temperature: float = 0.3) -> LLMResponse:
        """Fallback direct generation if cascadeflow is unavailable."""
        try:
            client = GroqClient(
                model_name=self._model_name,
                max_tokens=max_tokens or 1024,
            )
            return client.generate(system_prompt, user_prompt,
                                   max_tokens, temperature)
        except Exception:
            import time
            return LLMResponse(
                content="Cascadeflow unavailable and Groq fallback failed.",
                model_used="fallback",
                cost_usd=0.0,
                latency_seconds=0.0,
            )

    def get_model_name(self) -> str:
        return self._model_name

    def get_cost_info(self) -> Dict[str, float]:
        return {
            'cost_per_1k_input': self._cost_per_1k_input,
            'cost_per_1k_output': self._cost_per_1k_output,
            'model': self._model_name,
            'tier': self._tier,
        }


class ModelRouter:
    """Routes incidents and enforces budgets using cascadeflow's harness.

    Uses cascadeflow's CascadeAgent with two model tiers:
    - Cheap model for known/partial incidents (high similarity score)
    - Powerful model for novel incidents (low similarity score)

    cascadeflow handles the intelligent routing between these tiers,
    budget enforcement, and provides a full audit trail.
    """

    def __init__(self):
        # Budget configuration
        self.budget_cap = float(os.getenv('BUDGET_CAP_USD', '1.00'))
        self._cumulative_cost = 0.0

        # Model names from env
        self.cheap_model_name = os.getenv('CHEAP_MODEL', 'groq/llama-3.1-8b-instant')
        self.powerful_model_name = os.getenv('POWERFUL_MODEL', 'groq/qwen/qwen3-32b')
        self.local_fallback_name = os.getenv('LOCAL_MODEL', 'ollama/llama3')

        # Routing thresholds (matches config/model_config.yaml)
        self.similarity_threshold_high = 0.8
        self.similarity_threshold_mid = 0.5

        # Initialize cascadeflow global harness for budget tracking
        try:
            cascadeflow.init(
                mode='enforce',
                budget=self.budget_cap,
            )
            logger.info(f"cascadeflow harness initialized. Budget cap: ${self.budget_cap}")
        except Exception as e:
            logger.warning(f"cascadeflow init skipped (will use direct Groq): {e}")

        # Initialize CascadeAgent with both model tiers
        # cascadeflow will automatically route between them based on
        # complexity detection and quality verification
        self._cascade_agent = self._build_cascade_agent()

        # Create standalone clients for non-cascadeflow routes
        self._cheap_client: Optional[BaseLLMClient] = None
        self._powerful_client: Optional[BaseLLMClient] = None
        self._local_client: Optional[LocalLLMClient] = None

    def _build_cascade_agent(self) -> Optional[CascadeAgent]:
        """Build a CascadeAgent with cheap + powerful models.

        cascadeflow will intelligently route between them:
        - Tries cheap model first (fast, low cost)
        - If quality check fails, cascades to powerful model
        - Tracks all costs and routing decisions
        """
        try:
            agent = CascadeAgent(
                models=[
                    ModelConfig(
                        name='cheap',
                        provider='groq',
                        model=self.cheap_model_name,
                        max_tokens=1024,
                        temperature=0.3,
                        cost=0.00005,
                        quality_score=0.7,
                    ),
                    ModelConfig(
                        name='powerful',
                        provider='groq',
                        model=self.powerful_model_name,
                        max_tokens=2048,
                        temperature=0.3,
                        cost=0.00029,
                        quality_score=0.9,
                    ),
                ],
                enable_cascade=True,
                verbose=False,
            )
            logger.info(f"CascadeAgent ready: cheap={self.cheap_model_name}, "
                        f"powerful={self.powerful_model_name}")
            return agent
        except Exception as e:
            logger.warning(f"Could not create CascadeAgent: {e}")
            return None

    def route(self, similarity_score: float) -> Tuple[BaseLLMClient, str, str]:
        """Route to the appropriate model based on similarity score.

        Args:
            similarity_score: Score from memory retrieval (0.0 to 1.0)

        Returns:
            Tuple of (client, model_tier, routing_reason)
        """
        is_budget_exhausted = self.is_budget_exhausted()
        cascade_available = self._cascade_agent is not None

        # If budget is exhausted, use local Ollama
        if is_budget_exhausted:
            return self._get_local_client(), 'local', \
                   "Budget cap reached — using local Ollama (free)"

        # High similarity -> use cheap model
        if similarity_score >= self.similarity_threshold_high:
            reason = f"Known incident (score={similarity_score:.2f}) — using cheap model"
            if cascade_available:
                return self._get_cascade_client('cheap'), 'cheap', reason
            return self._get_cheap_client(), 'cheap', reason

        # Mid similarity -> use cheap model
        if similarity_score >= self.similarity_threshold_mid:
            reason = f"Partial match (score={similarity_score:.2f}) — using cheap model"
            if cascade_available:
                return self._get_cascade_client('cheap'), 'cheap', reason
            return self._get_cheap_client(), 'cheap', reason

        # Low or no similarity -> use powerful model via cascade
        reason = f"Novel incident (score={similarity_score:.2f}) — using powerful model"
        if cascade_available:
            return self._get_cascade_client('powerful'), 'powerful', reason
        return self._get_powerful_client(), 'powerful', reason

    def _get_cascade_client(self, tier: str) -> BaseLLMClient:
        """Get a CascadeAgent-based client for the given tier."""
        if tier == 'cheap':
            return CascadeAgentWrapper(
                agent=self._cascade_agent,
                model_name=self.cheap_model_name,
                tier='cheap',
                cost_per_1k_input=0.00005,
                cost_per_1k_output=0.00008,
            )
        return CascadeAgentWrapper(
            agent=self._cascade_agent,
            model_name=self.powerful_model_name,
            tier='powerful',
            cost_per_1k_input=0.00029,
            cost_per_1k_output=0.00029,
        )

    def _get_cheap_client(self) -> BaseLLMClient:
        """Get a direct Groq client for cheap model."""
        if not self._cheap_client:
            self._cheap_client = GroqClient(
                model_name=self.cheap_model_name,
                cost_per_1k_input=0.00005,
                cost_per_1k_output=0.00008,
                max_tokens=1024,
            )
        return self._cheap_client

    def _get_powerful_client(self) -> BaseLLMClient:
        """Get a direct Groq client for powerful model."""
        if not self._powerful_client:
            self._powerful_client = GroqClient(
                model_name=self.powerful_model_name,
                cost_per_1k_input=0.00029,
                cost_per_1k_output=0.00029,
                max_tokens=2048,
            )
        return self._powerful_client

    def _get_local_client(self) -> BaseLLMClient:
        """Get a local Ollama client for fallback."""
        if not self._local_client:
            self._local_client = LocalLLMClient(
                model_name=self.local_fallback_name.split('/')[-1],
            )
        return self._local_client

    def update_cost(self, cost_usd: float):
        """Track cumulative cost across all diagnoses."""
        self._cumulative_cost += cost_usd
        logger.info(f"Cumulative cost: ${self._cumulative_cost:.6f} / ${self.budget_cap:.2f}")

    def get_cumulative_cost(self) -> float:
        """Get the total cumulative cost."""
        return self._cumulative_cost

    def get_budget_cap(self) -> float:
        """Get the budget cap."""
        return self.budget_cap

    def is_budget_exhausted(self) -> bool:
        """Check if the budget cap has been reached."""
        return self._cumulative_cost >= self.budget_cap


