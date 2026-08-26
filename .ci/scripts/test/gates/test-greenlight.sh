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
    printf '{"runId":%s,"jobs":[{"name":"Tests + Infra / Renet","conclusion":"success"}],"gitlinks":{"private/renet":"%s"},"closureHash":"%s"}' \
        "$1" "$SHA_A" "$HASH_A"
}

# want <candidates-json> -- the full evaluateGreenlight input for key renet.
# `wantGitlinks` is a { path -> sha } MAP because a key may pin several
# submodules (the eight VM/E2E keys pin four) or none at all.
want() {
    printf '{"key":"renet","wantGitlinks":{"private/renet":"%s"},"wantClosureHash":"%s","candidates":%s}' \
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
    v="$(ev "{\"key\":\"renet\",\"wantGitlinks\":{\"private/renet\":\"$SHA_B\"},\"wantClosureHash\":\"$HASH_A\",\"candidates\":[$(green_candidate 4242)]}")"
    assert_eq "$(jget "$v" greenlit)" "false" "the same candidate against another pointer must NOT greenlight"
    assert_eq "$(jget "$v" reason)" "no-usable-candidate" "and the walk must end with no usable candidate"
    log_pass "a full match greenlights and names its evidence run (case 1)"
}

# ---------------------------------------------------------------------------
# Case 2: the job ran and FAILED. Matching inputs are irrelevant.
# ---------------------------------------------------------------------------
test_failed_job_refuses() {
    local cand v
    cand="{\"runId\":7,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"failure\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a failed job must never greenlight"
    assert_contains "$(jget "$v" trail)" "job-failed:failure" "refused as job-failed, carrying the conclusion"

    # A cancelled run is the same class and is NOT rare: a live listing of
    # rediacc/console showed 'Tests + Infra / Account E2E' cancelled on the
    # most recent completed run.
    cand="{\"runId\":8,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"cancelled\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
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
    cand="{\"runId\":9,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"skipped\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a skipped job must never greenlight"
    assert_contains "$(jget "$v" trail)" "job-not-run" "refused as job-not-run, exactly like an absent job"

    # A run carrying no such job at all lands on the same reason, because
    # neither can prove the suite executed.
    cand="{\"runId\":10,\"jobs\":[{\"name\":\"Tests + Infra / Unit\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_contains "$(jget "$v" trail)" "job-not-run" "an absent job is refused as job-not-run"

    # CONTROL: flipping only the conclusion to success greenlights the very
    # same fixture, so the refusal above is about the conclusion and nothing
    # else in the candidate.
    cand="{\"runId\":9,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
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
    cand="{\"runId\":11,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_B\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a differing console-side closure must refuse"
    assert_contains "$(jget "$v" trail)" "closure-differs" "named as closure-differs"

    # CONTROL: flipping only the closure hash back greenlights the same
    # fixture, so the refusal is about the closure and nothing else.
    cand="{\"runId\":11,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
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

    v="$(ev "{\"key\":\"renet\",\"wantGitlinks\":{},\"wantClosureHash\":\"$HASH_A\",\"candidates\":[$(green_candidate 1)]}")"
    assert_eq "$(jget "$v" reason)" "no-local-gitlink" "an unreadable local gitlink must not greenlight"

    v="$(ev "{\"key\":\"nonsense\",\"wantGitlinks\":{\"private/renet\":\"$SHA_A\"},\"wantClosureHash\":\"$HASH_A\",\"candidates\":[$(green_candidate 1)]}")"
    assert_contains "$(jget "$v" reason)" "unknown-key" "an unknown key must not greenlight"

    # A THROWING fetch at each of the three lazy stages. Injected here rather
    # than fixtured, because a thrown fetch is exactly what a rate-limited or
    # 404ing API looks like and JSON cannot express it.
    local thrown
    thrown="$(node -e '
const g = require(process.argv[1]);
const boom = () => { throw new Error("api exploded"); };
const out = [];
for (const stage of ["jobs", "gitlinks", "closureHash"]) {
  const cand = {
    runId: 1,
    jobs: [{ name: "Tests + Infra / Renet", conclusion: "success" }],
    gitlinks: { "private/renet": "1111111111111111111111111111111111111111" },
    closureHash: "aaaa000000000000000000000000000000000000000000000000000000000000",
  };
  cand[stage] = boom;
  const v = g.evaluateGreenlight({
    key: "renet",
    wantGitlinks: { "private/renet": "1111111111111111111111111111111111111111" },
    wantClosureHash: "aaaa000000000000000000000000000000000000000000000000000000000000",
    candidates: [cand],
  });
  out.push(`${stage}:${v.greenlit}:${v.trail[0].reason}`);
}
process.stdout.write(out.join(" "));
' "$ENGINE")"
    assert_contains "$thrown" "jobs:false:jobs-unreadable:api exploded" "a throwing jobs fetch fails open"
    assert_contains "$thrown" "gitlinks:false:gitlink-unreadable:api exploded" "a throwing gitlink fetch fails open"
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
    cand="{\"runId\":31,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_B\"},\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a moved submodule pointer must never greenlight"
    assert_eq "$(jget "$v" runId)" "null" "and must name no evidence run"
    assert_contains "$(jget "$v" trail)" "pointer-differs" "refused as pointer-differs"

    # CONTROL: restore the pointer, change nothing else, and the same fixture
    # greenlights. Without this the refusal above could come from any field.
    cand="{\"runId\":31,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "true" "the same fixture with the matching pointer DOES greenlight"

    # A one-character difference is a difference. Equality is over the whole
    # hash, not a prefix, so a near-miss cannot be read as a match.
    local near="${SHA_A:0:39}9"
    cand="{\"runId\":32,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$near\"},\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "false" "a pointer differing in one character must refuse"

    # An absent gitlink (the candidate commit did not carry that submodule)
    # is a difference too, not a free pass.
    cand="{\"runId\":33,\"jobs\":[{\"name\":\"Tests + Infra / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{},\"closureHash\":\"$HASH_A\"}"
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
        cand="{\"runId\":21,\"jobs\":[{\"name\":\"$decoy\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
        v="$(ev "$(want "[$cand]")")"
        assert_eq "$(jget "$v" greenlit)" "false" "'$decoy' must not be read as the Renet suite"
    done

    # CONTROL: the real name, under a DIFFERENT caller prefix, still matches.
    # Only the leaf is ct-tests.yml's to control, so only the leaf is matched.
    cand="{\"runId\":22,\"jobs\":[{\"name\":\"Some Other Caller / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
    v="$(ev "$(want "[$cand]")")"
    assert_eq "$(jget "$v" greenlit)" "true" "the leaf name matches regardless of the caller prefix"

    # Two jobs answering to one name means the name no longer identifies the
    # suite, so neither reading is evidence.
    cand="{\"runId\":23,\"jobs\":[{\"name\":\"A / Renet\",\"conclusion\":\"success\"},{\"name\":\"B / Renet\",\"conclusion\":\"success\"}],\"gitlinks\":{\"private/renet\":\"$SHA_A\"},\"closureHash\":\"$HASH_A\"}"
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
  for (const p of c.submodules) lines.push(`${key}\t${p}`);
  for (const p of c.paths) lines.push(`${key}\t${p}`);
}
process.stdout.write(`${lines.join("\n")}\n`);
' "$ENGINE")"

    local count=0
    while IFS=$'\t' read -r key path; do
        [[ -n "$path" ]] || continue
        assert_eq "$(git -C "$REPO_ROOT" ls-tree HEAD -- "$path" | wc -l)" "1" \
            "closure path for $key must exist in HEAD: $path"
        count=$((count + 1))
    done <<<"$paths"
    # The floor sits JUST BELOW the real total (408 across 18 keys as of
    # 2026-08-08), not at some token value: a `> 15` floor survived a table
    # that had lost every key but one. At 400 a parse break reads as 0 and a
    # dropped VM/E2E key costs 30 entries, both of which fire this; trimming a
    # path or two during honest maintenance does not.
    assert_eq "$((count > 400 ? 1 : 0))" "1" "the table must stay whole ($count entries seen, floor 400)"

    # CONTROL: the same assertion applied to a path that does NOT exist must
    # fail, or the loop above proves only that the loop ran.
    assert_eq "$(git -C "$REPO_ROOT" ls-tree HEAD -- .ci/scripts/private/no-such-file.sh | wc -l)" "0" \
        "the existence probe returns 0 lines for a path that is not there"
    log_pass "every declared closure path exists in HEAD ($count entries)"
}

