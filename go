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
        exit 1
    fi
}

# Load environment variables if .env exists in parent directory
if [ -f "$ROOT_DIR/../.env" ]; then
    source "$ROOT_DIR/../.env"
else
    # No .env file found
    check_required_env
fi

# Check if required environment variables are set after loading
check_required_env

# Console port can have a default
CONSOLE_PORT=${CONSOLE_PORT:-3000}

# Export for Vite (use offset port if available)
export VITE_HTTP_PORT=${SYSTEM_HTTP_PORT_ACTUAL:-$SYSTEM_HTTP_PORT}
export VITE_API_URL="http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT_ACTUAL:-$SYSTEM_HTTP_PORT}/api"
export VITE_APP_VERSION=${TAG:-dev}

# Function to run development server
function dev() {
  echo "Starting Rediacc Console development server..."
  
  # Install dependencies if node_modules doesn't exist or if package-lock.json is newer than node_modules
  if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  # Start development server
  echo "Starting development server on port ${CONSOLE_PORT}..."
  PORT=$CONSOLE_PORT npm run dev
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
  echo "Cleaning build artifacts..."
  rm -rf dist/
  rm -rf node_modules/.vite
  sudo rm -rf playwright/artifacts/ 2>/dev/null || true
  echo "Build artifacts cleaned."
}

# Function to run Playwright tests using Docker
function test_playwright() {
  local HEADED_MODE=true
  local SLOW_MO=""
  local TEST_FILE=""
  
  # Parse arguments
  for arg in "$@"; do
    case $arg in
      --headless)
        HEADED_MODE=false
        ;;
      --slow)
        SLOW_MO="500"
        ;;
      --slow=*)
        SLOW_MO="${arg#*=}"
        ;;
      --file=*)
        TEST_FILE="${arg#*=}"
        ;;
    esac
  done
  
  echo "Starting Console Playwright Tests..."
  echo "===================================="
  
  # Determine which test file to run
  if [ -n "$TEST_FILE" ]; then
    # Running specific test file
    local TEST_PATH=""
    
    # Check if it's just a filename or a path
    if [[ "$TEST_FILE" == *"/"* ]]; then
      # Full or relative path provided
      TEST_PATH="$TEST_FILE"
    else
      # Just filename - check common locations
      if [ -f "$ROOT_DIR/playwright/$TEST_FILE" ]; then
        TEST_PATH="$TEST_FILE"
      elif [ -f "$ROOT_DIR/playwright/smart/$TEST_FILE" ]; then
        TEST_PATH="smart/$TEST_FILE"
      else
        echo "❌ Error: Test file not found: $TEST_FILE"
        echo "Searched in:"
        echo "  - playwright/$TEST_FILE"
        echo "  - playwright/smart/$TEST_FILE"
        return 1
      fi
    fi
    
    echo "Running specific test file: $TEST_PATH"
  else
    # Default to running all tests
    local TEST_PATH="smart/test_suite_runner.py"
    if [ ! -f "$ROOT_DIR/playwright/$TEST_PATH" ]; then
      echo "❌ Error: Default test script not found at playwright/$TEST_PATH"
      return 1
    fi
    echo "Running main test suite: $TEST_PATH"
  fi
  
  # Check X11 for headed mode
  if [ "$HEADED_MODE" = true ]; then
    echo "Running in headed mode (with GUI)..."
    export DISPLAY=${DISPLAY:-:0}
    
    if [ -e /tmp/.X11-unix/X0 ]; then
      echo "✓ X11 socket detected"
      export HEADED=true
    else
      echo "⚠️  X11 socket not found - falling back to headless"
      HEADED_MODE=false
    fi
  else
    echo "Running in headless mode..."
  fi
  
  # Show slow mode if enabled
  [ -n "$SLOW_MO" ] && [ "$SLOW_MO" != "0" ] && echo "Slow motion: ${SLOW_MO}ms delay"
  
  # Create artifacts directory structure
  mkdir -p "$ROOT_DIR/playwright/artifacts/screenshots"
  mkdir -p "$ROOT_DIR/playwright/artifacts/logs"
  mkdir -p "$ROOT_DIR/playwright/artifacts/reports"
  mkdir -p "$ROOT_DIR/playwright/artifacts/debug_dumps"
  
  echo -e "\nBuilding Docker image..."
  cd "$ROOT_DIR/playwright"
  docker compose build
  
  # Wait for API to be available
  echo -n "Waiting for API at localhost:$SYSTEM_HTTP_PORT"
  for i in {1..30}; do
    if curl -f -s http://localhost:$SYSTEM_HTTP_PORT/api > /dev/null 2>&1; then
      echo " ✓"
      break
    elif [ $i -eq 30 ]; then
      echo " ⚠️"
      echo "Warning: API not detected at localhost:$SYSTEM_HTTP_PORT"
      echo "Tests may fail if the middleware is not running"
      echo "Make sure to start the middleware first with: cd ../middleware && ./go start"
      read -p "Continue anyway? (y/N): " -n 1 -r
      echo
      if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        return 1
      fi
      break
    fi
    echo -n "."
    sleep 1
  done
  
  # Run tests
  echo -e "\nRunning tests..."
  
  if [ "$HEADED_MODE" = true ]; then
    docker compose run --rm -e HEADED=true playwright python3 $TEST_PATH
  else
    docker compose run --rm playwright python3 $TEST_PATH
  fi
  
  local test_exit_code=$?
  
  # Results
  if [ $test_exit_code -eq 0 ]; then
    echo -e "\n✅ All tests passed!"
  else
    echo -e "\n❌ Some tests failed (exit code: $test_exit_code)"
  fi
  
  cd "$ROOT_DIR"
  return $test_exit_code
}

