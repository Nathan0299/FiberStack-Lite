#!/bin/bash
# archive-release.sh — Archive release artifacts with checksums
# Usage: ./scripts/archive-release.sh v1.0.0-mvp

set -e

VERSION="${1:-v1.0.0-mvp}"
ARCHIVE_DIR="releases/${VERSION}"

echo "📦 Archiving release: ${VERSION}"
echo "================================"

# Create archive directory
mkdir -p "${ARCHIVE_DIR}"

# 1. Docker Images (if available)
echo "1. Saving Docker images..."
if docker images | grep -q "fiberstack"; then
    docker save fiberstack/api:latest 2>/dev/null | gzip > "${ARCHIVE_DIR}/api.tar.gz" || echo "  ⚠️  API image not found"
    docker save fiberstack/dashboard:latest 2>/dev/null | gzip > "${ARCHIVE_DIR}/dashboard.tar.gz" || echo "  ⚠️  Dashboard image not found"
    docker save fiberstack/etl:latest 2>/dev/null | gzip > "${ARCHIVE_DIR}/etl.tar.gz" || echo "  ⚠️  ETL image not found"
    docker save fiberstack/probe:latest 2>/dev/null | gzip > "${ARCHIVE_DIR}/probe.tar.gz" || echo "  ⚠️  Probe image not found"
else
    echo "  ℹ️  No fiberstack images found, skipping Docker archive"
fi

# 2. Config Bundle
echo "2. Archiving configuration..."
cp fiber-deploy/docker-compose.dev.yml "${ARCHIVE_DIR}/" 2>/dev/null || echo "  ⚠️  docker-compose.dev.yml not found"

# 3. Database Schema (if running)
echo "3. Capturing database schema..."
if docker ps | grep -q "fiber-db"; then
    docker exec fiber-db pg_dump -U postgres -s fiberstack > "${ARCHIVE_DIR}/schema.sql" 2>/dev/null || echo "  ⚠️  Could not dump schema"
else
    echo "  ℹ️  Database not running, skipping schema dump"
fi

# 4. Documentation Bundle
echo "4. Creating docs bundle..."
if command -v pandoc &> /dev/null; then
    pandoc docs/SYSTEM_BLUEPRINT.md docs/ARCHITECTURE_FREEZE.md docs/DEV_GUIDE.md docs/RELEASE_NOTES.md \
        -o "${ARCHIVE_DIR}/FiberStack-Docs-${VERSION}.pdf" 2>/dev/null || echo "  ⚠️  Pandoc failed, skipping PDF"
else
    echo "  ℹ️  Pandoc not installed, skipping PDF generation"
    # Fallback: just copy markdown
    cp docs/*.md "${ARCHIVE_DIR}/" 2>/dev/null || true
fi

# 5. Source Code Snapshot
echo "5. Creating source archive..."
git archive --format=tar.gz --prefix="FiberStack-Lite-${VERSION}/" HEAD > "${ARCHIVE_DIR}/source.tar.gz"

# 6. Generate Checksums
echo "6. Generating checksums..."
cd "${ARCHIVE_DIR}"
sha256sum * > SHA256SUMS.txt 2>/dev/null || shasum -a 256 * > SHA256SUMS.txt

echo ""
echo "✅ Archive complete: ${ARCHIVE_DIR}"
echo "================================"
ls -la
echo ""
echo "To verify: sha256sum -c SHA256SUMS.txt"