# ---------------------------------------------------------------------------
# Case 10: MATRIX EVIDENCE. e2e_workers is five API jobs, one per distro. The
# property is that ALL FIVE must have run green: a candidate carrying four of
# them, or five with one skipped, proves nothing about the missing leg, and
# accepting it would let exactly the distro a PR breaks be the one never run.
#
# This is rule 1 restated for the matrix case, and it is the reason `jobNames`
# is a list rather than a name plus a count.
# ---------------------------------------------------------------------------
test_matrix_key_needs_every_leg() {
    local legs v cand
    legs="$(node -e '
const { CLOSURES } = require(process.argv[1]);
process.stdout.write(CLOSURES.e2e_workers.jobNames.join("\n"));
' "$ENGINE")"
    assert_eq "$(printf '%s\n' "$legs" | wc -l)" "5" "e2e_workers declares five matrix legs"

    # A helper that builds the candidate from a list of "<leaf>=<conclusion>".
    local mk
    # `node -e <code> -- a b` puts a at argv[1], not argv[2]: node consumes the
    # `--` itself. Slicing from 2 here silently dropped the first leg and read
    # as a real refusal, which is exactly the shape of bug this file exists to
    # catch, so the index is stated rather than guessed.
    mk='
const jobs = process.argv.slice(1).map((s) => {
  const i = s.lastIndexOf("=");
  return { name: `Tests + Infra / ${s.slice(0, i)}`, conclusion: s.slice(i + 1) };
});
process.stdout.write(JSON.stringify({
  runId: 60,
  jobs,
  gitlinks: {
    "private/renet": "1111111111111111111111111111111111111111",
    "private/account": "1111111111111111111111111111111111111111",
    "private/elite": "1111111111111111111111111111111111111111",
    "private/homebrew-tap": "1111111111111111111111111111111111111111",
  },
  closureHash: "aaaa000000000000000000000000000000000000000000000000000000000000",
}));
'
    # want_workers <candidate-json> -- the evaluateGreenlight input for the
    # four-submodule VM/E2E shape.
    local want_workers
    want_workers='{"key":"e2e_workers","wantGitlinks":{"private/renet":"'"$SHA_A"'","private/account":"'"$SHA_A"'","private/elite":"'"$SHA_A"'","private/homebrew-tap":"'"$SHA_A"'"},"wantClosureHash":"'"$HASH_A"'","candidates":[CAND]}'

    # FIRE 1: one leg absent from the run entirely.
    cand="$(node -e "$mk" -- \
        "E2E Workers (ubuntu-24.04)=success" \
        "E2E Workers (debian-13)=success" \
        "E2E Workers (fedora-43)=success" \
        "E2E Workers (opensuse-16.0)=success")"
    v="$(ev "${want_workers/CAND/$cand}")"
    assert_eq "$(jget "$v" greenlit)" "false" "four green legs out of five must NOT greenlight"
    assert_contains "$(jget "$v" trail)" "job-not-run@E2E Workers (oracle-10)" \
        "and the trail must name the leg that was missing"

    # FIRE 2: all five present, one of them SKIPPED. This is the shape a
    # reduced run leaves behind, and it is the one that must never chain.
    cand="$(node -e "$mk" -- \
        "E2E Workers (ubuntu-24.04)=success" \
        "E2E Workers (debian-13)=success" \
        "E2E Workers (fedora-43)=skipped" \
        "E2E Workers (opensuse-16.0)=success" \
        "E2E Workers (oracle-10)=success")"
    v="$(ev "${want_workers/CAND/$cand}")"
    assert_eq "$(jget "$v" greenlit)" "false" "one skipped leg out of five must NOT greenlight"
    assert_contains "$(jget "$v" trail)" "job-not-run@E2E Workers (fedora-43)" \
        "named as the skipped leg, not as a generic refusal"

    # FIRE 3: one leg red.
    cand="$(node -e "$mk" -- \
        "E2E Workers (ubuntu-24.04)=success" \
        "E2E Workers (debian-13)=failure" \
        "E2E Workers (fedora-43)=success" \
        "E2E Workers (opensuse-16.0)=success" \
        "E2E Workers (oracle-10)=success")"
    v="$(ev "${want_workers/CAND/$cand}")"
    assert_eq "$(jget "$v" greenlit)" "false" "one failed leg out of five must NOT greenlight"

    # CONTROL: all five green, nothing else changed, and the same shape DOES
    # greenlight. Without it every assertion above could be a broken fixture.
    cand="$(node -e "$mk" -- \
        "E2E Workers (ubuntu-24.04)=success" \
        "E2E Workers (debian-13)=success" \
        "E2E Workers (fedora-43)=success" \
        "E2E Workers (opensuse-16.0)=success" \
        "E2E Workers (oracle-10)=success")"
    v="$(ev "${want_workers/CAND/$cand}")"
    assert_eq "$(jget "$v" greenlit)" "true" "all five legs green DOES greenlight"
    assert_eq "$(jget "$v" runId)" "60" "naming the run that proved it"

    # And a moved pointer on ANY ONE of the four pinned submodules withdraws
    # it, so the multi-submodule rule 2 is not satisfied by the first entry.
    local one_moved
    one_moved='{"key":"e2e_workers","wantGitlinks":{"private/renet":"'"$SHA_A"'","private/account":"'"$SHA_A"'","private/elite":"'"$SHA_B"'","private/homebrew-tap":"'"$SHA_A"'"},"wantClosureHash":"'"$HASH_A"'","candidates":[CAND]}'
    v="$(ev "${one_moved/CAND/$cand}")"
    assert_eq "$(jget "$v" greenlit)" "false" "one moved pointer of four withdraws the greenlight"
    assert_contains "$(jget "$v" trail)" "pointer-differs" "refused as pointer-differs"
    log_pass "a matrix key needs every leg green; four of five is not evidence (case 10)"
}

