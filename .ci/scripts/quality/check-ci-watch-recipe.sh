#!/usr/bin/env bash
# Gate: the canonical CI-watch loop lives in ONE place and is attempt-stable.
#
# Why this exists. On 2026-08-25, landing console#574, a background watch on run
# 32810322315 fired and reported `cancelled` / `CI Complete` failed. Moments
# later the same run read `in_progress`: `run_attempt` had gone to 2, because
# the watchdog classified a hung `OPS Provision (macos-intel)` leg as transient
# and re-dispatched it. Attempt 2 passed. The verdict the watch delivered
# belonged to a superseded attempt, and the recipe that produced it was the one
# the repo recommends.
#
# The recipe existed in NINE places. A manual sweep found six; this gate, on its
# very first run, found the other three, because the sweep had grepped only
# *.md and the hook SCRIPTS were invisible to it. Two of those were worse than
# stale: block-long-sleep.sh's message explained that "attempt 2 lands on the
# SAME Console CI run" while printing a loop that could not survive it, and
# cancel-old-ci.sh recommended `gh run watch`, which this repo rejects 4/4.
# Nothing gated any of it: every existing check reads code, and this defect
# lives in the prose that agents copy.
#
# Three assertions, each with a control BUILT BY CONSTRUCTION (fixtures written
# literally, never a pattern substitution on real source), so a control cannot
# be silently voided by rewording the line it targets -- the failure mode
# check-control-vacuity.sh exists to catch.
#
#   A. The canonical block in SKILL.md is attempt-stable and reports every job
#      that is neither success nor skipped.
#   B. That block is syntactically valid bash.
#   C. No doc or hook outside the evidence file carries a watch loop that waits
#      only on `status == completed`, or recommends `gh run watch` as the
#      wake-up.
#
# The 60-line cap on both skill files is NOT checked here: `check:ci-skill-size`
# already owns it, and it caps every file in a self-improving skill directory,
# not just SKILL.md. Two gates on one invariant is a maintenance liability, not
# extra safety.
#
# Hermetic: no network, no gh, no CI. Runs in about a second.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SKILL="$ROOT/.claude/skills/ci-watch/SKILL.md"
EVIDENCE_FILE=".claude/skills/ci-watch/incidents.md"

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

# ---------------------------------------------------------------------------
# Extract the first ```bash fenced block from a markdown file.
# ---------------------------------------------------------------------------
bash_block() {
    awk '/^```bash$/ { inblk=1; next } /^```$/ { if (inblk) exit } inblk { print }' "$1"
}

# ---------------------------------------------------------------------------
# The detector, used by C and by C's controls alike. A "stale watch loop" is a
# line that reads the run's `.status` via jq AND compares it to "completed",
# in a file that never mentions `run_attempt`.
#
# Keying on the jq accessor rather than the bare word "completed" is deliberate:
# prose SAYS completed constantly ("`completed` is not terminal"), and a gate
# that flagged prose would be reworded around within a week. `.status` is the
# signature of an actual command being handed to a reader.
# ---------------------------------------------------------------------------
has_stale_watch_loop() {
    local f="$1"
    grep -qE '\.status' "$f" || return 1
    grep -E '\.status' "$f" | grep -qE '"completed"' || return 1
    # An attempt-aware file is by definition not handing out the stale form.
    grep -q 'run_attempt' "$f" && return 1
    return 0
}

# ---------------------------------------------------------------------------
# The second detector: a file that RECOMMENDS `gh run watch` as the wake-up.
#
# The first attempt at this asked whether the file was recommending or rejecting
# the tool, and flagged five files that were all rejecting it -- including
# SKILL.md, whose "stays rejected" happened to wrap across two lines, and a test
# fixture that merely carried the string as data. A gate that flags every file
# NAMING a banned tool gets suppressed, and then nothing is guarded.
#
# So this keys on a command signature instead, the same property that makes the
# stale-loop detector above work: a recommendation hands over an INVOCATION,
# with flags. cancel-old-ci.sh printed `gh run watch <id> --exit-status
# --interval 100`. A sentence rejecting the tool never carries flags.
# ---------------------------------------------------------------------------
recommends_gh_run_watch() {
    # A command sitting in a JSON value -- "command":"gh run watch ..." -- is
    # DATA, not advice: test harnesses carry those to simulate a background task
    # some other session started, and whether the command is good advice is not
    # what such a test is about. Prose that hands the reader an invocation is
    # what this looks for, so JSON-valued occurrences are dropped first.
    grep -vE '"(command|cmd)"[[:space:]]*:' "$1" \
        | grep -qE 'gh run watch[^|;&]*--(exit-status|interval)'
}

