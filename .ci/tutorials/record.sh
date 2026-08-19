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
# The recorded terminal geometry. This default is the SAME value run.sh passes,
# deliberately: they disagreed for a long time (100x30 here vs 107x32 there), so a
# manual `record.sh foo.sh foo.cast` silently produced a cast of the wrong width
# that nothing detected. Change both together, or better, change only here.
COLS="${3:-${TUTORIAL_COLS:-107}}"
ROWS="${4:-${TUTORIAL_ROWS:-32}}"
# Tutorial scripts size their own output to this (see tutorial-helpers.sh
# _format_display_cmd), so it has to reach them.
export TUTORIAL_COLS="$COLS"
export TUTORIAL_ROWS="$ROWS"

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
        # PRESERVE the recording. Deleting it here destroyed the only artifact that
        # explains the failure: the tutorial silences its own setup with
        # exec >/dev/null, so the cast is the sole record of what the CLI printed.
        FAILED_CAST="/tmp/tutorial-failed-$(basename "$TUTORIAL_SCRIPT" .sh).cast"
        cp -f "$RAW_CAST" "$FAILED_CAST" 2>/dev/null &&
            echo "Recording kept for diagnosis: $FAILED_CAST" >&2
        # Replay the tail on stderr so the reason reaches the caller's log without
        # anyone having to fetch a file off the recording host.
        echo "--- last terminal output before the failure ---" >&2
        node -e '
            const fs = require("fs");
            const lines = fs.readFileSync(process.argv[1], "utf8").split("\n");
            let out = "";
            for (const line of lines) {
                if (!line.startsWith("[")) continue;
                let ev;
                try { ev = JSON.parse(line); } catch { continue; }
                if (Array.isArray(ev) && ev[1] === "o") out += ev[2];
            }
            const rows = out.split(/\r?\n/).filter((r) => r.trim() !== "");
            process.stderr.write(rows.slice(-40).join("\n") + "\n");
        ' "$RAW_CAST" >&2 || echo "(could not replay the cast)" >&2
        echo "--- end of recorded output ---" >&2
        # A tutorial that dies in PRE-RECORDING setup produces an EMPTY replay
        # above, because setup runs before output is restored to the camera.
        # That is not "no information available" - the setup log has it.
        SETUP_LOG="/tmp/tutorial-setup-$(basename "$TUTORIAL_SCRIPT" .sh).log"
        if [[ -s "$SETUP_LOG" ]]; then
            echo "--- last 40 lines of PRE-RECORDING setup ($SETUP_LOG) ---" >&2
            tail -40 "$SETUP_LOG" >&2
            echo "--- end of setup log ---" >&2
        else
            echo "(no setup log at $SETUP_LOG; an older tutorial script may still discard setup output)" >&2
        fi
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
