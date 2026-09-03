#!/bin/bash
# check:ci-plan-housekeeping -- a plan file nobody has touched for delete_days
# must be deleted, and the gate says the exact date each one goes red.
#
# The operator: "let's also add another quality check for housekeeping of old
# plan files! If a plan file is older than 33 days, then CI should complain until
# someone deletes them from the branch."
#
# WHY THE INSTRUMENT IS `git log`, AND WHY THAT ALMOST MADE THIS VACUOUS.
# mtime is wrong: a clone or a checkout rewrites it, so the gate would answer
# differently on every machine. But the obvious replacement is wrong HERE in a
# way that fails GREEN, which is worse. Measured on this checkout:
#
#     $ git rev-parse --is-shallow-repository
#     true
#     $ git log -1 --format=%cI -- agent/PLAN-cold-path.md
#     2026-09-01T14:25:23+02:00     # the GRAFT commit, not the file's
#
# Every one of the 70 tracked plans reports one day old, because `git log` on a
# shallow clone attributes each file to the graft boundary. A gate built on that
# is not merely inaccurate, it is a gate that CANNOT FAIL -- and it would report
# a confident "none over 33 days" forever. check_git_history_depth.py:6 already
# documents the class. So a shallow checkout is REFUSED here, not answered.
#
# WHY LAST-COMMIT AND NOT ADDED-DATE. The operator's words are "old plan files
# ... until someone deletes them", which describes a file that has been SITTING
# there. A plan edited yesterday is being worked on. And the property that
# dissolves the hard case: a plan genuinely being executed is being EDITED, an
# edit is a COMMIT, and a commit resets the clock. So the instrument auto-exempts
# every actually-active plan against an oracle nobody can forge by typing a word
# in a Status header -- which is why `Status: executing` buys nothing here.
#
# %cI AND NOT %aI, measured: author and committer dates diverge on 735 of 4001
# commits in this repo with a maximum skew of 21.5 days, which is 65% of the
# window. %cI answers "when did this file, in its current form, enter the
# branch". It errs lenient -- a rebase makes a file look fresher, never staler --
# which is the safe direction for a gate whose false positive deletes a document
# somebody needs.
#
# THE NUMBERS LIVE IN .ci/config/plan-lifecycle.json and are NOT inlined here,
# because check_plan_boxes.py's A5 refuses a deletion this gate demands unless
# the same threshold is crossed. Two copies of `33` is a deadlock.
#
# Exit 1 on any offender or on a refusal, 2 on setup error.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${PLAN_HK_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
cd "$ROOT_DIR" || exit 2

if [[ "${CI:-}" == "true" ]]; then RED="" GREEN="" YEL="" NC=""; else
    RED='\033[0;31m' GREEN='\033[0;32m' YEL='\033[0;33m' NC='\033[0m'
fi

CFG="${PLAN_HK_CONFIG:-$ROOT_DIR/.ci/config/plan-lifecycle.json}"
ALLOWLIST="${PLAN_HK_ALLOWLIST:-$ROOT_DIR/.plan-housekeeping-allowlist}"
# Floor. Measured 2026-09-03: 70 tracked plans. Well under it on purpose -- this
# guards against the glob losing the corpus, not against ordinary housekeeping.
MIN_PLANS="${PLAN_HK_MIN_FILES:-30}"

[[ -f "$CFG" ]] || {
    echo "VACUOUS INPUT: $CFG is missing, so no threshold can be read" >&2
    exit 1
}
WARN_DAYS=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['warn_days'])" "$CFG") || exit 2
DELETE_DAYS=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['delete_days'])" "$CFG") || exit 2
PLAN_GLOB=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['plan_glob'])" "$CFG") || exit 2

# ---------------------------------------------------------------------------
# CONTROL FIRST. The age arithmetic is the whole gate, so it is proven on
# synthetic input in BOTH directions before the real tree is judged -- an
# over-age date must be reported and an under-age one must not. Without the
# second, a function returning "too old" for everything would look identical to
# a real finding.
# ---------------------------------------------------------------------------
age_days() { # <iso8601> -> whole days since, on stdout
    python3 - "$1" <<'PY'
import datetime as dt, sys
try:
    then = dt.datetime.fromisoformat(sys.argv[1])
except ValueError:
    print(-1); raise SystemExit(0)
if then.tzinfo is None:
    then = then.replace(tzinfo=dt.UTC)
print((dt.datetime.now(dt.UTC) - then).days)
PY
}

