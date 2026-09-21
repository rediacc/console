#!/bin/bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-plan-housekeeping is now registered to the Python port's entry point,
# .ci/scripts/quality/check_plan_housekeeping.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs ".ci/scripts/quality/check_plan_housekeeping.py" but its header derives ".ci/scripts/quality/check-plan-housekeeping.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

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
# W12: THE REMEDY IS NO LONGER "DELETE IT", AND THAT WORD IS GONE ON PURPOSE.
# The operator's standing rule is that nothing is deleted, so this gate spent its
# whole life demanding an act nobody was allowed to perform -- and the only escape
# was the allowlist, which is a suppression rather than an answer. The third door
# is COMPACTION: `worklist.py --plan-compact` replaces a finished plan with an
# attested record that KEEPS ITS OWN PATH, so every citation still resolves, while
# the full text moves into a git blob (content-addressed, so `gh pr merge --rebase`
# cannot break the pointer -- measured 2026-09-06, 37 of 71 commit-shaped tokens
# already cited in plans no longer resolve).
#
# A `Status: compacted` plan whose `Full-Text-Blob:` RESOLVES is exempt here and
# counted separately. The resolution test is the whole exemption: a record whose
# blob is missing is worse than the deleted plan it replaced, because it advertises
# a recovery command that silently returns nothing, so it is reported as an
# OFFENDER rather than waved through on the strength of its own header word.
# `Status: parked` -- a plan whose text is compacted while its work is NOT finished
# -- stays on the clock. Parking buys a smaller file, never an exemption.
#
# The pointer itself is checked in depth by check:ci-plan-record, which needs
# fetch-depth 0 and the PR head ref. This gate only asks "does the blob exist",
# which is the cheap half and the half that decides the exemption.
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
ALLOWLIST="${PLAN_HK_ALLOWLIST:-$ROOT_DIR/.ci/policy/.plan-housekeeping-allowlist}"
# Floor. Measured 2026-09-03: 70 tracked plans. Well under it on purpose -- this
# guards against the glob losing the corpus, not against ordinary housekeeping.
MIN_PLANS="${PLAN_HK_MIN_FILES:-30}"

[[ -f "$CFG" ]] || {
    echo "VACUOUS INPUT: $CFG is missing, so no threshold can be read" >&2
    exit 1
}
WARN_DAYS=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['warn_days'])" "$CFG") || exit 2
DELETE_DAYS=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['delete_days'])" "$CFG") || exit 2
# A LIST OF GLOBS, NOT ONE, since a plan gained folders (2026-09-21). The two
# terminal folders are deliberately absent: a closed plan under
# `agent/plans/_done/` is on the 40-day retention clock check:ci-plan-folders
# owns, and demanding its compaction on the way to its deletion would be two
# gates pulling one file in opposite directions. Newline-separated so a glob
# containing a space could never split into two pathspecs.
PLAN_GLOBS=$(python3 -c "import json,sys;print('\n'.join(json.load(open(sys.argv[1]))['plan_globs']))" "$CFG") || exit 2
[[ -n "$PLAN_GLOBS" ]] || {
    echo "VACUOUS INPUT: $CFG carries no plan_globs, so the corpus would be empty" >&2
    exit 2
}
# The `Status:` word a POINTER carries. A move leaves one at the old path so
# every citation still resolves, and a pointer is not a plan: on this clock it
# would go red 33 days after a migration that closed nothing, and the only
# remedy offered would be to compact a file three lines long.
STUB_STATUS=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['stub_status'])" "$CFG") || exit 2
[[ -n "$STUB_STATUS" ]] || {
    echo "VACUOUS INPUT: $CFG carries no stub_status, so every pointer would be judged as a plan" >&2
    exit 2
}
# W12 P3.3. THE RECORD-STATUS VOCABULARY COMES FROM THE CONFIG, not from a
# literal in the sed below. It used to be the alternation `compacted\|parked`
# typed here, again in `.ci/rediacc_ci/quality/plan_housekeeping.py` and a third
# time verbatim in `.ci/rediacc_ci/tests/test_quality_plan_housekeeping.py`.
# Adding a state meant finding all three, and missing one makes a plan a RECORD
# in one reader and an OFFENDER in the other -- the exact disagreement
# record_status()'s own comment warns about. The config is a MIRROR of
# `wl_planrec.RECORD_STATES`; the mirror is compared against the origin in both
# directions by the twin test, because a mirror nobody compares is a fourth copy.
RECORD_STATES_ALT=$(python3 -c "import json,sys;print(r'\\|'.join(json.load(open(sys.argv[1]))['record_states']))" "$CFG") || exit 2
[[ -n "$RECORD_STATES_ALT" ]] || {
    echo "VACUOUS INPUT: $CFG carries no record_states, so no plan could ever be read as a" >&2
    echo "  compaction record and every compacted plan would lose its exemption at once." >&2
    exit 2
}

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

