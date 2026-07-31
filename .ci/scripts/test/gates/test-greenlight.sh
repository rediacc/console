#!/bin/bash
# Unit test for the cross-PR greenlight engine, .ci/scripts/ci/greenlight.cjs.
#
# WHAT THIS GUARDS. The engine lets a PR skip test-renet (90 minutes) or the
# account E2E suite on evidence that some OTHER run, on any branch, already
# executed that exact job green over byte-identical inputs. A false refusal
# costs one full CI round. A false GREENLIGHT merges untested code, so every
# rule that narrows the evidence is asserted here with a CONTROL that produces
# the opposite outcome: an engine hardcoded to "always greenlight" and one
# hardcoded to "never greenlight" both fail this file.
#
# THE RULE THAT CARRIES THE MOST WEIGHT is rule 1, intent versus outcome: a
# SKIPPED job must never count as evidence. Without it a reduced run whose
# renet job was skipped would greenlight the next PR, which would skip it too,
# and the suite would go unrun forever while every check stayed green. That is
# the case the planted-defect proof below is aimed at.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

ENGINE="$REPO_ROOT/.ci/scripts/ci/greenlight.cjs"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

SHA_A="1111111111111111111111111111111111111111"
SHA_B="2222222222222222222222222222222222222222"
HASH_A="aaaa000000000000000000000000000000000000000000000000000000000000"
HASH_B="bbbb000000000000000000000000000000000000000000000000000000000000"

# ev <json> -- drive the PURE core over an injected fixture. No network, no
# git, no clock: the whole decision is a function of its argument.
ev() {
    node -e '
const g = require(process.argv[1]);
const v = g.evaluateGreenlight(JSON.parse(process.argv[2]));
process.stdout.write(JSON.stringify({
  greenlit: v.greenlit,
  runId: v.runId === undefined ? null : v.runId,
  reason: v.reason,
  trail: v.trail.map((t) => t.reason),
}));
' "$ENGINE" "$1"
}

# green_candidate <run-id> -- a fixture candidate that satisfies every rule.
# Cases mutate one field of it, so each assertion isolates one rule.
green_candidate() {
    printf '{"runId":%s,"jobs":[{"name":"Tests + Infra / Renet","conclusion":"success"}],"gitlink":"%s","closureHash":"%s"}' \
        "$1" "$SHA_A" "$HASH_A"
}

# want <candidates-json> -- the full evaluateGreenlight input for key renet.
want() {
    printf '{"key":"renet","wantSubmoduleSha":"%s","wantClosureHash":"%s","candidates":%s}' \
        "$SHA_A" "$HASH_A" "$1"
}

# jget <json> <field> -- read one field out of a verdict.
jget() {
    node -e '
const v = JSON.parse(process.argv[1]);
const x = v[process.argv[2]];
process.stdout.write(typeof x === "string" ? x : JSON.stringify(x));
' "$1" "$2"
}

# ---------------------------------------------------------------------------
# Case 1: a full match greenlights, and names the run that proved it.
# ---------------------------------------------------------------------------
test_full_match_greenlights_and_names_the_run() {
    local v
    v="$(ev "$(want "[$(green_candidate 4242)]")")"
    assert_eq "$(jget "$v" greenlit)" "true" "a candidate matching every rule must greenlight"
    assert_eq "$(jget "$v" runId)" "4242" "and must name the run id that is the evidence"
    assert_eq "$(jget "$v" reason)" "job-green-same-inputs" "with the reason stated"

    # CONTROL: greenlit is not the constant answer. The SAME candidate against
    # a different wanted pointer must refuse, or nothing above is proven.
    v="$(ev "{\"key\":\"renet\",\"wantSubmoduleSha\":\"$SHA_B\",\"wantClosureHash\":\"$HASH_A\",\"candidates\":[$(green_candidate 4242)]}")"
    assert_eq "$(jget "$v" greenlit)" "false" "the same candidate against another pointer must NOT greenlight"
    assert_eq "$(jget "$v" reason)" "no-usable-candidate" "and the walk must end with no usable candidate"
    log_pass "a full match greenlights and names its evidence run (case 1)"
}

# ---------------------------------------------------------------------------
# Case 2: the job ran and FAILED. Matching inputs are irrelevant.
# ---------------------------------------------------------------------------
test_failed_job_refuses() {
    local cand v
    cand="{\"runId\":7,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"failure\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a failed job must never greenlight"
    assert_contains "$(jget "$v" trail)" "job-failed:failure" "refused as job-failed, carrying the conclusion"

    # A cancelled run is the same class and is NOT rare: a live listing of
    # rediacc/console showed 'Tests + Infra / Account E2E' cancelled on the
    # most recent completed run.
    cand="{\"runId\":8,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"cancelled\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_contains "$(jget "$v" trail)" "job-failed:cancelled" "a cancelled job is refused the same way"
    log_pass "a job that ran and did not succeed is refused (case 2)"
}

