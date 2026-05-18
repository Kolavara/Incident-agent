"""Embedding module for converting logs to vector representations."""

import hashlib
import json
import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger('incident_agent.embedder')


class LogEmbedder:
    """Converts error logs to embeddings for similarity search.

    Uses a simple TF-IDF-like approach as a local fallback when
    no embedding API is configured. In production, this would use
    a proper embedding model (e.g., text-embedding-ada-002 or similar).
    """

    def __init__(self, cache_path: str = "data/embeddings"):
        self.cache_path = cache_path
        os.makedirs(cache_path, exist_ok=True)
        self._cache: Dict[str, List[float]] = {}

    def embed(self, text: str) -> List[float]:
        """Generate an embedding vector for the given text.

        Uses a simple hash-based approach for local operation.
        For production, integrate with an embedding API.
        """
        # Check cache first
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cached = self._load_cache(text_hash)
        if cached:
            return cached

        # Simple bag-of-words embedding with hashing trick
        vector = self._compute_hash_embedding(text)

        # Cache the result
        self._save_cache(text_hash, vector)
        return vector

    def _compute_hash_embedding(self, text: str, dimensions: int = 256) -> List[float]:
        """Compute a simple hash-based embedding vector.

        Uses a hashing trick to create a fixed-dimension vector
        from token-level features.
        """
        import math
        tokens = text.lower().split()
        vector = [0.0] * dimensions

        for token in tokens:
            token_hash = hashlib.md5(token.encode()).hexdigest()
            # Use first 8 bytes to determine position and value
            idx = int(token_hash[:4], 16) % dimensions
            val = (int(token_hash[4:8], 16) / 65535.0) * 2.0 - 1.0
            vector[idx] += val

        # Normalize the vector
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))

        if mag_a == 0 or mag_b == 0:
            return 0.0

        return dot_product / (mag_a * mag_b)

    def _load_cache(self, key: str) -> Optional[List[float]]:
        """Load cached embedding if available."""
        cache_file = os.path.join(self.cache_path, f"{key}.json")
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _save_cache(self, key: str, vector: List[float]):
        """Save embedding to cache."""
        try:
            cache_file = os.path.join(self.cache_path, f"{key}.json")
            with open(cache_file, 'w') as f:
                json.dump(vector, f)
        except Exception as e:
            logger.debug(f"Failed to cache embedding: {e}")
