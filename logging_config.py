"""Logging configuration for the Incident Agent."""

import os
import sys
import logging
import logging.config
from pathlib import Path


def _fix_console_encoding():
    """Fix Windows console encoding to handle Unicode characters.

    On Windows cmd (cp1252), Unicode characters like → (U+2192) cause
    RichHandler to crash with UnicodeEncodeError. This reconfigures
    stdout/stderr to use UTF-8 with backslashreplace error handling.
    """
    if sys.platform != 'win32':
        return
    for stream in [sys.stdout, sys.stderr]:
        if stream and hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='backslashreplace')
            except Exception:
                pass


def setup_logging(config_path: str = "config/logging_config.yaml") -> bool:
    """Set up logging configuration from YAML file or defaults.

    Args:
        config_path: Path to the logging configuration YAML file

    Returns:
        True if configured successfully
    """
    # Fix Windows console encoding to handle Unicode characters
    _fix_console_encoding()

    try:
        import yaml
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            if config:
                # Ensure log directory exists
                log_dir = Path("logs")
                log_dir.mkdir(exist_ok=True)
                logging.config.dictConfig(config)
                return True
    except Exception as e:
        print(f"Warning: Could not load logging config: {e}")

    # Fallback to basic configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    return True
