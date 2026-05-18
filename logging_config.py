"""Logging configuration for the Incident Agent."""

import os
import logging
import logging.config
from pathlib import Path


def setup_logging(config_path: str = "config/logging_config.yaml") -> bool:
    """Set up logging configuration from YAML file or defaults.

    Args:
        config_path: Path to the logging configuration YAML file

    Returns:
        True if configured successfully
    """
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