# ---------------------------------------------------------------------------
# Case 11: `submodules: []` is LEGAL and VACUOUS, not a mistake to be rescued.
# `Linux Packages` checks out with no submodules at all (ci.yml:709), so there
# is no pointer to pin and rule 2 has nothing to compare. The hazard being
# asserted against is the opposite of the usual one: an empty pin list must not
# be treated as "no local gitlink" and refuse forever, and it must not stop
# rules 1 and 3 from still deciding.
#
# This case used `unit` as its example until Unit grew a submodule checkout --
# its suite parses private/renet source and was failing on a file it never
# fetched. The assertion moved to a key that is STILL an example rather than
# being deleted: what is under test is the empty-list BEHAVIOUR, not which key
# happens to have one, and dropping the assertion would have left that
# behaviour unpinned while looking like a tidy-up.
# ---------------------------------------------------------------------------
test_empty_submodule_list_is_vacuous_not_broken() {
    local decl v cand
    decl="$(node -e '
const { CLOSURES } = require(process.argv[1]);
process.stdout.write(String(CLOSURES.package_tests.submodules.length));
' "$ENGINE")"
    assert_eq "$decl" "0" "the package_tests key declares no submodules at all"

    cand='{"runId":70,"jobs":[{"name":"Linux Packages","conclusion":"success"}],"gitlinks":{},"closureHash":"'"$HASH_A"'"}'
    v="$(ev '{"key":"package_tests","wantGitlinks":{},"wantClosureHash":"'"$HASH_A"'","candidates":['"$cand"']}')"
    assert_eq "$(jget "$v" greenlit)" "true" "an empty pin list still greenlights on rules 1 and 3"
    assert_eq "$(jget "$v" runId)" "70" "naming the evidence run"

    # CONTROL 1: rule 3 still decides for a key with no pins, so the pass above
    # is not "empty submodules disables every rule".
    cand='{"runId":71,"jobs":[{"name":"Linux Packages","conclusion":"success"}],"gitlinks":{},"closureHash":"'"$HASH_B"'"}'
    v="$(ev '{"key":"package_tests","wantGitlinks":{},"wantClosureHash":"'"$HASH_A"'","candidates":['"$cand"']}')"
    assert_eq "$(jget "$v" greenlit)" "false" "a differing closure still refuses a pinless key"
    assert_contains "$(jget "$v" trail)" "closure-differs" "named as closure-differs"

    # CONTROL 2: rule 1 still decides too.
    cand='{"runId":72,"jobs":[{"name":"Linux Packages","conclusion":"skipped"}],"gitlinks":{},"closureHash":"'"$HASH_A"'"}'
    v="$(ev '{"key":"package_tests","wantGitlinks":{},"wantClosureHash":"'"$HASH_A"'","candidates":['"$cand"']}')"
    assert_eq "$(jget "$v" greenlit)" "false" "a skipped job still refuses a pinless key"

    # CONTROL 3: the emptiness is a property of THAT key, not of the check. A
    # key that DOES declare pins and cannot read one of them must still refuse
    # with no-local-gitlink rather than proceeding on a short map.
    v="$(ev '{"key":"e2e_workers","wantGitlinks":{"private/renet":"'"$SHA_A"'"},"wantClosureHash":"'"$HASH_A"'","candidates":[]}')"
    assert_eq "$(jget "$v" reason)" "no-local-gitlink" \
        "a key with unread pins refuses rather than comparing a short map"
    log_pass "an empty submodule list is vacuous for that key and only that key (case 11)"
}