# W12. The compaction exemption, as two tiny functions so the controls below can
# drive them on synthetic input. Kept textual rather than shelling out to the
# record parser: this gate must stay runnable in a checkout where .claude/ is
# absent, and the only question it asks is whether a 40-hex blob exists.
record_blob() { # <plan file> -> the Full-Text-Blob, or nothing
    # ANCHORED AT END OF LINE, matching wl_planrec.FULLTEXT_BLOB_RE. A trailing
    # `.*` accepted `Full-Text-Blob: <41 hex>` by reading the first 40 characters
    # of it, so a value the strict gate REJECTS would have been exempted here --
    # the two readers of one header disagreeing is how a plan ends up exempt in
    # one place and red in the other.
    sed -n '1,10s/^Full-Text-Blob:[[:space:]]*\([0-9a-f]\{40\}\)[[:space:]]*$/\1/p' "$1" | head -1
}
record_status() { # <plan file> -> `compacted` / `parked`, or nothing
    # THE SAME 10-LINE WINDOW every status regex in this repo reads
    # (wl_checks.PLAN_HEADER_LINES). The general status sed below deliberately
    # scans the whole file -- it is for DISPLAY and some plans put their header
    # low -- but this one decides an EXEMPTION, so it must agree with
    # wl_planrec.parse exactly. Otherwise a plan whose prose quotes
    # `Status: compacted` routes into the compacted branch and is reported as an
    # offender regardless of its age.
    sed -n "1,10s/^Status:[[:space:]]*\($RECORD_STATES_ALT\)[[:space:]]*\$/\1/p" "$1" | head -1
}
display_status() { # <plan file> -> the first Status: anywhere in the file
    # WHOLE FILE, deliberately, unlike record_status above: some plans put their
    # header low and this one is for DISPLAY and for the stub filter, neither of
    # which decides an exemption. Lifted out of the report loop when the corpus
    # filter grew a second caller, so the two cannot read a status differently.
    sed -n 's/^[[:space:]]*\(\*\*\)\?Status[[:space:]]*[:=][[:space:]]*\(\*\*\)\?\([A-Za-z][A-Za-z-]*\).*/\3/p' "$1" | head -1
}
blob_is_real() { # <blob> -> 0 when git has it AS A BLOB
    [[ -n "${1:-}" ]] || return 1
    [[ "$(git cat-file -t "$1" 2>/dev/null)" == "blob" ]]
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
# W12 controls, BOTH DIRECTIONS. The exemption is the only thing in this gate
# that can turn a red into a green, so a broken extractor would silently exempt
# nothing (noisy, survivable) or -- far worse -- a broken blob_is_real would
# exempt every plan carrying the word `compacted`. Both are planted here.
_ctl=$(mktemp)
# THE CONTROL IS HERMETIC, and two rejected alternatives are why. `git
# hash-object` without `-w` computes an id and writes nothing, so `cat-file -t`
# misses and the control fails for the wrong reason. Reading a blob out of HEAD's
# tree works in this repository and FAILS IN AN EMPTY FIXTURE -- measured: it
# turned the gate-test's "an empty tree must fail" case from exit 1 into exit 2,
# which is the case that proves PLAN_HK_ROOT is not an escape hatch. So the
# control mints its own blob in a scratch repository it throws away. Nothing is
# written to the repository being judged, and the control holds whatever state
# that repository is in, which is the property a control needs most.
_ctldir=$(mktemp -d)
git init -q "$_ctldir" 2>/dev/null
_self_blob=$(printf 'a control blob\n' | git -C "$_ctldir" hash-object -w --stdin 2>/dev/null)
[[ -n "$_self_blob" ]] || {
    echo "control: could not mint a scratch blob, so the exemption cannot be proven" >&2
    CONTROL_FAIL=1
}
printf '# t\nStatus: compacted\nFull-Text-Blob: %s\nRecord-Sig: 00000000\n' "$_self_blob" >"$_ctl"
[[ "$(record_blob "$_ctl")" == "$_self_blob" ]] || {
    echo "control: record_blob did not read the blob out of a record header" >&2
    CONTROL_FAIL=1
}
# blob_is_real reads the repository it is RUN IN, so both directions are driven
# inside the scratch one. Subshells rather than a cd/cd-back pair: an early exit
# between them would otherwise leave the whole gate judging the wrong tree.
(cd "$_ctldir" && blob_is_real "$_self_blob") || {
    echo "control: blob_is_real refused a blob git demonstrably has" >&2
    CONTROL_FAIL=1
}
(cd "$_ctldir" && blob_is_real "0000000000000000000000000000000000000000") && {
    echo "control: blob_is_real accepted an all-zero blob, so the exemption is unconditional" >&2
    CONTROL_FAIL=1
}
[[ "$(record_status "$_ctl")" == "compacted" ]] || {
    echo "control: record_status did not read a compacted header" >&2
    CONTROL_FAIL=1
}
printf '# t\nStatus: compacted\nno pointer here\n' >"$_ctl"
[[ -z "$(record_blob "$_ctl")" ]] || {
    echo "control: record_blob invented a blob for a record that carries none" >&2
    CONTROL_FAIL=1
}
# A 41-hex value must be REFUSED, not silently truncated to 40. The strict gate
# rejects it, and a reader that accepted it would exempt a plan CI reds.
printf '# t\nStatus: compacted\nFull-Text-Blob: %sf\n' "$_self_blob" >"$_ctl"
[[ -z "$(record_blob "$_ctl")" ]] || {
    echo "control: record_blob accepted a 41-hex pointer by truncating it" >&2
    CONTROL_FAIL=1
}
# The word in PROSE must not exempt anything: only an anchored header line does.
printf '# t\nStatus: draft\n\nWe should set Status: compacted here one day.\n' >"$_ctl"
[[ -z "$(record_status "$_ctl")" ]] || {
    echo "control: record_status read a status out of prose" >&2
    CONTROL_FAIL=1
}
# ...and a real header BELOW the window must not either.
{
    echo "# t"
    for _i in 1 2 3 4 5 6 7 8 9 10; do echo "filler $_i"; done
    echo "Status: compacted"
} >"$_ctl"
[[ -z "$(record_status "$_ctl")" ]] || {
    echo "control: record_status read a status from below the 10-line window" >&2
    CONTROL_FAIL=1
}
# The 10-line window is the same one every status regex in this repo reads
# (wl_checks.PLAN_HEADER_LINES). A pointer below it is a pointer no consumer can
# see, and must not exempt anything.
{
    echo "# t"
    echo "Status: compacted"
    for _i in 1 2 3 4 5 6 7 8 9 10; do echo "filler $_i"; done
    printf 'Full-Text-Blob: %s\n' "$_self_blob"
} >"$_ctl"
[[ -z "$(record_blob "$_ctl")" ]] || {
    echo "control: record_blob read a pointer from below the 10-line header window" >&2
    CONTROL_FAIL=1
}
rm -f "$_ctl"
rm -rf "$_ctldir"

if [[ "$CONTROL_FAIL" == 1 ]]; then
    echo -e "${RED}✗${NC} instrument control failed; every verdict below would be meaningless" >&2
    exit 2
fi
echo "✓ control: the age arithmetic reports over and under the threshold, and refuses a bad date"
echo "✓ control: the compaction exemption reads a real pointer and a real header, refuses a fake blob, a 41-hex blob, a status in prose, and anything below line 10"

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
GLOB_ARGS=()
while IFS= read -r _g; do
    [[ -n "$_g" ]] && GLOB_ARGS+=("$_g")
done <<<"$PLAN_GLOBS"
PLANS=()
while IFS= read -r _p; do
    [[ -n "$_p" ]] || continue
    [[ "$(display_status "$_p")" == "$STUB_STATUS" ]] && continue
    PLANS+=("$_p")
done < <(git ls-files "${GLOB_ARGS[@]}" 2>/dev/null)
if ((${#PLANS[@]} < MIN_PLANS)); then
    echo "VACUOUS INPUT: found ${#PLANS[@]} tracked plan file(s) matching ${GLOB_ARGS[*]}, floor is $MIN_PLANS." >&2
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
OFFENDERS=() WARNINGS=() N_EXEMPT=0 N_COMPACTED=0
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
    status=$(display_status "$p")
    # W12. Checked BEFORE the allowlist and before the age thresholds, because a
    # compacted record is not being suppressed and is not waiting for a date -- it
    # has already been dealt with, and the age of a record is not a defect. Note
    # that `parked` deliberately does NOT appear here: its work is unfinished, so
    # it falls through to the ordinary clock.
    if [[ "$(record_status "$p")" == "compacted" ]]; then
        _blob=$(record_blob "$p")
        if blob_is_real "$_blob"; then
            # The allowlist's third liveness rule -- an entry must actually be
            # suppressing something -- reaches this plan only from HERE, because
            # the `continue` below skips the allowlist branch. Compaction is a
            # BETTER exemption than a dated suppression, so an entry that
            # survives it is dead weight with an expiry date, and dead weight in
            # a suppression file is how that file becomes a dumping ground.
            if [[ -n "${EXEMPT_UNTIL[$p]:-}" ]]; then
                ALLOW_PROBLEMS+=("$p is COMPACTED, so the allowlist entry (expires ${EXEMPT_UNTIL[$p]}) suppresses nothing. Delete the line; the record's blob is what exempts it now.")
            fi
            N_COMPACTED=$((N_COMPACTED + 1))
            continue
        fi
        # A BROKEN RECORD IS STILL ALLOWLISTABLE. The first cut reported it and
        # `continue`d past the allowlist branch, so remedy step 3 did not work
        # for the one case where a session might genuinely need it (a blob this
        # checkout does not have yet, e.g. mid-rebase or a partial clone), and
        # that plan's allowlist entry was never liveness-checked either. An
        # unexpired entry suppresses it; an expired one does not.
        if [[ -n "${EXEMPT_UNTIL[$p]:-}" && ! "$TODAY" > "${EXEMPT_UNTIL[$p]}" ]]; then
            N_EXEMPT=$((N_EXEMPT + 1))
            continue
        fi
        OFFENDERS+=("$p|$days|$red_on|compacted|its Full-Text-Blob ${_blob:-is missing and} does not resolve, so its full text is UNRECOVERABLE")
        continue
    fi
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

  Fix, in order of preference. NOTHING HERE ASKS YOU TO DELETE A PLAN: the
  operator's standing rule is that nothing is deleted, and a gate demanding an
  act nobody may perform is a gate whose only exit is a suppression.

  1. WORK ON IT. A commit touching the file resets the clock. There is no
     "mark it fresh" edit -- an empty touch is a lie the log records.

  2. COMPACT IT, if the plan is finished. The file KEEPS ITS PATH, so every
     citation of it still resolves, and its full text moves into a git blob
     that a plain \`git show\` recovers for as long as the repository exists:
       .claude/hooks/stop/worklist.py --plan-compact <me> <path> --why auto
       .claude/hooks/stop/worklist.py --plan-compact <me> <path> --write
     The first run prints the record without writing it; read it, then write.
     A plan with open boxes is refused unless you pass --park, which records
     it as \`parked\` and deliberately KEEPS it on this clock -- parking buys a
     smaller file, never an exemption.
     Land it with its ledger and its index in the SAME commit, or two gates
     will disagree with each other:
       npm run check:ci-plan-boxes  -- --update
       npm run check:ci-plan-record -- --update

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
        echo -e "${GREEN}✓${NC} plan housekeeping: ${#PLANS[@]} tracked plan file(s) (floor $MIN_PLANS), $N_EXEMPT exempt, $N_COMPACTED compacted."
        echo "  PARTIAL RUN: the age verdict was skipped (shallow clone), not passed."
    else
        echo -e "${GREEN}✓${NC} plan housekeeping: ${#PLANS[@]} tracked plan file(s) (floor $MIN_PLANS), none over $DELETE_DAYS days, ${#WARNINGS[@]} within $((DELETE_DAYS - WARN_DAYS)) days, $N_EXEMPT exempt, $N_COMPACTED compacted (their full text is in a blob; check:ci-plan-record verifies the pointer)."
    fi
fi
exit "$RC"
