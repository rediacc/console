#!/usr/bin/env bash
# Collect backend logs for debugging CI failures
# Usage: collect-backend-logs.sh [output_dir]
#
# This script collects docker container logs and state from the Elite backend
# services running in the infra-backend CI job. The collected logs help
# diagnose 502 errors and other backend issues that occur during E2E tests.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUTPUT_DIR="${1:-/tmp/backend-logs}"
mkdir -p "$OUTPUT_DIR"

echo "=== Collecting Backend Logs ==="
echo "Output directory: $OUTPUT_DIR"
echo ""

# Collect container logs
echo "Collecting container logs..."
docker logs rediacc-api > "$OUTPUT_DIR/rediacc-api.log" 2>&1 || echo "No rediacc-api logs available" > "$OUTPUT_DIR/rediacc-api.log"
docker logs rediacc-sql > "$OUTPUT_DIR/rediacc-sql.log" 2>&1 || echo "No rediacc-sql logs available" > "$OUTPUT_DIR/rediacc-sql.log"
docker logs rediacc-web > "$OUTPUT_DIR/rediacc-web.log" 2>&1 || echo "No rediacc-web logs available" > "$OUTPUT_DIR/rediacc-web.log"

# Collect container states (JSON format for easy parsing)
echo "Collecting container states..."
docker inspect rediacc-api --format='{{json .State}}' > "$OUTPUT_DIR/rediacc-api-state.json" 2>&1 || echo '{"error": "container not found"}' > "$OUTPUT_DIR/rediacc-api-state.json"
docker inspect rediacc-sql --format='{{json .State}}' > "$OUTPUT_DIR/rediacc-sql-state.json" 2>&1 || echo '{"error": "container not found"}' > "$OUTPUT_DIR/rediacc-sql-state.json"
docker inspect rediacc-web --format='{{json .State}}' > "$OUTPUT_DIR/rediacc-web-state.json" 2>&1 || echo '{"error": "container not found"}' > "$OUTPUT_DIR/rediacc-web-state.json"

# Collect docker ps snapshot
echo "Collecting docker ps snapshot..."
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" > "$OUTPUT_DIR/docker-ps.txt" 2>&1 || echo "Failed to get docker ps" > "$OUTPUT_DIR/docker-ps.txt"

# Collect health check response
echo "Collecting health check response..."
if curl -sf http://localhost/api/health > "$OUTPUT_DIR/health-response.json" 2>&1; then
    echo "Health check: OK"
else
    echo '{"error": "health check failed", "timestamp": "'$(date -Iseconds)'"}' > "$OUTPUT_DIR/health-response.json"
    echo "Health check: FAILED"
fi

# Summary
echo ""
echo "=== Backend Logs Collected ==="
ls -la "$OUTPUT_DIR"
echo ""
echo "Files collected:"
for f in "$OUTPUT_DIR"/*; do
    size=$(wc -c < "$f" 2>/dev/null || echo "0")
    echo "  - $(basename "$f"): ${size} bytes"
done
