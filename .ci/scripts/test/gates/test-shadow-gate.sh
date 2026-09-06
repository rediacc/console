#!/bin/bash
# The shadow comparator (scripts/lib/shadow-gate.ts) proves ports equivalent, so
# the question this file exists to answer is who proves the comparator.
#
# WHY THAT IS THE WHOLE POINT. A comparator that cannot report a mismatch is
# worse than no comparator, because it does not merely fail to help -- it
# LAUNDERS every port that follows it. Seventy-four bash quality gates and 131
# gate tests are scheduled to move behind this thing. If it says EQUIVALENT
# unconditionally, all 205 of those moves acquire a green artifact and nobody
# looks again. The failure would be silent, would look like success, and would
# be discovered as a missing gate months later.
#
# So this file asserts in BOTH directions, and neither direction is optional:
#
#   IT MUST FIRE.  Real divergences, on real code, are reported and NAMED. Three
#                  kinds: a documented divergence between two live
#                  implementations, a one-line plant, and total blindness.
#   IT MUST BE QUIET. A genuine match across language, stream, marker and order
#                  is EQUIVALENT. Without this half, "always mismatch" passes
#                  every firing test and is equally useless.
#   ITS OWN SELFTEST MUST BE ABLE TO FAIL. The three MUTATION CONTROLS below
#                  break one load-bearing line each in a COPY of the module and
#                  require the copy's selftest to go red. A selftest that passes
#                  against a broken comparator is decoration.
#
# THE PILOT PAIR IS REAL, NOT A FIXTURE. `.ci/scripts/lib/blocker-validator.sh`
# and `scripts/lib/blocker-validator.ts` are two live implementations of one
# rule, scheduled to collapse under W4. `.ci/breakpoint/lib/breakpoint-blocker.sh`
# is a third, DELIBERATELY a subset, and its five recorded divergences from the
# canonical one (`test-blocker-golden-corpus.sh:20-33`) are used here as a
# divergence nobody planted. The corpus is lifted verbatim from that same file.
#
# NOTHING HERE WRITES TO THE TRACKED TREE. Every fixture, every mutated copy and
# every ledger lives in a mktemp directory. `.ci/scripts/test/run-all.sh:398-427`
# snapshots git status around the battery and reds on any tracked change, and a
# comparator whose test dirties the tree would also make its own rule-4 case
# untestable.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

LIB="$REPO_ROOT/scripts/lib/shadow-gate.ts"
# The workspace binary rather than `npx`: npx re-resolves the package on every
# call and prints an unrelated "Unknown project config minimum-release-age"
# warning on stderr, which would land in output this file reads. Same reasoning
# as test-policy-path.sh:44-47.
TSX="$REPO_ROOT/node_modules/.bin/tsx"
[[ -x "$TSX" ]] || log_fail "tsx not installed at $TSX (run npm install)"
[[ -f "$LIB" ]] || log_fail "the subject is missing: $LIB"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/shadow-gate-test-XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# Run the comparator, capturing stdout and stderr SEPARATELY into $SG_OUT and
# $SG_ERR and the status into $SG_RC. Never `2>&1`: a stream swap is a class of
# defect this repo has actually shipped (see .ci/scripts/lib/emit-advisory.sh:22-52),
# and merging is how a test stops being able to see it.
SG_OUT=""
SG_ERR=""
SG_RC=0
sg() {
    local subject="${SG_SUBJECT:-$LIB}"
    SG_RC=0
    (cd "$REPO_ROOT" && "$TSX" "$subject" "$@") >"$WORK/out" 2>"$WORK/err" || SG_RC=$?
    SG_OUT="$(cat "$WORK/out")"
    SG_ERR="$(cat "$WORK/err")"
}

# ---------------------------------------------------------------------------
# Fixtures: two live implementations of one rule, each wrapped as a gate.
# ---------------------------------------------------------------------------

CORPUS="$WORK/corpus.txt"
CORPUS_CLEAN="$WORK/corpus-clean.txt"
GOLDEN="$SCRIPT_DIR/test-blocker-golden-corpus.sh"

