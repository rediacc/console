#!/usr/bin/env bash
# Gate: there is ONE way to read CI, and every surface points at it.
#
# Why this exists. On 2026-08-25, landing console#574, the hand-rolled CI-watch
# recipe was found in NINE places and had rotted in most of them. Two were worse
# than stale: block-long-sleep.sh explained that "attempt 2 lands on the SAME
# Console CI run" while printing a loop that could not survive it, and
# cancel-old-ci.sh recommended the very tool this repo rejects 4/4. Three of the
# nine were invisible to a manual sweep because they lived in hook SCRIPTS while
# the sweep grepped *.md.
#
# The fix was to stop distributing a recipe at all: .ci/scripts/ci/ci-trace.py is
# the only sanctioned reader, ad-hoc forms are refused by
# block-adhoc-sanctioned.sh, and a hand-rolled watch left running blocks the Stop
# hook. This gate keeps that true.
#
#   A. The skill hands out the SCRIPT, not a loop.
#   B. Every surface that instructs watching names the script.
#   C. No doc or hook hands out a hand-rolled loop or a banned invocation.
#   D. The sanctioned registry is self-consistent and its tools exist.
#   E. The script's own --help works.
#   F. The skill teaches --run for a DISPATCHED run, not --ref.
#
# (A former Check G here, "every CLI flag is taught in the skill," moved to
# check-cli-doc-coverage.sh 2026-08-27 and generalized to a second pair
# beyond ci-trace.py/SKILL.md -- see that file, not duplicated here.)
#
# Controls are built by CONSTRUCTION (fixtures written literally), never by
# pattern-substituting real source, so rewording a target cannot silently void
# them -- the failure check-control-vacuity.sh exists to catch.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SKILL="$ROOT/.claude/skills/ci-watch/SKILL.md"
EVIDENCE_FILE=".claude/skills/ci-watch/incidents.md"
TRACE_REL=".ci/scripts/ci/ci-trace.py"
TRACE="$ROOT/$TRACE_REL"
REGISTRY="$ROOT/.claude/hooks/lib/sanctioned.py"

RED=''
GREEN=''
NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    NC=$'\033[0m'
fi

