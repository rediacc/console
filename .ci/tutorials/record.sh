#!/bin/bash
# Record a tutorial script as an asciinema .cast file.
#
# Usage: record.sh <tutorial-script> <output.cast> [cols] [rows]
#
# Runs the script inside asciinema rec, then post-processes to inject markers.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

TUTORIAL_SCRIPT="${1:?Usage: record.sh <script> <output.cast> [cols] [rows]}"
OUTPUT_CAST="${2:?Usage: record.sh <script> <output.cast> [cols] [rows]}"
COLS="${3:-100}"
ROWS="${4:-30}"

# Resolve to absolute path
TUTORIAL_SCRIPT="$(cd "$(dirname "$TUTORIAL_SCRIPT")" && pwd)/$(basename "$TUTORIAL_SCRIPT")"

if [[ ! -f "$TUTORIAL_SCRIPT" ]]; then
    echo "Error: tutorial script not found: $TUTORIAL_SCRIPT" >&2
    exit 1
fi

if ! command -v asciinema &>/dev/null; then
    echo "Error: asciinema is not installed. Install with: pip install asciinema" >&2
    exit 1
fi

RAW_CAST="$(mktemp /tmp/tutorial-raw-XXXXXX.cast)"
trap 'rm -f "$RAW_CAST"' EXIT

echo "Recording: $(basename "$TUTORIAL_SCRIPT") → $(basename "$OUTPUT_CAST")"
echo "Terminal: ${COLS}x${ROWS}"

# Cap idle time to keep recordings snappy
export ASCIINEMA_REC_IDLE_TIME_LIMIT=3

asciinema rec \
    --cols "$COLS" \
    --rows "$ROWS" \
    --command "bash '$TUTORIAL_SCRIPT'" \
    --overwrite \
    "$RAW_CAST"

echo "Post-processing markers..."

node "$ROOT_DIR/.ci/scripts/docs/process-cast-markers.mjs" \
    --input "$RAW_CAST" \
    --output "$OUTPUT_CAST"

echo "Done: $OUTPUT_CAST"