build_corpus() {
    [[ -f "$GOLDEN" ]] || log_fail "the recorded corpus is missing: $GOLDEN"
    sed -n "/^read -r -d '' CORPUS/,/^EOF\$/p" "$GOLDEN" |
        grep -v "^read -r\|^EOF" | grep . |
        awk -F'|' '{print $1"|"$2}' >"$CORPUS" || true
    # The accepting subset: nothing for either side to find. This is the tree a
    # blind port gets blessed on, which is why rule 2 has to refuse it.
    grep '^real-\|^len-30' "$CORPUS" >"$CORPUS_CLEAN" || true
    local n
    n=$(grep -c . "$CORPUS")
    # A collapsed corpus would make every case below vacuously green.
    ((n >= 14)) || log_fail "corpus collapsed to $n case(s); the recorded floor is 14"
}

# The bash twin, in gate shape: one `✗` finding per rejected reason, on stderr,
# the reason KIND read back out of the implementation's own message.
write_gate_bash() {
    cat >"$WORK/gate-bash.sh" <<'EOF'
#!/bin/bash
set -uo pipefail
LIB="$1"; CORPUS="$2"
source "$LIB"
n=0
while IFS='|' read -r id reason; do
    [ -z "$id" ] && continue
    if out=$(validate_blocker_quality "$id" "$reason" "corpus.txt" 2>&1); then continue; fi
    case "$out" in
        *"low-effort placeholder"*) kind="low-effort" ;;
        *"defers a routine bump"*)  kind="deferral" ;;
        *"is too short"*)           kind="too-short" ;;
        *)                          kind="UNCLASSIFIED" ;;
    esac
    echo "✗ corpus.txt: $id rejected as $kind" >&2
    n=$((n+1))
done < "$CORPUS"
echo "→ $n rejected reason(s)"
[ "$n" -eq 0 ] || exit 1
EOF
    # The vendored SUBSET. Never edited -- it is drift-locked by
    # check-breakpoint-drift.sh and vendored into other repositories.
    cat >"$WORK/gate-bp.sh" <<'EOF'
#!/bin/bash
set -uo pipefail
LIB="$1"; CORPUS="$2"; COMMON="$3"
source "$COMMON" >/dev/null 2>&1
source "$LIB"
n=0
while IFS='|' read -r id reason; do
    [ -z "$id" ] && continue
    if out=$(bp_validate_blocker "$id" "$reason" 2>&1); then continue; fi
    case "$out" in
        *"low-effort placeholder"*) kind="low-effort" ;;
        *"is too short"*)           kind="too-short" ;;
        *)                          kind="UNCLASSIFIED" ;;
    esac
    echo "✗ corpus.txt: $id rejected as $kind" >&2
    n=$((n+1))
done < "$CORPUS"
echo "→ $n rejected reason(s)"
[ "$n" -eq 0 ] || exit 1
EOF
}

# The TypeScript twin, in gate shape. DELIBERATELY DIFFERENT on every axis a
# port is allowed to differ on: `::error::` instead of `✗`, stdout instead of
# stderr, reverse order, and a different progress line. If the comparator scores
# this as a mismatch it is comparing bytes, and every real port would be red.
write_gate_ts() {
    cat >"$WORK/gate-ts.ts" <<'EOF'
import fs from 'node:fs';
async function main(): Promise<number> {
  const [lib, corpus] = process.argv.slice(2);
  const { validateBlockerQuality } = await import(lib);
  const rows = fs.readFileSync(corpus, 'utf-8').split('\n').filter((l) => l.trim() !== '');
  const out: string[] = [];
  for (const row of rows) {
    const i = row.indexOf('|');
    const r = validateBlockerQuality(row.slice(0, i), row.slice(i + 1), 'corpus.txt');
    if (r !== null) out.push(`::error::corpus.txt: ${row.slice(0, i)} rejected as ${r.kind}`);
  }
  process.stdout.write(`→ inspected ${rows.length} entries in 7ms\n`);
  for (const line of out.reverse()) process.stdout.write(`${line}\n`);
  return out.length === 0 ? 0 : 1;
}
main().then((c) => process.exit(c));
EOF
}