fails=0
fail() {
    echo "${RED}✗${NC} $*" >&2
    fails=$((fails + 1))
}
pass() { echo "${GREEN}ok${NC}   $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

bash_block() {
    awk '/^```bash$/ { inblk=1; next } /^```$/ { if (inblk) exit } inblk { print }' "$1"
}

# Lines that are DATA or ASSERTIONS, not advice. Both were real false positives:
# a worklist test carries a background task's command as a JSON value, and the
# hook suite asserts `check 2 ...` on the banned shape precisely BECAUSE it is
# banned. Flagging either would push someone to weaken the test to satisfy the
# gate, which is backwards.
advice_only() {
    grep -vE '"(command|cmd)"[[:space:]]*:|^[[:space:]]*check [0-9]+ ' "$1"
}

hands_out_loop() {
    local f="$1"
    advice_only "$f" | grep -qE '\.status' || return 1
    advice_only "$f" | grep -E '\.status' | grep -qE '"completed"' || return 1
    grep -q 'run_attempt' "$f" && return 1
    return 0
}

hands_out_banned() {
    advice_only "$1" | grep -qE 'gh run watch[^|;&]*--(exit-status|interval)'
}

# ---- A. the skill hands out the script --------------------------------------
assert_skill() {
    local skill="$1" blk
    blk="$(bash_block "$skill")"
    if [ -z "$blk" ]; then
        echo "no bash block found"
        return 1
    fi
    if ! printf '%s' "$blk" | grep -q 'ci-trace'; then
        echo "the canonical block does not invoke $TRACE_REL"
        return 1
    fi
    if printf '%s' "$blk" | grep -qE '(until|while)[^\n]*gh '; then
        echo "the canonical block still contains a hand-rolled loop"
        return 1
    fi
    return 0
}

if out="$(assert_skill "$SKILL")"; then
    pass "A. the skill hands out $TRACE_REL, not a loop"
else
    fail "A. $out"
fi

cat >"$TMP/loop-skill.md" <<'FIXTURE'
# fixture
```bash
R=1
until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do :; done
```
FIXTURE
if assert_skill "$TMP/loop-skill.md" >/dev/null; then
    fail "A CONTROL DID NOT FIRE: a skill handing out a loop passed, so A proves nothing"
else
    pass "A control: a skill handing out a loop is rejected"
fi

# ---- B. every watching surface names the script ------------------------------
scan_files() {
    git -C "$ROOT" ls-files \
        '.claude/**/*.md' '.claude/**/*.sh' 'docs/agent-reference/*.md' 2>/dev/null |
        grep -v "^${EVIDENCE_FILE}$"
}

instructs_watching() {
    grep -qiE 'terminal-state watch|arm a watch|watch the console ci' "$1"
}

silent=()
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    [ -f "$ROOT/$rel" ] || continue
    instructs_watching "$ROOT/$rel" || continue
    grep -q 'ci-trace' "$ROOT/$rel" || silent+=("$rel")
done < <(scan_files)

if [ ${#silent[@]} -eq 0 ]; then
    pass "B. every surface that instructs watching names $TRACE_REL"
else
    fail "B. instruct watching but never name the script: ${silent[*]}"
fi

printf 'Arm a watch on that run and wait for it.\n' >"$TMP/mute.md"
if instructs_watching "$TMP/mute.md" && ! grep -q 'ci-trace' "$TMP/mute.md"; then
    pass "B control: a watching surface with no script mention is detectable"
else
    fail "B CONTROL DID NOT FIRE: the detector missed a fixture that instructs watching"
fi

# ---- C. nobody hands out a loop or a banned invocation -----------------------
offenders=()
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    [ -f "$ROOT/$rel" ] || continue
    hands_out_loop "$ROOT/$rel" && offenders+=("$rel (hand-rolled loop)")
    hands_out_banned "$ROOT/$rel" && offenders+=("$rel (banned invocation)")
done < <(scan_files)

scanned="$(scan_files | wc -l | tr -d ' ')"
if [ "$scanned" -eq 0 ]; then
    fail "C. scanned ZERO files -- the glob matched nothing, so this assertion is vacuous"
elif [ ${#offenders[@]} -eq 0 ]; then
    pass "C. no hand-rolled watch in $scanned scanned file(s)"
else
    fail "C. these hand out a broken wake-up: ${offenders[*]}"
fi

cat >"$TMP/bad.md" <<'FIXTURE'
Poll it with:
`R=1; until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do :; done`
FIXTURE
if hands_out_loop "$TMP/bad.md"; then
    pass "C control: a hand-rolled loop is detected"
else
    fail "C CONTROL DID NOT FIRE: a hand-rolled loop went undetected"
fi

cat >"$TMP/good.md" <<'FIXTURE'
Trace it with `.ci/scripts/ci/ci-trace.py --wait`.
FIXTURE
if hands_out_loop "$TMP/good.md" || hands_out_banned "$TMP/good.md"; then
    fail "C IS OVER-BROAD: the sanctioned invocation was flagged"
else
    pass "C control: the sanctioned invocation is not flagged"
fi

{
    printf 'BG=[{"command":"gh run watch 1 --exit-status"}]\n'
    printf 'check 2 pre-bash/block-adhoc-sanctioned.sh "gh run watch 1 --exit-status" "refused"\n'
} >"$TMP/data.md"
if hands_out_banned "$TMP/data.md"; then
    fail "C IS OVER-BROAD: a JSON value and a test assertion were read as advice"
else
    pass "C control: data and test assertions are not advice"
fi

# ---- D. the registry is self-consistent --------------------------------------
if [ ! -f "$REGISTRY" ]; then
    fail "D. sanctioned registry missing: $REGISTRY"
else
    if python3 "$ROOT/.ci/scripts/quality/lib/check_sanctioned_registry.py" \
        "$REGISTRY" "$ROOT" >"$TMP/reg.out" 2>&1; then
        pass "D. registry: $(cat "$TMP/reg.out")"
    else
        fail "D. registry inconsistent:"
        sed 's/^/     /' "$TMP/reg.out" >&2
    fi
fi

# ---- E. the script's own --help works ----------------------------------------
if [ ! -x "$TRACE" ]; then
    fail "E. $TRACE_REL is missing or not executable"
elif "$TRACE" --help >"$TMP/help.out" 2>&1; then
    if grep -q "exit codes:" "$TMP/help.out"; then
        pass "E. $TRACE_REL --help works and documents its exit codes"
    else
        fail "E. --help works but documents no exit codes; a caller would have to guess"
    fi
else
    fail "E. $TRACE_REL --help exited non-zero"
fi

# ---- F. the skill teaches --run for a DISPATCHED run --------------------------
# `--wait --ref main` cannot see a workflow_dispatch run's check runs at all --
# a branch's statusCheckRollup structurally excludes them (incidents.md,
# 2026-08-26). That is not fixable in ci-trace.py itself; the only defense is
# that the taught recipe says to use --run for that case, and stays saying so.
if [ ! -f "$SKILL" ]; then
    fail "F. $SKILL is missing"
elif grep -q -- '--run' "$SKILL" && grep -qi 'workflow_dispatch\|dispatched' "$SKILL"; then
    pass "F. the skill teaches --run for a dispatched run"
else
    fail "F. $SKILL no longer teaches --run for a dispatched run -- this is exactly" \
        "how the 2026-08-26 false-green (main read GREEN while a Release run was" \
        "still tagging/deploying) would silently come back"
fi

echo
if [ "$fails" -eq 0 ]; then
    echo "${GREEN}✓${NC} ci-watch: one reader, $scanned file(s) clean."
    echo "  Blind spot, stated so a green is not read as more than it is: this checks"
    echo "  what agents are HANDED. It cannot see a watch an agent actually armed at"
    echo "  runtime, nor whether GitHub's rollup semantics change under the script."
    exit 0
fi
echo "${RED}✗${NC} ci-watch: $fails failure(s)."
exit 1
