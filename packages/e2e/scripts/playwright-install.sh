#!/bin/bash
# Playwright Installation Script
# Installs Playwright and browser dependencies

set -e

# Load shared utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_shared.sh"

install_playwright() {
    print_separator
    echo "🎭 INSTALLING PLAYWRIGHT"
    print_separator
    echo ""

    log_info "Setting up Playwright environment..."
    
    # Set Playwright browsers path
    echo 'export PLAYWRIGHT_BROWSERS_PATH=$HOME/.playwright-browsers' >> ~/.bashrc
    source ~/.bashrc
    
    log_info "Installing Playwright dependencies..."
    npm install
    
    log_info "Installing Playwright browsers..."
    npx playwright install
    
    log_info "Installing system dependencies..."
    npx playwright install-deps
    
    echo ""
    print_separator
    log_success "Playwright installation completed!"
    print_separator
    echo ""
    log_info "Next steps:"
    echo "   1. Run tests: npm test"
    echo "   2. Check browsers: npx playwright --version"
    echo ""
}

# Run installation
install_playwright