OLD_SIDE=""
NEW_SIDE=""
BP_SIDE=""
build_sides() {
    OLD_SIDE="bash $WORK/gate-bash.sh $REPO_ROOT/.ci/scripts/lib/blocker-validator.sh $CORPUS"
    NEW_SIDE="$TSX $WORK/gate-ts.ts $REPO_ROOT/scripts/lib/blocker-validator.ts $CORPUS"
    BP_SIDE="bash $WORK/gate-bp.sh $REPO_ROOT/.ci/breakpoint/lib/breakpoint-blocker.sh $CORPUS $REPO_ROOT/.ci/breakpoint/lib/breakpoint-common.sh"
}

# ---------------------------------------------------------------------------
# The module's own selftest, and the three controls proving it can fail
# ---------------------------------------------------------------------------

test_selftest_battery() {
    sg --selftest
    assert_exit_code 0 "$SG_RC" "the module selftest must pass"
    local n
    n=$(printf '%s\n' "$SG_OUT" | grep -c '^PASS: ' || true)
    # A FLOOR, not an exact count, so new cases may be added -- but a selftest
    # that quietly shrinks to two cases is the shape this whole file distrusts.
    ((n >= 20)) || log_fail "the selftest made $n assertion(s); the recorded floor is 20"
    [[ -z "$SG_ERR" ]] || log_fail "a passing selftest wrote to stderr: $SG_ERR"
    log_pass "the comparator's selftest passes with $n assertions and a silent stderr"
}

# Break ONE load-bearing line in a COPY and require the selftest to notice.
# $1 = label, $2 = sed expression, $3 = the case name that must go red.
assert_mutation_is_caught() {
    local label="$1" expr="$2" must_fail="$3"
    local copy="$WORK/mutant-$label.ts"
    sed "$expr" "$LIB" >"$copy"
    cmp -s "$LIB" "$copy" && log_fail "the $label mutation changed nothing; the sed no longer matches"
    SG_SUBJECT="$copy" sg --selftest
    ((SG_RC != 0)) || log_fail "the $label mutation was NOT caught: a broken comparator's selftest passed"
    printf '%s\n' "$SG_ERR" | grep -q "$must_fail" ||
        log_fail "the $label mutation went red, but not on '$must_fail'; got: $SG_ERR"
    log_pass "MUTATION CONTROL: breaking $label turns the selftest red on '$must_fail'"
}

test_mutation_controls() {
    # Rule 2. With the vacuity branch dead, both-empty falls through to the
    # equality test and is scored EQUIVALENT -- the exact laundering this module
    # exists to prevent.
    assert_mutation_is_caught 'the-vacuity-rule' \
        's/if (oldRun.findings.length === 0 \&\& newRun.findings.length === 0) {/if (false) {/' \
        'RULE 2'
    # Rule 3. With the blindness branch dead, a port that sees nothing is filed
    # under MISMATCH_EXIT, where a reviewer reads it as a numeric quibble.
    assert_mutation_is_caught 'the-blindness-rule' \
        's/if (newClean \&\& !oldClean) {/if (false) {/' \
        'RULE 3'
    # Invariant 5. With the K test dead, forty runs on one checkout satisfy K=40.
    assert_mutation_is_caught 'invariant-5' \
        's/if (distinctTrees.length < k) {/if (false) {/' \
        'INVARIANT 5'
}

# ---------------------------------------------------------------------------
# The real pair
# ---------------------------------------------------------------------------

test_real_pair_is_equivalent() {
    sg --pair t-match --old "$OLD_SIDE" --new "$NEW_SIDE"
    assert_exit_code 0 "$SG_RC" "the two live implementations must be EQUIVALENT"
    assert_contains "$SG_OUT" 'EQUIVALENT' 'the verdict'
    assert_contains "$SG_OUT" 'agreeing finding(s)' 'the summary names the agreeing set'
    # Both fingerprints equal is the strong form: identical normalized sets, not
    # merely sets the diff happened not to separate.
    local fps
    # `|| true`: under `set -euo pipefail` a `grep` that matches nothing exits 1
    # and aborts the script with no message. The `((fps == 1))` below is the
    # assertion, and it reports 0 far better than a silent abort does.
    fps=$(printf '%s\n' "$SG_OUT" | grep -o 'fp=[0-9a-f]*' | sort -u | wc -l || true)
    ((fps == 1)) || log_fail "EQUIVALENT was reported with $fps distinct fingerprints"
    log_pass "bash and TypeScript twins agree across stream, marker, order and wording"
}

