#!/bin/bash
set -e

ENV_FILE=".env"
EXAMPLE_FILE=".env.example"

# 1. Initialize Env
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating .env from example..."
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    
    # Secure permissions immediately
    chmod 600 "$ENV_FILE"
fi

# 2. Generate Identity
current_id=$(grep NODE_ID "$ENV_FILE" | cut -d '=' -f2)
if [ -z "$current_id" ]; then
    new_id=$(uuidgen)
    echo "Generating new Node UUID: $new_id"
    # MacOS/BSD sed vs GNU sed handling
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^NODE_ID=$/NODE_ID=$new_id/" "$ENV_FILE"
    else
        sed -i "s/^NODE_ID=$/NODE_ID=$new_id/" "$ENV_FILE"
    fi
else
    echo "Node Identity Exists: $current_id"
fi

# 3. Start
echo "Starting Fiber Edge Node..."
docker-compose up -d

echo "Done. Logs: docker-compose logs -f fiber-probe"
