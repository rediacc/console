#!/bin/bash

# Exit on error
set -e

# Required environment variables (must be defined in parent .env file):
# - SYSTEM_HTTP_PORT: Middleware API port
# - SYSTEM_DOMAIN: Domain for API access
# Optional environment variables:
# - CONSOLE_PORT: Console dev server port (default: 3000)

# Root directory
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Function to check required environment variables
check_required_env() {
    # For sandbox mode, we don't need these variables
    if [ "$1" = "sandbox" ] || [ "$SANDBOX_MODE" = "true" ]; then
        return 0
    fi
    
    if [ -z "$SYSTEM_HTTP_PORT" ] || [ -z "$SYSTEM_DOMAIN" ]; then
        echo "❌ Error: Required environment variables are not set!"
        echo ""
        if [ ! -f "$ROOT_DIR/../.env" ]; then
            echo "The parent .env file does not exist at: $ROOT_DIR/../.env"
        else
            echo "The parent .env file exists but is missing required variables."
        fi
        echo ""
        echo "Please ensure the following variables are defined:"
        echo "  - SYSTEM_HTTP_PORT (e.g., 7322)"
        echo "  - SYSTEM_DOMAIN (e.g., localhost)"
        echo ""
        echo "Or run in sandbox mode for open-source development:"
        echo "  ./go sandbox    # Use sandbox backend (no local setup needed)"
        exit 1
    fi
}

# Load environment variables if .env exists in parent directory
if [ -f "$ROOT_DIR/../.env" ]; then
    source "$ROOT_DIR/../.env"
fi

# Check command to determine if we need env vars
COMMAND="$1"
if [ "$COMMAND" = "sandbox" ] || [ "$COMMAND" = "help" ] || [ "$COMMAND" = "--help" ] || [ "$COMMAND" = "-h" ] || [ -z "$COMMAND" ]; then
    # These commands don't require environment variables
    :
else
    # Check if required environment variables are set after loading
    check_required_env "$COMMAND"
fi

# Console port can have a default
CONSOLE_PORT=${CONSOLE_PORT:-3000}

# Export for Vite (use offset port if available) - only if variables are set
if [ -n "$SYSTEM_HTTP_PORT" ]; then
    export VITE_HTTP_PORT=${SYSTEM_HTTP_PORT_ACTUAL:-$SYSTEM_HTTP_PORT}
    export VITE_API_URL="http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT_ACTUAL:-$SYSTEM_HTTP_PORT}/api"
fi
export VITE_APP_VERSION=${TAG:-dev}
# Export Turnstile site key (Cloudflare Captcha)
export VITE_TURNSTILE_SITE_KEY=${TURNSTILE_SITE_KEY:-"0x4AAAAAACBhdTQowG3P_iM8"}

# Function to run development server
function dev() {
  echo "Starting Rediacc Console development server..."
  
  # Install dependencies if node_modules doesn't exist or if package-lock.json is newer than node_modules
  if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  # Set build type to DEBUG for development (will try localhost, fallback to sandbox)
  export REDIACC_BUILD_TYPE=${REDIACC_BUILD_TYPE:-DEBUG}
  
  # Start development server
  echo "Starting development server on port ${CONSOLE_PORT}..."
  echo "Build type: $REDIACC_BUILD_TYPE"
  PORT=$CONSOLE_PORT npm run dev
}

