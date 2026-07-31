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
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
# get_repo_root, NOT a hand-counted ../..: the old form resolved to .ci from
# this script's directory, so the find below scanned .ci/.ci/scripts and
# .ci/scripts/dev -- neither exists -- and the gate checked ZERO files from
# the day it was written. Second of the two independent bugs (with the awk
# guard escapes) that each alone kept this gate permanently green.
REPO_ROOT="$(get_repo_root)"

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
PIPE_HEADS_REGEX='(aws s3 ls|aws s3api list-objects-v2 +--query|find [^|]|grep [^|]+)'
# Class 2: a redaction filter as the pipeline SINK. `cmd 2>&1 | grep -v X`
# under pipefail dies with ZERO error text when grep filters every line --
# including on SUCCESS, when the head's whole output happens to be the
# redacted lines (live: clone-d1.sh's D1 export, run 30628110972: a
# 21-second gap, then cleanup, nothing else). The head's own failure text is
# also lost when its output never flushes. Capture to a file, redact after,
# and test the head's own exit code instead.
REDACT_SINK_REGEX='2>&1 *[|] *grep -v'
# Sinks: pipeline endings that pipefail would propagate from.
SINK_REGEX='[|] *(wc -l|head|tail|awk|jq)'
# CHARACTER CLASSES, NEVER BACKSLASH ESCAPES, in every regex handed to awk
# via -v: awk rewrites \| in a -v value to a plain |, which turns the old
# '\|\| *(...)' guard into an ERE with EMPTY alternations that matches
# every line. That made the unguarded test false everywhere, so this gate
# had never fired on anything since it was written (proven 2026-07-31 by a
# planted defect it could not see; the escape warnings were swallowed by
# the 2>/dev/null on the awk call).
# A line is guarded if it contains `|| true`, `|| echo`, `|| return`,
# or a trailing `2>/dev/null` immediately after the head (the latter
# doesn't actually rescue exit codes but is the common operator
# habit; we treat it as a soft signal and still flag).
GUARD_REGEX='[|][|] *(true|echo|return|exit|continue|:)'

# Single-pass scan: walk every shell script under SCAN_DIRS, awk-extract any
# risky pipelines, capture them into the `findings` array AND mirror to
# stdout if we're in human (non-JSON) mode. Plain `while read` instead of
# `mapfile` to stay bash 3.2-compatible (check-commands.sh forbids mapfile).
findings=()
while IFS= read -r -d '' file; do
    # Only inspect files that set strict mode.
    if ! grep -qE '^set [+\-]([euo]*pipefail|euo +pipefail|e |eu |eo |euo)' "$file"; then
        continue
    fi
    while IFS= read -r finding; do
        [[ -z "$finding" ]] && continue
        findings+=("$finding")
    done < <(awk -v file="$file" \
        -v pipe_head="$PIPE_HEADS_REGEX" \
        -v sink="$SINK_REGEX" \
        -v guard="$GUARD_REGEX" \
        -v redact_sink="$REDACT_SINK_REGEX" '
        BEGIN { strict = 0; skip_next = 0 }
        /^set [+\-]e/ {
            if ($0 ~ /pipefail/) {
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
            # Condition heads are exempt from BOTH classes: an if/while
            # pipeline is consumed as a test, so pipefail cannot abort the
            # script there.
            if ($0 ~ pipe_head && $0 ~ sink) {
                if ($0 !~ guard &&
                    $0 !~ /^[[:space:]]*(if|elif|while|until) /) {
                    printf "%s:%d: %s\n", file, NR, $0
                }
            }
            # Class 2 (see REDACT_SINK_REGEX above). Condition heads are
            # exempt: an if/while pipeline is consumed as a test, so
            # pipefail cannot abort the script there.
            if ($0 ~ redact_sink && $0 !~ guard &&
                $0 !~ /^[[:space:]]*(if|elif|while|until) /) {
                printf "%s:%d: %s (redaction-filter sink: capture to a file, redact after, test the head'"'"'s own rc)\n", file, NR, $0
            }
        }
    ' "$file" 2>/dev/null || true)
done < <(find "${SCAN_DIRS[@]/#/$REPO_ROOT/}" -type f -name '*.sh' -print0 2>/dev/null)

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
