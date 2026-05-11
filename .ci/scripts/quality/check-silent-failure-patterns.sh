#!/bin/bash
# Catch shell scripts that pipe commands which can exit non-zero on empty
# input through a pipeline under `set -eo pipefail` without a guard.
#
# Why: `aws s3 ls` returns exit 1 when the prefix has no contents. Combined
# with `set -eo pipefail`, that propagates through any pipe (`| wc -l`,
# `| awk ...`, `| head -1`, `| grep ...`) and aborts the calling script
# silently mid-execution. We hit this three times in one day:
#   - scrub-sentinel.sh dry-run hung on empty cli/v1.0.7/ prefix
#   - assert-r2-sentinel.sh would have aborted before flagging missing bytes
#   - cleanup-versions.sh Phase 8 retention loop could die on a deleted-
#     between-check-and-use race
#
# The lint scans every .sh under .ci/scripts/ and scripts/dev/ that has
# `set -eo pipefail` (or `set -e ... pipefail`) and flags occurrences of
# `aws s3 ls`, `find ...`, `grep ...` piped into `wc -l` / `head` / `tail`
# / `awk` without a `|| true` / `|| echo ...` guard on the same logical
# pipeline.
#
# Exit 0 on no findings, 1 on any unguarded match. The shared helper
# r2_count_objects in .ci/scripts/lib/common.sh is the recommended fix.
#
# Whitelist: add `# silent-failure-ok: <reason>` on the line above the
# risky line if the unguarded pattern is intentional (e.g. an inner step
# that actually wants to fail the script on missing input).
#
# Usage:
#   ./check-silent-failure-patterns.sh
#   ./check-silent-failure-patterns.sh --json   # machine-readable output

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

JSON_OUTPUT=false
for arg in "$@"; do
    case "$arg" in
        --json) JSON_OUTPUT=true ;;
        --help | -h)
            sed -n '2,30p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            log_error "unknown argument: $arg"
            exit 2
            ;;
    esac
done

# Scopes: every shell script under .ci/scripts/ and scripts/dev/.
SCAN_DIRS=(".ci/scripts" "scripts/dev")
PIPE_HEADS_REGEX='(aws s3 ls|aws s3api list-objects-v2 +--query|find [^|]|grep [^|]+ +-r)'
# Sinks: pipeline endings that pipefail would propagate from.
SINK_REGEX='\| *(wc -l|head|tail|awk|jq)'
# A line is guarded if it contains `|| true`, `|| echo`, `|| return`,
# or a trailing `2>/dev/null` immediately after the head (the latter
# doesn't actually rescue exit codes but is the common operator
# habit; we treat it as a soft signal and still flag).
GUARD_REGEX='\|\| *(true|echo|return|exit|continue|:)'

findings=()

while IFS= read -r -d '' file; do
    # Only inspect files that set strict mode.
    if ! grep -qE '^set [+\-]([euo]*pipefail|euo +pipefail|e |eu |eo |euo)' "$file"; then
        continue
    fi

    # awk pass over the file: track whether we're between `set -eo pipefail`
    # and any subsequent `set +e` / `set +o pipefail` (relaxation), and
    # flag risky pipelines while strict mode is in effect.
    awk -v file="$file" \
        -v pipe_head="$PIPE_HEADS_REGEX" \
        -v sink="$SINK_REGEX" \
        -v guard="$GUARD_REGEX" '
        BEGIN { strict = 0; in_block = "" }
        /^set [+\-]e/ {
            if ($0 ~ /[+\-]e[uo]*o? *pipefail/) {
                if ($0 ~ /set -/) strict = 1
                else if ($0 ~ /set \+/) strict = 0
            }
        }
        # silent-failure-ok comment whitelists the next non-blank line.
        /# *silent-failure-ok/ { skip_next = 1; next }
        /^[[:space:]]*$/ || /^[[:space:]]*#/ { next }
        {
            if (skip_next) { skip_next = 0; next }
            if (!strict) next
            # Look for a risky pipeline on this line OR a continuation
            # (line ending with `|`).
            if ($0 ~ pipe_head && $0 ~ sink) {
                if ($0 !~ guard) {
                    printf "%s:%d: %s\n", file, NR, $0
                }
            }
        }
    ' "$file" || true
done < <(find "${SCAN_DIRS[@]/#/$REPO_ROOT/}" -type f -name '*.sh' -print0 2>/dev/null)

# Capture findings from the awk pass (the loop above streamed to stdout;
# re-run once into an array so we can format the final report).
# Use a plain `while read` loop instead of mapfile -- mapfile is bash 4+
# only and breaks macOS / minimal-CI shells. .ci/scripts/security/check-commands.sh
# specifically forbids mapfile across the suite.
findings=()
while IFS= read -r finding_line; do
    [[ -z "$finding_line" ]] && continue
    findings+=("$finding_line")
done < <(
    while IFS= read -r -d '' file; do
        if ! grep -qE '^set [+\-]([euo]*pipefail|euo +pipefail|e |eu |eo |euo)' "$file"; then
            continue
        fi
        awk -v file="$file" \
            -v pipe_head="$PIPE_HEADS_REGEX" \
            -v sink="$SINK_REGEX" \
            -v guard="$GUARD_REGEX" '
            BEGIN { strict = 0; skip_next = 0 }
            /^set [+\-]e/ {
                if ($0 ~ /pipefail/) {
                    if ($0 ~ /set -/) strict = 1
                    else if ($0 ~ /set \+/) strict = 0
                }
            }
            /# *silent-failure-ok/ { skip_next = 1; next }
            /^[[:space:]]*$/ || /^[[:space:]]*#/ { next }
            {
                if (skip_next) { skip_next = 0; next }
                if (!strict) next
                if ($0 ~ pipe_head && $0 ~ sink) {
                    if ($0 !~ guard) {
                        printf "%s:%d: %s\n", file, NR, $0
                    }
                }
            }
        ' "$file"
    done < <(find "${SCAN_DIRS[@]/#/$REPO_ROOT/}" -type f -name '*.sh' -print0 2>/dev/null)
)

if [[ ${#findings[@]} -eq 0 ]]; then
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo '{"findings": [], "ok": true}'
    else
        log_info "No unguarded pipefail-risk pipelines found in .ci/scripts/ or scripts/dev/"
    fi
    exit 0
fi

if [[ "$JSON_OUTPUT" == "true" ]]; then
    printf '{"ok": false, "findings": ['
    sep=""
    for f in "${findings[@]}"; do
        path="${f%%:*}"
        rest="${f#*:}"
        line="${rest%%:*}"
        text="${rest#*:}"
        text_escaped="$(printf '%s' "$text" | sed 's/\\/\\\\/g; s/"/\\"/g')"
        printf '%s{"file": "%s", "line": %s, "text": "%s"}' "$sep" "$path" "$line" "$text_escaped"
        sep=","
    done
    printf ']}\n'
    exit 1
fi

log_error "Found ${#findings[@]} unguarded pipefail-risk pipeline(s):"
for f in "${findings[@]}"; do
    log_error "  $f"
done
log_error ""
log_error "Each line pipes a command that may exit non-zero on empty input"
log_error "through a pipeline. Under \`set -eo pipefail\` the script will"
log_error "abort silently. Either:"
log_error "  - Add \`|| true\` / \`|| echo 0\` to the pipeline."
log_error "  - Use the r2_count_objects helper in .ci/scripts/lib/common.sh."
log_error "  - Add \`# silent-failure-ok: <reason>\` on the line above if"
log_error "    aborting is actually the intended behaviour."
exit 1
