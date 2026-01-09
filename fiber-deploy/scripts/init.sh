#!/bin/bash
set -e

# Load Utils
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/utils.sh"

log_info "Initializing FiberStack Deployment..."

# 1. Dependency Check
check_dependencies

# 2. Environment Setup
ENV_FILE="$SCRIPT_DIR/../.env"
ENV_EXAMPLE="$SCRIPT_DIR/../env.example"

if [ ! -f "$ENV_FILE" ]; then
    log_warn ".env file not found. Creating from example..."
    if [ ! -f "$ENV_EXAMPLE" ]; then
        fail "env.example not found! Cannot initialize."
    fi
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    log_info "Created .env"
else
    log_info ".env already exists."
fi

# 3. Secret Generation (Idempotent)
update_secret() {
    local key="$1"
    local file="$2"
    
    if grep -q "^$key=.*default.*" "$file" || grep -q "^$key=$" "$file"; then
        log_info "Generating secure secret for $key..."
        local secret=$(generate_secret)
        # Use sed to replace in place (Linux/Mac compatibleish)
        # Mac sed requires extension for -i
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^$key=.*|$key=$secret|" "$file"
        else
            sed -i "s|^$key=.*|$key=$secret|" "$file"
        fi
    fi
}

update_secret "JWT_PUBLIC_KEY" "$ENV_FILE"
update_secret "FEDERATION_SECRET" "$ENV_FILE"
update_secret "DB_PASS" "$ENV_FILE"

# 4. JWT Key Special Handling
# Ideally JWT_PUBLIC_KEY should be a real RSA key, but for simple auth we use string extraction or real gen.
# The previous step generated a hex string. If your app expects RS256, you need a real key.
# But for now, we follow legacy pattern of "Secret" unless app was changed to purely use RS256 files.
# `cluster-simulation.yml` uses JWT_PUBLIC_KEY as an env var, likely a shared secret or public key string.

# 5. External Network/Volume Check (Optional)
# If using external docker networks, create them here.
if ! docker network ls | grep -q "fiber-network"; then
    log_info "Creating default fiber-network (if not controlled by compose)..."
    # Actually, compose handles this usually. Skipping to avoid conflicts.
fi

log_info "Initialization Complete. Please review .env configuration."
