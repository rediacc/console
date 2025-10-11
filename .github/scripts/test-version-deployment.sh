#!/bin/bash
# Test script for versioned deployment
# Simulates the GitHub Actions workflow locally

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the console directory
if [ ! -f "package.json" ] || [ ! -f "vite.config.ts" ]; then
    log_error "This script must be run from the console directory"
    exit 1
fi

# Parse arguments
VERSION="${1:-v0.0.1-test}"
SKIP_BUILD="${2:-false}"

log_info "Testing versioned deployment for version: $VERSION"

# Create test directories
TEST_DIR=".test-deployment"
GH_PAGES_DIR="$TEST_DIR/gh-pages"
BUILD_DIR="$TEST_DIR/dist"

log_info "Cleaning up previous test..."
rm -rf "$TEST_DIR"
mkdir -p "$GH_PAGES_DIR"
mkdir -p "$BUILD_DIR"

# Build the console if not skipping
if [ "$SKIP_BUILD" != "true" ]; then
    log_info "Building console..."
    export REDIACC_BUILD_TYPE=RELEASE
    export VITE_APP_VERSION="$VERSION"
    export NODE_ENV=production
    npm run build

    # Copy build to test directory
    cp -r dist/* "$BUILD_DIR/"
else
    log_info "Skipping build (using existing dist)"
    if [ ! -d "dist" ]; then
        log_error "No dist directory found. Run without SKIP_BUILD or build first."
        exit 1
    fi
    cp -r dist/* "$BUILD_DIR/"
fi

# Add version.json
cat > "$BUILD_DIR/version.json" <<EOF
{
  "version": "$VERSION",
  "buildDate": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "gitCommit": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
  "gitCommitShort": "$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
}
EOF

# Add CNAME
echo 'console.rediacc.com' > "$BUILD_DIR/CNAME"

# Add 404.html for SPA routing
cp "$BUILD_DIR/index.html" "$BUILD_DIR/404.html"

# Simulate existing versions in gh-pages (optional)
log_info "Creating mock existing versions..."
mkdir -p "$GH_PAGES_DIR/versions/v0.0.0-old"
echo "<html><body>Old version</body></html>" > "$GH_PAGES_DIR/versions/v0.0.0-old/index.html"

# Run the version management script
log_info "Running version deployment script..."
.github/scripts/manage-versions.sh deploy "$GH_PAGES_DIR" "$BUILD_DIR" "$VERSION"

# Verify deployment
log_info "Verifying deployment..."

# Check root deployment
if [ ! -f "$GH_PAGES_DIR/index.html" ]; then
    log_error "Root index.html not found"
    exit 1
fi
log_success "✓ Root deployment found"

# Check versioned deployment
if [ ! -f "$GH_PAGES_DIR/versions/$VERSION/index.html" ]; then
    log_error "Versioned deployment not found at versions/$VERSION/"
    exit 1
fi
log_success "✓ Versioned deployment found at versions/$VERSION/"

# Check versions index
if [ ! -f "$GH_PAGES_DIR/versions/index.html" ]; then
    log_error "Versions index page not found"
    exit 1
fi
log_success "✓ Versions index page created"

# Check versions.json
if [ ! -f "$GH_PAGES_DIR/versions.json" ]; then
    log_error "versions.json manifest not found"
    exit 1
fi
log_success "✓ versions.json manifest created"

# Display results
log_info ""
log_info "========================================="
log_info "Deployment Test Results"
log_info "========================================="
log_info "Test directory: $TEST_DIR"
log_info "Version deployed: $VERSION"
log_info ""
log_info "Deployed files:"
echo ""
echo "Root (latest):"
ls -lh "$GH_PAGES_DIR" | grep -E "index.html|version.json|versions.json|CNAME"
echo ""
echo "Versioned deployments:"
ls -lh "$GH_PAGES_DIR/versions/"
echo ""
echo "This version:"
ls -lh "$GH_PAGES_DIR/versions/$VERSION/"
echo ""

log_success "All tests passed!"
log_info ""
log_info "To inspect the deployment, check: $TEST_DIR/gh-pages/"
log_info "To start a local server: cd $TEST_DIR/gh-pages && python3 -m http.server 8080"
log_info ""
log_info "Cleanup: rm -rf $TEST_DIR"