# Function to run in sandbox mode (for open-source contributors)
function sandbox() {
  local USE_DOCKER=false
  local DOCKER_PORT=8080
  local OPEN_BROWSER=true
  
  # Parse arguments
  for arg in "$@"; do
    case $arg in
      --docker)
        USE_DOCKER=true
        ;;
      --port=*)
        DOCKER_PORT="${arg#*=}"
        ;;
      --no-browser)
        OPEN_BROWSER=false
        ;;
      --help)
        echo "Usage: ./go sandbox [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --docker        Run in Docker container (recommended for quick start)"
        echo "  --port=PORT     Docker port (default: 8080)"
        echo "  --no-browser    Don't open browser automatically"
        echo ""
        echo "Examples:"
        echo "  ./go sandbox              # Run locally with npm"
        echo "  ./go sandbox --docker     # Run in Docker (recommended)"
        echo ""
        return 0
        ;;
    esac
  done
  
  echo "Starting Rediacc Console in Sandbox Mode (Open-Source)..."
  echo "========================================================"
  echo ""
  
  if [ "$USE_DOCKER" = true ]; then
    # Docker mode - build and run container
    echo "🐳 Docker Mode - Building and running containerized console"
    echo ""
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
      echo "❌ Error: Docker is not installed!"
      echo ""
      echo "Please install Docker first:"
      echo "  - Linux: https://docs.docker.com/engine/install/"
      echo "  - macOS: https://docs.docker.com/desktop/mac/install/"
      echo "  - Windows: https://docs.docker.com/desktop/windows/install/"
      echo ""
      echo "Or run without Docker: ./go sandbox"
      return 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
      echo "❌ Error: Docker daemon is not running!"
      echo "Please start Docker and try again."
      return 1
    fi
    
    # Build the Docker image
    echo "📦 Building Docker image..."
    echo "This may take a few minutes on first run..."
    echo ""
    
    if ! docker build -f Dockerfile.standalone -t rediacc-console:sandbox \
      --build-arg REDIACC_BUILD_TYPE=DEBUG .; then
      echo ""
      echo "❌ Error: Docker build failed!"
      echo "Please check the error messages above."
      return 1
    fi
    
    echo ""
    echo "✅ Docker image built successfully!"
    echo ""
    
    # Stop any existing container
    docker stop rediacc-console-sandbox 2>/dev/null || true
    docker rm rediacc-console-sandbox 2>/dev/null || true
    
    # Run the container
    echo "🚀 Starting container on port ${DOCKER_PORT}..."
    docker run -d \
      --name rediacc-console-sandbox \
      -p ${DOCKER_PORT}:80 \
      -e INSTANCE_NAME=sandbox \
      -e BUILD_TYPE=DEBUG \
      -e ENABLE_DEBUG=true \
      rediacc-console:sandbox
    
    # Wait for container to be ready
    echo -n "⏳ Waiting for console to be ready"
    for i in {1..30}; do
      if curl -s http://localhost:${DOCKER_PORT}/health > /dev/null 2>&1; then
        echo " ✓"
        break
      elif [ $i -eq 30 ]; then
        echo " ⚠️"
        echo "Warning: Console may not be fully ready yet."
        break
      fi
      echo -n "."
      sleep 1
    done
    
    echo ""
    echo "✅ Rediacc Console is running in Docker!"
    echo ""
    echo "🌐 Access the console at: http://localhost:${DOCKER_PORT}"
    echo ""
    echo "📋 Container Management:"
    echo "  View logs:    docker logs -f rediacc-console-sandbox"
    echo "  Stop:         docker stop rediacc-console-sandbox"
    echo "  Restart:      docker start rediacc-console-sandbox"
    echo "  Remove:       docker rm -f rediacc-console-sandbox"
    echo ""
    
    # Open browser if requested
    if [ "$OPEN_BROWSER" = true ]; then
      open_browser "http://localhost:${DOCKER_PORT}"
    fi
    
    # Show logs
    echo "📜 Showing container logs (Ctrl+C to exit):"
    echo "----------------------------------------"
    docker logs -f rediacc-console-sandbox
    
  else
    # Local development mode
    echo "This mode is designed for open-source contributors who want to"
    echo "work on the frontend without setting up a local backend."
    echo ""
    echo "💡 Tip: Use './go sandbox --docker' for easier setup with Docker"
    echo ""
    echo "The console will connect to: sandbox.rediacc.com"
    echo ""
    
    # Install dependencies if node_modules doesn't exist or if package-lock.json is newer than node_modules
    if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
      echo "Installing dependencies..."
      npm install
    fi
    
    # Set environment for sandbox mode
    export REDIACC_BUILD_TYPE=DEBUG
    export SANDBOX_MODE=true
    export VITE_HTTP_PORT=7322  # Default port for consistency
    export VITE_SANDBOX_API_URL=${SANDBOX_API_URL:-https://sandbox.rediacc.com/api}
    export CONSOLE_PORT=${CONSOLE_PORT:-3000}
    
    # Start development server
    echo ""
    echo "Starting development server on port ${CONSOLE_PORT}..."
    echo "Build type: DEBUG (with sandbox fallback)"
    echo "Sandbox URL: $VITE_SANDBOX_API_URL"
    echo ""
    echo "Note: The console will attempt to connect to localhost:7322 first,"
    echo "      then automatically fallback to sandbox if localhost is unavailable."
    echo ""
    
    # Open browser if requested
    if [ "$OPEN_BROWSER" = true ]; then
      # Wait a bit for the server to start
      (sleep 3 && open_browser "http://localhost:${CONSOLE_PORT}") &
    fi
    
    PORT=$CONSOLE_PORT npm run dev
  fi
}