# ---------------------------------------------------------------------------
# A. The canonical block is attempt-stable.
# ---------------------------------------------------------------------------
assert_canonical() {
    local skill="$1" label="$2" blk
    blk="$(bash_block "$skill")"
    if [ -z "$blk" ]; then
        echo "$label: no \`\`\`bash block found"
        return 1
    fi
    if ! printf '%s' "$blk" | grep -q 'run_attempt'; then
        echo "$label: canonical block does not read run_attempt, so it exits on the first \`completed\` and can report a superseded attempt"
        return 1
    fi
    if ! printf '%s' "$blk" | grep -q '!="success"'; then
        echo "$label: canonical block does not list jobs that are not success (filtering for ==\"failure\" hides a cancelled gate)"
        return 1
    fi
    if ! printf '%s' "$blk" | grep -q '!="skipped"'; then
        echo "$label: canonical block does not exclude skipped jobs, so a normal skip reads as a problem"
        return 1
    fi
    return 0
}

if out="$(assert_canonical "$SKILL" "SKILL.md")"; then
    pass "A. canonical block is attempt-stable and reports non-success/non-skipped jobs"
else
    fail "A. $out"
fi

# A-control, by construction: a canonical block with the pre-2026-08-25 form.
cat > "$TMP/stale-skill.md" <<'FIXTURE'
# fixture

```bash
R=<run-id>
until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do sleep 20; done
gh run view $R --json conclusion,jobs --jq '[.jobs[]|select(.conclusion=="failure")|.name]'
```
FIXTURE
if assert_canonical "$TMP/stale-skill.md" "control" >/dev/null; then
    fail "A CONTROL DID NOT FIRE: the pre-fix recipe passed assertion A, so A proves nothing"
else
    pass "A control: the pre-fix recipe is rejected"
fi

# ---------------------------------------------------------------------------
# B. The canonical block is valid bash. A recipe that does not parse is worse
#    than no recipe: it fails at 3am, in the background, with nobody reading.
# ---------------------------------------------------------------------------
bash_block "$SKILL" \
    | sed 's/<run-id>/1/; s|<owner>/<repo>|o/r|' > "$TMP/canonical.sh"

# Prove the placeholder substitution LANDED before trusting what bash -n says
# about the result. This normalisation is a pattern substitution, so renaming a
# placeholder in SKILL.md would leave the text unsubstituted and B would be
# parsing something nobody writes -- the vacuity failure mode
# check-control-vacuity.sh exists to catch. Any surviving <angle-placeholder>
# means the substitution list has drifted from the document.
if grep -q '<[a-z][a-z-]*>' "$TMP/canonical.sh"; then
    fail "B: placeholder substitution did not land -- $(grep -oE '<[a-z][a-z-]*>' "$TMP/canonical.sh" | sort -u | tr '\n' ' ')still present, so the bash -n below would test unsubstituted text. Update the sed list in this gate to match SKILL.md."
elif bash -n "$TMP/canonical.sh" 2>"$TMP/bash-n.err"; then
    pass "B. canonical block parses as bash"
else
    fail "B. canonical block is not valid bash: $(tr '\n' ' ' < "$TMP/bash-n.err")"
fi

# B-control, by construction.
printf 'while :; do\n  case "$S" in\n' > "$TMP/broken.sh"
if bash -n "$TMP/broken.sh" 2>/dev/null; then
    fail "B CONTROL DID NOT FIRE: an unterminated block parsed clean, so B proves nothing"
else
    pass "B control: unterminated bash is rejected"
fi