test_real_pair_divergence_is_named() {
    sg --pair t-diverge --old "$OLD_SIDE" --new "$BP_SIDE"
    ((SG_RC == 1)) || log_fail "a real divergence must exit 1, got $SG_RC"
    assert_contains "$SG_OUT" 'MISMATCH_FINDINGS' 'the verdict'
    # The five recorded divergences: three where the vendored subset rejects for
    # a different REASON (so the case appears on both sides with different
    # kinds), and two where it accepts what the canonical validator rejects (so
    # the case appears only on the old side).
    local only_old only_new
    only_old=$(printf '%s\n' "$SG_OUT" | grep -c '^  only-old ' || true)
    only_new=$(printf '%s\n' "$SG_OUT" | grep -c '^  only-new ' || true)
    ((only_old == 5)) || log_fail "expected 5 old-only findings, got $only_old"
    ((only_new == 3)) || log_fail "expected 3 new-only findings, got $only_new"
    assert_contains "$SG_OUT" 'defer-dedicated rejected as deferral' 'the verdict-level divergence'
    assert_contains "$SG_OUT" 'banned-no-fix rejected as too-short' 'the reason-level divergence'
    log_pass "the documented vendored-subset divergence is reported as 5 old-only and 3 new-only findings"
}

test_planted_dropped_finding() {
    local planted="$WORK/planted-drop.ts"
    # One line removed from the port's banned-substring list. Nothing else.
    sed "s|^  'deferred to a dedicated dependency-bump pr',|  // PLANTED: line removed|" \
        "$REPO_ROOT/scripts/lib/blocker-validator.ts" >"$planted"
    cmp -s "$REPO_ROOT/scripts/lib/blocker-validator.ts" "$planted" &&
        log_fail "the plant changed nothing; the banned-substring list moved"

    sg --pair t-plant --old "$OLD_SIDE" --new "$TSX $WORK/gate-ts.ts $planted $CORPUS"
    ((SG_RC == 1)) || log_fail "a planted dropped finding must exit 1, got $SG_RC"
    assert_contains "$SG_OUT" 'MISMATCH_FINDINGS' 'the verdict'
    assert_contains "$SG_OUT" 'only-old  [error] corpus.txt: defer-dedicated rejected as deferral' \
        'the exact finding the plant removed'
    # THE ARGUMENT FOR COMPARING FINDINGS AT ALL. Both sides still exit 1 here,
    # so an exit-code-only comparator blesses this port.
    assert_contains "$SG_OUT" 'exit codes agree at 1' 'the exit codes still agree'
    log_pass "a one-line plant is caught and named, while the exit codes still agree"
}

test_planted_blindness_is_new_side_true() {
    local blind="$WORK/planted-blind.ts"
    sed "s|^export function validateBlockerQuality(|export function validateBlockerQuality_UNUSED(|" \
        "$REPO_ROOT/scripts/lib/blocker-validator.ts" >"$blind"
    cat >>"$blind" <<'EOF'
export function validateBlockerQuality(_e: string, _r: string, _f: string): null { return null; }
EOF
    sg --pair t-blind --old "$OLD_SIDE" --new "$TSX $WORK/gate-ts.ts $blind $CORPUS"
    ((SG_RC == 1)) || log_fail "a totally blind port must exit 1, got $SG_RC"
    assert_contains "$SG_OUT" 'NEW_SIDE_TRUE' 'the blindness class is named as itself'
    assert_not_contains "$SG_OUT" 'MISMATCH_EXIT' 'blindness must not be filed as an exit quibble'
    log_pass "a port that accepts everything is NEW_SIDE_TRUE, not a generic mismatch"
}