CONTROL_FAIL=0
_old=$(age_days "$(python3 -c "
import datetime as dt
print((dt.datetime.now(dt.UTC) - dt.timedelta(days=40)).isoformat())")")
_new=$(age_days "$(python3 -c "
import datetime as dt
print((dt.datetime.now(dt.UTC) - dt.timedelta(days=2)).isoformat())")")
[[ "$_old" -ge "$DELETE_DAYS" ]] || {
    echo "control: a 40-day date did not read as over $DELETE_DAYS (got $_old)" >&2
    CONTROL_FAIL=1
}
[[ "$_new" -lt "$DELETE_DAYS" ]] || {
    echo "control: a 2-day date read as over $DELETE_DAYS (got $_new)" >&2
    CONTROL_FAIL=1
}
[[ "$(age_days 'not-a-date')" == "-1" ]] || {
    echo "control: an unparseable date did not report -1" >&2
    CONTROL_FAIL=1
}
if [[ "$CONTROL_FAIL" == 1 ]]; then
    echo -e "${RED}✗${NC} instrument control failed; every verdict below would be meaningless" >&2
    exit 2
fi
echo "✓ control: the age arithmetic reports over and under the threshold, and refuses a bad date"

# ---------------------------------------------------------------------------
# THE SHALLOW REFUSAL. See the header: this is the one that stops the gate being
# a comment. HARD in CI because the answer would be wrong there; locally a LOUD
# skip of the age verdict only, so the floor and the allowlist checks still run
# and a partial run stays distinguishable from a clean one.
# ---------------------------------------------------------------------------
#
# `git rev-parse --is-shallow-repository` IS NOT THE TEST, and believing it cost a
# CI round. It answers on the EXISTENCE of .git/shallow, and `git fetch
# --unshallow` against a partial clone (`--filter=blob:none`, which every
# fetch-depth: 0 checkout in this repo uses) leaves that file behind EMPTY. So on
# 2026-09-03 job 100500447167 unshallowed successfully at 02:28:52 -- the log shows
# every branch and tag arriving -- and this gate still refused at 02:33:39, in the
# very lane its own error message names as the correct one. A gate that cannot pass
# in the job it tells you to use is indistinguishable from a broken gate.
#
# The property that actually matters is whether any GRAFT remains, because a graft
# is what makes every file report the boundary's date. An empty .git/shallow means
# no grafts, so history is complete for this gate's purpose whatever rev-parse says.
is_shallow() {
    [[ "$(git rev-parse --is-shallow-repository 2>/dev/null)" == "true" ]] || return 1
    local f
    f="$(git rev-parse --git-path shallow 2>/dev/null)"
    [[ -s "$f" ]]
}

# ---------------------------------------------------------------------------
# The corpus. Tracked-only and non-recursive, which is exactly the Stop hook's
# own glob (wl_store.agent_plan_dir -> agent_root, d.glob("PLAN-*.md")). If the
# gate and the hook disagreed about what a plan file IS, one of them would be
# enforcing a rule about a set the other cannot see. Non-recursive also excludes
# the archive, which is the SUCCESSFUL outcome of housekeeping.
# ---------------------------------------------------------------------------
# A `while read` loop rather than `mapfile`: check:ci-shell-commands refuses
# mapfile because it is bash-4-only and the minimal CI images do not carry it.
PLANS=()
while IFS= read -r _p; do
    [[ -n "$_p" ]] && PLANS+=("$_p")