# ---------------------------------------------------------------------------
# C. No second copy of the stale loop anywhere agents read.
# ---------------------------------------------------------------------------
scan_files() {
    git -C "$ROOT" ls-files \
        '.claude/**/*.md' '.claude/**/*.sh' 'docs/agent-reference/*.md' 2>/dev/null \
        | grep -v "^${EVIDENCE_FILE}$"
}

offenders=()
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    [ -f "$ROOT/$rel" ] || continue
    if has_stale_watch_loop "$ROOT/$rel"; then
        offenders+=("$rel (stale loop)")
    fi
    if recommends_gh_run_watch "$ROOT/$rel"; then
        offenders+=("$rel (recommends gh run watch)")
    fi
done < <(scan_files)

scanned="$(scan_files | wc -l | tr -d ' ')"
if [ "$scanned" -eq 0 ]; then
    fail "C. scanned ZERO files -- the glob matched nothing, so this assertion is vacuous"
elif [ ${#offenders[@]} -eq 0 ]; then
    pass "C. no stale watch loop in $scanned scanned file(s) (evidence file $EVIDENCE_FILE excluded by name)"
else
    fail "C. these hand out a broken wake-up: ${offenders[*]}"
    echo "     Point them at .claude/skills/ci-watch/SKILL.md instead of embedding a copy." >&2
fi

# C-control, by construction: the detector must fire on the stale form...
cat > "$TMP/caller-stale.md" <<'FIXTURE'
Arm the watch:
`R=1; until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do sleep 20; done`
FIXTURE
if has_stale_watch_loop "$TMP/caller-stale.md"; then
    pass "C control: the stale form is detected"
else
    fail "C CONTROL DID NOT FIRE: the stale loop went undetected, so C proves nothing"
fi

# ...and must NOT fire on the corrected form, or C is a gate that flags everything.
cat > "$TMP/caller-good.md" <<'FIXTURE'
Arm the watch:
`S=$(gh api "repos/$REPO/actions/runs/$R" --jq '"\(.status) \(.run_attempt)"')`
`case "$S" in completed*) [ "$P" = "$S" ] && break;; esac`
FIXTURE
if has_stale_watch_loop "$TMP/caller-good.md"; then
    fail "C IS OVER-BROAD: the corrected, attempt-stable form was flagged as stale"
else
    pass "C control: the corrected form is not flagged"
fi

# C-control for the second detector: an INVOCATION is caught...
printf 'Watch it with: gh run watch <id> --exit-status --interval 100\n' > "$TMP/rec-bad.md"
if recommends_gh_run_watch "$TMP/rec-bad.md"; then
    pass "C control: a gh run watch invocation is detected"
else
    fail "C CONTROL DID NOT FIRE: a gh run watch invocation went undetected"
fi

# ...while every way of NAMING it without handing it over is not. All four of
# these are real lines from this repo that earlier drafts wrongly flagged --
# the last one WITH flags, to pin that a JSON-valued command stays data.
{
    printf 'push. **`gh run watch` stays\n'
    printf 'rejected**; see incidents.md.\n'
    printf 'poll to a terminal state -- `gh run watch` has dropped silently on\n'
    printf 'you do not run `gh run watch/view/list` or fetch a job log\n'
    printf 'BG=[{"command":"gh run watch 30514648812 --exit-status"}]\n'
} > "$TMP/rec-ok.md"
if recommends_gh_run_watch "$TMP/rec-ok.md"; then
    fail "C IS OVER-BROAD: naming gh run watch without flags was read as recommending it"
else
    pass "C control: naming gh run watch without handing over an invocation is not flagged"
fi

echo
if [ "$fails" -eq 0 ]; then
    echo "${GREEN}✓${NC} ci-watch recipe: one source, attempt-stable, $scanned file(s) clean."
    echo "  Blind spot, stated so a green is not read as more than it is: this gate"
    echo "  checks the recipe agents are HANDED. It cannot see a watch an agent"
    echo "  actually armed at runtime, nor whether GitHub's re-run semantics change."
    exit 0
fi
echo "${RED}✗${NC} ci-watch recipe: $fails failure(s)."
exit 1
