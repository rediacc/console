#!/usr/bin/env bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-git-op-conditionals is now registered to the Python port's entry point,
# .ci/scripts/quality/check_git_op_conditionals.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs "...check_git_op_conditionals.py" but its header derives "...check-git-op-conditionals.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

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

# The line-level half of scan_python_file. Emits `<kind>\t<var>\t<lineno>`:
#   A  an assignment capture whose window names --abbrev-ref
#   E  any other assignment capture
#   B  the bare `return git_out(...)` shape, which has no name to guard
PY_SCAN_AWK='
function headvar(s,   t) {
    if (match(s, /^[ \t]*[A-Za-z_][A-Za-z0-9_]*[ \t]*(:[^=]+)?=([^=]|$)/)) {
        t = substr(s, RSTART, RLENGTH)
        sub(/^[ \t]*/, "", t)
        sub(/[ \t]*(:[^=]+)?=.*$/, "", t)
        return t
    }
    return ""
}
{ line[NR] = $0 }
END {
    inctl = 0
    for (i = 1; i <= NR; i++) {
        l = line[i]
        if (inctl) {
            if (l !~ /^[ \t]*$/ && l ~ /^[^ \t]/) inctl = 0
            else { skip[i] = 1; continue }
        }
        if (l ~ /^def (selftest|run_controls|controls?|build_fixture|_?fixture|plant)[ \t]*\(/) {
            inctl = 1
            skip[i] = 1
        }
    }
    for (i = 1; i <= NR; i++) {
        if (skip[i]) continue
        l = line[i]
        if (l ~ /^[ \t]*#/) continue
        if (l !~ /rev-parse/ && l !~ /symbolic-ref/ && l !~ /["\x27]branch["\x27]/) continue
        # WINDOW FIRST, git TEST SECOND -- black splits the call so that `git`
        # is on the head line and `rev-parse` on the continuation.
        window = l
        var = headvar(l)
        for (b = 1; b <= 3 && var == ""; b++) {
            if (i - b < 1) break
            prev = line[i - b]
            if (prev !~ /[[({][ \t]*$/) break
            window = prev " " window
            var = headvar(prev)
        }
        if (window !~ /(^|[^0-9A-Za-z])git([^0-9A-Za-z]|$)/) continue
        if (var == "") {
            # A PLACEHOLDER, NOT AN EMPTY FIELD. Tab is IFS whitespace, so bash
            # `read` COLLAPSES `B\t\t2` into two fields and the line number
            # lands in the variable slot. That printed `bare-statement-line-`
            # with no number while the port printed `-line-2`, and only the
            # planted differential showed it; on this tree neither side has a
            # bare finding, so both were silently "equal".
            if (l ~ /^[ \t]*return([ \t]|$)/ && window ~ /--abbrev-ref/) printf "B\t-\t%d\n", i
            continue
        }
        if (window ~ /^[ \t]*(if|elif|while)([ \t]|$)/) continue
        if (window ~ /check[ \t]*=[ \t]*True/ || window ~ /check_output/ || window ~ /check_call/) continue
        if (window ~ /--abbrev-ref/) printf "A\t%s\t%d\n", var, i
        else printf "E\t%s\t%d\n", var, i
    }
}'

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

# scan_python_file <path> -> the same findings as scan_file, for Python sources.
#
# THE PORT'S PYTHON HALF, MIRRORED. `.ci/rediacc_ci/quality/git_op_conditionals.py`
# carries the full reasoning; this is the same predicate so that the differential
# between the two implementations stays a real comparison. A twin that scanned
# only `.sh` while the port scanned both would agree on this tree by accident and
# stop being evidence of anything.
#
# awk does the LINE work (control-body skip, comment skip, identity trigger, the
# three-line backward window, the git-token test, the condition and fail-loud
# guards) and emits one record per capture; bash does the FILE-WIDE guard
# searches, exactly as it does for the shell half. `grep -P`, never `-E`: ugrep
# 7.5.0 returns silent false zeros for an alternated `^` beside a negated class,
# which is precisely the shape of the git-token test.
scan_python_file() {
    local f="$1" body label rec kind var lineno
    # Test files are fixtures. BOTH separators, because this tree spells one of
    # them `guards/test-block_unverified_push.py` with a HYPHEN and a `test_`
    # -only pattern would miss it while looking correct.
    case "${f##*/}" in
        test-*.py | test_*.py) return 0 ;;
    esac
    body="$(cat "$f" 2>/dev/null)" || return 0
    label="${f#"$ROOT"/}"

    while IFS=$'\t' read -r kind var lineno; do
        [ -n "$kind" ] || continue
        case "$kind" in
            B)
                printf '%s:bare-statement-line-%s\n' "$label" "$lineno"
                ;;
            A)
                # `--abbrev-ref HEAD` returns the literal "HEAD" rather than
                # failing, so only an explicit HEAD comparison clears it.
                grep -qP "(?:\b\Q${var}\E\s*(?:==|!=)\s*['\"]HEAD['\"]|['\"]HEAD['\"]\s*(?:==|!=)\s*\Q${var}\E\b)" <<<"$body" && continue
                printf '%s:%s\n' "$label" "$var"
                ;;
            E)
                grep -qP "(?:(?:if|elif|while|not|and|or|assert)\s+\Q${var}\E(?![0-9A-Za-z_])|\b\Q${var}\E\s+(?:is\s+(?:not\s+)?None|and|or)(?![0-9A-Za-z_])|\b\Q${var}\E\s*(?:==|!=)\s*(?:''|\"\"))" <<<"$body" && continue
                printf '%s:%s\n' "$label" "$var"
                ;;
        esac
    done < <(awk "$PY_SCAN_AWK" "$f")
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

# --- the PYTHON controls, inline, same rule ----------------------------------
# The awk predicate above has to be watched fire too. Without these the twin's
# python half could break silently and every bash control would still pass --
# which is the precise shape of "a gate that passes without running".
py_ctl() {
    local name="$1" must="$2" got
    got="$(scan_python_file "$CTL/$name")"
    if [ "$must" = fire ] && [ -z "$got" ]; then
        fail "CONTROL FAILED: python fixture $name was NOT flagged."
        exit 1
    fi
    if [ "$must" = silent ] && [ -n "$got" ]; then
        fail "CONTROL FAILED: python fixture $name WAS flagged ($got)."
        exit 1
    fi
}

cat >"$CTL/bad.py" <<'FIX'
branch = hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"])
if not branch or branch == "main":
    raise SystemExit(0)
FIX
py_ctl bad.py fire

cat >"$CTL/good.py" <<'FIX'
branch = hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"])
if not branch or branch == "main" or branch == "HEAD":
    raise SystemExit(0)
FIX
py_ctl good.py silent

cat >"$CTL/good-symbolic.py" <<'FIX'
branch = hookio.git_out(["symbolic-ref", "--short", "-q", "HEAD"], want_rc=True)
if branch is None or branch == "":
    raise SystemExit(0)
FIX
py_ctl good-symbolic.py silent

# THE SPLIT CALL: `git` on the head line, `rev-parse` on the continuation. A
# line-oriented scanner misses this silently, and it is real at
# warn_remote_drift.py:209.
cat >"$CTL/bad-multiline.py" <<'FIX'
branch = hookio.git_out(
    ["rev-parse", "--abbrev-ref", "HEAD"], cwd=root
)
if branch == "main":
    raise SystemExit(0)
FIX
py_ctl bad-multiline.py fire

cat >"$CTL/bad-dashC.py" <<'FIX'
branch = hookio.git_out(["-C", root, "rev-parse", "--abbrev-ref", "HEAD"])
if branch == "main":
    raise SystemExit(0)
FIX
py_ctl bad-dashC.py fire

cat >"$CTL/bad-bare.py" <<'FIX'
def current_branch():
    return hookio.git_out(["rev-parse", "--abbrev-ref", "HEAD"]) or "main"
FIX
py_ctl bad-bare.py fire

cat >"$CTL/good-checked.py" <<'FIX'
sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True).stdout
if sha == "":
    raise SystemExit(0)
FIX
py_ctl good-checked.py silent

# THE `git` TOKEN TEST, WHICH NOTHING WATCHED UNTIL A MUTATION SAID SO.
# Disabling it was measured on 2026-09-08 to change nothing on the real tree and
# to fail no control, so it was live code with no proof it did anything.
cat >"$CTL/no-git.py" <<'FIX'
branch = github_api(["rev-parse", "--abbrev-ref", "HEAD"])
if branch == "main":
    raise SystemExit(0)
FIX
py_ctl no-git.py silent

cat >"$CTL/plain-status.py" <<'FIX'
status = hookio.git_out(["status", "--porcelain"])
if status != "":
    pass
FIX
py_ctl plain-status.py silent

pass "control: an unguarded python rev-parse --abbrev-ref HEAD is detected"
pass "control: a python HEAD-literal guard clears it"
pass "control: a None-checked python symbolic-ref capture is not flagged"
pass "control: a SPLIT python call (git on one line, rev-parse on the next) is detected"
pass "control: the python git -C <dir> shape is detected"
pass "control: the bare \`return git_out(...) or <fallback>\` shape is detected"
pass "control: a fail-loud check=True capture is not flagged"
pass "control: \`github_api\` is not read as the git CLI"
pass "control: a non-identity \`git status\` capture is not flagged"

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

# THE PYTHON PATHSPECS. FLAT SPELLINGS ON BOTH, and for the reason the block
# above already learned the hard way in the other direction: git's default
# pathspec is wildmatch WITHOUT pathname mode, so `*` crosses `/` and
# `.claude/rediacc_hooks/*.py` picks up the nested guards/ and tests/ files too.
# Here it is `**` that is wrong -- measured 2026-09-08,
# `.claude/rediacc_hooks/**/*.py` returns 58 files and the flat form returns 64,
# because `**/*.py` still demands a literal slash and so drops the SIX top-level
# modules. One of the six is hookio.py, which DEFINES git_out and run_out.
PY_SCAN_GLOBS=('.claude/rediacc_hooks/*.py' '.ci/scripts/quality/*.py')

collect() {
    for g in "$@"; do
        git -C "$ROOT" ls-files "$g" 2>/dev/null
        git -C "$ROOT" ls-files --others --exclude-standard "$g" 2>/dev/null
    done | sort -u
}

files=()
while IFS= read -r f; do files+=("$f"); done < <(collect "${SCAN_GLOBS[@]}")
pyfiles=()
while IFS= read -r f; do pyfiles+=("$f"); done < <(collect "${PY_SCAN_GLOBS[@]}")

# COUNTED AND REFUSED SEPARATELY. One combined count cannot tell "186 python and
# 116 shell" from "302 shell and a python glob matching nothing", and the second
# is how a widening manufactures a confident green.
if [ "${#files[@]}" -eq 0 ]; then
    fail "found ZERO shell files under ${SCAN_GLOBS[*]} -- this gate is not seeing that half of the tree, and its green would mean nothing."
    exit 1
fi
if [ "${#pyfiles[@]}" -eq 0 ]; then
    fail "found ZERO python files under ${PY_SCAN_GLOBS[*]} -- this gate is not seeing that half of the tree, and its green would mean nothing."
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
for rel in "${pyfiles[@]}"; do
    while IFS= read -r hit; do
        [ -n "$hit" ] && findings+=("$hit")
    done < <(scan_python_file "$ROOT/$rel")
done

if [ "${#findings[@]}" -eq 0 ]; then
    pass "${#files[@]} shell file(s) under ${SCAN_GLOBS[*]} and ${#pyfiles[@]} python file(s) under ${PY_SCAN_GLOBS[*]} scanned, no unguarded git-identity conditional found"
    echo "${GREEN}✓${NC} every git-identity capture under .claude and .ci is guarded before it reaches a conditional, in both languages."
    exit 0
fi

for f in "${findings[@]}"; do
    echo "${RED}✗${NC} $f: captures a git identity command with no guard against failure or the misleading HEAD literal" >&2
done
echo "" >&2
echo "${RED}✗${NC} ${#findings[@]} unguarded git-identity assignment(s)." >&2
echo "  Fix, in shell: check emptiness before use, \`[[ -z \"\$VAR\" ]] && exit 0\`." >&2
echo "  Fix, in python: check the value before it reaches a conditional --" >&2
echo "  \`if not var: return ALLOW\`, or capture with \`want_rc=True\` and test \`is None\`." >&2
echo "  For rev-parse --abbrev-ref HEAD specifically, ALSO guard the literal \"HEAD\"" >&2
echo "  value it returns on a detached checkout; emptiness alone misses it." >&2
exit 1
