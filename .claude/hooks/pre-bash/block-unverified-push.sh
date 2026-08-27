#!/usr/bin/env bash
# Refuse a push whose tree no local gate run has judged.
#
# WHY. A CI round costs ~15 minutes. Measured on PR #579, three of the five
# reds this wave were `check:format` (1.72s), `check:ci-python-lint` (0.59s) and
# `check:ci-parity` (1.29s) -- 3.6 seconds of gate time between them, and they
# cost roughly 45 minutes of CI. The gates were there, the runner was there, and
# nothing made anyone run them.
#
# PROSE ALREADY TRIED. docs/agent-reference/ci-gates.md says "Run it before
# pushing to catch issues early" and CLAUDE.md points at it. Five rounds
# happened anyway. wl_git.py's own header states the principle this guard
# follows: prose is not a safety mechanism, and the recorded incidents show it
# failing.
#
# WHY A RECEIPT AND NOT A RUN. This hook sits in the PreToolUse chain, which
# fires on EVERY Bash call, so it must cost microseconds -- one `git rev-parse`
# and one file read. The expensive half (33 seconds, 254 gates) happens in an
# ordinary Bash call the session makes itself, where the runner's untruncated
# failure block is readable. Splitting them is the only shape that is both
# enforceable and cheap.
#
# KEYED ON `HEAD^{tree}`. CI checks out the pushed commit, so the tree object is
# exactly what CI will judge. It is also invariant to the dozens of dirty paths
# this repo's tree normally carries from OTHER live sessions -- keying on the
# worktree would invalidate the receipt on someone else's keystroke and make it
# unobtainable, which is how a guard becomes a wall and then gets bypassed.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# Command position, so prose about pushing is not a push. Same anchor as
# block-untagged-commit.sh; see lib/command-scan.sh for why the raw string is
# never matched directly.
printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|\$\(|`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+push([[:space:]]|$)' || exit 0

# A dry run publishes nothing and buys no CI round.
printf '%s' "$CMD" | grep -qE 'git push[^|;&]*--dry-run' && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$ROOT" ] || exit 0

# SUBMODULE PUSHES ARE OUT OF SCOPE, deliberately. They advance no console
# branch and trigger no console CI; cancel-old-ci.sh draws the same line for the
# same reason. The pointer-bump commit that DOES advance console is covered by
# the ordinary path.
case "$CMD" in
    *"-C $ROOT/private/"* | *"cd $ROOT/private/"* | *"git -C private/"* | *"cd private/"*) exit 0 ;;
esac

RECEIPT="$ROOT/.ci/cache/prepush-receipt.json"
TREE=$(git -C "$ROOT" rev-parse 'HEAD^{tree}' 2>/dev/null) || exit 0
[ -n "$TREE" ] || exit 0

# FAIL OPEN ON A BROKEN ENVIRONMENT, never on a broken verdict. No jq, no git,
# no repo: allow, exactly as warn-remote-drift.sh does -- "a drift CHECK must
# never become a push outage". A MISSING or STALE receipt is a different thing
# and is refused below, because that is the condition this guard exists for.
command -v jq >/dev/null 2>&1 || exit 0

refuse() {
    cat >&2 <<MSG
BLOCKED: $1

The pre-push lane is 254 gates in ~33 seconds, and it exists because three of
the five CI reds on PR #579 were sub-2-second gates that cost ~45 minutes of CI
between them. Run it, fix what it names, then push:

  npm run ci:quick

It is a PARTIAL run and says so: 58 slower gates are deferred to CI, and it
names any it had to defer because a prerequisite was slow. \`npm run ci\` is
still the whole set.

If a gate it names is not yours -- another session's uncommitted file often
reddens this shared tree -- do not work around it and do not fix their file.
Ask them, and keep working while they answer:

  .claude/hooks/stop/worklist.py --list --open        # who else is live here
  .claude/hooks/stop/worklist.py --ask <you> <them> '<gate>: <what you saw>'

If a gate cannot RUN here (a toolchain this machine lacks), that is not a red
you can fix by pushing: the gate's own message names the install line.
MSG
    exit 2
}

[ -f "$RECEIPT" ] || refuse "no local gate run has judged this tree."

R_TREE=$(jq -r '.headTree // ""' "$RECEIPT" 2>/dev/null)
R_WHOLE=$(jq -r '.whole // false' "$RECEIPT" 2>/dev/null)
R_EXIT=$(jq -r '.exitCode // 1' "$RECEIPT" 2>/dev/null)
R_FAILED=$(jq -r '(.failed // []) | join(", ")' "$RECEIPT" 2>/dev/null)
R_DIRTY=$(jq -r '.dirtyDigest // ""' "$RECEIPT" 2>/dev/null)
R_BLOCKED=$(jq -r '(.blocked // []) | join(", ")' "$RECEIPT" 2>/dev/null)

[ "$R_TREE" = "$TREE" ] ||
    refuse "the gate run judged a different tree ($R_TREE), not this one ($TREE)."

# A NARROWED RUN PROVES ALMOST NOTHING. `--quick --only <one-gate>` produces a
# receipt that is otherwise indistinguishable from all 254, so the runner
# records whether the lane ran WHOLE and this reads the flag rather than
# parsing the selection prose -- a guard that parses English fails open on a
# rewording.
[ "$R_WHOLE" = "true" ] ||
    refuse "that receipt came from a NARROWED run (--only/--skip), not the whole lane."

if [ "$R_EXIT" != "0" ]; then
    # A RED RECEIPT MAY STILL AUTHORISE A PUSH, but only when every failure is
    # named and justified in .ci/config/carried-reds.json. All-or-nothing is the
    # shape that gets a guard routed around; naming the exception keeps the
    # refusal informative and leaves the excuse in git where it can be reviewed.
    CARRIED_FILE="$ROOT/.ci/config/carried-reds.json"
    CARRIED=""
    if [ -f "$CARRIED_FILE" ]; then
        # Only entries whose reason is SUBSTANTIVE count. The bar is the one
        # .dead-bash-allowlist uses and gate-test:dead-bash pins with a
        # low-effort-BLOCKER case: a bare "known issue" excuses nothing.
        CARRIED=$(jq -r '[.carried[]? | select((.reason // "" | length) >= 80) | .gate] | join(" ")' \
            "$CARRIED_FILE" 2>/dev/null)
    fi

    UNNAMED=""
    for g in $(jq -r '(.failed // [])[]' "$RECEIPT" 2>/dev/null); do
        case " $CARRIED " in
            *" $g "*) ;;
            *) UNNAMED="$UNNAMED $g" ;;
        esac
    done

    # STALE ENTRIES REFUSE. An excuse that outlives its failure is exactly how an
    # allowlist rots into a permanent hole -- the npm side of this repo once
    # carried 101 dead entries for that reason. If a carried gate is no longer
    # failing, the entry must go before the next push.
    STALE=""
    for g in $CARRIED; do
        jq -e --arg g "$g" '(.failed // []) | index($g)' "$RECEIPT" >/dev/null 2>&1 ||
            STALE="$STALE $g"
    done

    if [ -n "$UNNAMED" ]; then
        refuse "the gate run went RED and these failures are neither fixed nor carried:${UNNAMED}.
  To carry one deliberately, add it to .ci/config/carried-reds.json with a reason
  that says WHY it cannot be fixed now. CI still runs it and still fails on it --
  carrying only records the decision instead of routing around it."
    fi

    if [ -n "$STALE" ]; then
        refuse "these gates are carried in .ci/config/carried-reds.json but are NOT failing any more:${STALE}.
  Remove the entries. A carried red that has gone green is a standing excuse for
  a problem that no longer exists, which is how an allowlist becomes permanent."
    fi

    echo "NOTE: pushing with CARRIED reds, each named in .ci/config/carried-reds.json:" >&2
    echo "  ${R_FAILED}" >&2
    echo "  CI runs these for real and will fail on them. Carrying is a record of a" >&2
    echo "  deliberate decision, not a way to make CI green." >&2
fi

# A GATE THAT COULD NOT RUN WARNS, IT DOES NOT REFUSE (operator decision,
# 2026-08-27). Measured that day: twelve reds on a normal developer tree, ten of
# them ambient, several purely "this machine has no ruff / no workers-types". A
# missing toolchain is not evidence about the code, and refusing on it would
# make the receipt unobtainable -- an unobtainable receipt is a guard people
# route around, which costs more than the rounds it saves.
#
# Never silent, though. "A linter that cannot run is a gate that cannot fail"
# stays true; this makes that state loud instead of forgiving it, and CI still
# runs those gates for real.
if [ -n "$R_BLOCKED" ]; then
    echo "NOTE: these gates could NOT RUN locally, so nothing here judged what they cover:" >&2
    echo "  $R_BLOCKED" >&2
    echo "  They are not a verdict on your code and they do not block this push --" >&2
    echo "  but CI runs them for real, so a finding in them lands there instead." >&2
    echo "  Each names its own install line; \`.ci/scripts/lib/toolchain.sh --report\`" >&2
    echo "  lists what this machine is missing against the pinned versions." >&2
fi

# THE HONEST RESIDUAL, stated rather than hidden: the gates ran against the
# WORKING TREE, not against `HEAD^{tree}`. If the dirty set has moved since,
# something the gates read has changed. That is a warning and not a refusal --
# this tree carries dozens of dirty paths from other sessions at any moment, so
# refusing on it would make the receipt unobtainable, and an unobtainable
# receipt is a guard nobody keeps.
NOW_DIRTY=$(git -C "$ROOT" status --porcelain=v1 -z 2>/dev/null | sha256sum 2>/dev/null | cut -c1-16)
if [ -n "$NOW_DIRTY" ] && [ -n "$R_DIRTY" ] && [ "$NOW_DIRTY" != "$R_DIRTY" ]; then
    echo "NOTE: the working tree has changed since the gates ran (they judged the" >&2
    echo "  worktree, this push carries HEAD^{tree}). The receipt still matches the" >&2
    echo "  committed tree, so this is allowed -- but if you changed something a gate" >&2
    echo "  reads, re-run: npm run ci:quick" >&2
fi
exit 0