# Helper function to open browser (cross-platform)
function open_browser() {
  local url="$1"
  echo "🌐 Opening browser to: $url"
  
  # Detect platform and open browser
  case "$OSTYPE" in
    linux*)
      if command -v xdg-open &> /dev/null; then
        xdg-open "$url" 2>/dev/null || true
      elif command -v gnome-open &> /dev/null; then
        gnome-open "$url" 2>/dev/null || true
      else
        echo "Please open your browser and navigate to: $url"
      fi
      ;;
    darwin*)
      open "$url" 2>/dev/null || true
      ;;
    msys*|cygwin*|win32)
      start "$url" 2>/dev/null || true
      ;;
    *)
      echo "Please open your browser and navigate to: $url"
      ;;
  esac
}

# Function to build the application
function build() {
  echo "Building Rediacc Console..."
  
  # Install dependencies if node_modules doesn't exist or if package-lock.json is newer than node_modules
  if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  # Clean caches before build
  rm -rf node_modules/.vite
  
  # Default to RELEASE for production builds
  export REDIACC_BUILD_TYPE=${REDIACC_BUILD_TYPE:-RELEASE}
  echo "Build type: $REDIACC_BUILD_TYPE"
  
  # Build with NODE_ENV explicitly set to production
  NODE_ENV=production npm run build
}

# Function to preview the build
function preview() {
  echo "Previewing the Rediacc Console build..."
  
  # Install dependencies if node_modules doesn't exist or if package-lock.json is newer than node_modules
  if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  npm run preview
}

# Function to lint the code
function lint() {
  echo "Linting code..."
  
  # Install dependencies if node_modules doesn't exist
  if [ ! -d "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  npm run lint
}

# Function to clean up
function clean() {
  local CLEAN_DOCKER=false
  
  # Parse arguments
  for arg in "$@"; do
    case $arg in
      --docker)
        CLEAN_DOCKER=true
        ;;
    esac
  done
  
  echo "Cleaning build artifacts..."
  rm -rf dist/
  rm -rf node_modules/.vite
  
  # Clean Docker artifacts if requested
  if [ "$CLEAN_DOCKER" = true ]; then
    echo "Cleaning Docker containers and images..."
    
    # Stop and remove container
    docker stop rediacc-console-sandbox 2>/dev/null || true
    docker rm rediacc-console-sandbox 2>/dev/null || true
    
    # Remove image
    docker rmi rediacc-console:sandbox 2>/dev/null || true
    
    echo "Docker artifacts cleaned."
  fi
  
  echo "Build artifacts cleaned."
}

# Function to run tests
function test() {
  echo "Running tests..."

  if [ -f "$ROOT_DIR/test-api.mjs" ]; then
    echo "Testing API connectivity..."
    node test-api.mjs
  else
    echo "No API tests found (test-api.mjs not present)."
  fi
}

