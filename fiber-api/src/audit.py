"""
Day 78: Append-Only Audit Trail
Tamper-evident logging for all privileged actions.

Security Properties:
- Append-only file (no UPDATE/DELETE)
- Hash chain for tamper detection
- Structured JSONL format for queryability
- Integrity verification endpoint
"""
import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger("fiber-api.audit")

# Audit log file path (append-only)
AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "/tmp/fiber-audit.jsonl"))

# Ensure parent directory exists
try:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Hash chain state
_last_hash = "GENESIS"


def _compute_hash(entry: dict, prev_hash: str) -> str:
    """
    Compute hash chain entry.
    Uses SHA-256 truncated to 16 chars for readability.
    """
    # Create deterministic string representation
    data = json.dumps(entry, sort_keys=True) + prev_hash
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def audit_log(
    user: Dict[str, Any],
    action: str,
    resource: str,
    details: Optional[Dict] = None
) -> dict:
    """
    Write an append-only audit log entry.
    
    Properties:
    - Append-only: Old entries cannot be modified
    - Hash chain: Each entry links to previous
    - Tamper detection: verify_audit_chain() can detect modifications
    
    Args:
        user: User info dict with 'username' and 'role'
        action: Action performed (e.g., 'LOGIN_SUCCESS', 'DELETE_NODE', 'DENIED')
        resource: Resource affected (e.g., 'node:probe-123', 'auth')
        details: Optional additional details
    
    Returns:
        The audit entry dict
    """
    global _last_hash
    
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": user.get("username", "unknown"),
        "role": user.get("role", "unknown"),
        "action": action,
        "resource": resource,
        "details": details or {},
    }
    
    # Add hash chain
    entry["prev_hash"] = _last_hash
    entry["hash"] = _compute_hash(entry, _last_hash)
    _last_hash = entry["hash"]
    
    # Console log for immediate visibility
    logger.info(
        f"AUDIT | {entry['user']} ({entry['role']}) | {action} | {resource}",
        extra=entry
    )
    
    # Append-only file write
    try:
        with open(AUDIT_LOG_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception as e:
        logger.error(f"Audit file write failed: {e}")
    
    return entry


def verify_audit_chain(log_path: Optional[Path] = None) -> tuple:
    """
    Verify audit log hash chain integrity.
    
    Returns:
        Tuple of (is_valid: bool, break_at_line: Optional[int])
        - If valid, returns (True, None)
        - If broken, returns (False, line_number_of_break)
    """
    path = log_path or AUDIT_LOG_PATH
    
    if not path.exists():
        return True, None
    
    prev_hash = "GENESIS"
    
    try:
        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                    
                try:
                    entry = json.loads(line)
                    
                    # Check chain continuity
                    if entry.get("prev_hash") != prev_hash:
                        logger.error(f"Audit chain broken at line {line_num}: prev_hash mismatch")
                        return False, line_num
                    
                    # Verify hash
                    stored_hash = entry.pop("hash")
                    expected_hash = _compute_hash(entry, prev_hash)
                    
                    if stored_hash != expected_hash:
                        logger.error(f"Audit chain broken at line {line_num}: hash mismatch")
                        return False, line_num
                    
                    prev_hash = stored_hash
                    
                except json.JSONDecodeError:
                    logger.error(f"Audit chain broken at line {line_num}: invalid JSON")
                    return False, line_num
                    
    except Exception as e:
        logger.error(f"Audit verification failed: {e}")
        return False, 0
    
    return True, None


def get_audit_stats() -> dict:
    """Get audit log statistics."""
    path = AUDIT_LOG_PATH
    
    if not path.exists():
        return {"total_entries": 0, "file_size_bytes": 0}
    
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
        
        return {
            "total_entries": len(lines),
            "file_size_bytes": path.stat().st_size,
            "path": str(path)
        }
    except Exception as e:
        return {"error": str(e)}
