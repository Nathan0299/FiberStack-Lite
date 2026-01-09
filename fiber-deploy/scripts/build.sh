#!/bin/bash
set -e

# Load Utils
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/utils.sh"

# Args
ENV="$1"      # dev, prod
SERVICE="$2"  # fiber-api, fiber-etl, etc. (or 'all')
VERSION="$3"  # 1.0.0 (Optional for dev)

if [ -z "$ENV" ]; then
    fail "Usage: $0 [env] [service] [version] [--push] [--multi-arch]"
fi

# Flags
PUSH=false
MULTI_ARCH=false
NO_CACHE=false
if [[ "$*" == *"--push"* ]]; then PUSH=true; fi
if [[ "$*" == *"--multi-arch"* ]]; then MULTI_ARCH=true; fi
if [[ "$*" == *"--no-cache"* ]]; then NO_CACHE=true; fi

# Validation
if [ "$ENV" != "dev" ] && [ -z "$VERSION" ]; then
    fail "Versioning is MANDATORY for $ENV builds (e.g. 1.0.0)"
fi

# Pre-flight
if [ ! -f "requirements.txt" ]; then
    log_warn "Lockfile requirements.txt not found in root (if needed)."
fi

# Build Function
build_service() {
    local svc="$1"
    local dockerfile="fiber-deploy/docker/Dockerfile.${svc#fiber-}" # fiber-api -> Dockerfile.api
    
    # Map 'probe' manually if needed
    if [ "$svc" == "fiber-probe" ]; then dockerfile="fiber-deploy/docker/Dockerfile.probe"; fi
    
    if [ ! -f "$dockerfile" ]; then
        log_error "Dockerfile not found for $svc at $dockerfile"
        return
    fi
    
    local tag_base="fiberstack/${svc}"
    local tags=()
    local sha=$(git rev-parse --short HEAD)
    
    # Tagging Strategy
    tags+=("-t" "${tag_base}:latest")
    tags+=("-t" "${tag_base}:${sha}")
    if [ -n "$VERSION" ]; then
        tags+=("-t" "${tag_base}:${VERSION}")
    fi
    
    log_info "Building $svc ($ENV)..."
    
    local build_cmd="docker buildx build"
    if [ "$MULTI_ARCH" = true ]; then
        build_cmd="$build_cmd --platform linux/amd64,linux/arm64"
    else
        build_cmd="$build_cmd --load" # Load into local docker daemon
    fi
    
    if [ "$PUSH" = true ]; then
        build_cmd="$build_cmd --push"
    fi
    
    if [ "$NO_CACHE" = true ]; then
         build_cmd="$build_cmd --no-cache"
    fi
    
    # Execute Build
    # Note: We run from Root context
    cd "$SCRIPT_DIR/../.." 
    $build_cmd "${tags[@]}" -f "$dockerfile" .
    
    # Capture Digest (Single arch mostly, or manifest list)
    # If using buildx, we need to inspect the image name or output
    # For simplification, we assume local build and inspect 'latest'
    if [ "$MULTI_ARCH" = false ]; then
        local digest=$(docker inspect --format='{{.RepoDigests}}' "${tag_base}:latest" | awk -F'[@ ]' '{print $2}' | tr -d '[]')
        echo "$svc=$digest" >> "$SCRIPT_DIR/release.json.tmp"
    else
         echo "$svc=multi-arch-pushed" >> "$SCRIPT_DIR/release.json.tmp"
    fi
}

# Clean release temp
rm -f "$SCRIPT_DIR/release.json.tmp"

log_info "Release: $VERSION ($ENV)"

SERVICES=("fiber-api" "fiber-etl" "fiber-probe")
if [ "$SERVICE" != "all" ] && [ -n "$SERVICE" ]; then
    SERVICES=("$SERVICE")
fi

for s in "${SERVICES[@]}"; do
    build_service "$s"
done

# Finalize Release JSON
echo "{" > "$SCRIPT_DIR/release.json"
echo "  \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"," >> "$SCRIPT_DIR/release.json"
echo "  \"version\": \"${VERSION:-dev}\"," >> "$SCRIPT_DIR/release.json"
echo "  \"env\": \"$ENV\"," >> "$SCRIPT_DIR/release.json"
echo "  \"images\": {" >> "$SCRIPT_DIR/release.json"

first=true
while IFS='=' read -r key val; do
    if [ "$first" = true ]; then first=false; else echo "," >> "$SCRIPT_DIR/release.json"; fi
    echo "    \"$key\": \"$val\"" >> "$SCRIPT_DIR/release.json"
done < "$SCRIPT_DIR/release.json.tmp"

echo "  }" >> "$SCRIPT_DIR/release.json"
echo "}" >> "$SCRIPT_DIR/release.json"
rm "$SCRIPT_DIR/release.json.tmp"

log_info "Build Complete. Artifact: fiber-deploy/scripts/release.json"
