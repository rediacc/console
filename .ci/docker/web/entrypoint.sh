#!/bin/sh
# Rediacc Console Web entrypoint script
# Generates runtime configuration and starts nginx
#
# Features:
# - Generate config.js from environment variables
# - Generate cli-packages.json metadata (checksums, versions)
# - Detect SSL certificates for HTTPS mode
# - Log startup configuration

set -e

# =============================================================================
# Environment defaults
# =============================================================================
export INSTANCE_NAME="${INSTANCE_NAME:-opensource}"
export API_URL="${API_URL:-/api}"
export ENABLE_DEBUG="${ENABLE_DEBUG:-false}"
export BUILD_TYPE="${BUILD_TYPE:-DEBUG}"
export HTTP_PORT="${HTTP_PORT:-80}"
export HTTPS_PORT="${HTTPS_PORT:-443}"
export JSON_URL="${JSON_URL:-/json}"

# =============================================================================
# Generate config.js
# =============================================================================
generate_config_js() {
    cat >/usr/share/nginx/html/config.js <<EOCONFIG
window.REDIACC_CONFIG = {
  instanceName: '${INSTANCE_NAME}',
  apiUrl: '${API_URL}',
  domain: window.location.hostname,
  httpPort: '${HTTP_PORT}',
  buildType: '${BUILD_TYPE}',
  enableDebug: '${ENABLE_DEBUG}',
  enableSandboxFallback: '${BUILD_TYPE}' === 'DEBUG' ? 'true' : 'false',
  version: '${VITE_APP_VERSION:-latest}',
  buildTime: '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
  environment: '${BUILD_TYPE}' === 'RELEASE' ? 'production' : 'development',
  defaultLanguage: 'en',
  jsonUrl: '${JSON_URL}'
};

if (window.REDIACC_CONFIG.enableDebug === 'true') {
  console.log('Rediacc Configuration:', window.REDIACC_CONFIG);
}
EOCONFIG
}

# =============================================================================
# Generate cli-packages.json metadata
# =============================================================================
generate_cli_packages_json() {
    _json_file="/usr/share/nginx/html/cli-packages.json"
    _npm_dir="/usr/share/nginx/html/npm"
    _bin_dir="/usr/share/nginx/html/bin"
    _generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # Start JSON
    cat >"$_json_file" <<EOF
{
  "generatedAt": "${_generated_at}",
  "cli": {
    "packages": [
EOF

    # Add CLI packages
    _first_pkg=true
    if [ -d "$_npm_dir" ]; then
        for _tgz in "$_npm_dir"/*.tgz; do
            [ -f "$_tgz" ] || continue
            _filename="$(basename "$_tgz")"
            _size="$(stat -c%s "$_tgz" 2>/dev/null || stat -f%z "$_tgz" 2>/dev/null || echo 0)"
            _sha256="$(sha256sum "$_tgz" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$_tgz" 2>/dev/null | cut -d' ' -f1 || echo "")"

            # Extract version from filename (rediacc-cli-X.Y.Z.tgz)
            _version="$(echo "$_filename" | sed -n 's/rediacc-cli-\([0-9.]*\)\.tgz/\1/p')"
            [ -z "$_version" ] && _version="latest"

            if [ "$_first_pkg" = true ]; then
                _first_pkg=false
            else
                echo "," >>"$_json_file"
            fi

            cat >>"$_json_file" <<PKGEOF
      {
        "filename": "${_filename}",
        "url": "/npm/${_filename}",
        "version": "${_version}",
        "size": ${_size},
        "sha256": "${_sha256}"
      }
PKGEOF
        done
    fi

    # Close packages array, start binaries
    cat >>"$_json_file" <<EOF

    ]
  },
  "renet": {
    "binaries": [
EOF

    # Add renet binaries
    _first_bin=true
    if [ -d "$_bin_dir" ]; then
        for _binary in "$_bin_dir"/renet-*; do
            [ -f "$_binary" ] || continue
            # Skip symlinks for main listing
            [ -L "$_binary" ] && continue

            _filename="$(basename "$_binary")"
            _size="$(stat -c%s "$_binary" 2>/dev/null || stat -f%z "$_binary" 2>/dev/null || echo 0)"
            _sha256="$(sha256sum "$_binary" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$_binary" 2>/dev/null | cut -d' ' -f1 || echo "")"

            # Extract arch from filename (renet-linux-amd64)
            _arch="$(echo "$_filename" | sed 's/renet-linux-//')"

            if [ "$_first_bin" = true ]; then
                _first_bin=false
            else
                echo "," >>"$_json_file"
            fi

            cat >>"$_json_file" <<BINEOF
      {
        "filename": "${_filename}",
        "url": "/bin/${_filename}",
        "os": "linux",
        "arch": "${_arch}",
        "size": ${_size},
        "sha256": "${_sha256}"
      }
BINEOF
        done
    fi

    # Close JSON
    cat >>"$_json_file" <<EOF

    ]
  }
}
EOF

    echo "Generated cli-packages.json"
}

# =============================================================================
# Configure HTTPS if certificates are present
# =============================================================================
configure_https() {
    _cert_dir="/etc/nginx/certs"
    _https_conf="/etc/nginx/http.d/https.conf"
    _https_template="/etc/nginx/nginx-https.conf"

    if [ -f "$_cert_dir/cert.pem" ] && [ -f "$_cert_dir/key.pem" ]; then
        echo "SSL certificates detected, enabling HTTPS"
        if [ -f "$_https_template" ]; then
            cp "$_https_template" "$_https_conf"
            return 0
        else
            echo "Warning: nginx-https.conf template not found, HTTPS not enabled"
            return 1
        fi
    else
        echo "No SSL certificates found, running HTTP only"
        # Remove HTTPS config if it exists
        rm -f "$_https_conf"
        return 1
    fi
}

# =============================================================================
# Log startup configuration
# =============================================================================
log_startup() {
    _ssl_mode="HTTP only"
    [ -f "/etc/nginx/http.d/https.conf" ] && _ssl_mode="HTTP + HTTPS"

    echo "=========================================="
    echo "Starting Rediacc Console"
    echo "=========================================="
    echo "Instance Name: ${INSTANCE_NAME}"
    echo "Build Type:    ${BUILD_TYPE}"
    echo "API URL:       ${API_URL}"
    echo "Debug Mode:    ${ENABLE_DEBUG}"
    echo "SSL Mode:      ${_ssl_mode}"
    echo ""

    # List available packages
    if [ -d "/usr/share/nginx/html/npm" ]; then
        echo "CLI packages:"
        ls -la /usr/share/nginx/html/npm/*.tgz 2>/dev/null | awk '{print "  - " $NF}' || echo "  (none)"
    fi

    if [ -d "/usr/share/nginx/html/bin" ]; then
        echo "Renet binaries:"
        ls -la /usr/share/nginx/html/bin/renet-* 2>/dev/null | awk '{print "  - " $NF}' || echo "  (none)"
    fi

    echo "=========================================="
}

# =============================================================================
# Main
# =============================================================================
main() {
    # Generate runtime configuration
    generate_config_js

    # Generate package metadata
    generate_cli_packages_json

    # Configure HTTPS if certificates are available
    configure_https || true

    # Start account server (background) if present
    # The server is optional - nginx will serve the SPA even if the API is down
    if [ -f /app/account/bundle.js ]; then
        echo "Starting account server on port 3000..."
        (node /app/account/bundle.js || echo "Warning: account server exited with code $?") &
    fi

    # Log startup info
    log_startup

    # Start nginx
    exec nginx -g "daemon off;"
}

main "$@"
