#!/usr/bin/env bash
# Every vacuity floor must actually REFUSE an empty corpus.
#
# WHY THIS EXISTS, and why it is not a check-*.ts. check:ci-enumeration-vacuity proves a
# guard is PRESENT -- a `MIN_*`, the word VACUOUS, an explicit refusal -- and says so in
# its own blind-spot line. Presence is a source shape. Whether the floor fires is
# BEHAVIOUR, and the testing skill is explicit that a behavioural defect given a
# check-*.ts gets "a gate that asserts the source still looks right, which is not the
# same claim".
#
# A static version was written on 2026-09-04 and discarded: it was wrong on all six
# names it flagged (names inside string literals and comments, an env var compared by a
# different script, and one floor wired indirectly as `needed = observed * MIN_HEADROOM`).
# No name-matcher can see that last one. Running the thing can.
#
# WHAT IT DOES NOT COVER, stated so a green is not read as more than it is: only the
# floors whose corpus is addressable from outside -- an env override or a function
# parameter. The seven whose corpus is fixed relative to __dirname
# (generate-translation-hashes, i18n-coverage-report, sync-translations,
# i18n-backfill-commits) or which need a built tree or AWS (build-pkg-repo,
# promote-r2-to-stable{,-hotfix}, upload-repos-to-r2) are confirmed by reading only.
# Widening this means making their corpus injectable, which is a change to them.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Each case: an impossible floor must REFUSE, and the real corpus must PASS.
# Both halves matter -- a floor that always fires is as useless as one that never does.
# ---------------------------------------------------------------------------

check_floor() { # check_floor <name> <env-assignment> <command...>
    local name="$1" assign="$2"
    shift 2
    local out rc=0
    out="$(env "$assign" "$@" 2>&1)" || rc=$?
    if [[ "$rc" -eq 0 ]]; then
        log_fail "$name: an impossible floor was ACCEPTED (exit 0); the floor refuses nothing"
        return 1
    fi
    if ! grep -qi 'vacuous' <<<"$out"; then
        log_fail "$name: refused (exit $rc) but never said VACUOUS: ${out:0:120}"
        return 1
    fi
    log_pass "$name refuses an impossible floor, and says VACUOUS"
}

check_passes() { # check_passes <name> <command...>
    local name="$1"
    shift
    if ! "$@" >/dev/null 2>&1; then
        log_fail "$name: the REAL corpus was refused; the floor is above the true count"
        return 1
    fi
    log_pass "CONTROL: $name accepts the real corpus"
}

# 1. shfmt.sh -- SHFMT_MIN_FILES over the four shell scopes.
check_floor "shfmt" "SHFMT_MIN_FILES=999999" bash .ci/scripts/security/shfmt.sh

# 2/3. Two Python floors, driven through their own module so the CLI's usage
#      path (which exits before the walk) does not stand in for the walk.
py_floor() { # py_floor <label> <file> <env> <value> <func>
    python3 - "$2" "$3" "$4" "$5" <<'PY'
import importlib.util, os, sys
path, var, val, func = sys.argv[1:5]
os.environ[var] = val
spec = importlib.util.spec_from_file_location("m", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
getattr(m, func)()
PY
}
if out="$(py_floor x .ci/scripts/housekeeping/retire-shadowed-secrets.py RETIRE_MIN_WORKFLOWS 999999 files 2>&1)"; then
    log_fail "retire-shadowed-secrets: an impossible MIN_WORKFLOWS was accepted"
elif grep -qi 'vacuous' <<<"$out"; then
    log_pass "retire-shadowed-secrets refuses an impossible floor, and says VACUOUS"
else
    log_fail "retire-shadowed-secrets: refused but never said VACUOUS: ${out:0:120}"
fi
if out="$(py_floor x scripts/dev/secret-rename.py SECRET_RENAME_MIN_FILES 999999 files 2>&1)"; then
    log_fail "secret-rename: an impossible MIN_FILES was accepted"
elif grep -qi 'vacuous' <<<"$out"; then
    log_pass "secret-rename refuses an impossible floor, and says VACUOUS"
else
    log_fail "secret-rename: refused but never said VACUOUS: ${out:0:120}"
fi

# 4. action-refs.ts -- corpus is a PARAMETER, so the empty case is a real empty tree
#    rather than an impossible threshold. That is the stronger form of this test.
AR_TMP="$(mktemp -d)"
trap 'rm -rf "$AR_TMP"' EXIT
mkdir -p "$AR_TMP/.github/workflows"
if out="$(npx tsx -e "
import { collectActionRefs } from './scripts/lib/action-refs.ts';
collectActionRefs('$AR_TMP');
" 2>&1)"; then
    log_fail "action-refs: an EMPTY .github/workflows was accepted"
elif grep -qi 'vacuous' <<<"$out"; then
    log_pass "action-refs refuses an empty .github tree, and says VACUOUS"
else
    log_fail "action-refs: refused but never said VACUOUS: ${out:0:160}"
fi

# The other half: every one of them must still accept the real tree.
check_passes "shfmt" bash .ci/scripts/security/shfmt.sh
check_passes "action-refs" npx tsx -e "import { collectActionRefs } from './scripts/lib/action-refs.ts'; collectActionRefs('$REPO_ROOT');"

log_pass "all tests passed"