test_both_empty_refuses_to_bless() {
    # THE SCENARIO THIS RULE EXISTS FOR, run on real code: the same totally blind
    # port, over a corpus with nothing to find. Exit 0 on both sides, no output
    # on either. Every equality-based comparator calls this equivalence.
    local blind="$WORK/planted-blind.ts"
    sg --pair t-vacuous --old "bash $WORK/gate-bash.sh $REPO_ROOT/.ci/scripts/lib/blocker-validator.sh $CORPUS_CLEAN" \
        --new "$TSX $WORK/gate-ts.ts $blind $CORPUS_CLEAN"
    ((SG_RC == 1)) || log_fail "a both-empty comparison must not exit 0, got $SG_RC"
    assert_contains "$SG_OUT" 'VACUOUS_BOTH_EMPTY' 'the verdict'
    assert_contains "$SG_OUT" 'proves nothing' 'the message says why'
    assert_not_contains "$SG_OUT" 'EQUIVALENT' 'a vacuous comparison is never equivalence'
    log_pass "a blind port on a clean corpus is REFUSED, not blessed"
}

test_refusal_suspends_the_comparison() {
    # A gate that could not run exits non-zero with zero findings, which is the
    # same shape as a clean run. Filing that under either heading sends the
    # reader to the wrong problem.
    sg --pair t-refusal --old "$OLD_SIDE" \
        --new 'echo "VACUOUS INPUT: /x is not a git work tree" >&2; exit 1'
    ((SG_RC == 1)) || log_fail "a refusal must not exit 0, got $SG_RC"
    assert_contains "$SG_OUT" 'ERROR_REFUSAL' 'the verdict'
    assert_contains "$SG_OUT" 'refusal-new  VACUOUS INPUT' 'the refusal text is echoed back'
    log_pass "a gate refusing to report a verdict suspends the comparison instead of colouring it"
}

test_comment_ratio_is_recorded() {
    # Driver contract 5c: the differential artifact carries the comment-byte
    # ratio, and a port below 0.90 is refused. The two live implementations sit
    # at roughly 0.63 today, so this pair also demonstrates the floor biting.
    sg --pair t-comments --old "$OLD_SIDE" --new "$NEW_SIDE" \
        --old-file "$REPO_ROOT/.ci/scripts/lib/blocker-validator.sh" \
        --new-file "$REPO_ROOT/scripts/lib/blocker-validator.ts"
    assert_contains "$SG_OUT" 'comments  old=' 'the comment audit line'
    printf '%s\n' "$SG_OUT" | grep -q 'ratio=0\.[0-8]' ||
        log_fail "expected the recorded sub-0.90 ratio for this pair; got: $SG_OUT"
    assert_contains "$SG_OUT" 'below the 0.90 floor' 'the floor is named when it is missed'
    log_pass "the differential carries the comment-byte ratio and flags the 0.90 floor"
}

# ---------------------------------------------------------------------------
# The ledger: rule 4, and K distinct trees
# ---------------------------------------------------------------------------

# A throwaway repository whose HEAD tree we control. `git -c` rather than a
# config write, so nothing depends on the developer's identity.
# The fixture identity used by .ci/scripts/test/lib/git-fixture.sh:61-62.
# `-c` rather than a config write, so nothing depends on the developer's
# identity and .claude/hooks/pre-bash/block-unlinked-commit-author.sh has a
# recognised address to see.
tgit() { git -C "$1" -c user.email=fixture@example.invalid -c user.name=git-fixture -c commit.gpgsign=false "${@:2}"; }

# Record one observation in $1 over a fixture holding the ids in $2.
record_tree() {
    local repo="$1" ids="$2" msg="$3"
    printf '%s\n' "$ids" >"$repo/fixture.txt"
    tgit "$repo" add -A >/dev/null
    tgit "$repo" commit -q -m "$msg" >/dev/null
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k \
        --old "bash $WORK/tiny-gate.sh $repo/fixture.txt old" \
        --new "bash $WORK/tiny-gate.sh $repo/fixture.txt new" --record) >"$WORK/out" 2>"$WORK/err"
}