# ---------------------------------------------------------------------------
# Case 12: KEY ORDER IS COST-DESCENDING. scope-shadow.sh passes the pending
# keys through in CLOSURES' own order and the walk budget is per invocation, so
# the tail of this list is what a timeout abandons. Pin both ends: the most
# expensive key first, the cheapest last. Inserting a new key at the top of the
# table (the natural place to paste one) would fire this.
# ---------------------------------------------------------------------------
test_key_order_is_cost_descending() {
    local keys first last
    keys="$(node -e '
const { CLOSURES } = require(process.argv[1]);
process.stdout.write(Object.keys(CLOSURES).join(" "));
' "$ENGINE")"
    first="${keys%% *}"
    last="${keys##* }"
    assert_eq "$first" "e2e_workers" "the first key must be the most expensive one (five 90-minute legs)"
    assert_eq "$last" "unit" "the last key must be the cheapest one, so a dead budget starves it"

    # CONTROL: the probe reads the real order rather than echoing its argument.
    assert_not_contains "$first" "unit" "the first key is not the last one"

    # scope-shadow.sh must be the consumer of that order, and must ask for the
    # raised budget. Asserted against the INVOCATION LINE, not the file: the
    # first version of this grepped the whole file for '--budget 90', and the
    # mutation proof caught it passing with the flag deleted from the command,
    # because the comment ABOVE the command explains the flag and still says
    # '--budget 90'. A gate satisfied by its own prose cannot fire.
    local invocation
    invocation="$(grep -E '^\s*if ! bounded node "\$GREENLIGHT"' \
        "$REPO_ROOT/.ci/scripts/ci/scope-shadow.sh" || true)"
    assert_contains "$invocation" '--budget 90' \
        "the scope-shadow greenlight INVOCATION must raise the walk budget"
    log_pass "the key order is cost-descending and scope-shadow.sh raises the budget (case 12)"
}

