import os
from pathlib import Path

class SandboxLoader:
    """Loads sandbox environment configs for test runs."""

    def load(self, env_name: str = "dev"):
        base = Path("sandbox/environments") / env_name
        return {
            "api": base / "api",
            "storage": base / "storage",
            "identity": base / "identity",
        }