# Function to run Playwright tests in headless mode
function test_playwright_headless() {
  test_playwright --headless "$@"
}

# Function to clean Playwright test artifacts
function test_playwright_clean() {
  echo "Cleaning up Playwright test artifacts..."
  sudo rm -rf "$ROOT_DIR/playwright/artifacts/"
  cd "$ROOT_DIR/playwright" && docker compose down -v 2>/dev/null || true
  cd "$ROOT_DIR"
  echo "✅ Playwright cleanup completed"
}

# Function to run tests
function test() {
  local RUN_API=false
  local RUN_BROWSER=false
  local PLAYWRIGHT_ARGS=""
  
  # Parse arguments
  for arg in "$@"; do
    case $arg in
      --api)
        RUN_API=true
        ;;
      --browser)
        RUN_BROWSER=true
        ;;
      --headless)
        PLAYWRIGHT_ARGS="$PLAYWRIGHT_ARGS --headless"
        ;;
      --slow)
        PLAYWRIGHT_ARGS="$PLAYWRIGHT_ARGS --slow"
        ;;
      --slow=*)
        PLAYWRIGHT_ARGS="$PLAYWRIGHT_ARGS $arg"
        ;;
      --file=*)
        PLAYWRIGHT_ARGS="$PLAYWRIGHT_ARGS $arg"
        ;;
    esac
  done
  
  # If no specific flags, run both
  if [ "$RUN_API" = false ] && [ "$RUN_BROWSER" = false ]; then
    RUN_API=true
    RUN_BROWSER=true
  fi
  
  echo "Running tests..."
  
  # Run API tests if requested
  if [ "$RUN_API" = true ]; then
    if [ -f "$ROOT_DIR/test-api.mjs" ]; then
      echo "Testing API connectivity..."
      node test-api.mjs
    else
      echo "No API tests found (test-api.mjs not present)."
      echo "API test suite placeholder - implement API tests in test-api.mjs"
    fi
  fi
  
  # Run browser/Playwright tests if requested
  if [ "$RUN_BROWSER" = true ]; then
    if [ -d "$ROOT_DIR/playwright" ] && [ -f "$ROOT_DIR/playwright/smart/test_suite_runner.py" ]; then
      echo ""
      echo "Running browser tests (Playwright)..."
      test_playwright $PLAYWRIGHT_ARGS
    else
      echo "No browser tests found (Playwright tests not available)."
    fi
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
  
  # Copy built files
  echo "Copying build files to bin..."
  cp -r "$ROOT_DIR/dist/"* "$BIN_DIR/"
  
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
  echo "Setting up development environment..."
  
  # Check if middleware is running
  if ! curl -s http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}/api > /dev/null 2>&1; then
    echo "⚠️  Middleware API is not running on ${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}!"
    echo "Start it with: cd ../middleware && ./go start"
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
  echo "Usage: ./go [COMMAND]"
  echo ""
  echo "Commands:"
  echo "  dev           Start development server"
  echo "  build         Build the application for production"
  echo "  preview       Preview the production build"
  echo "  lint          Run ESLint on the codebase"
  echo "  test          Run all tests (API and browser tests)"
  echo "    --api       Run only API tests"
  echo "    --browser   Run only browser (Playwright) tests"
  echo "    --headless  Run browser tests in headless mode"
  echo "    --slow[=ms] Run browser tests with slow motion"
  echo "    --file=<path>  Run specific test file (e.g., --file=test_repository_push.py)"
  echo "  test_playwright  Run Playwright UI tests with GUI (Docker)"
  echo "    --file=<path>  Run specific test file"
  echo "  test_playwright_headless  Run Playwright tests headless (Docker)"
  echo "    --file=<path>  Run specific test file"
  echo "  test_playwright_clean  Clean Playwright test artifacts"
  echo "  clean         Clean build artifacts"
  echo "  release       Build and create release package in bin/"
  echo "  setup         Setup development environment"
  echo "  status        Check application status"
  echo ""
  echo "  help          Show this help message"
  echo ""
  echo "Quick Start:"
  echo "  ./go setup    # Setup web environment"
  echo "  ./go dev      # Start web development"
  echo ""
}

# Main function to handle commands
main() {
    case "$1" in
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
        shift  # Remove 'test' from arguments
        test "$@"
        ;;
      test_playwright)
        test_playwright "$@"
        ;;
      test_playwright_headless)
        test_playwright_headless "$@"
        ;;
      test_playwright_clean)
        test_playwright_clean
        ;;
      clean)
        clean
        ;;
      release)
        release
        ;;
      setup)
        setup
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