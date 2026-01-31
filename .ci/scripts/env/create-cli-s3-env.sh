#!/bin/bash
# Append S3 test environment variables to an existing .env file
# Usage: create-cli-s3-env.sh --output <path>
#
# Appends S3_TEST_* variables for CLI S3 integration tests.
# The target .env file must already exist (created by create-cli-local-env.sh).
#
# Options:
#   --output    Output .env file path (required)
#
# Example:
#   .ci/scripts/env/create-cli-s3-env.sh --output packages/cli/tests/.env

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

OUTPUT="${ARG_OUTPUT:-}"

# Validate required arguments
if [[ -z "$OUTPUT" ]]; then
    log_error "Usage: create-cli-s3-env.sh --output <path>"
    exit 1
fi

log_step "Appending S3 test env vars to: $OUTPUT"

cat >> "$OUTPUT" << 'EOF'

# S3 Integration Tests (added by create-cli-s3-env.sh)
S3_TEST_ENDPOINT=http://192.168.111.1:9000
S3_TEST_ACCESS_KEY=rustfsadmin
S3_TEST_SECRET_KEY=rustfsadmin
S3_TEST_BUCKET=rediacc-test
EOF

log_info "S3 test env vars appended to: $OUTPUT"

# Display contents for debugging
if [[ "${DEBUG:-false}" == "true" ]]; then
    echo ""
    echo "Contents:"
    cat "$OUTPUT"
fi