setup_k_repo() {
    # A two-implementation "gate" that agrees: one reports with `✗` on stderr,
    # the other with `::error::` on stdout in reverse order.
    cat >"$WORK/tiny-gate.sh" <<'EOF'
#!/bin/bash
set -uo pipefail
FIX="$1"; SIDE="$2"
lines=$(grep -c . "$FIX" || true)
if [ "$SIDE" = old ]; then
    while IFS= read -r id; do [ -n "$id" ] && echo "✗ fixture.txt: $id is bad" >&2; done <"$FIX"
else
    echo "→ $lines entries"
    tac "$FIX" | while IFS= read -r id; do [ -n "$id" ] && echo "::error::fixture.txt: $id is bad"; done
fi
[ "$lines" -eq 0 ] || exit 1
EOF
    # A FRESH directory per caller. The first version reused one path and the
    # dirty-tree case left an uncommitted file behind, so the next case re-inited
    # over it and every recording was refused for the previous test's reason.
    local repo
    repo="$(mktemp -d "$WORK/k-repo-XXXXXX")"
    tgit "$repo" init -q -b main >/dev/null 2>&1
    printf '%s\n' "$repo"
}

test_dirty_tree_is_refused_and_writes_nothing() {
    local repo
    repo="$(setup_k_repo)"
    record_tree "$repo" "alpha" "one"
    # Now dirty it. Nothing about the comparison changes; only the tree does.
    echo "uncommitted" >"$repo/scratch.txt"
    local rc=0
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair dirty \
        --old "bash $WORK/tiny-gate.sh $repo/fixture.txt old" \
        --new "bash $WORK/tiny-gate.sh $repo/fixture.txt new" --record) \
        >"$WORK/out" 2>"$WORK/err" || rc=$?
    ((rc == 3)) || log_fail "a --record over a dirty tree must exit 3, got $rc"
    assert_contains "$(cat "$WORK/out")" 'EQUIVALENT' 'the comparison itself still ran'
    assert_contains "$(cat "$WORK/err")" 'DIRTY' 'the refusal names the reason'
    assert_contains "$(cat "$WORK/err")" 'scratch.txt' 'the refusal names the offending path'
    [[ ! -f "$repo/.ci/shadow/dirty.jsonl" ]] || log_fail "a dirty tree WROTE a ledger row"
    log_pass "rule 4: an EQUIVALENT comparison over a dirty tree is refused (exit 3) and writes nothing"
}

test_k_counts_distinct_trees_not_runs() {
    local repo
    repo="$(setup_k_repo)"
    # Three recordings, ONE tree. The comparison is identical every time.
    record_tree "$repo" "alpha" "t1"
    local rc=0
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k \
        --old "bash $WORK/tiny-gate.sh $repo/fixture.txt old" \
        --new "bash $WORK/tiny-gate.sh $repo/fixture.txt new" --record) >/dev/null 2>&1 || rc=$?
    ((rc == 0)) || log_fail "the second recording on a clean tree should succeed, got $rc"
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k \
        --old "bash $WORK/tiny-gate.sh $repo/fixture.txt old" \
        --new "bash $WORK/tiny-gate.sh $repo/fixture.txt new" --record) >/dev/null 2>&1 || true

    local rows

    rows=$(grep -c . "$repo/.ci/shadow/k.jsonl")
    ((rows == 3)) || log_fail "expected 3 ledger rows, found $rows"

    rc=0
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k --assert --k 3) \
        >"$WORK/out" 2>"$WORK/err" || rc=$?
    ((rc == 1)) || log_fail "three runs on one tree must NOT satisfy K=3, got exit $rc"
    assert_contains "$(cat "$WORK/out")" '1 distinct clean tree(s)' 'the count is of trees, not rows'
    assert_contains "$(cat "$WORK/err")" 'Invariant 5' 'the refusal cites the invariant'
    log_pass "invariant 5: 3 ledger rows over 1 tree is 1 observation and does not satisfy K=3"

    # Two more trees, each with a DIFFERENT finding set.
    record_tree "$repo" "beta
gamma" "t2"
    record_tree "$repo" "delta
