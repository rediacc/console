#!/usr/bin/env bash
# Drive `wl_git.py rebase-resolve` against REAL halted rebases, one per kind.
#
# WHY A REAL HALT AND NOT A STAGE TABLE. wl_git.py's selftest already checks the
# classifier and the union as pure functions over hand-written inputs, and that
# proves their ARITHMETIC. It says nothing about whether the verb reads what git
# actually writes into `.git/rebase-merge` and the index -- and it did not: the
# first wiring passed `conflicted_paths`' `(sha, mode)` tuples to an oracle that
# wanted bare shas, and unpacked a `(target, why)` return as if it were a
# string. Both are invisible to a pure-function test and both died instantly
# here.
#
# The five kinds are the taxonomy measured across two real rebases of branch
# 0826-3 on 2026-08-26/27: ten conflicts, one gitlink, six registry unions, two
# genuine judgement calls. See agent/PLAN-resumable-rebase-executor.md.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# THE SHARED HELPERS, not hand-rolled echoes. The ci-runner treats a gate-test
# that exits 0 without a single `PASS:` line as having asserted NOTHING, and
# refuses it -- which is exactly what happened to the first draft of this file:
# eight cases printed `ok`, every one of them genuinely passing, and the runner
# was right to reject a green it could not recognise.
source "$ROOT/.ci/scripts/test/lib/test-helpers.sh"
# shellcheck source=../lib/git-fixture.sh
source "$ROOT/.ci/scripts/test/lib/git-fixture.sh"

WL="$ROOT/.claude/hooks/stop/wl_git.py"
fails=0
ran=0

# log_fail EXITS, which is right for a gate that stops at its first defect and
# wrong here: eight independent kinds are being driven, and stopping at the
# first would hide the other seven behind one fixture problem. Accumulate, then
# let the summary exit.
soft_fail() { echo "FAIL: $*" >&2; }

drive() { # drive <kind> <must-contain>...
    local kind="$1" dir out rc miss=""
    shift
    if ! dir="$(git_fixture_rebase "$kind")"; then
        soft_fail "${kind}: the fixture did not halt, so it proves nothing"
        fails=$((fails + 1))
        return
    fi
    out="$(cd "$dir" && python3 "$WL" rebase-resolve 2>&1)"
    rc=$?
    local needle
    for needle in "$@"; do
        grep -qF -- "$needle" <<<"$out" || miss="$miss [$needle]"
    done
    ran=$((ran + 1))
    if [[ -z "$miss" ]]; then
        log_pass "${kind} (exit ${rc})"
    else
        soft_fail "${kind} (exit ${rc}) never said:${miss}"
        sed 's/^/        /' <<<"$out" | head -16
        fails=$((fails + 1))
    fi
    git_fixture_cleanup "$dir"
}

log_test "rebase-resolve and rebase-continue, against real halted rebases"

# A registry union it CAN decide, and it must SAY the identity set was verified
# rather than merely exiting 0 -- a union that parses proves nothing.
drive registry "registry union" "identity set verified"

# A genuine design collision stays untouched, and says so in the words that stop
# the next reader reaching for --skip.
drive judgement "judgement" "NOTHING was written"

# Divergent submodule pointers: the oracle REFUSES rather than guessing, and the
# refusal is one path's verdict, not an exception that abandons the report.
drive gitlink "neither contains the other" "NOTHING was written"

# The resolvable gitlink, and the insight the whole oracle rests on: the
# submodule was rebased FIRST, so its HEAD contains both sides and is in NEITHER
# conflict stage. Without this case the only gitlink control proves the refusal
# and never the resolution.
drive gitlink-rebased "gitlink"

# ALL OR NOTHING. A gitlink AND a judgement file in one halt must write nothing,
# even though the gitlink half is perfectly decidable: resolving only that half
# leaves an index that reads as nearly done, and the next --continue then fails
# for a reason that no longer names the submodule.
drive mixed "NOTHING was written"

# --- and the LOOP, with --execute, which is where writing actually happens ----
# Everything above drives the PLAN. These three drive the executor against a
# disposable fixture repo, because "it decided correctly" and "it left the tree
# in the state it claimed" are different questions, and only the second one can
# leave a rebase half-applied.
exec_case() { # exec_case <label> <kind> <expect-finished:yes|no> <needle>
    local label="$1" kind="$2" want_done="$3" needle="$4" dir out before after inprog
    if ! dir="$(git_fixture_rebase "$kind")"; then
        soft_fail "${label}: the fixture did not halt"
        fails=$((fails + 1))
        return
    fi
    before="$(cd "$dir" && git rev-list --count HEAD)"
    out="$(cd "$dir" && python3 "$WL" rebase-continue --execute 2>&1)"
    inprog="no"
    [ -d "$dir/.git/rebase-merge" ] && inprog="yes"
    after="$(cd "$dir" && git rev-list --count HEAD)"
    local bad=""
    [ "$inprog" = "$([ "$want_done" = yes ] && echo no || echo yes)" ] ||
        bad="$bad [mid-rebase=$inprog, wanted finished=$want_done]"
    grep -qF -- "$needle" <<<"$out" || bad="$bad [never said: $needle]"
    # NO COMMIT MAY VANISH. `git rebase --skip` is the one thing this verb must
    # never do, and a dropped commit is exactly how it would show up.
    [ "$after" -ge "$before" ] || bad="$bad [commits went $before -> $after]"
    if [[ -z "$bad" ]]; then
        log_pass "${label}"
    else
        soft_fail "${label}:${bad}"
        sed 's/^/        /' <<<"$out" | head -12
        fails=$((fails + 1))
    fi
    ran=$((ran + 1))
    git_fixture_cleanup "$dir"
}

exec_case "execute: a decidable halt COMPLETES the rebase" registry yes "rebase finished"
exec_case "execute: a judgement halt STOPS, mid-rebase, untouched" judgement no "STOPPED, nothing written"

# THE DRY RUN MUST NOT WRITE. Without this, every green above is compatible with
# a verb that ignores --execute and always writes.
if dir="$(git_fixture_rebase registry)"; then
    b="$(md5sum "$dir/reg.json" | cut -d' ' -f1)"
    out="$(cd "$dir" && python3 "$WL" rebase-continue 2>&1)"
    a="$(md5sum "$dir/reg.json" | cut -d' ' -f1)"
    ran=$((ran + 1))
    if [[ "$b" == "$a" && -d "$dir/.git/rebase-merge" ]] && grep -qF "DRY RUN" <<<"$out"; then
        log_pass "no --execute: nothing written, rebase untouched"
    else
        soft_fail "a dry run wrote, advanced the rebase, or did not say so"
        fails=$((fails + 1))
    fi
    git_fixture_cleanup "$dir"
fi

# ANTI-VACUITY. Every assertion above lives inside a helper, so a fixture harness
# that silently produced nothing would print no failures and exit 0.
if ((ran < 8)); then
    soft_fail "only ${ran} of 8 case(s) ran; a green over missing cases is not a green"
    fails=$((fails + 1))
fi

echo
if ((fails == 0)); then
    log_pass "5 conflict kinds decided, and the loop executed, against real halts"
    echo "  Blind spot, stated so the green is not read as more than it is: the"
    echo "  fixtures are single-halt, so a MULTI-halt rebase -- the loop actually"
    echo "  looping -- is not covered here."
    exit 0
fi
soft_fail "${fails} kind(s) misbehaved"
exit 1