done < <(git ls-files "$PLAN_GLOB" 2>/dev/null)
if ((${#PLANS[@]} < MIN_PLANS)); then
    echo "VACUOUS INPUT: found ${#PLANS[@]} tracked plan file(s) matching $PLAN_GLOB, floor is $MIN_PLANS." >&2
    echo "  The glob lost the corpus; refusing a verdict rather than reporting a clean tree." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# THE SHALLOW REFUSAL, and it is measured against THE PLANS rather than against
# the repository. Third iteration, because the first two asked the wrong question.
#
#   1. `git rev-parse --is-shallow-repository` alone. It answers on the EXISTENCE
#      of .git/shallow, which `git fetch --unshallow` can leave behind empty.
#   2. "any graft at all". Correct but far too wide: CI job 100507628220 measured
#      90 commits reachable and 1 graft, and refused -- in the lane its own error
#      message recommends -- while every plan file's history was entirely present.
#      `agent/` has only been a tracked directory since 2026-08-18, so nothing in
#      this corpus is older than the boundary.
#
# A graft only corrupts THIS gate when a plan's last commit IS the boundary,
# because that is the case where `git log -1` reports the graft's date instead of
# the file's. So ask exactly that, per plan. A deepened clone that contains every
# plan's history answers correctly and is allowed to.
GRAFTS_FILE="$(git rev-parse --git-path shallow 2>/dev/null)"
SKIP_AGES=0
GRAFTED_PLANS=()
if [[ -n "$GRAFTS_FILE" && -s "$GRAFTS_FILE" ]]; then
    for _p in "${PLANS[@]}"; do
        _last="$(git log -1 --format=%H -- "$_p" 2>/dev/null)"
        # A plan whose last commit is a graft boundary reports the boundary's
        # date. A plan with NO commit at all is the same failure, louder.
        if [[ -z "$_last" ]] || grep -qxF "$_last" "$GRAFTS_FILE" 2>/dev/null; then
            GRAFTED_PLANS+=("$_p")
        fi
    done
fi

if ((${#GRAFTED_PLANS[@]} > 0)); then
    if [[ "${CI:-}" == "true" ]]; then
        echo -e "${RED}✗${NC} plan housekeeping: this checkout is SHALLOW at a boundary that ${#GRAFTED_PLANS[@]} plan(s)" >&2
        echo "  sit on, so they report the GRAFT commit's date and the age verdict would be" >&2
        echo "  fiction. Refusing rather than answering." >&2
        printf '    %s\n' "${GRAFTED_PLANS[@]}" >&2
        echo "  Fix: the step must run in a job whose actions/checkout carries" >&2
        echo "    fetch-depth: 0" >&2
        echo "    filter: blob:none" >&2
        echo "  Measured: $(git rev-list --count HEAD 2>/dev/null) commit(s) reachable, and" >&2
        echo "  $GRAFTS_FILE holds $(wc -l <"$GRAFTS_FILE" 2>/dev/null || echo 0) graft(s)." >&2
        exit 1
    fi
    echo -e "${YEL}⚠${NC} plan housekeeping: ${#GRAFTED_PLANS[@]} plan(s) sit on a shallow boundary"
    echo "  ($(git rev-list --count HEAD) commit(s) reachable); their AGE verdict is DEFERRED."
    echo "  To run it here: git fetch --unshallow --filter=blob:none"
    SKIP_AGES=1
elif [[ -n "$GRAFTS_FILE" && -s "$GRAFTS_FILE" ]]; then
    echo "  note: the clone is shallow ($(wc -l <"$GRAFTS_FILE") graft(s), $(git rev-list --count HEAD) commit(s)),"
    echo "  but every plan's last commit is present, so the age verdict below is real."
fi

# ---------------------------------------------------------------------------
# The allowlist, and its three liveness rules. Every entry must NAME something,
# must actually be suppressing something, and dies on its own stated date. Rule
# three alone is what stops this becoming a dumping ground: an entry cannot
# outlive the argument for it without being re-argued.
# ---------------------------------------------------------------------------
declare -A EXEMPT_UNTIL=()
ALLOW_PROBLEMS=()
if [[ -f "$ALLOWLIST" ]]; then
    reason=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" =~ ^[[:space:]]*#[[:space:]]*BLOCKER: ]]; then
            reason="${line#*BLOCKER:}"
            continue
        fi
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// /}" ]] && continue
        read -r expiry path <<<"$line"
        if [[ -z "${path:-}" ]]; then
            ALLOW_PROBLEMS+=("malformed entry '$line' (want: YYYY-MM-DD  path)")
            continue
        fi
        if [[ -z "${reason// /}" ]] || ((${#reason} < 40)); then
            ALLOW_PROBLEMS+=("$path carries no substantive '# BLOCKER:' line above it")
            reason=""
            continue
        fi
        EXEMPT_UNTIL["$path"]="$expiry"
        reason=""
    done <"$ALLOWLIST"
fi

# ---------------------------------------------------------------------------
# The verdict.
# ---------------------------------------------------------------------------
OFFENDERS=() WARNINGS=() N_EXEMPT=0
TODAY=$(date -u +%Y-%m-%d)

# ONE python start for the whole corpus, not two per plan. The first cut spawned
# `age_days` and a red-on date per file; on a 70-plan tree that is 140 interpreter
# starts, and check:ci-gate-manifest caught the selftest at 33.5s because of it.
# The dates come out of a single `git log` per file (unavoidable) and one batch
# conversion, which took the gate-test from 33.5s to under a second.
AGE_TSV=""
if [[ "$SKIP_AGES" == 0 ]]; then
    for p in "${PLANS[@]}"; do
        when=$(git log -1 --format=%cI -- "$p" 2>/dev/null)
        [[ -n "$when" ]] && AGE_TSV+="$p	$when"$'\n'
    done
    AGE_TSV=$(printf '%s' "$AGE_TSV" | python3 -c "
import datetime as dt, sys
now = dt.datetime.now(dt.UTC)
delete_days = int(sys.argv[1])
for line in sys.stdin:
    line = line.rstrip('\n')
    if not line:
        continue
    path, _, when = line.partition('\t')
    try:
        then = dt.datetime.fromisoformat(when)
    except ValueError:
        continue
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.UTC)
    days = (now - then).days
    red = (then + dt.timedelta(days=delete_days)).date().isoformat()
    print('%s\t%d\t%s' % (path, days, red))
" "$DELETE_DAYS")
fi

while IFS=$'\t' read -r p days red_on; do
    [[ -n "${p:-}" ]] || continue
    status=$(sed -n 's/^[[:space:]]*\(\*\*\)\?Status[[:space:]]*[:=][[:space:]]*\(\*\*\)\?\([A-Za-z][A-Za-z-]*\).*/\3/p' "$p" | head -1)
    if [[ -n "${EXEMPT_UNTIL[$p]:-}" ]]; then
        exp="${EXEMPT_UNTIL[$p]}"
        if [[ "$TODAY" > "$exp" ]]; then
            OFFENDERS+=("$p|$days|$red_on|${status:-UNKNOWN}|the allowlist entry EXPIRED on $exp")
        elif ((days < DELETE_DAYS)); then
            ALLOW_PROBLEMS+=("$p is exempted until $exp but is only $days day(s) old -- the entry suppresses nothing. Delete it.")
        else
            N_EXEMPT=$((N_EXEMPT + 1))
        fi
        continue
    fi
    if ((days >= DELETE_DAYS)); then
        OFFENDERS+=("$p|$days|$red_on|${status:-UNKNOWN}|")
    elif ((days >= WARN_DAYS)); then
        WARNINGS+=("$p|$days|$red_on|${status:-UNKNOWN}")
    fi
done <<<"$AGE_TSV"

for p in "${!EXEMPT_UNTIL[@]}"; do
    git ls-files --error-unmatch "$p" >/dev/null 2>&1 ||
        ALLOW_PROBLEMS+=("$p is allowlisted but is not a tracked plan file. Delete the line; the plan is gone.")
done

RC=0
if ((${#ALLOW_PROBLEMS[@]})); then
    echo -e "${RED}✗${NC} plan housekeeping: ${#ALLOW_PROBLEMS[@]} allowlist problem(s):" >&2
    for m in "${ALLOW_PROBLEMS[@]}"; do echo "    $m" >&2; done
    RC=1
fi

if ((${#OFFENDERS[@]})); then
    echo -e "${RED}✗${NC} plan housekeeping: ${#OFFENDERS[@]} plan file(s) unchanged for more than $DELETE_DAYS days" >&2
    for row in "${OFFENDERS[@]}"; do
        IFS='|' read -r p days _red st extra <<<"$row"
        printf '    %-52s %3s days  Status: %s %s\n' "$p" "$days" "$st" "$extra" >&2
    done
    cat >&2 <<MSG

  Fix, in order of preference:

  1. WORK ON IT. A commit touching the file resets the clock. There is no
     "mark it fresh" edit -- an empty touch is a lie the log records.

  2. DELETE IT, if the plan is finished or abandoned:
       git rm <path>
     FIRST check nothing cites it -- a dangling citation is a regression:
       git grep -n '<plan-slug>' -- ':!<path>'

  3. EXEMPT IT, only if it must outlive $DELETE_DAYS days on purpose. Add to
     $(basename "$ALLOWLIST"):
       # BLOCKER: <why this plan must stay, and what makes that true>
       2026-12-01  agent/PLAN-example.md
     The date is a HARD expiry: it goes red again on that date whether or not
     anyone looked. An entry whose plan is under $DELETE_DAYS days, or whose
     path no longer exists, is REFUSED -- an exemption must suppress something.
MSG
    RC=1
fi

if ((${#WARNINGS[@]})); then
    echo -e "${YEL}⚠${NC} ${#WARNINGS[@]} plan(s) will cross $DELETE_DAYS days soon:"
    for row in "${WARNINGS[@]}"; do
        IFS='|' read -r p days red st <<<"$row"
        printf '    %-52s %3s days  Status: %-12s red on %s\n' "$p" "$days" "$st" "$red"
    done
fi

if ((RC == 0)); then
    if [[ "$SKIP_AGES" == 1 ]]; then
        echo -e "${GREEN}✓${NC} plan housekeeping: ${#PLANS[@]} tracked plan file(s) (floor $MIN_PLANS), $N_EXEMPT exempt."
        echo "  PARTIAL RUN: the age verdict was skipped (shallow clone), not passed."
    else
        echo -e "${GREEN}✓${NC} plan housekeeping: ${#PLANS[@]} tracked plan file(s) (floor $MIN_PLANS), none over $DELETE_DAYS days, ${#WARNINGS[@]} within $((DELETE_DAYS - WARN_DAYS)) days, $N_EXEMPT exempt."
    fi
fi
exit "$RC"