epsilon
zeta" "t3"
    rc=0
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k --assert --k 3) \
        >"$WORK/out" 2>"$WORK/err" || rc=$?
    ((rc == 0)) || log_fail "three distinct trees with distinct findings must satisfy K=3: $(cat "$WORK/err")"
    assert_contains "$(cat "$WORK/out")" '3 distinct clean tree(s)' 'the tree count'
    assert_contains "$(cat "$WORK/out")" '3 distinct finding set(s)' 'the fingerprint count'
    log_pass "CONTROL: three distinct trees with three distinct finding sets satisfy K=3"
}

test_reshaded_trees_do_not_count() {
    local repo
    repo="$(setup_k_repo)"
    record_tree "$repo" "alpha" "t1"
    # A new commit, a new TREE ID, and the gate's behaviour is untouched: the
    # only change is a file the comparison never reads. This is invariant 5
    # defeated by whitespace, and the distinct-evidence rule is what refuses it.
    echo "unrelated" >"$repo/README.md"
    record_tree "$repo" "alpha" "t2"
    echo "unrelated again" >>"$repo/README.md"
    record_tree "$repo" "alpha" "t3"

    local rc=0
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k --assert --k 3) \
        >"$WORK/out" 2>"$WORK/err" || rc=$?
    ((rc == 1)) || log_fail "three re-shaded trees must NOT satisfy K=3, got exit $rc"
    assert_contains "$(cat "$WORK/out")" '3 distinct clean tree(s)' 'the trees really are distinct'
    assert_contains "$(cat "$WORK/out")" '1 distinct finding set(s)' 'but they carry one observation'
    assert_contains "$(cat "$WORK/err")" 're-shaded' 'the refusal names the mechanism'
    log_pass "distinct-evidence: 3 distinct tree ids carrying ONE finding set do not satisfy K=3"
}

test_a_mismatch_cannot_be_cleared_by_rerunning() {
    local repo
    repo="$(setup_k_repo)"
    # Record a mismatch: the two sides disagree on this tree.
    printf 'alpha\n' >"$repo/fixture.txt"
    tgit "$repo" add -A >/dev/null
    tgit "$repo" commit -q -m t1 >/dev/null
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k \
        --old "bash $WORK/tiny-gate.sh $repo/fixture.txt old" \
        --new 'echo "✗ fixture.txt: something else is bad" >&2; exit 1' --record) >/dev/null 2>&1 || true
    # Now the honest comparison on the SAME tree, twice.
    record_tree_same() {
        (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k \
            --old "bash $WORK/tiny-gate.sh $repo/fixture.txt old" \
            --new "bash $WORK/tiny-gate.sh $repo/fixture.txt new" --record) >/dev/null 2>&1 || true
    }
    record_tree_same
    record_tree_same

    local rc=0
    (cd "$REPO_ROOT" && "$TSX" "$LIB" --repo "$repo" --pair k --assert --k 1) \
        >"$WORK/out" 2>"$WORK/err" || rc=$?
    ((rc == 1)) || log_fail "a tree with a recorded mismatch must stay disqualified, got exit $rc"
    assert_contains "$(cat "$WORK/err")" 'DISQUALIFIED' 'the tree is disqualified by name'
    assert_contains "$(cat "$WORK/err")" 'cannot be cleared by re-running' 'the message says so'
    log_pass "no run-until-green: a recorded mismatch disqualifies its tree permanently"
}

# ---------------------------------------------------------------------------

log_test "test-shadow-gate"
build_corpus
write_gate_bash
write_gate_ts
build_sides

test_selftest_battery
test_mutation_controls
test_real_pair_is_equivalent
test_real_pair_divergence_is_named
test_planted_dropped_finding
test_planted_blindness_is_new_side_true
test_both_empty_refuses_to_bless
test_refusal_suspends_the_comparison
test_comment_ratio_is_recorded
test_dirty_tree_is_refused_and_writes_nothing
test_k_counts_distinct_trees_not_runs
test_reshaded_trees_do_not_count
test_a_mismatch_cannot_be_cleared_by_rerunning

echo ""
log_pass "all tests passed"
