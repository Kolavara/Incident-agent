#!/usr/bin/env python3
"""Build embeddings for demo incidents to pre-index them."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.embedder import LogEmbedder


def main():
    """Pre-index demo incidents by computing and caching embeddings."""
    demo_path = "data/demo_incidents.json"
    if not os.path.exists(demo_path):
        print(f"[ERROR] Demo data not found at {demo_path}")
        return

    with open(demo_path, 'r') as f:
        incidents = json.load(f)

    embedder = LogEmbedder()

    print(f"Building embeddings for {len(incidents)} incidents...")
    for i, incident in enumerate(incidents, 1):
        raw_log = incident.get('raw_log', '')
        if raw_log:
            vector = embedder.embed(raw_log)
            print(f"  [{i}/{len(incidents)}] {incident.get('id', 'unknown')}: {len(vector)} dimensions")

    print(f"\nDone! Embeddings cached at data/embeddings/")
    print(f"Total: {len(incidents)} incidents indexed")


if __name__ == '__main__':
    main()
