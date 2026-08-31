#!/usr/bin/env bash
# A git-identity assignment used later without checking whether it failed OR
# resolved to a KNOWN MISLEADING VALUE is a defect gates run git and observe
# success but never inspect what a CONDITIONAL later does with that output.
#
# WHY THIS EXISTS. Measured 2026-08-28: .claude/hooks/post-bash/cancel-old-ci.sh
# and .claude/hooks/post-bash/refresh-pr-body.sh both captured
# `git rev-parse --abbrev-ref HEAD` and guarded only `-z "$BRANCH"` and
# `"$BRANCH" == "main"`. `rev-parse --abbrev-ref HEAD` does not fail on a
# detached checkout the way `symbolic-ref` does; it returns the LITERAL STRING
# "HEAD" (documented at .claude/hooks/stop/wl_core.py:466, which chose
# symbolic-ref for exactly this reason). Neither guard catches that value, so
# both hooks fell through and treated "HEAD" as a real branch name -- harmless
# today only because no git branch can ever actually be named "HEAD", which is
# luck holding the door shut, not a check. check-swallowed-failures.sh does not
# cover this: it scans only .ci/scripts/{quality,security,lib}, never
# .claude/hooks where this defect lived, and its shape requires an explicit
# `2>/dev/null ... || true`-style discard, not a captured value that is simply
# never validated against the specific misleading strings git can return.
#
# WHAT IT FLAGS. A line assigning the output of a git command that resolves an
# IDENTITY (branch, ref, sha) to a shell variable -- or a BARE such command
# whose output becomes a function's de facto return value via stdout -- in a
# file under .claude/hooks/ or .ci/scripts/quality/, where the file does not
# ALSO -- anywhere -- guard that value before it reaches a conditional or
# comparison. .ci/scripts/quality specifically: check-submodule-branches.sh
# lived there with the second real defect and had no check:* key running it
# at all (defined-but-never-run, invoked only by a direct `run:` line in
# ci-quality.yml, outside the package.json/manifest.ts convention every other
# gate uses) -- fixed alongside this gate.
#
# NOT the whole .ci/scripts tree: widening past quality/ into ci/, autopilot/,
# release/ etc. surfaced false positives this gate cannot yet resolve --
# `|| { ... exit 0; }` block-style handlers and `||` continued onto the next
# physical line both clear a real guard that a single-line-oriented scanner
# cannot see. Precision over recall: a gate that flags safe code gets
# suppressed, which is the exact failure check-swallowed-failures.sh's own
# header names. Widening further needs a smarter guard search, not more scope.
#
# "Guard" means any of:
#   * the assignment itself ends in a failure handler: `|| exit`, `|| return`,
#     `|| continue`, `|| true`, `|| :`
#   * a later `-z "$VAR"` or `-n "$VAR"` test (empty-checked before use)
#   * for the specific `rev-parse --abbrev-ref HEAD` shape, an explicit
#     `"$VAR" == "HEAD"` (or `= "HEAD"`) comparison, since empty-checking alone
#     does not catch that command's detached-HEAD sentinel
#
# WHAT IT DELIBERATELY DOES NOT FLAG. `symbolic-ref` and `branch --show-current`
# calls: both fail closed to EMPTY on a detached HEAD (no misleading literal),
# so an adjacent `-z` check is the only guard either one needs, and that is
# already required above. A command whose captured value is never compared or
# branched on (used only for printing) is not this gate's business either --
# scope stays "feeds a conditional", not "every git capture in the tree".
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT" || exit 1

RED=''
GREEN=''
NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED=$'\033[0;31m'
    GREEN=$'\033[0;32m'
    NC=$'\033[0m'
fi
FAIL=0
pass() { printf '%sok%s   %s\n' "$GREEN" "$NC" "$1"; }
fail() {
    printf '%s✗%s   %s\n' "$RED" "$NC" "$1" >&2
    FAIL=$((FAIL + 1))
}