# ---------------------------------------------------------------------------
# Case 13: THE TRAIL MUST STAY READABLE. The trail is the only thing that makes
# a non-greenlight diagnosable, and it is surfaced through a step summary with
# a byte cap. At two keys the raw dump fitted; at eighteen keys against a
# 25-candidate list it is ~450 rows and it truncated MID-LINE inside the second
# key, so sixteen keys' diagnostics were simply absent. scope-shadow.sh's
# greenlight_digest exists to condense it, and this case is what stops the
# digest silently dropping keys as the table grows again.
# ---------------------------------------------------------------------------
test_the_trail_digest_names_every_key() {
    local fn="$WORK/digest.sh"
    sed -n '/^greenlight_digest() {/,/^}$/p' \
        "$REPO_ROOT/.ci/scripts/ci/scope-shadow.sh" >"$fn"
    assert_contains "$(cat "$fn")" "awk" "greenlight_digest must be extractable from scope-shadow.sh"
    # shellcheck source=/dev/null
    # BLOCKER: the function under test is defined in scope-shadow.sh, which cannot be
    # sourced whole because sourcing it runs the scope engine.
    source "$fn"

    # A synthetic trail in the engine's exact debug shape: three keys, each
    # with a header block and a multi-row candidate table.
    local raw="$WORK/trail.err"
    {
        echo "greenlight: repo=owner/name candidates=3 budget=90s"
        local k
        for k in alpha beta gamma; do
            echo ""
            echo "greenlight[$k] jobs='Some Job'"
            echo "greenlight[$k] pins=private/renet=abcdef12"
            echo "greenlight[$k] closure=${k}0000000000000000000000 (26 paths)"
            echo "  run id        head      verdict"
            echo "  900000001     11111111  pointer-differs"
            echo "  900000002     22222222  closure-differs"
            echo "  900000003     33333333  job-not-run@E2E Workers (oracle-10)"
            echo "greenlight[$k] VERDICT: no (no-usable-candidate)"
            echo "greenlight[$k]: no greenlight (no-usable-candidate)"
        done
        echo "greenlight[delta]: local inputs unreadable (boom), nothing is greenlit"
    } >"$raw"

    local digest
    digest="$(greenlight_digest "$raw")"

    # Every key survives, with its verdict and the newest candidate's reason.
    local k
    for k in alpha beta gamma; do
        assert_contains "$digest" "$k" "the digest must name key $k"
    done
    assert_contains "$digest" "walked=3" "and must say how many candidates were walked"
    assert_contains "$digest" "newest 900000001 pointer-differs" \
        "and must carry the NEWEST candidate's reason, which is the one that matters"

    # A reason containing spaces (the matrix form) must survive whole.
    local wide="$WORK/trail-matrix.err"
    {
        echo "greenlight[m] closure=aaaa000000000000 (26 paths)"
        echo "  run id        head      verdict"
        echo "  900000009     99999999  job-not-run@E2E Workers (oracle-10)"
        echo "greenlight[m] VERDICT: no (no-usable-candidate)"
    } >"$wide"
    assert_contains "$(greenlight_digest "$wide")" "job-not-run@E2E Workers (oracle-10)" \
        "a matrix refusal keeps the leg name, spaces and all"

    # An unrecognised line is PASSED THROUGH, never filtered into silence.
    assert_contains "$digest" "local inputs unreadable (boom)" \
        "a line the digest does not recognise must survive verbatim"

    # CONTROL: the digest is a real reduction. Against the LIVE-shaped input it
    # must be far smaller than the raw trail, or it is not solving the problem
    # it was written for.
    local rawbytes digestbytes
    rawbytes="$(wc -c <"$raw")"
    digestbytes="$(printf '%s' "$digest" | wc -c)"
    assert_eq "$((digestbytes < rawbytes ? 1 : 0))" "1" \
        "the digest must be smaller than the raw trail ($digestbytes vs $rawbytes bytes)"
    log_pass "the trail digest names every key and survives a growing table (case 13)"
}

