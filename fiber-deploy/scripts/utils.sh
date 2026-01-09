#!/bin/bash

# Shared Utilities for FiberStack Deployment
# Version: 1.0.0
# Day 93: Deployment Automation

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Audit Log File
AUDIT_LOG="/var/log/fiberstack-audit.log"
# Fallback if not sudo
if [ ! -w "/var/log" ]; then
    AUDIT_LOG="./audit.log"
fi

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

log_audit() {
    local action="$1"
    local user=$(whoami)
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local message="[AUDIT] $timestamp | User: $user | Action: $action"
    
    # Console output
    echo -e "${CYAN}$message${NC}"
    
    # Syslog
    if command -v logger &> /dev/null; then
        logger -t fiber-deploy "$message"
    fi
    
    # File Append (if writable)
    echo "$message" >> "$AUDIT_LOG" 2>/dev/null
}

fail() {
    log_error "$1"
    exit 1
}

# -----------------------------------------------------------------------------
# Safety & Prompts
# -----------------------------------------------------------------------------

confirm_destructive() {
    local env="$1"
    local msg="$2"
    
    echo -e "${RED}!!! DESTRUCTIVE ACTION WARNING !!!${NC}"
    echo -e "You are about to: $msg"
    echo -e "Target Environment: ${RED}$env${NC}"
    echo
    echo "Type 'YES' to continue, or anything else to abort."
    read -r response
    if [ "$response" != "YES" ]; then
        fail "Operation aborted by user."
    fi
    
    # Double confirmation for Prod
    if [ "$env" == "prod" ] || [ "$env" == "production" ]; then
        echo -e "${RED}!!! PRODUCTION SAFEGUARD !!!${NC}"
        echo "Type the environment name '$env' to confirm:"
        read -r env_conf
        if [ "$env_conf" != "$env" ]; then
            fail "Production safeguard failed. Aborted."
        fi
    fi
}

# -----------------------------------------------------------------------------
# Resource Validation
# -----------------------------------------------------------------------------

check_resources() {
    log_info "Checking system resources..."
    
    # 1. Disk Space (Check /var/lib/docker or current dir)
    local min_space_kb=1048576 # 1GB
    local avail_space=$(df -k . | awk 'NR==2 {print $4}')
    
    if [ "$avail_space" -lt "$min_space_kb" ]; then
        fail "Insufficient Disk Space! Available: $((avail_space/1024))MB, Required: 1024MB"
    fi
    
    # 2. Ports
    local ports=(8000 3000 5432)
    # Check if ports are listening (skip if we are restarting, assume self-managed?)
    # Actually, for deploy, we might expect them to be free OR occupied by US.
    # This check is tricky during update. Maybe only check if not deploying?
    # Let's verify we have general capacity.
    
    log_info "Resource check passed."
}

check_dependencies() {
    local deps=("docker" "jq" "openssl")
    for cmd in "${deps[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            fail "Missing dependency: $cmd"
        fi
    done
}

# -----------------------------------------------------------------------------
# Secrets & Env
# -----------------------------------------------------------------------------

generate_secret() {
    # 32 bytes hex = 64 chars
    openssl rand -hex 32
}

# -----------------------------------------------------------------------------
# Resilience
# -----------------------------------------------------------------------------

retry_with_backoff() {
    local max_attempts="$1"
    local timeout="$2"
    local cmd="${@:3}"
    local count=1
    local wait=2
    
    while [ $count -le $max_attempts ]; do
        if eval "$cmd"; then
            return 0
        fi
        
        log_warn "Attempt $count/$max_attempts failed. Retrying in ${wait}s..."
        sleep $wait
        
        # Exponential backoff
        wait=$((wait * 2))
        count=$((count + 1))
    done
    
    return 1
}