# scan_file <path> -> prints one finding per unguarded assignment, nothing on a clean file.
scan_file() {
    local f="$1" body
    body="$(cat "$f" 2>/dev/null)" || return 0

    # Every VAR=$(...) capturing a git identity command, keyed by LINE NUMBER
    # so the guard checks below run against the FULL source line -- `grep -oE`
    # truncates at the closing paren of $(...), which silently dropped a
    # trailing `|| exit 0` on the very shape this gate exists to require and
    # produced three false positives before this was caught.
    while IFS=: read -r lineno match; do
        [ -n "$match" ] || continue
        local varname line
        varname="$(printf '%s' "$match" | sed -nE 's/^([A-Za-z_][A-Za-z0-9_]*)=\$\(.*/\1/p')"
        [ -n "$varname" ] || continue
        line="$(sed -n "${lineno}p" "$f")"

        # Guard 0: the assignment is itself the CONDITION of an if/elif/while,
        # whose failure branch is the guard (`elif ! head_sha=$(...); then`).
        grep -qE '^[[:space:]]*(if|elif|while)[[:space:]]+!?[[:space:]]*'"${varname}"'=' <<<"$line" && continue

        # Guard 1: the assignment line itself ends in a failure handler.
        grep -qE '\|\|[[:space:]]*(exit|return|continue|true|:)([[:space:]]|$)' <<<"$line" && continue

        # rev-parse --abbrev-ref HEAD is a SPECIAL CASE, checked before the
        # general empty-check guard: it does not fail on a detached checkout
        # the way symbolic-ref does, it returns the literal string "HEAD", so
        # an emptiness check alone (guard below) does not catch it. Only the
        # explicit HEAD-literal comparison, or guard 1 above, clears this shape.
        if grep -qE 'rev-parse[[:space:]]+--abbrev-ref[[:space:]]+HEAD' <<<"$line"; then
            grep -qE "\"\\\$${varname}\"[[:space:]]*(==|=)[[:space:]]*\"HEAD\"" <<<"$body" && continue
            printf '%s:%s\n' "${f#"$ROOT"/}" "$varname"
            continue
        fi

        # Guard 2: an empty-check on this variable appears anywhere in the
        # file. Sufficient for symbolic-ref / branch --show-current, both of
        # which fail closed to EMPTY on a detached checkout with no misleading
        # literal to also guard against.
        grep -qE "(-z|-n)[[:space:]]+\"\\\$${varname}\"" <<<"$body" && continue

        printf '%s:%s\n' "${f#"$ROOT"/}" "$varname"
        # `git` and its subcommand are not necessarily adjacent: `git -C "$dir"
        # rev-parse ...` is the ACTUAL shape of the real defect this gate exists
        # for, and an adjacency-requiring pattern (`git[[:space:]]+rev-parse`)
        # missed it silently on the real tree while the synthetic control fixture,
        # written without `-C`, still passed -- a gate proving its own harness
        # works and nothing about the tree it was supposed to be reading.
    done < <(grep -noE '[A-Za-z_][A-Za-z0-9_]*=\$\(git\b[^)]*\b(rev-parse|symbolic-ref|branch)\b[^)]*\)' "$f")

    # SECOND SHAPE: a BARE statement, not a `VAR=$(...)` assignment at all --
    # `git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"` as a
    # function's last line, its stdout becoming the function's de facto return
    # value at the CALL SITE (`current_branch="$(get_current_branch)"`). The
    # `|| echo <fallback>` reads as a guard but is not one: it fires only when
    # git itself fails, and `rev-parse --abbrev-ref HEAD` SUCCEEDS on a
    # detached checkout, printing the literal "HEAD" straight past it. Found
    # 2026-08-28 in check-submodule-branches.sh's get_current_branch() and
    # get_submodule_branch(), where two independently-detached checkouts (the
    # superproject and a submodule) would both return "HEAD" and compare
    # EQUAL, reporting a branch match that was not real.
    # NO file-wide exemption here, unlike Guard 3 above -- a bare statement has
    # no variable name to anchor a guard-search on, and "does a HEAD-literal
    # comparison appear ANYWHERE in the file" was tried and PROVEN WRONG by the
    # real defect it was meant to catch: check-submodule-branches.sh has an
    # unrelated `"$sm_branch" == "HEAD"` check on a DIFFERENT variable
    # elsewhere in the file, which cleared this finding even with the real
    # unguarded shape reintroduced verbatim -- a mutation-proof caught this
    # gate lying about its own coverage before it shipped. The fix is not to
    # search harder for a nearby guard; it is to ban the bare shape outright.
    # Route the fallback through a captured, explicitly-checked variable
    # instead (see the `good-bare.sh` control fixture below).
    while IFS=: read -r lineno match; do
        [ -n "$match" ] || continue
        printf '%s:bare-statement-line-%s\n' "${f#"$ROOT"/}" "$lineno"
    done < <(grep -noE 'git\b[^|;&]*\brev-parse\b[^|;&]*--abbrev-ref[^|;&]*\bHEAD\b[^|;&]*\|\|[[:space:]]*echo\b' "$f")
}

