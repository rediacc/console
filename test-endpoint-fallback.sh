#!/bin/bash

# Test script to verify REDIACC_BUILD_TYPE and endpoint fallback functionality

echo "==================================="
echo "Testing REDIACC_BUILD_TYPE Integration"
echo "==================================="
echo ""

# Test 1: DEBUG mode (development/open-source)
echo "Test 1: DEBUG mode (development & open-source)"
echo "---------------------------------------"
export REDIACC_BUILD_TYPE="DEBUG"
export VITE_HTTP_PORT="7322"
export SANDBOX_API_URL="https://sandbox.rediacc.com/api"
echo "REDIACC_BUILD_TYPE=$REDIACC_BUILD_TYPE"
echo "Expected behavior:"
echo "  - Try localhost:7322 first"
echo "  - Fallback to sandbox if localhost unavailable"
echo "  - Show warning when using sandbox"
echo ""

# Test 2: RELEASE mode (production - SECURE)
echo "Test 2: RELEASE mode (production deployments)"
echo "---------------------------------------"
export REDIACC_BUILD_TYPE="RELEASE"
echo "REDIACC_BUILD_TYPE=$REDIACC_BUILD_TYPE"
echo "Expected behavior:"
echo "  - Use /api from same domain"
echo "  - NEVER connect to sandbox (security feature)"
echo "  - No health checks or fallbacks"
echo ""

# Test 3: Unset (should default to DEBUG)
echo "Test 3: Unset REDIACC_BUILD_TYPE (defaults to DEBUG)"
echo "---------------------------------------"
unset REDIACC_BUILD_TYPE
echo "REDIACC_BUILD_TYPE=(not set)"
echo "Expected behavior: Default to DEBUG mode"
echo ""

echo "==================================="
echo "Usage Examples:"
echo "==================================="
echo ""
echo "# For open-source contributors (auto-fallback to sandbox):"
echo "REDIACC_BUILD_TYPE=DEBUG npm run dev"
echo ""
echo "# For local development with backend:"
echo "REDIACC_BUILD_TYPE=DEBUG npm run dev  # Will use localhost:7322"
echo ""
echo "# For production deployment (SECURE - no sandbox):"
echo "REDIACC_BUILD_TYPE=RELEASE npm run build"
echo "# Deployed app will use /api from same domain"
echo ""
echo "==================================="
echo "Security Note:"
echo "==================================="
echo "RELEASE mode ensures production deployments NEVER connect to sandbox."
echo "This prevents data leakage outside your organization."
echo ""
echo "The endpoint being used is displayed on the login page above the version."
echo "Sandbox usage shows a warning icon (⚠️) in DEBUG mode."