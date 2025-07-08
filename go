#!/bin/bash

# Exit on error
set -e

# Root directory
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load environment variables if .env exists in parent directory
if [ -f "$ROOT_DIR/../.env" ]; then
    source "$ROOT_DIR/../.env"
    export VITE_HTTP_PORT=$SYSTEM_HTTP_PORT
fi

# Function to run development server
function dev() {
  echo "Starting Rediacc Console development server..."
  
  # Install dependencies if node_modules doesn't exist or if package-lock.json is newer than node_modules
  if [ ! -d "$ROOT_DIR/node_modules" ] || [ "$ROOT_DIR/package-lock.json" -nt "$ROOT_DIR/node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  # Start development server
  echo "Starting development server on port 3000..."
  npm run dev
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
  \"apiUrl\": \"http://localhost:8080/api\",
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
  if ! curl -s http://localhost:8080/api > /dev/null 2>&1; then
    echo "⚠️  Middleware API is not running!"
    echo "Start it with: cd ../middleware && ./go start"
  else
    echo "✅ Middleware API is running"
  fi
  
  # Install dependencies
  echo "Installing dependencies..."
  npm install
  
  # Create .env file if it doesn't exist
  if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "Creating .env file..."
    echo "VITE_API_URL=http://localhost:8080/api" > "$ROOT_DIR/.env"
    echo "✅ .env file created"
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
  if lsof -i :3000 > /dev/null 2>&1; then
    echo "✅ Development server is running on port 3000"
  else
    echo "❌ Development server is not running"
  fi
  
  # Check if middleware is running
  if curl -s http://localhost:8080/api > /dev/null 2>&1; then
    echo "✅ Middleware API is running on port 8080"
  else
    echo "❌ Middleware API is not running"
  fi
  
  # Check build status
  if [ -d "$ROOT_DIR/dist" ]; then
    echo "✅ Production build exists"
  else
    echo "❌ No production build found"
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