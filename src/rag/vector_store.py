"""Hindsight client wrapper for persistent memory using the real Hindsight API.

Uses the official `hindsight_client` SDK (pip install hindsight-client) to
store and retrieve incident memories. Falls back to a local JSON file store
if Hindsight is not configured or unavailable (e.g. offline/dev mode).
"""

import json
import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger('incident_agent.vector_store')


class LocalMemoryStore:
    """Local JSON-based memory store as fallback when Hindsight is unavailable."""

    def __init__(self, data_path: str = "data/memory_store.json"):
        self.data_path = data_path
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        self._entries: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.data_path):
                with open(self.data_path, 'r') as f:
                    data = json.load(f)
                    self._entries = data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Failed to load local memory store: {e}")
            self._entries = []

    def _save(self):
        try:
            with open(self.data_path, 'w') as f:
                json.dump(self._entries, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save local memory store: {e}")

    def store(self, content: str, metadata: Dict[str, Any]) -> bool:
        entry = {
            'content': content,
            'metadata': metadata,
            'stored_at': datetime.now(timezone.utc).isoformat(),
        }
        self._entries.append(entry)
        self._save()
        return True

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Simple keyword-based search as local fallback."""
        query_lower = query.lower()
        scored = []
        for entry in self._entries:
            content = entry.get('content', '').lower()
            meta_text = ' '.join(str(v).lower() for v in entry.get('metadata', {}).values())
            combined = content + ' ' + meta_text
            # Count query term occurrences as simple similarity
            score = sum(1 for word in query_lower.split() if word in combined)
            normalized = score / max(len(query_lower.split()), 1)
            scored.append({
                **entry,
                'similarity': min(normalized * 2.0, 1.0),  # Scale up a bit
            })

        scored.sort(key=lambda x: x['similarity'], reverse=True)
        return scored[:top_k]

    def get_all(self) -> List[Dict[str, Any]]:
        return self._entries


class VectorStore:
    """Wrapper around the Hindsight memory API for incident memory.

    Uses the official hindsight_client SDK when configured, with automatic
    fallback to a local JSON store for development/offline use.

    Environment variables:
        HINDSIGHT_API_KEY: API key for Hindsight Cloud
        HINDSIGHT_BASE_URL: Base URL for Hindsight (default: production)
        HINDSIGHT_PIPELINE_ID: Bank/pipeline ID for memory scoping
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.api_key = os.getenv('HINDSIGHT_API_KEY', '')
        self.base_url = os.getenv('HINDSIGHT_BASE_URL', 'https://api.hindsight.vectorize.io')
        self.pipeline_id = os.getenv('HINDSIGHT_PIPELINE_ID', 'incident-memory-bank')

        # Initialize store backend
        self._hindsight_client = None
        if storage_path:
            self._local_store = LocalMemoryStore(data_path=storage_path)
        else:
            self._local_store = LocalMemoryStore()

        if self.api_key and self.api_key != 'your_hindsight_key':
            self._init_hindsight()

    def _init_hindsight(self):
        """Initialize the Hindsight API client."""
        try:
            from hindsight_client import Hindsight

            self._hindsight_client = Hindsight(
                base_url=self.base_url,
                api_key=self.api_key,
            )

            # Ensure the bank exists
            try:
                self._hindsight_client.create_bank(
                    bank_id=self.pipeline_id,
                    name="Incident Memory Bank",
                    reflect_mission="You are an incident memory bank storing "
                                   "resolved SRE incidents for future reference.",
                )
            except Exception:
                # Bank probably already exists
                pass

            logger.info(f"Hindsight Memory initialized: bank={self.pipeline_id}")
        except Exception as e:
            logger.warning(f"Hindsight init failed, using local store: {e}")
            self._hindsight_client = None

    def store(self, content: str, metadata: Dict[str, Any]) -> bool:
        """Store an incident in Hindsight memory.

        Args:
            content: The cleaned error log text
            metadata: Dict with root_cause, fix_applied, service, etc.

        Returns:
            True if stored successfully
        """
        entry_data = {
            'content': content,
            'metadata': {
                **metadata,
                'stored_at': datetime.now(timezone.utc).isoformat(),
            }
        }

        # Try Hindsight API first
        if self._hindsight_client:
            try:
                self._hindsight_client.retain(
                    bank_id=self.pipeline_id,
                    content=json.dumps(entry_data),
                    tags=[
                        f"service:{metadata.get('service', 'unknown')}",
                        f"root_cause:{metadata.get('root_cause', 'unknown')[:50]}",
                    ],
                )
                logger.info(f"Stored in Hindsight: {metadata.get('root_cause', 'unknown')}")
                return True
            except Exception as e:
                logger.warning(f"Hindsight retain failed, falling back to local: {e}")

        # Fallback to local store
        return self._local_store.store(content, metadata)

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for similar incidents in Hindsight memory.

        Args:
            query: The search query (cleaned error log text)
            top_k: Number of top matches to return

        Returns:
            List of matching incidents with similarity scores
        """
        # Try Hindsight API first
        if self._hindsight_client:
            try:
                response = self._hindsight_client.recall(
                    bank_id=self.pipeline_id,
                    query=query,
                    max_tokens=4096,
                    budget='mid',
                )

                # Parse Hindsight recall results
                parsed_results = []
                if hasattr(response, 'results') and response.results:
                    for match in response.results[:top_k]:
                        try:
                            incident = json.loads(match.content)
                            incident['similarity'] = getattr(match, 'score', 0.0)
                            parsed_results.append(incident)
                        except (json.JSONDecodeError, AttributeError):
                            continue

                if parsed_results:
                    return parsed_results

            except Exception as e:
                logger.warning(f"Hindsight recall failed, falling back to local: {e}")

        # Fallback to local store search
        return self._local_store.search(query, top_k)

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all stored incidents from memory.

        Returns:
            List of all incident entries with content and metadata
        """
        # Try Hindsight API first
        if self._hindsight_client:
            try:
                response = self._hindsight_client.list_memories(
                    bank_id=self.pipeline_id,
                    limit=100,
                )

                parsed = []
                if hasattr(response, 'items') and response.items:
                    for item in response.items:
                        try:
                            content = getattr(item, 'content', '{}')
                            parsed.append(json.loads(content) if isinstance(content, str) else content)
                        except (json.JSONDecodeError, TypeError):
                            parsed.append({'content': str(content), 'metadata': {}})
                    return parsed
            except Exception as e:
                logger.warning(f"Hindsight list_memories failed, using local: {e}")

        # Fallback to local store
        return self._local_store.get_all()