# ---------------------------------------------------------------------------
# Case 3: the job was SKIPPED. THE intent-versus-outcome case, and the one the
# planted-defect proof targets.
#
# PLANTED-DEFECT PROOF, executed 2026-07-31. Rule 1 in
# greenlight.cjs::evaluateCandidate was inverted so a skipped conclusion fell
# through to the success path (`if (conclusion === 'skipped') { /* accept */ }`
# in place of the refusal). With that one edit:
#   - this case FAILED, with the exact text
#       FAIL: a skipped job must never greenlight: expected 'false', got 'true'
#   - cases 1 and 2 still PASSED, so the defect is detected by this property
#     alone and not by a suite-wide collapse.
# The engine was then restored and re-verified byte-identical by md5
# (8b35c56e7f5ca90c959f90ac7db029b9 before and after).
# ---------------------------------------------------------------------------
test_skipped_job_refuses_as_not_run() {
    local cand v
    cand="{\"runId\":9,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"skipped\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a skipped job must never greenlight"
    assert_contains "$(jget "$v" trail)" "job-not-run" "refused as job-not-run, exactly like an absent job"

    # A run carrying no such job at all lands on the same reason, because
    # neither can prove the suite executed.
    cand="{\"runId\":10,\"jobs\":[{\"name\":\"Tests + Infra / Unit\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_contains "$(jget "$v" trail)" "job-not-run" "an absent job is refused as job-not-run"

    # CONTROL: flipping only the conclusion to success greenlights the very
    # same fixture, so the refusal above is about the conclusion and nothing
    # else in the candidate.
    cand="{\"runId\":9,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "true" "the same fixture with conclusion=success DOES greenlight"
    log_pass "a skipped job is refused, so evidence cannot chain across reduced runs (case 3)"
}

# ---------------------------------------------------------------------------
# Case 4: the job is green and the pointer matches, but a console-side input
# differs. This is the rule that makes the greenlight safe for a PR that edits
# run-renet.sh without touching the submodule.
# ---------------------------------------------------------------------------
test_differing_closure_refuses() {
    local cand v
    cand="{\"runId\":11,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_B\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a differing console-side closure must refuse"
    assert_contains "$(jget "$v" trail)" "closure-differs" "named as closure-differs"

    # CONTROL: flipping only the closure hash back greenlights the same
    # fixture, so the refusal is about the closure and nothing else.
    cand="{\"runId\":11,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "true" "the same fixture with the matching closure DOES greenlight"
    log_pass "a changed console-side input refuses as closure-differs (case 4)"
}

