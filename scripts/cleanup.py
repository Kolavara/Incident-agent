#!/usr/bin/env python3
"""Cleanup script for Incident Response Agent.

Removes generated data, caches, and audit logs.
"""

import os
import shutil
import argparse


def clean_data():
    """Remove generated data files."""
    dirs_to_clean = [
        "data/cache",
        "data/embeddings",
        "data/vectordb",
        "__pycache__",
    ]

    for dirpath in dirs_to_clean:
        if os.path.exists(dirpath):
            shutil.rmtree(dirpath)
            print(f"  Removed: {dirpath}/")

    # Remove audit log
    if os.path.exists("audit_log.json"):
        os.remove("audit_log.json")
        print("  Removed: audit_log.json")

    # Remove logs
    if os.path.exists("logs"):
        shutil.rmtree("logs")
        print("  Removed: logs/")


def clean_pycache():
    """Remove all __pycache__ directories recursively."""
    for root, dirs, _ in os.walk("."):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            shutil.rmtree(pycache_path)
            print(f"  Removed: {pycache_path}/")
            dirs.remove("__pycache__")


def clean_all():
    """Full cleanup."""
    print("Cleaning Incident Response Agent workspace...")
    clean_data()
    clean_pycache()
    print("\nDone. Workspace cleaned.")


def clean_everything():
    """Clean everything including venv."""
    clean_all()
    if os.path.exists("venv"):
        shutil.rmtree("venv")
        print("  Removed: venv/")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Clean Incident Agent workspace")
    parser.add_argument('--all', action='store_true', help='Remove everything, including venv')
    args = parser.parse_args()

    if args.all:
        clean_everything()
    else:
        clean_all()
