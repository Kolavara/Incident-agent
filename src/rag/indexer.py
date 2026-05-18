"""Indexer module for storing resolved incidents into memory."""

import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone

from src.rag.vector_store import VectorStore

logger = logging.getLogger('incident_agent.indexer')


class IncidentIndexer:
    """Stores resolved incidents into Hindsight/local memory for future reference."""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def store_resolved(self, cleaned_log: str, diagnosis: Dict[str, Any],
                       fix_applied: str, service: Optional[str] = None,
                       resolution_time_minutes: int = 0,
                       model_used: str = 'unknown',
                       cost_usd: float = 0.0) -> bool:
        """Store a resolved incident in memory.

        Args:
            cleaned_log: The cleaned error log text
            diagnosis: The diagnosis dict (root_cause, confidence, fix_steps, notes)
            fix_applied: Description of the fix that was applied
            service: The service name
            resolution_time_minutes: Time taken to resolve
            model_used: The model used for diagnosis
            cost_usd: The cost of the diagnosis

        Returns:
            True if stored successfully
        """
        metadata = {
            'root_cause': diagnosis.get('root_cause', 'unknown'),
            'fix_applied': fix_applied,
            'service': service or diagnosis.get('service', 'unknown'),
            'resolved': True,
            'resolution_time_minutes': resolution_time_minutes,
            'model_used': model_used,
            'cost_usd': cost_usd,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        success = self.vector_store.store(
            content=cleaned_log,
            metadata=metadata,
        )

        if success:
            logger.info(
                f"Stored resolved incident: {diagnosis.get('root_cause', 'unknown')} "
                f"| service={metadata['service']} | time={resolution_time_minutes}min "
                f"| cost=${cost_usd:.6f}"
            )
        else:
            logger.error("Failed to store resolved incident.")

        return success