# ---------------------------------------------------------------------------
# Case 5: FAIL-OPEN. Absence and failure must both yield greenlit=false, never
# an exception and never a greenlight. This is the contract the whole design
# rests on: the engine may only ever turn a RUN into a SKIP, so every way it
# can go wrong has to land on "changed nothing".
# ---------------------------------------------------------------------------
test_absent_and_throwing_candidates_fail_open() {
    local v
    v="$(ev "$(want "[]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "an empty candidate list must not greenlight"
    assert_eq "$(jget "$v" reason)" "no-candidates" "named as no-candidates"

    v="$(ev "{\"key\":\"renet\",\"wantSubmoduleSha\":\"\",\"wantClosureHash\":\"$HASH_A\",\"candidates\":[$(green_candidate 1)]}")"
    assert_eq "$(jget "$v" reason)" "no-local-gitlink" "an unreadable local gitlink must not greenlight"

    v="$(ev "{\"key\":\"nonsense\",\"wantSubmoduleSha\":\"$SHA_A\",\"wantClosureHash\":\"$HASH_A\",\"candidates\":[$(green_candidate 1)]}")"
    assert_contains "$(jget "$v" reason)" "unknown-key" "an unknown key must not greenlight"

    # A THROWING fetch at each of the three lazy stages. Injected here rather
    # than fixtured, because a thrown fetch is exactly what a rate-limited or
    # 404ing API looks like and JSON cannot express it.
    local thrown
    thrown="$(node -e '
const g = require(process.argv[1]);
const boom = () => { throw new Error("api exploded"); };
const out = [];
for (const stage of ["jobs", "gitlink", "closureHash"]) {
  const cand = {
    runId: 1,
    jobs: [{ name: "Tests + Infra / Renet", conclusion: "success" }],
    gitlink: "1111111111111111111111111111111111111111",
    closureHash: "aaaa000000000000000000000000000000000000000000000000000000000000",
  };
  cand[stage] = boom;
  const v = g.evaluateGreenlight({
    key: "renet",
    wantSubmoduleSha: "1111111111111111111111111111111111111111",
    wantClosureHash: "aaaa000000000000000000000000000000000000000000000000000000000000",
    candidates: [cand],
  });
  out.push(`${stage}:${v.greenlit}:${v.trail[0].reason}`);
}
process.stdout.write(out.join(" "));
' "$ENGINE")"
    assert_contains "$thrown" "jobs:false:jobs-unreadable:api exploded" "a throwing jobs fetch fails open"
    assert_contains "$thrown" "gitlink:false:gitlink-unreadable:api exploded" "a throwing gitlink fetch fails open"
    assert_contains "$thrown" "closureHash:false:closure-unreadable:api exploded" "a throwing closure fetch fails open"
    log_pass "absence, bad input and a throwing API all fail open to no greenlight (case 5)"
}

# ---------------------------------------------------------------------------
# install_fake_gh -- put a working fake `gh` on PATH at $WORK/bin.
#
# It serves this repo's REAL tree as the candidate's content, so the fixture
# cannot rot: whatever HEAD holds, the candidate holds the same, and a
# greenlight is due. Each CLI-level case then flips exactly ONE fact and
# asserts the greenlight withdraws.
#
# Every case that uses it calls it first, deliberately. One case replaces the
# binary with a deliberately broken one, and a later case that inherited that
# would pass for the wrong reason while looking like a real control.
# ---------------------------------------------------------------------------
install_fake_gh() {
    local bin="$WORK/bin"
    mkdir -p "$bin"

    # Directory listings come straight out of `git ls-tree`, which is the same
    # shape the contents API returns (name plus object sha, for blobs, trees
    # and submodules alike).
    cat >"$WORK/fake-gh.cjs" <<'BACKEND'
const { execFileSync } = require('child_process');
const args = process.argv.slice(2);
const endpoint = args[1] || '';
const root = process.env.GL_REPO_ROOT;
const out = (o) => process.stdout.write(JSON.stringify(o));

if (endpoint.includes('/actions/workflows/ci.yml/runs')) {
  out({ workflow_runs: [{ id: 555001, head_sha: 'deadbee' + 'f'.repeat(33) }] });
} else if (/\/actions\/runs\/\d+\/jobs/.test(endpoint)) {
  out({ jobs: [{ name: 'Tests + Infra / Renet', conclusion: process.env.GL_CONCLUSION || 'success' }] });
} else if (endpoint.startsWith('repos/') && endpoint.includes('/contents')) {
  const dir = endpoint.replace(/^.*\/contents\/?/, '').replace(/\?.*$/, '');
  const spec = dir ? `${dir}/` : './';
  const text = execFileSync('git', ['-C', root, 'ls-tree', 'HEAD', '--', spec], { encoding: 'utf8' });
  const entries = [];
  for (const line of text.split('\n')) {
    const m = /^\d+ \w+ ([0-9a-f]{40})\t(.*)$/.exec(line);
    if (!m) continue;
    const name = m[2].split('/').pop();
    // The perturbation control: one blob of the declared closure is reported
    // with a different sha, which must be enough to withdraw the greenlight.
    const sha = process.env.GL_PERTURB === name ? '0'.repeat(40) : m[1];
    entries.push({ name, sha });
  }
  out(entries);
} else {
  process.stderr.write(`fake-gh: unrouted endpoint ${endpoint}\n`);
  process.exit(1);
}
BACKEND

    cat >"$bin/gh" <<BACKEND
#!/bin/bash
exec node "$WORK/fake-gh.cjs" "\$@"
BACKEND
    chmod +x "$bin/gh"
}

# ---------------------------------------------------------------------------
# Case 6: the CLI's emit, end to end and offline.
#
# The property asserted is the fail-open asymmetry: stdout may carry
# `run_<key>=false` and may never carry `run_<key>=true`, because `=false` is
# the only value that can shrink a round and there is no `=true` form to get
# wrong.
# ---------------------------------------------------------------------------
test_cli_emit_is_false_only() {
    install_fake_gh
    local bin="$WORK/bin"

    local out
    out="$(PATH="$bin:$PATH" GL_REPO_ROOT="$REPO_ROOT" \
        node "$ENGINE" --key renet --repo owner/name --limit 1 2>/dev/null)"

    assert_contains "$out" "run_renet=false" "a due greenlight emits run_renet=false"
    assert_not_contains "$out" "run_renet=true" "and NEVER emits run_renet=true"
    assert_not_contains "$out" "=true" "the CLI has no =true emit form at all"
    assert_contains "$out" "evidence_renet=555001" "naming the run that is the evidence"

    # CONTROL 1: the same fixture with the job skipped emits NOTHING. This is
    # case 3 again at CLI level, where it decides real jobs.
    out="$(PATH="$bin:$PATH" GL_REPO_ROOT="$REPO_ROOT" GL_CONCLUSION=skipped \
        node "$ENGINE" --key renet --repo owner/name --limit 1 2>/dev/null)"
    assert_eq "$out" "" "a skipped candidate job emits no output line at all"

    # CONTROL 2: one console-side closure blob moved, everything else identical.
    out="$(PATH="$bin:$PATH" GL_REPO_ROOT="$REPO_ROOT" GL_PERTURB=run-renet.sh \
        node "$ENGINE" --key renet --repo owner/name --limit 1 2>/dev/null)"
    assert_eq "$out" "" "a single changed closure file withdraws the greenlight"

    # CONTROL 3: a gh that fails outright. The engine must stay silent and
    # exit 0, because a crash inside `initialize` stalls every job that needs
    # it, and this engine must never be the thing that fails.
    cat >"$bin/gh" <<'BROKEN'
#!/bin/bash
echo "gh: boom" >&2
exit 1
BROKEN
    chmod +x "$bin/gh"
    local rc=0
    out="$(PATH="$bin:$PATH" node "$ENGINE" --key renet --repo owner/name --limit 1 2>/dev/null)" || rc=$?
    assert_eq "$rc" "0" "a broken gh must still exit 0"
    assert_eq "$out" "" "and emit nothing"
    log_pass "the CLI emits run_<key>=false or nothing, never =true (case 6)"
}

# ---------------------------------------------------------------------------
# Case 7: THE SUBMODULE POINTER RULE, stated by the operator as the core
# soundness requirement of the whole feature: a suite may be skipped ONLY when
# the submodule points at the exact hash some job-green run already tested. Any
# submodule change, however small, means the related tests run.
#
# It gets its own case because it is the rule most likely to be quietly
# weakened later. It is also the only rule that a plausible-sounding
# "optimisation" would break: accepting an ANCESTOR of the tested commit, or a
# pointer that merely resolves to the same branch, both read as reasonable and
# both let untested submodule code merge. The comparison is hash equality and
# nothing else.
#
# PLANTED-DEFECT PROOF, executed 2026-07-31. Rule 2 in
# greenlight.cjs::evaluateCandidate was weakened from full equality to a
# 4-character prefix comparison, the shape a "cheap early-out" would take.
# With that one edit:
#   - this case FAILED, on the near-miss assertion specifically, with
#       FAIL: a pointer differing in one character must refuse: expected 'false', got 'true'
#   - cases 1 to 6 ALL still passed, so a weakened pointer rule is invisible
#     to every other property in this file and visible to this one.
# The engine was restored and re-verified byte-identical by md5
# (8b35c56e7f5ca90c959f90ac7db029b9 before and after).
# ---------------------------------------------------------------------------
test_moved_pointer_refuses() {
    local cand v

    # FIRE: everything else is a perfect match. Job green, closure identical,
    # and ONLY the gitlink moved.
    cand="{\"runId\":31,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_B\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a moved submodule pointer must never greenlight"
    assert_eq "$(jget "$v" runId)" "null" "and must name no evidence run"
    assert_contains "$(jget "$v" trail)" "pointer-differs" "refused as pointer-differs"

    # CONTROL: restore the pointer, change nothing else, and the same fixture
    # greenlights. Without this the refusal above could come from any field.
    cand="{\"runId\":31,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "true" "the same fixture with the matching pointer DOES greenlight"

    # A one-character difference is a difference. Equality is over the whole
    # hash, not a prefix, so a near-miss cannot be read as a match.
    local near="${SHA_A:0:39}9"
    cand="{\"runId\":32,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$near\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a pointer differing in one character must refuse"

    # An absent gitlink (the candidate commit did not carry that submodule)
    # is a difference too, not a free pass.
    cand="{\"runId\":33,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlink\":null,\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_contains "$(jget "$v" trail)" "pointer-differs" "an absent gitlink refuses as pointer-differs"

    # AND IT CHANGES NOTHING, proven at CLI level against the real tree: the
    # fake gh serves this repo's own content, so everything matches and a
    # greenlight is due, except that private/renet's gitlink is reported moved.
    # The emit must be empty, which is the state in which ci.yml runs the job.
    install_fake_gh
    local out
    out="$(PATH="$WORK/bin:$PATH" GL_REPO_ROOT="$REPO_ROOT" GL_PERTURB=renet \
        node "$ENGINE" --key renet --repo owner/name --limit 1 2>/dev/null)"
    assert_eq "$out" "" "a moved private/renet pointer emits nothing, so the suite runs"

    # CONTROL for that emit: the same invocation WITHOUT the perturbation does
    # greenlight, so the empty output above is the moved pointer and not a
    # broken harness quietly emitting nothing for every input.
    out="$(PATH="$WORK/bin:$PATH" GL_REPO_ROOT="$REPO_ROOT" \
        node "$ENGINE" --key renet --repo owner/name --limit 1 2>/dev/null)"
    assert_contains "$out" "run_renet=false" "the unperturbed pointer still greenlights"
    log_pass "the skip requires the EXACT submodule hash; any move runs the tests (case 7)"
}

# ---------------------------------------------------------------------------
# The job-name hazard, live-derived. A real run of rediacc/console carries all
# of "Tests + Infra / Renet" (the suite), "Build (Renet) / Renet (cached)" and
# "Build (Docker Fast) / Renet Docker". A prefix or substring match would read
# a cache-hit build job as proof that a 90-minute test suite passed.
# ---------------------------------------------------------------------------
test_job_name_leaf_must_match_exactly() {
    local cand v
    for decoy in "Build (Renet) / Renet (cached)" "Build (Docker Fast) / Renet Docker" "Tests + Infra / Renet Extra"; do
        cand="{\"runId\":21,\"jobs\":[{\"name\":\"$decoy\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
        v="$(ev "$(want "[$cand]")")"
        assert_eq "$(jget "$v" greenlit)" "false" "'$decoy' must not be read as the Renet suite"
    done

    # CONTROL: the real name, under a DIFFERENT caller prefix, still matches.
    # Only the leaf is ct-tests.yml's to control, so only the leaf is matched.
    cand="{\"runId\":22,\"jobs\":[{\"name\":\"Some Other Caller / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "true" "the leaf name matches regardless of the caller prefix"

    # Two jobs answering to one name means the name no longer identifies the
    # suite, so neither reading is evidence.
    cand="{\"runId\":23,\"jobs\":[{\"name\":\"A / Renet\",\"conclusion\":\"success\"},{\"name\":\"B / Renet\",\"conclusion\":\"success\"}],\"gitlink\":\"$SHA_A\",\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_contains "$(jget "$v" trail)" "job-ambiguous" "two jobs of one name refuse as job-ambiguous"
    log_pass "only an exact job leaf name is evidence, and only when it is unique"
}

# ---------------------------------------------------------------------------
# ANTI-VACUITY on the closure table itself. A declared path that no longer
# exists would be hashed by nobody and noticed by nothing; the table would
# quietly stop covering the input it names. Assert the paths are real, and that
# both keys declare a non-trivial closure.
# ---------------------------------------------------------------------------
test_declared_closure_paths_exist() {
    local paths
    paths="$(node -e '
const { CLOSURES } = require(process.argv[1]);
const lines = [];
for (const [key, c] of Object.entries(CLOSURES)) {
  lines.push(`${key}\t${c.submodule}`);
  for (const p of c.paths) lines.push(`${key}\t${p}`);
}
process.stdout.write(lines.join("\n"));
' "$ENGINE")"

    local count=0
    while IFS=$'\t' read -r key path; do
        [[ -n "$path" ]] || continue
        assert_eq "$(git -C "$REPO_ROOT" ls-tree HEAD -- "$path" | wc -l)" "1" \
            "closure path for $key must exist in HEAD: $path"
        count=$((count + 1))
    done <<<"$paths"
    assert_eq "$((count > 15 ? 1 : 0))" "1" "both keys must declare a non-trivial closure ($count paths seen)"

    # CONTROL: the same assertion applied to a path that does NOT exist must
    # fail, or the loop above proves only that the loop ran.
    assert_eq "$(git -C "$REPO_ROOT" ls-tree HEAD -- .ci/scripts/private/no-such-file.sh | wc -l)" "0" \
        "the existence probe returns 0 lines for a path that is not there"
    log_pass "every declared closure path exists in HEAD ($count paths)"
}

log_test "test-greenlight"
test_full_match_greenlights_and_names_the_run
test_failed_job_refuses
test_skipped_job_refuses_as_not_run
test_differing_closure_refuses
test_absent_and_throwing_candidates_fail_open
test_cli_emit_is_false_only
test_moved_pointer_refuses
test_job_name_leaf_must_match_exactly
test_declared_closure_paths_exist
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
