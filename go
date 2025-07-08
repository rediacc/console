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

# Export for Vite
export VITE_HTTP_PORT=$SYSTEM_HTTP_PORT
export VITE_API_URL="http://${SYSTEM_DOMAIN}:${SYSTEM_HTTP_PORT}/api"

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
  rm -rf src-tauri/target/
  echo "Build artifacts cleaned."
}

# Function to run tests
function test() {
  echo "Running tests..."
  
  # Test API connectivity
  if [ -f "$ROOT_DIR/test-api.mjs" ]; then
    echo "Testing API connectivity..."
    node test-api.mjs
  else
    echo "No API tests found."
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
  
  # Check Tauri build status
  if [ -f "$ROOT_DIR/src-tauri/target/release/rediacc-console" ]; then
    echo "✅ Tauri desktop app built"
  else
    echo "❌ No Tauri desktop build found"
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

# Function to setup Tauri for desktop app development
function tauri:setup() {
  echo "Setting up Tauri desktop app environment..."
  
  # Check Node.js
  if ! command -v node >/dev/null 2>&1; then
    echo "❌ Node.js not found. Please install Node.js 18 or later."
    exit 1
  else
    echo "✅ Node.js found: $(node --version)"
  fi
  
  # Source cargo environment if available
  if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
  fi
  
  # Check Rust
  if ! command -v rustc >/dev/null 2>&1; then
    echo "❌ Rust not found. Please run '../_scripts/system.sh setup' to install Rust."
    exit 1
  else
    echo "✅ Rust found: $(rustc --version)"
  fi
  
  # Check Python (for CLI integration)
  if command -v python3 >/dev/null 2>&1; then
    echo "✅ Python found: $(python3 --version)"
  elif command -v python >/dev/null 2>&1; then
    echo "✅ Python found: $(python --version)"
  else
    echo "⚠️  Python not found. Desktop app will have limited functionality."
  fi
  
  # Add cross-compilation targets
  echo ""
  echo "Adding cross-compilation targets..."
  rustup target add aarch64-apple-darwin 2>/dev/null && echo "✅ Added macOS ARM64 target" || true
  rustup target add aarch64-pc-windows-msvc 2>/dev/null && echo "✅ Added Windows ARM64 target" || true
  rustup target add aarch64-unknown-linux-gnu 2>/dev/null && echo "✅ Added Linux ARM64 target" || true
  rustup target add armv7-unknown-linux-gnueabihf 2>/dev/null && echo "✅ Added Linux ARMv7 target" || true
  
  # Check if Tauri CLI is installed
  if ! npm list --depth=0 @tauri-apps/cli >/dev/null 2>&1; then
    echo ""
    echo "Installing Tauri CLI..."
    npm install --save-dev @tauri-apps/cli
  else
    echo "✅ Tauri CLI already installed"
  fi
  
  echo ""
  echo "✅ Tauri setup complete!"
  echo "You can now run: ./go tauri:dev"
}

# Function to run Tauri in development mode
function tauri:dev() {
  echo "Starting Tauri desktop app in development mode..."
  
  # Source cargo environment if available
  if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
  fi
  
  # Check if cargo is available
  if ! command -v cargo >/dev/null 2>&1; then
    echo "❌ Cargo not found. Please run './go tauri:setup' first."
    exit 1
  fi
  
  # Install dependencies if needed
  if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  npm run tauri:dev
}

# Function to build Tauri desktop app
function tauri:build() {
  echo "Building Tauri desktop app..."
  
  # Source cargo environment if available
  if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
  fi
  
  # Check if cargo is available
  if ! command -v cargo >/dev/null 2>&1; then
    echo "❌ Cargo not found. Please run './go tauri:setup' first."
    exit 1
  fi
  
  # Install dependencies if needed
  if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  # Parse arguments for platform-specific builds
  local platform=""
  local arch=""
  
  for arg in "$@"; do
    case "$arg" in
      --mac|--macos)
        platform="mac"
        ;;
      --mac-arm|--macos-arm)
        platform="mac"
        arch="arm"
        ;;
      --win|--windows)
        platform="win"
        ;;
      --win-arm|--windows-arm)
        platform="win"
        arch="arm"
        ;;
      --linux)
        platform="linux"
        ;;
      --linux-arm|--linux-arm64)
        platform="linux"
        arch="arm"
        ;;
      --linux-armhf|--linux-arm32)
        platform="linux"
        arch="armhf"
        ;;
      *)
        echo "Unknown argument: $arg"
        echo "Usage: ./go tauri:build [OPTIONS]"
        echo "Options:"
        echo "  --mac/--macos         Build for macOS (universal binary)"
        echo "  --mac-arm             Build for macOS ARM64 only"
        echo "  --win/--windows       Build for Windows x64"
        echo "  --win-arm             Build for Windows ARM64"
        echo "  --linux               Build for Linux x64"
        echo "  --linux-arm           Build for Linux ARM64"
        echo "  --linux-armhf         Build for Linux ARMv7 (32-bit)"
        exit 1
        ;;
    esac
  done
  
  # Build frontend first
  echo "Building frontend..."
  npm run build
  
  # Build Tauri app
  if [ -n "$platform" ]; then
    # Platform-specific build
    local build_cmd="tauri:build:$platform"
    if [ -n "$arch" ]; then
      build_cmd="${build_cmd}:${arch}"
    fi
    
    echo "Target: $platform $([ -n "$arch" ] && echo "($arch)")"
    npm run $build_cmd
  else
    # Default build for current platform
    npm run tauri:build
  fi
  
  echo ""
  echo "✅ Tauri desktop app built successfully!"
  echo "Build output: src-tauri/target/release/bundle/"
  
  # Copy to bin/console if bin directory exists
  if [ -d "$ROOT_DIR/../bin" ]; then
    echo ""
    echo "Copying Tauri executables to bin/console..."
    
    # Create console directory in bin
    CONSOLE_BIN_DIR="$ROOT_DIR/../bin/console"
    mkdir -p "$CONSOLE_BIN_DIR"
    
    # Copy the main executable
    if [ -f "$ROOT_DIR/src-tauri/target/release/rediacc-console" ]; then
      cp "$ROOT_DIR/src-tauri/target/release/rediacc-console" "$CONSOLE_BIN_DIR/rediacc-console"
      echo "✅ Copied executable to: $CONSOLE_BIN_DIR/rediacc-console"
    fi
    
    # Copy .deb package if it exists (without version number)
    DEB_FILE=$(find "$ROOT_DIR/src-tauri/target/release/bundle/deb" -name "*.deb" -type f | grep -v "_amd64/" | head -1)
    if [ -n "$DEB_FILE" ] && [ -f "$DEB_FILE" ]; then
      cp "$DEB_FILE" "$CONSOLE_BIN_DIR/rediacc-console.deb"
      echo "✅ Copied .deb package to: $CONSOLE_BIN_DIR/rediacc-console.deb"
    fi
    
    # Copy .rpm package if it exists (without version number)
    RPM_FILE=$(find "$ROOT_DIR/src-tauri/target/release/bundle/rpm" -name "*.rpm" -type f | head -1)
    if [ -n "$RPM_FILE" ] && [ -f "$RPM_FILE" ]; then
      cp "$RPM_FILE" "$CONSOLE_BIN_DIR/rediacc-console.rpm"
      echo "✅ Copied .rpm package to: $CONSOLE_BIN_DIR/rediacc-console.rpm"
    fi
    
    # Copy AppImage if it exists
    APPIMAGE_FILE=$(find "$ROOT_DIR/src-tauri/target/release/bundle" -name "*.AppImage" -type f | head -1)
    if [ -n "$APPIMAGE_FILE" ] && [ -f "$APPIMAGE_FILE" ]; then
      cp "$APPIMAGE_FILE" "$CONSOLE_BIN_DIR/rediacc-console.AppImage"
      echo "✅ Copied AppImage to: $CONSOLE_BIN_DIR/rediacc-console.AppImage"
    fi
    
    # Copy Windows exe if it exists (for cross-compilation)
    if [ -f "$ROOT_DIR/src-tauri/target/release/rediacc-console.exe" ]; then
      cp "$ROOT_DIR/src-tauri/target/release/rediacc-console.exe" "$CONSOLE_BIN_DIR/rediacc-console.exe"
      echo "✅ Copied Windows executable to: $CONSOLE_BIN_DIR/rediacc-console.exe"
    fi
    
    # Copy macOS app bundle if it exists
    if [ -d "$ROOT_DIR/src-tauri/target/release/bundle/macos/Rediacc Console.app" ]; then
      cp -r "$ROOT_DIR/src-tauri/target/release/bundle/macos/Rediacc Console.app" "$CONSOLE_BIN_DIR/rediacc-console.app"
      echo "✅ Copied macOS app bundle to: $CONSOLE_BIN_DIR/rediacc-console.app"
    fi
    
    # Create version info file
    VERSION=$(node -p "require('$ROOT_DIR/package.json').version")
    echo "{
  \"version\": \"${VERSION}\",
  \"buildDate\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
  \"gitCommit\": \"$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')\",
  \"type\": \"desktop\",
  \"platforms\": [\"linux\", \"windows\", \"macos\"]
}" > "$CONSOLE_BIN_DIR/version.json"
    
    echo ""
    echo "All Tauri executables copied to: $CONSOLE_BIN_DIR"
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
  echo "  test          Run tests"
  echo "  clean         Clean build artifacts"
  echo "  release       Build and create release package in bin/"
  echo "  setup         Setup development environment"
  echo "  status        Check application status"
  echo ""
  echo "Tauri Desktop Commands:"
  echo "  tauri:setup   Setup Tauri desktop app environment"
  echo "  tauri:dev     Start Tauri in development mode"
  echo "  tauri:build   Build Tauri desktop app"
  echo ""
  echo "  help          Show this help message"
  echo ""
  echo "Quick Start:"
  echo "  ./go setup    # Setup web environment"
  echo "  ./go dev      # Start web development"
  echo ""
  echo "Desktop App:"
  echo "  ./go tauri:setup    # Setup desktop environment"
  echo "  ./go tauri:dev      # Start desktop development"
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
        test
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
      tauri:setup)
        tauri:setup
        ;;
      tauri:dev)
        tauri:dev
        ;;
      tauri:build)
        shift
        tauri:build "$@"
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