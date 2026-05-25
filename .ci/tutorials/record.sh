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
MARKED_CAST="$(mktemp /tmp/tutorial-marked-XXXXXX.cast)"
EXIT_CODE_FILE="/tmp/tutorial-exit-code-$$"
trap 'rm -f "$RAW_CAST" "$MARKED_CAST" "$EXIT_CODE_FILE"' EXIT

echo "Recording: $(basename "$TUTORIAL_SCRIPT") → $(basename "$OUTPUT_CAST")"
echo "Terminal: ${COLS}x${ROWS}"

# Cap idle time to keep recordings snappy
export ASCIINEMA_REC_IDLE_TIME_LIMIT=3

# Force rdc to render human-readable table output regardless of the parent
# shell's agent-detection state (e.g. CLAUDECODE=1). Each tutorial script
# also sets this via tutorial-helpers.sh; this is belt-and-suspenders so a
# script that forgets to source the helpers still records cleanly.
export REDIACC_DEFAULT_OUTPUT=table

# Wrap the tutorial script to capture its exit code independently.
# asciinema v2 exits 0 even when --command fails (it saves the recording regardless).
asciinema rec \
    --cols "$COLS" \
    --rows "$ROWS" \
    --command "bash '$TUTORIAL_SCRIPT'; echo \$? > '$EXIT_CODE_FILE'" \
    --overwrite \
    "$RAW_CAST"

if [[ -f "$EXIT_CODE_FILE" ]]; then
    SCRIPT_EXIT=$(cat "$EXIT_CODE_FILE")
    if [[ "$SCRIPT_EXIT" != "0" ]]; then
        echo "Error: tutorial script exited with code $SCRIPT_EXIT" >&2
        echo "Script: $TUTORIAL_SCRIPT" >&2
        rm -f "$RAW_CAST"
        exit 1
    fi
else
    echo "Warning: could not determine script exit code" >&2
fi

echo "Post-processing markers..."

node "$ROOT_DIR/.ci/scripts/docs/process-cast-markers.mjs" \
    --input "$RAW_CAST" \
    --output "$MARKED_CAST"

echo "Compressing idle gaps (max=${MAX_IDLE_MS:-800}ms)..."
node "$ROOT_DIR/.ci/scripts/docs/compress-cast-idle.mjs" \
    --input "$MARKED_CAST" \
    --output "$OUTPUT_CAST" \
    --max-idle-ms "${MAX_IDLE_MS:-800}"

echo "Done: $OUTPUT_CAST"
