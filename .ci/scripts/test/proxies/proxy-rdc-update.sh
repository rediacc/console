#!/bin/bash
# Local proxy for the CI job that drives `rdc update` end to end.
#
# CI runs `.ci/scripts/test/test-rdc-update.sh all` in the update-flow job of
# .github/workflows/ct-update-flow.yml, against a REAL SEA binary produced by
# build-cli-linux-x64. That workflow is outside the parity surface, so nothing
# in `npm run ci` has ever touched the updater.
#
# THE REDUCTION, AND ITS COST, STATED IN THE OUTPUT EVERY RUN.
# Two of the seven scenarios -- `happy` and `rollback` -- require a genuinely
# packaged binary: the CLI refuses with "Cannot update: not running as a
# packaged binary. Build with SEA first." and "Rollback is only available for
# SEA binary installations." A developer checkout has packages/cli/dist/
# cli-bundle.cjs, which is a plain node bundle, so those two cannot run against
# it. The other five exercise the whole fixture-server path for real.
#
# So this proxy does the thing the house rule asks for instead of quietly
# dropping them: it EXEMPTS the two by name, PRINTS them on every single run,
# and runs all seven the moment a real binary is available. Set RDC_BINARY (or
# build one with `cd packages/cli && npm run build:cli`) and the exemption
# disappears by itself.
#
#   RDC_BINARY set          -> all 7 scenarios, no exemption
#   RDC_BINARY unset        -> 5 scenarios against the node bundle, 2 named
#   neither binary present  -> exit 77, cannot-run
#
# A REDUCED RUN IS STILL A REAL RUN. Each of the five boots the Python fixture
# server, serves a controlled manifest/latest/binary/.sha256 tree, and isolates
# HOME to a throwaway tmpdir, exactly as CI does.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

SUBJECT="$ROOT_DIR/.ci/scripts/test/test-rdc-update.sh"
FALLBACK_BINARY="$ROOT_DIR/packages/cli/dist/cli-bundle.cjs"

# Scenarios that need no SEA packaging. Kept as a list rather than a count so a
# name added to the subject and forgotten here is visible in the diff.
SEA_FREE=(check-only sha256-mismatch rollback-empty channel-switch reinstall)
# BLOCKER: these two invoke the SEA-only update and rollback paths, which a node
# bundle cannot reach at all. Exempt by name, reported every run, and skipped
# only while RDC_BINARY is unset.
SEA_ONLY=(happy rollback)

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

proxy_init rdc-update ".ci/scripts/test/test-rdc-update.sh"

REDUCED=0
if [[ -z "${RDC_BINARY:-}" ]]; then
    REDUCED=1
    RDC_BINARY="$FALLBACK_BINARY"
    export RDC_BINARY
fi

proxy_need_exec "$SUBJECT" "the subject script is missing from this checkout"
proxy_need_exec "$RDC_BINARY" "cd packages/cli && npm run build:cli, or export RDC_BINARY=/path/to/rdc"
proxy_need_cmd python3 "sudo apt-get install -y python3 (the subject's update fixture server)"
proxy_need_cmd node "./run.sh setup"
proxy_need_file "$ROOT_DIR/packages/www/public/install.sh" "the installer the subject drives is missing from this checkout"
proxy_preflight

# THE SUBJECT'S OWN SCENARIO SET, read from its dispatch rather than retyped.
# If a scenario is added there and not here, this reds instead of silently
# running a smaller suite than the name of the file promises.
DECLARED=$(grep -oE '^        [a-z0-9-]+\) scenario_' "$SUBJECT" | sed 's/) scenario_//; s/^ *//' | sort)
DECLARED_N=$(printf '%s\n' "$DECLARED" | grep -c . || true)
KNOWN=$(printf '%s\n' "${SEA_FREE[@]}" "${SEA_ONLY[@]}" | sort)
if [[ "$DECLARED_N" -eq 0 ]]; then
    echo "${PROXY_RED}proxy rdc-update: read ZERO scenarios out of the subject's dispatch${PROXY_OFF}" >&2
    echo "  The partition below would then be vacuous. Check the grep in this file" >&2
    echo "  against the dispatch block at the end of $SUBJECT." >&2
    exit 1
fi
if [[ "$DECLARED" == "$KNOWN" ]]; then
    proxy_pass "this proxy's partition covers all $DECLARED_N scenarios the subject declares"
else
    proxy_fail "scenario drift: the subject declares [$(echo "$DECLARED" | tr '\n' ' ')] but this proxy partitions [$(echo "$KNOWN" | tr '\n' ' ')]"
fi

if [[ $REDUCED -eq 1 ]]; then
    RUN=("${SEA_FREE[@]}")
    echo "${PROXY_YEL}proxy rdc-update: REDUCED RUN. RDC_BINARY is unset, so the fallback is${PROXY_OFF}"
    echo "${PROXY_YEL}  $FALLBACK_BINARY (a node bundle, not a packaged SEA binary).${PROXY_OFF}"
    echo "${PROXY_YEL}  NOT EXERCISED HERE: ${SEA_ONLY[*]} -- both need SEA packaging.${PROXY_OFF}"
    echo "${PROXY_YEL}  CI runs all ${DECLARED_N} against a real binary; to do the same locally run${PROXY_OFF}"
    echo "${PROXY_YEL}  'cd packages/cli && npm run build:cli' and re-run with RDC_BINARY set.${PROXY_OFF}"
else
    RUN=("${SEA_FREE[@]}" "${SEA_ONLY[@]}")
    echo "proxy rdc-update: FULL RUN against RDC_BINARY=$RDC_BINARY (${#RUN[@]} scenarios)"
fi

OUT="$(mktemp)"
ERR="$(mktemp)"
trap 'rm -f "$OUT" "$ERR"' EXIT

"$SUBJECT" "${RUN[@]}" >"$OUT" 2>"$ERR"
RC=$?

if [[ $RC -eq 0 ]]; then
    proxy_pass "${#RUN[@]} scenario(s) passed: ${RUN[*]}"
else
    proxy_fail "the subject exited $RC over ${RUN[*]}"
    echo "  --- subject stdout ---" >&2
    cat "$OUT" >&2
    echo "  --- subject stderr ---" >&2
    cat "$ERR" >&2
fi

# One PASS: line per scenario is the subject's contract. Fewer means a scenario
# returned without asserting, which exits 0 and looks identical to success.
PASS_LINES=$(grep -c 'PASS:' "$OUT" || true)
if [[ "$PASS_LINES" -eq "${#RUN[@]}" ]]; then
    proxy_pass "the subject emitted one PASS: line per scenario ($PASS_LINES of ${#RUN[@]})"
else
    proxy_fail "the subject emitted $PASS_LINES PASS: line(s) for ${#RUN[@]} scenario(s); at least one asserted nothing"
fi

proxy_finish
