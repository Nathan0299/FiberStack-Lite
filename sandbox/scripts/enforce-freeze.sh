#!/bin/bash
# enforce-freeze.sh
# Ensures no unauthorized changes during MVP Freeze

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

ROOT_DIR=$(pwd)
FREEZE_LOG="$ROOT_DIR/FREEZE.md"

log() {
    echo -e "${GREEN}[FREEZE-GUARD]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

log "Checking for unapproved changes..."

# 1. Check for modified src/ files
# We use git status to find modified or new files in src/
# Note: This assumes we are in a git repo. If not, this check might need 'find' logic.
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    CHANGED_FILES=$(git status --porcelain | grep "src/" || true)
    
    if [ -n "$CHANGED_FILES" ]; then
        echo -e "${RED}Found modified files in src/:${NC}"
        echo "$CHANGED_FILES"
        echo ""
        echo "Strict Freeze is Active. You must revert these changes or log them in FREEZE.md (social override)."
        
        # Social Override Check
        # If the FREEZE.md was updated today, we assume social approval (weak enforcement for dry-run)
        TODAY=$(date +%Y-%m-%d)
        if grep -q "\\[$TODAY\\]" "$FREEZE_LOG"; then
           log "Warning: Changes detected, but FREEZE.md has entries for today. Proceeding with CAUTION."
        else
           error "Mechanical Freeze Violation: No FREEZE.md entry for today."
        fi
    else
        log "No source code changes detected. Clean."
    fi
else
    log "Not a git repository. Skipping strict source diff check."
fi

# 2. Architecture Integrity
# Ensure critical definition files match strict expectations (Checksum approach could go here)
# For now, we just ensure they exist
if [ ! -f "$ROOT_DIR/fiber-dashboard/ARCHITECTURE.md" ]; then
    error "Critical Missing File: fiber-dashboard/ARCHITECTURE.md"
fi

log "Freeze Enforcement PASSED. ❄️"
exit 0
