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
  echo "  help          Show this help message"
  echo ""
  echo "Quick Start:"
  echo "  ./go setup    # Setup environment"
  echo "  ./go dev      # Start development"
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