log_test "test-greenlight"
test_full_match_greenlights_and_names_the_run
test_failed_job_refuses
test_skipped_job_refuses_as_not_run
test_differing_closure_refuses
test_absent_and_throwing_candidates_fail_open
test_cli_emit_is_false_only
test_moved_pointer_refuses

# Case 15: THE CANDIDATE WINDOW MUST BE WIDER THAN THE DEFAULT.
#
# A GREENLIT run cannot serve as evidence for the next one -- rule 1 refuses a
# `skipped` job (greenlight.cjs:675-697) -- so the last EXECUTING run recedes one
# slot per push. With the engine's default of 25 (greenlight.cjs:980) that window
# is small enough to fall off in normal use: measured on run 32946684108, renet,
# package_tests and license_enforcement were already at walked=21 of 24, three
# pushes from dropping out.
#
# What happens then is the reason this is pinned rather than left to judgement:
# CI silently reverts to running the 90-minute suites. Nothing goes red, nothing
# is reported, and the only symptom is that CI got slower -- which nobody
# investigates.
#
# Widening is monotone in the SAFE direction (it can only find an EXISTING proof,
# never manufacture one), so the floor below is a floor, not an equality.
test_candidate_window_is_widened() {
    local line limit
    line="$(grep -n -- '--limit' "$REPO_ROOT/.ci/scripts/ci/scope-shadow.sh" |
        grep -v '^[[:space:]]*#' | grep 'GREENLIGHT' || true)"
    [[ -n "$line" ]] ||
        log_fail "scope-shadow.sh no longer passes --limit, so the engine falls back to 25 and the window can silently close"

    limit="$(sed -E 's/.*--limit[[:space:]]+([0-9]+).*/\1/' <<<"$line")"
    [[ "$limit" =~ ^[0-9]+$ ]] ||
        log_fail "could not read the --limit value from: $line"
    [[ "$limit" -ge 40 ]] ||
        log_fail "--limit is $limit; the observed walk already reached 21 of 24, so anything near the default reopens the cliff"

    # CONTROL, by construction: the same extractor must REFUSE an invocation
    # that omits --limit. Without this the assertion above passes trivially the
    # day someone drops the flag and the grep returns nothing... which is what
    # the first branch checks, so prove that branch can actually distinguish.
    local probe
    probe="$(mktemp)"
    printf '%s\n' 'bounded node "$GREENLIGHT" --repo x --budget 90 --debug' >"$probe"
    if grep -n -- '--limit' "$probe" | grep -q 'GREENLIGHT'; then
        rm -f "$probe"
        log_fail "CONTROL DID NOT FIRE: an invocation with no --limit read as compliant"
    fi
    rm -f "$probe"

    log_pass "candidate window widened to $limit (default 25 would close silently)"
}

test_job_name_leaf_must_match_exactly
test_declared_closure_paths_exist
test_matrix_key_needs_every_leg
test_empty_submodule_list_is_vacuous_not_broken
test_key_order_is_cost_descending
test_the_trail_digest_names_every_key
test_candidate_window_is_widened
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