# --- controls first: a gate nobody has watched fail is not a gate ------------
CTL="$(mktemp -d)"
trap 'rm -rf "$CTL"' EXIT

cat >"$CTL/bad.sh" <<'FIX'
#!/usr/bin/env bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[[ -z "$BRANCH" || "$BRANCH" == "main" ]] && exit 0
echo "on $BRANCH"
FIX
got="$(scan_file "$CTL/bad.sh")"
if [ -z "$got" ]; then
    fail "CONTROL FAILED: an unguarded rev-parse --abbrev-ref HEAD (missing the HEAD-literal check) was NOT flagged."
    exit 1
fi

cat >"$CTL/good.sh" <<'FIX'
#!/usr/bin/env bash
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
[[ -z "$BRANCH" || "$BRANCH" == "main" || "$BRANCH" == "HEAD" ]] && exit 0
echo "on $BRANCH"
FIX
got="$(scan_file "$CTL/good.sh")"
if [ -n "$got" ]; then
    fail "CONTROL FAILED: a properly guarded assignment (checks the HEAD literal) WAS flagged."
    exit 1
fi

cat >"$CTL/good-symbolic.sh" <<'FIX'
#!/usr/bin/env bash
BRANCH=$(git symbolic-ref --short -q HEAD) || exit 0
[ -n "$BRANCH" ] || exit 0
echo "on $BRANCH"
FIX
got="$(scan_file "$CTL/good-symbolic.sh")"
if [ -n "$got" ]; then
    fail "CONTROL FAILED: a symbolic-ref call with a trailing || exit WAS flagged."
    exit 1
fi

# THE `-C <dir>` SHAPE, planted because the real defect wore it and a first
# draft of this gate's extraction regex (adjacency-only, `git[[:space:]]+rev-parse`)
# missed it silently: the synthetic fixtures above never used `-C`, so they
# kept passing while the real scan below found zero findings on a tree that
# genuinely had one. A control using the exact shape that broke the gate once
# is the only way to know the fix holds.
cat >"$CTL/bad-dashC.sh" <<'FIX'
#!/usr/bin/env bash
BRANCH=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --abbrev-ref HEAD 2>/dev/null)
[[ -z "$BRANCH" || "$BRANCH" == "main" ]] && exit 0
echo "on $BRANCH"
FIX
got="$(scan_file "$CTL/bad-dashC.sh")"
if [ -z "$got" ]; then
    fail "CONTROL FAILED: git -C <dir> rev-parse --abbrev-ref HEAD (the real defect's exact shape) was NOT flagged."
    exit 1
fi
pass "control: an unguarded rev-parse --abbrev-ref HEAD is detected"
pass "control: the HEAD-literal guard clears it"
pass "control: a fail-closed symbolic-ref assignment is not flagged"
pass "control: the git -C <dir> shape (the real defect) is detected too"

# THE BARE-STATEMENT SHAPE, planted because the SECOND real defect wore it:
# `git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"` as a function's
# last line, never assigned to a variable inside the function at all -- its
# caller captures the function's whole stdout instead
# (`current_branch="$(get_current_branch)"`). The `|| echo` fallback only
# fires on git FAILING; a detached checkout makes git SUCCEED with the
# literal "HEAD", walking straight past it.
cat >"$CTL/bad-bare.sh" <<'FIX'
#!/usr/bin/env bash
get_current_branch() {
    git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"
}
current_branch="$(get_current_branch)"
echo "on $current_branch"
FIX
got="$(scan_file "$CTL/bad-bare.sh")"
if [ -z "$got" ]; then
    fail "CONTROL FAILED: a bare rev-parse --abbrev-ref HEAD || echo fallback (the second real defect's shape) was NOT flagged."
    exit 1
