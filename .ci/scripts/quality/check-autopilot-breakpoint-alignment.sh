#!/bin/bash
# The autopilot's hold-open debug session COPIES three dispatch inputs from
# breakpoint. This gate holds the copies to the original.
#
# WHY A GATE AND NOT A COMMENT. .github/workflows/autopilot.yml's model job
# can hold its runner open with a tmate shell behind a Cloudflare tunnel,
# driven by the vendored scripts in .ci/breakpoint/scripts/. The inputs that
# drive it (`hold-duration`, `debug-shell`, `send-email`) are hand-copied from
# .ci/breakpoint/workflow/breakpoint.yml, because breakpoint.yml is FROZEN in
# MANIFEST.sha256 and cannot grow an autopilot-shaped variant, and GitHub has
# no include mechanism for workflow inputs. Hand-copied shapes drift silently,
# and the drift is worst exactly where it matters: `send-email` defaulting to
# false in one file and true in the other would mean one of the two tools
# prints a bearer-credential URL into a world-readable log while the operator
# believes both behave the same way.
#
# breakpoint.yml is the CANONICAL side. autopilot.yml follows it, never the
# reverse: this gate never asks anyone to edit the frozen file.
#
# WHAT IS COMPARED
#   breakpoint `duration`      options == autopilot `hold-duration` options
#   breakpoint `debug-shell`   type + default == autopilot `debug-shell`
#   breakpoint `send-email`    type + default == autopilot `send-email`
# Descriptions are deliberately NOT compared: breakpoint's `duration` text
# talks about named-mode Access logins, which the autopilot (quick tunnel
# only) does not have, and forcing prose equality would make the gate wrong.
#
# ANTI-VACUITY. Every extraction that comes back empty is a FAILURE, not a
# pass: a missing file, a missing input block, a missing field, or an options
# list that parses to nothing all exit 1. A gate that silently compares "" to
# "" is the failure mode this repo has already shipped once.
#
# Env seams (for the gate's own test; both default to the real files):
#   AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE
#   AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE
#
# Usage: check-autopilot-breakpoint-alignment.sh
# Exit:  0 aligned, 1 drift or nothing-to-check.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

BP_FILE="${AUTOPILOT_BP_ALIGN_BREAKPOINT_FILE:-.ci/breakpoint/workflow/breakpoint.yml}"
AP_FILE="${AUTOPILOT_BP_ALIGN_AUTOPILOT_FILE:-.github/workflows/autopilot.yml}"

for f in "$BP_FILE" "$AP_FILE"; do
    if [ ! -f "$f" ]; then
        log_error "file not found: $f (nothing to compare cannot pass)"
        exit 1
    fi
done

# input_field <file> <input-name> <field>
# Reads one field out of one workflow_dispatch input block. Both files declare
# inputs at the same depth (`on:` -> `workflow_dispatch:` -> `inputs:` -> the
# input at 6 spaces, its fields at 8), so one extractor serves both. Scanning
# is scoped to the inputs block: a 6-space bare key elsewhere in the file
# (there are several) must never be mistaken for an input.
#
# Values are read as written, then normalized by the caller. An inline flow
# list (`['5', '10']`) is the shape both files use; a block list would return
# empty here and be caught by the anti-vacuity check rather than silently
# comparing nothing.
input_field() {
    awk -v want="$2" -v field="$3" '
        /^  workflow_dispatch:[[:space:]]*$/ { wd = 1; next }
        wd && /^    inputs:[[:space:]]*$/ { in_inputs = 1; next }
        in_inputs {
            if ($0 ~ /^[[:space:]]*$/) next
            match($0, /^ */); ind = RLENGTH
            body = substr($0, ind + 1)
            if (substr(body, 1, 1) == "#") next
            if (ind < 6) { exit }
            if (ind == 6 && body ~ /^[A-Za-z0-9_-]+:[[:space:]]*$/) {
                name = body; sub(/:.*/, "", name)
                cur = (name == want)
                next
            }
            if (cur && ind == 8 && index(body, field ": ") == 1) {
                print substr(body, length(field) + 3)
                exit
            }
        }
    ' "$1"
}

# normalize_options: strip brackets, quotes and whitespace so the comparison
# is over the VALUES, not over the YAML author's spacing.
normalize_options() {
    tr -d "[]'\" " | sed 's/,$//'
}

FAILED=0
fail() {
    log_error "AUTOPILOT/BREAKPOINT DRIFT: $1"
    FAILED=1
}

# require_value <label> <value> - an empty extraction means the parser lost
# its target, which is a broken gate, not an aligned pair.
require_value() {
    if [ -z "$2" ]; then
        log_error "could not extract $1 (the input block, the field, or the file layout moved; this gate refuses to pass blind)"
        exit 1
    fi
}

# --- 1. duration option lists must be identical --------------------------
BP_DURATION="$(input_field "$BP_FILE" duration options | normalize_options)"
AP_DURATION="$(input_field "$AP_FILE" hold-duration options | normalize_options)"
require_value "breakpoint duration options ($BP_FILE)" "$BP_DURATION"
require_value "autopilot hold-duration options ($AP_FILE)" "$AP_DURATION"

# A one- or two-entry list means the extractor matched something that is not
# the option list at all; the real one has always carried the full ladder.
if [ "$(printf '%s' "$BP_DURATION" | tr ',' '\n' | grep -c .)" -lt 5 ]; then
    log_error "breakpoint duration parsed to fewer than 5 options ('$BP_DURATION'); the extractor is broken"
    exit 1
fi

if [ "$BP_DURATION" != "$AP_DURATION" ]; then
    fail "hold-duration options differ from breakpoint's duration options
  breakpoint ($BP_FILE): $BP_DURATION
  autopilot  ($AP_FILE): $AP_DURATION
  Fix: copy breakpoint's list verbatim. breakpoint.yml is frozen in MANIFEST.sha256 and is the canonical side."
fi

# --- 2. the two booleans must share type AND default ---------------------
for input in debug-shell send-email; do
    for field in type default; do
        bp_value="$(input_field "$BP_FILE" "$input" "$field")"
        ap_value="$(input_field "$AP_FILE" "$input" "$field")"
        require_value "breakpoint $input.$field ($BP_FILE)" "$bp_value"
        require_value "autopilot $input.$field ($AP_FILE)" "$ap_value"
        if [ "$bp_value" != "$ap_value" ]; then
            fail "$input.$field differs: breakpoint '$bp_value' vs autopilot '$ap_value'
  Fix: match breakpoint. send-email in particular defaults to true because on a public repo the session URL is a bearer credential."
        fi
    done
done

if [ "$FAILED" -ne 0 ]; then
    log_error "the autopilot's copied debug inputs have drifted from breakpoint's originals"
    exit 1
fi

log_info "autopilot debug inputs match breakpoint: duration options ($BP_DURATION), debug-shell and send-email type+default"
