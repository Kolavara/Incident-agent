"""Retrieval module for finding similar past incidents."""

import logging
from typing import Dict, List, Optional, Tuple

from src.rag.vector_store import VectorStore

logger = logging.getLogger('incident_agent.retriever')


class IncidentRetriever:
    """Retrieves similar past incidents from memory for context."""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def retrieve(self, cleaned_log: str, top_k: int = 3) -> Dict[str, any]:
        """Search for similar incidents in memory.

        Args:
            cleaned_log: The preprocessed error log text
            top_k: Number of top matches to return

        Returns:
            Dict with:
                - matches: list of similar incidents with similarity scores
                - top_score: highest similarity score (0.0 if no matches)
                - incident_type: "KNOWN", "PARTIAL", or "NOVEL"
                - memory_context: formatted string of past incidents for prompts
        """
        try:
            results = self.vector_store.search(query=cleaned_log, top_k=top_k)
        except Exception as e:
            logger.warning(f"Memory search failed: {e}. Proceeding without context.")
            return {
                'matches': [],
                'top_score': 0.0,
                'incident_type': 'NOVEL',
                'memory_context': 'No past incidents found.',
            }

        if not results:
            return {
                'matches': [],
                'top_score': 0.0,
                'incident_type': 'NOVEL',
                'memory_context': 'No past incidents found.',
            }

        top_score = max(r.get('similarity', 0.0) for r in results)

        # Classify the incident type
        if top_score >= 0.8:
            incident_type = 'KNOWN'
        elif top_score >= 0.5:
            incident_type = 'PARTIAL'
        else:
            incident_type = 'NOVEL'

        # Build memory context string
        memory_lines = []
        for i, match in enumerate(results, 1):
            sim = match.get('similarity', 0.0)
            meta = match.get('metadata', {})
            content = match.get('content', '')[:150]
            root_cause = meta.get('root_cause', 'unknown')[:60]
            fix = meta.get('fix_applied', 'unknown')[:80]

            memory_lines.append(
                f"--- Past Incident {i} (similarity: {sim:.2%}) ---\n"
                f"Root Cause: {root_cause}\n"
                f"Fix: {fix}\n"
            )

        memory_context = '\n'.join(memory_lines) if memory_lines else 'No past incidents found.'

        return {
            'matches': results,
            'top_score': top_score,
            'incident_type': incident_type,
            'memory_context': memory_context,
        }
