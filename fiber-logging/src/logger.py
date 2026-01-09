import logging
import logging.config
import json
from pathlib import Path
from typing import Optional

# =============================================================================
# FiberStack Logging Contract (Day 56)
# =============================================================================
# USAGE RULES:
#   - ENTRYPOINTS (main.py, worker.py, scripts) call get_logger(service, env)
#   - MODULES use logging.getLogger("service.module") — inherits from parent
#
# Required fields in every log:
#   - asctime: ISO timestamp
#   - name: service name (fiber-api, fiber-etl, fiber-probe)
#   - levelname: DEBUG/INFO/WARNING/ERROR
#   - message: log content
#
# WARNING: Do NOT call logging.basicConfig() in service code.
# It will override this configuration.
#
# File logging is BEST-EFFORT only:
#   - No rotation, no permission checks, no truncation
#   - For production, use Docker log drivers or ELK/Loki
# =============================================================================

VALID_SERVICES = {"fiber-api", "fiber-etl", "fiber-probe", "fiber-dashboard"}

# Track if config has been applied (idempotency guard)
_config_applied = False


def get_logger(
    name: str, 
    env: str = "dev",
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Get a configured logger for a FiberStack service.
    
    ONLY call this from entrypoints (main.py, worker.py, scripts).
    Modules should use logging.getLogger("service.module") instead.
    
    Args:
        name: Service name (must be one of VALID_SERVICES)
        env: Environment (dev, sandbox, staging, prod)
        log_file: Optional file path for additional file output (best-effort)
    
    Returns:
        Configured logger instance
    
    Raises:
        ValueError: If name is not a valid service name
    """
    global _config_applied
    
    if name not in VALID_SERVICES:
        raise ValueError(
            f"Invalid service name: '{name}'. "
            f"Must be one of: {', '.join(sorted(VALID_SERVICES))}"
        )
    
    # Apply dictConfig only once to avoid duplicate handlers
    if not _config_applied:
        config_path = Path(__file__).parent.parent / "configs" / f"logging.{env}.json"
        
        # Fallback to dev config if env config doesn't exist
        if not config_path.exists():
            config_path = Path(__file__).parent.parent / "configs" / "logging.dev.json"
        
        with open(config_path, "r") as f:
            config = json.load(f)
        
        logging.config.dictConfig(config)
        _config_applied = True
    
    logger = logging.getLogger(name)
    
    # Add optional file handler (best-effort, no rotation)
    if log_file:
        # Check if file handler already exists to avoid duplicates
        has_file_handler = any(
            isinstance(h, logging.FileHandler) and h.baseFilename == log_file
            for h in logger.handlers
        )
        if not has_file_handler:
            try:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
                )
                file_handler.setLevel(logging.DEBUG)
                logger.addHandler(file_handler)
            except (IOError, OSError) as e:
                # Best-effort: log warning but don't fail
                logger.warning(f"Could not create file handler for {log_file}: {e}")
    
    return logger
