import logging
import logging.config
import json
from pathlib import Path

def get_logger(name: str, env: str = "dev"):
    config_path = Path(__file__).parent.parent / "configs" / f"logging.{env}.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    logging.config.dictConfig(config)
    return logging.getLogger(name)