fi

cat >"$CTL/good-bare.sh" <<'FIX'
#!/usr/bin/env bash
get_current_branch() {
    local b
    b="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || b=""
    if [[ -z "$b" || "$b" == "HEAD" ]]; then
        echo "main"
    else
        echo "$b"
    fi
}
current_branch="$(get_current_branch)"
echo "on $current_branch"
FIX
got="$(scan_file "$CTL/good-bare.sh")"
if [ -n "$got" ]; then
    fail "CONTROL FAILED: a properly guarded bare-statement function (checks the HEAD literal) WAS flagged."
    exit 1
fi
pass "control: the bare-statement || echo fallback (the second real defect) is detected"
pass "control: an explicit HEAD-literal check in the guarded version clears it"

# --- the real scan -------------------------------------------------------------
# .claude/hooks: where the first pair of real defects lived. .ci/scripts:
# where the second (check-submodule-branches.sh) lived -- a file this gate did
# not originally cover, which is exactly why the gate probe on this finding
# named "no check:* key runs it" as a separate, now also fixed, gap.
# `**/*.sh` requires a genuine subdirectory between the prefix and the
# filename in git's pathspec glob -- it matched ZERO files in
# .ci/scripts/quality/, which is FLAT (every .sh sits directly in it, no
# nested dirs), so this gate reported "71 shell file(s) scanned" while the
# second glob silently contributed nothing at all. Caught only because a
# mutation-proof on the real defect this scope widening exists to catch
# still passed clean -- the exact vacuity class this session spent all night
# hunting in OTHER gates, found here in its own. .claude/hooks DOES have
# subdirectories (pre-bash/, post-bash/, stop/, ...), so `**/*.sh` was
# already correct there; only the flat directory needed the plain form.
SCAN_GLOBS=('.claude/hooks/**/*.sh' '.ci/scripts/quality/*.sh')

files=()
while IFS= read -r f; do
    files+=("$f")
done < <(
    for g in "${SCAN_GLOBS[@]}"; do
        git -C "$ROOT" ls-files "$g" 2>/dev/null
        git -C "$ROOT" ls-files --others --exclude-standard "$g" 2>/dev/null
    done | sort -u
)
if [ "${#files[@]}" -eq 0 ]; then
    fail "found ZERO .sh files under ${SCAN_GLOBS[*]} -- this gate is not seeing the tree, its green would mean nothing."
    exit 1
fi

# This gate's OWN file is exempt: its job is to talk ABOUT the risky shapes,
# so its header comments quote them verbatim as examples and its controls
# plant them as deliberate fixtures in heredocs. Both matched the extraction
# regex and were reported as findings, which is the "gate about a rule
# accidentally judged by that same rule" trap -- same reasoning
# check-toolchain-pins.sh already documents for exempting itself.
SELF_REL="${BASH_SOURCE[0]#"$ROOT"/}"

findings=()
for rel in "${files[@]}"; do
    [ "$rel" = "$SELF_REL" ] && continue
    while IFS= read -r hit; do
        [ -n "$hit" ] && findings+=("$hit")
    done < <(scan_file "$ROOT/$rel")
done

if [ "${#findings[@]}" -eq 0 ]; then
    pass "${#files[@]} shell file(s) scanned under ${SCAN_GLOBS[*]}, no unguarded git-identity conditional found"
    echo "${GREEN}✓${NC} every git-identity capture under .claude/hooks and .ci/scripts is guarded before it reaches a conditional."
    exit 0
fi

for f in "${findings[@]}"; do
    echo "${RED}✗${NC} $f: captures a git identity command with no guard against failure or the misleading HEAD literal" >&2
done
echo "" >&2
echo "${RED}✗${NC} ${#findings[@]} unguarded git-identity assignment(s)." >&2
echo "  Fix: check emptiness before use (\`[[ -z \"\$VAR\" ]] && exit 0\`), and for" >&2
echo "  rev-parse --abbrev-ref HEAD specifically, also guard the literal \"HEAD\"" >&2
echo "  value it returns on a detached checkout." >&2
exit 1