# Function to create release package
function release() {
  echo "Creating release build..."
  
  # Create bin directory if it doesn't exist
  BIN_DIR="$ROOT_DIR/bin"
  
  # Clean up bin directory
  echo "Cleaning up bin directory..."
  rm -rf "$BIN_DIR"
  mkdir -p "$BIN_DIR"
  
  # Build the application first
  build
  
  # Get version from package.json
  VERSION=$(node -p "require('./package.json').version")
  
  # Copy built files from workspace package
  echo "Copying build files to bin..."
  cp -r "$ROOT_DIR/packages/web/dist/"* "$BIN_DIR/"
  
  # Create version info file
  echo "{
  \"version\": \"${VERSION}\",
  \"tag\": \"${TAG:-latest}\",
  \"buildDate\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
  \"gitCommit\": \"$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')\",
  \"environment\": \"production\"
}" > "$BIN_DIR/version.json"
  
  # Create deployment config template
  echo "{
  \"apiUrl\": \"http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}/api\",
  \"environment\": \"production\"
}" > "$BIN_DIR/config.template.json"
  
  echo ""
  echo "Release build created successfully!"
  echo "Version: ${VERSION}"
  echo "Files copied to: $BIN_DIR"
  
  # Copy to root bin/html/console for nginx serving
  echo "Copying to root bin/html/console directory for nginx..."
  ROOT_BIN="$ROOT_DIR/../bin/html/console"
  mkdir -p "$ROOT_BIN"
  # Clean existing console files
  rm -rf "$ROOT_BIN"/*
  # Copy all files to root bin/html/console
  cp -r "$BIN_DIR/"* "$ROOT_BIN/"
  echo "Files also copied to: $ROOT_BIN"
}

# Function to setup development environment
function setup() {
  local SETUP_MODE="$1"
  
  if [ "$SETUP_MODE" = "sandbox" ]; then
    echo "Setting up sandbox development environment..."
    echo "============================================"
    echo ""
    echo "This setup is for open-source contributors who want to"
    echo "work on the frontend without a local backend."
    echo ""
    
    # Install dependencies
    echo "Installing dependencies..."
    npm install
    
    echo ""
    echo "✅ Sandbox environment setup complete!"
    echo ""
    echo "You can now run:"
    echo "  ./go sandbox    # Start with sandbox backend"
    echo ""
    return 0
  fi
  
  echo "Setting up development environment..."
  
  # Check environment variables
  if [ -z "$SYSTEM_HTTP_PORT" ] || [ -z "$SYSTEM_DOMAIN" ]; then
    echo ""
    echo "⚠️  Environment variables not configured."
    echo ""
    echo "You have two options:"
    echo ""
    echo "1. Setup for local development (requires backend):"
    echo "   - Create a .env file in the parent directory with:"
    echo "     SYSTEM_HTTP_PORT=7322"
    echo "     SYSTEM_DOMAIN=localhost"
    echo "   - Then run: ./go setup"
    echo ""
    echo "2. Setup for sandbox development (no backend needed):"
    echo "   ./go setup sandbox"
    echo ""
    return 1
  fi
  
  # Check if middleware is running
  if ! curl -s http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}/api > /dev/null 2>&1; then
    echo "⚠️  Middleware API is not running on ${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}!"
    echo "Start it with: cd ../middleware && ./go start"
    echo ""
    echo "Or use sandbox mode if you don't have a local backend:"
    echo "  ./go sandbox"
  else
    echo "✅ Middleware API is running on ${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}"
  fi
  
  # Install dependencies
  echo "Installing dependencies..."
  npm install
  
  # Create .env file if it doesn't exist
  if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "Creating .env file..."
    echo "VITE_API_URL=http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}/api" > "$ROOT_DIR/.env"
    echo "✅ .env file created with API URL: http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}/api"
  fi
  
  echo ""
  echo "✅ Development environment setup complete!"
  echo ""
  echo "🔍 Telemetry Information:"
  echo "  - OpenTelemetry telemetry is enabled for user behavior analytics"
  echo "  - Telemetry data is sent to obs.rediacc.com for monitoring and insights"
  echo "  - No sensitive data (passwords, keys) is collected"
  echo "  - Data helps improve the application and user experience"
  echo ""
  echo "You can now run: ./go dev"
}


# Function to check status
function status() {
  echo "Rediacc Console Status:"
  echo "======================"
  
  # Check if dev server is running
  if lsof -i :${CONSOLE_PORT} > /dev/null 2>&1; then
    echo "✅ Development server is running on port ${CONSOLE_PORT}"
  else
    echo "❌ Development server is not running"
  fi
  
  # Check if middleware is running
  if curl -s http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}/api > /dev/null 2>&1; then
    echo "✅ Middleware API is running on ${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}"
  else
    echo "❌ Middleware API is not running"
  fi
  
  # Check build status
  if [ -d "$ROOT_DIR/dist" ]; then
    echo "✅ Production build exists"
  else
    echo "❌ No production build found"
  fi
  
  
  # Check bin/console directory
  if [ -d "$ROOT_DIR/../bin/console" ]; then
    echo "✅ Console binaries in bin/console:"
    if [ -f "$ROOT_DIR/../bin/console/rediacc-console" ]; then
      echo "   • Linux executable"
    fi
    if [ -f "$ROOT_DIR/../bin/console/rediacc-console.deb" ]; then
      echo "   • Debian package (.deb)"
    fi
    if [ -f "$ROOT_DIR/../bin/console/rediacc-console.rpm" ]; then
      echo "   • RPM package (.rpm)"
    fi
    if [ -f "$ROOT_DIR/../bin/console/rediacc-console.exe" ]; then
      echo "   • Windows executable"
    fi
    if [ -d "$ROOT_DIR/../bin/console/rediacc-console.app" ]; then
      echo "   • macOS app bundle"
    fi
    if [ -f "$ROOT_DIR/../bin/console/rediacc-console.AppImage" ]; then
      echo "   • AppImage"
    fi
  fi
  
  # Show version
  if [ -f "$ROOT_DIR/package.json" ]; then
    VERSION=$(node -p "require('./package.json').version")
    echo "📦 Version: ${VERSION}"
  fi
}




# Help message
function show_help() {
  echo "Usage: ./go [COMMAND] [OPTIONS]"
  echo ""
  echo "Commands:"
  echo "  sandbox       Start in sandbox mode (for open-source contributors)"
  echo "    --docker    Run in Docker container (recommended)"
  echo "    --port=PORT Set Docker port (default: 8080)"
  echo "    --no-browser Don't open browser automatically"
  echo "  sandbox-docker Quick start with Docker (alias for 'sandbox --docker')"
  echo "  dev           Start development server (requires local backend)"
  echo "  build         Build the application for production"
  echo "  preview       Preview the production build"
  echo "  lint          Run ESLint on the codebase"
  echo "  test          Run tests"
  echo "  clean         Clean build artifacts"
  echo "    --docker    Also clean Docker containers/images"
  echo "  release       Build and create release package in bin/"
  echo "  setup [sandbox]  Setup development environment"
  echo "                   Use 'setup sandbox' for open-source setup"
  echo "  status        Check application status"
  echo ""
  echo "  help          Show this help message"
  echo ""
  echo "🚀 Quick Start (Open-Source Contributors):"
  echo "  ./go sandbox-docker     # Fastest way - run with Docker"
  echo "  ./go sandbox            # Run locally with npm"
  echo ""
  echo "📦 Docker Sandbox Examples:"
  echo "  ./go sandbox --docker              # Build and run in Docker"
  echo "  ./go sandbox --docker --port=3000  # Use custom port"
  echo "  ./go sandbox --docker --no-browser # Don't open browser"
  echo ""
  echo "🔧 Quick Start (With Local Backend):"
  echo "  ./go setup          # Setup local environment"
  echo "  ./go dev            # Start local development"
  echo ""
}

# Main function to handle commands
main() {
    case "$1" in
      sandbox)
        shift  # Remove 'sandbox' from arguments
        sandbox "$@"
        ;;
      sandbox-docker)
        # Convenience alias for sandbox --docker
        shift  # Remove 'sandbox-docker' from arguments
        sandbox --docker "$@"
        ;;
      dev)
        dev
        ;;
      build)
        build
        ;;
      preview)
        preview
        ;;
      lint)
        lint
        ;;
      test)
        test
        ;;
      clean)
        shift  # Remove 'clean' from arguments
        clean "$@"
        ;;
      release)
        release
        ;;
      setup)
        shift  # Remove 'setup' from arguments
        setup "$@"
        ;;
      status)
        status
        ;;
      help|--help|-h)
        show_help
        ;;
      *)
        show_help
        exit 1
        ;;
    esac
}

# Execute main function if run directly
[[ "${BASH_SOURCE[0]}" == "${0}" ]] && main "$@"