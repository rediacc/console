r"""Port of `.ci/scripts/test/gates/test-greenlight.sh`.

Unit test for the cross-PR greenlight engine, `.ci/scripts/ci/greenlight.cjs`.

WHAT THIS GUARDS. The engine lets a PR skip test-renet (90 minutes) or the
account E2E suite on evidence that some OTHER run, on any branch, already
executed that exact job green over byte-identical inputs. A false refusal costs
one full CI round. A false GREENLIGHT merges untested code, so every rule that
narrows the evidence is asserted here with a CONTROL that produces the opposite
outcome: an engine hardcoded to "always greenlight" and one hardcoded to "never
greenlight" both fail this file.

THE RULE THAT CARRIES THE MOST WEIGHT is rule 1, intent versus outcome: a
SKIPPED job must never count as evidence. Without it a reduced run whose renet
job was skipped would greenlight the next PR, which would skip it too, and the
suite would go unrun forever while every check stayed green.

--------------------------------------------------------------------------
WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP
--------------------------------------------------------------------------
Read from the lock rather than guessed from the fixtures, because the fixtures
mislead: most cases here are pure JSON in a tempdir and would suggest this port
needs no isolation at all. `gates.lock.json` declares `gate-test:greenlight` with
`reads: ["tree:repo"]`, and four cases earn it:

  * `test_declared_closure_paths_exist` runs `git ls-tree HEAD` for all 428
    declared closure entries of the REAL table.
  * `test_cli_emit_is_false_only` and `test_moved_pointer_refuses` drive the CLI
    against a fake `gh` that serves this repository's OWN `git ls-tree HEAD`
    output, so the candidate content is the real tree.
  * `test_key_order_is_cost_descending` and `test_candidate_window_is_widened`
    read the real `.ci/scripts/ci/scope-shadow.sh`, and
    `test_the_trail_digest_names_every_key` extracts a shell function out of it.

A battery step rewriting `scope-shadow.sh` or the engine mid-sweep is a
divergence that would be blamed on this port.

`REAL_TREE_TWIN = True` buys the serialisation, and it is honoured ONLY because
this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in
`test_twin_parity.py`, where an own group makes the opt-in vacuous.

--------------------------------------------------------------------------
DOES THE SUBJECT SELF-SCAN? NO, AND IT WAS MEASURED RATHER THAN ASSUMED
--------------------------------------------------------------------------
Two of the sweeps here could in principle see this file, so both were checked
before a fixture was written:

  * The closure table. `CLOSURES` declares 78 distinct `paths` entries; none is
    under `.ci/rediacc_ci`, and the eight `.ci/scripts/test/*` entries are named
    files, not directories. Measured by enumerating the table, not by reading it.
  * The fake `gh` backend serves `git ls-tree HEAD`, and the local side of the
    comparison is computed over the same tracked content, so an UNTRACKED file
    such as this one is invisible to both halves. The twin was driven green with
    this port's sibling already sitting untracked in the tree, which is the
    control for that claim.

So the fixtures are written out literally, exactly as the twin writes them.
"""

import json
import os
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-greenlight.sh"

# The closure-path sweep, the two fake-gh CLI cases and the three cases reading
# scope-shadow.sh all read the tracked tree. The lock says `tree:repo` too. See
# the docstring.
REAL_TREE_TWIN = True

ENGINE_REL = ".ci/scripts/ci/greenlight.cjs"
ENGINE = paths.from_root(*ENGINE_REL.split("/"))
SCOPE_SHADOW_REL = ".ci/scripts/ci/scope-shadow.sh"
SCOPE_SHADOW = paths.from_root(*SCOPE_SHADOW_REL.split("/"))
REPO_ROOT = paths.repo_root()

SHA_A = "1111111111111111111111111111111111111111"
SHA_B = "2222222222222222222222222222222222222222"
HASH_A = "aaaa000000000000000000000000000000000000000000000000000000000000"
HASH_B = "bbbb000000000000000000000000000000000000000000000000000000000000"

EV_JS = """
const g = require(process.argv[1]);
const v = g.evaluateGreenlight(JSON.parse(process.argv[2]));
process.stdout.write(JSON.stringify({
  greenlit: v.greenlit,
  runId: v.runId === undefined ? null : v.runId,
  reason: v.reason,
  trail: v.trail.map((t) => t.reason),
}));
"""


def require_engine(gate) -> str:
    """The subject, proved present before anything is claimed."""
    if not ENGINE.is_file():
        gate.log_fail("subject under test is missing: %s" % ENGINE_REL)
    return harness.require_tool("node", "install Node.js; the engine IS a CommonJS module")


def node_eval(gate, script: str, *args: str, env=None, cwd=None) -> harness.RunResult:
    """`node -e <script> <args...>`, with argv[1] the first arg as in the twin."""
    node = require_engine(gate)
    return harness.run([node, "-e", script, *args], env=env, cwd=cwd)


def ev(gate, payload: str) -> dict:
    """`ev <json>` -- drive the PURE core over an injected fixture.

    No network, no git, no clock: the whole decision is a function of its
    argument.
    """
    result = node_eval(gate, EV_JS, os.fspath(ENGINE), payload)
    if result.rc != 0:
        gate.log_fail(
            "the engine could not be driven at all (rc=%s): %s\ninput: %s"
            % (harness.describe_exit(result.rc), result.combined, payload)
        )
    try:
        return json.loads(result.out)
    except json.JSONDecodeError as exc:
        gate.log_fail("the engine emitted no parseable verdict (%s): %r" % (exc, result.out))
        raise  # unreachable; log_fail raises


def jget(verdict: dict, field: str) -> str:
    """`jget <json> <field>` -- read one field out of a verdict, AS A STRING.

    The twin's helper prints a string field verbatim and JSON-encodes anything
    else, so `greenlit` reads "true"/"false", an absent `runId` reads "null", and
    a trail reads as its JSON array. Preserved exactly, because every assertion
    below is written against those spellings.
    """
    value = verdict[field]
    if isinstance(value, str):
        return value
    return json.dumps(value)


def green_candidate(run_id: int) -> str:
    """`green_candidate <run-id>` -- a fixture candidate satisfying every rule.

    Cases mutate one field of it, so each assertion isolates one rule.
    """
    return (
        '{"runId":%d,"jobs":[{"name":"Tests + Infra / Renet","conclusion":"success"}],'
        '"gitlinks":{"private/renet":"%s"},"closureHash":"%s"}' % (run_id, SHA_A, HASH_A)
    )


def want(candidates: str) -> str:
    """`want <candidates-json>` -- the full evaluateGreenlight input for key renet.

    `wantGitlinks` is a { path -> sha } MAP because a key may pin several
    submodules (the eight VM/E2E keys pin four) or none at all.
    """
    return (
        '{"key":"renet","wantGitlinks":{"private/renet":"%s"},"wantClosureHash":"%s",'
        '"candidates":%s}' % (SHA_A, HASH_A, candidates)
    )


def candidate(run_id: int, name: str, conclusion: str, gitlinks: str, closure: str) -> str:
    """One candidate, spelled the way the twin spells its inline JSON."""
    return (
        '{"runId":%d,"jobs":[{"name":"%s","conclusion":"%s"}],"gitlinks":%s,"closureHash":"%s"}'
        % (run_id, name, conclusion, gitlinks, closure)
    )


def captured(result: harness.RunResult) -> str:
    """`$( ... )`: stdout with trailing newlines stripped, stderr discarded.

    Every CLI case in the twin is `out="$(... 2>/dev/null)"`, and several assert
    `out` is EMPTY. Comparing against `""` only means the same thing here if the
    trailing newline is stripped the way command substitution strips it.
    """
    return result.out.rstrip("\n")


# ---------------------------------------------------------------------------
# Case 1: a full match greenlights, and names the run that proved it.
# ---------------------------------------------------------------------------


def test_full_match_greenlights_and_names_the_run(gate):
    v = ev(gate, want("[%s]" % green_candidate(4242)))
    gate.assert_eq(jget(v, "greenlit"), "true", "a candidate matching every rule must greenlight")
    gate.assert_eq(jget(v, "runId"), "4242", "and must name the run id that is the evidence")
    gate.assert_eq(jget(v, "reason"), "job-green-same-inputs", "with the reason stated")

    # CONTROL: greenlit is not the constant answer. The SAME candidate against a
    # different wanted pointer must refuse, or nothing above is proven.
    v = ev(
        gate,
        '{"key":"renet","wantGitlinks":{"private/renet":"%s"},"wantClosureHash":"%s",'
        '"candidates":[%s]}' % (SHA_B, HASH_A, green_candidate(4242)),
    )
    gate.assert_eq(
        jget(v, "greenlit"),
        "false",
        "the same candidate against another pointer must NOT greenlight",
    )
    gate.assert_eq(
        jget(v, "reason"), "no-usable-candidate", "and the walk must end with no usable candidate"
    )
    gate.log_pass("a full match greenlights and names its evidence run (case 1)")


# ---------------------------------------------------------------------------
# Case 2: the job ran and FAILED. Matching inputs are irrelevant.
# ---------------------------------------------------------------------------


def test_failed_job_refuses(gate):
    cand = candidate(
        7, "Tests + Infra / Renet", "failure", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "a failed job must never greenlight")
    gate.assert_contains(
        jget(v, "trail"), "job-failed:failure", "refused as job-failed, carrying the conclusion"
    )

    # A cancelled run is the same class and is NOT rare: a live listing of
    # rediacc/console showed 'Tests + Infra / Account E2E' cancelled on the most
    # recent completed run.
    cand = candidate(
        8, "Tests + Infra / Renet", "cancelled", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_contains(
        jget(v, "trail"), "job-failed:cancelled", "a cancelled job is refused the same way"
    )
    gate.log_pass("a job that ran and did not succeed is refused (case 2)")


# ---------------------------------------------------------------------------
# Case 3: the job was SKIPPED. THE intent-versus-outcome case, and the one the
# planted-defect proof targets.
#
# PLANTED-DEFECT PROOF, executed 2026-07-31 on the twin. Rule 1 in
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


def test_skipped_job_refuses_as_not_run(gate):
    cand = candidate(
        9, "Tests + Infra / Renet", "skipped", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "a skipped job must never greenlight")
    gate.assert_contains(
        jget(v, "trail"), "job-not-run", "refused as job-not-run, exactly like an absent job"
    )

    # A run carrying no such job at all lands on the same reason, because
    # neither can prove the suite executed.
    cand = candidate(
        10, "Tests + Infra / Unit", "success", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_contains(jget(v, "trail"), "job-not-run", "an absent job is refused as job-not-run")

    # CONTROL: flipping only the conclusion to success greenlights the very same
    # fixture, so the refusal above is about the conclusion and nothing else in
    # the candidate.
    cand = candidate(
        9, "Tests + Infra / Renet", "success", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(
        jget(v, "greenlit"), "true", "the same fixture with conclusion=success DOES greenlight"
    )
    gate.log_pass("a skipped job is refused, so evidence cannot chain across reduced runs (case 3)")


# ---------------------------------------------------------------------------
# Case 4: the job is green and the pointer matches, but a console-side input
# differs. This is the rule that makes the greenlight safe for a PR that edits
# run-renet.sh without touching the submodule.
# ---------------------------------------------------------------------------


def test_differing_closure_refuses(gate):
    cand = candidate(
        11, "Tests + Infra / Renet", "success", '{"private/renet":"%s"}' % SHA_A, HASH_B
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "a differing console-side closure must refuse")
    gate.assert_contains(jget(v, "trail"), "closure-differs", "named as closure-differs")

    # CONTROL: flipping only the closure hash back greenlights the same fixture,
    # so the refusal is about the closure and nothing else.
    cand = candidate(
        11, "Tests + Infra / Renet", "success", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(
        jget(v, "greenlit"), "true", "the same fixture with the matching closure DOES greenlight"
    )
    gate.log_pass("a changed console-side input refuses as closure-differs (case 4)")


# ---------------------------------------------------------------------------
# Case 5: FAIL-OPEN. Absence and failure must both yield greenlit=false, never
# an exception and never a greenlight. This is the contract the whole design
# rests on: the engine may only ever turn a RUN into a SKIP, so every way it can
# go wrong has to land on "changed nothing".
# ---------------------------------------------------------------------------

THROWING_JS = """
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
"""


def test_absent_and_throwing_candidates_fail_open(gate):
    v = ev(gate, want("[]"))
    gate.assert_eq(jget(v, "greenlit"), "false", "an empty candidate list must not greenlight")
    gate.assert_eq(jget(v, "reason"), "no-candidates", "named as no-candidates")

    v = ev(
        gate,
        '{"key":"renet","wantGitlinks":{},"wantClosureHash":"%s","candidates":[%s]}'
        % (HASH_A, green_candidate(1)),
    )
    gate.assert_eq(
        jget(v, "reason"), "no-local-gitlink", "an unreadable local gitlink must not greenlight"
    )

    v = ev(
        gate,
        '{"key":"nonsense","wantGitlinks":{"private/renet":"%s"},"wantClosureHash":"%s",'
        '"candidates":[%s]}' % (SHA_A, HASH_A, green_candidate(1)),
    )
    gate.assert_contains(jget(v, "reason"), "unknown-key", "an unknown key must not greenlight")

    # A THROWING fetch at each of the three lazy stages. Injected here rather
    # than fixtured, because a thrown fetch is exactly what a rate-limited or
    # 404ing API looks like and JSON cannot express it.
    result = node_eval(gate, THROWING_JS, os.fspath(ENGINE))
    if result.rc != 0:
        gate.log_fail(
            "the throwing-fetch probe did not run at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    thrown = result.out
    gate.assert_contains(
        thrown, "jobs:false:jobs-unreadable:api exploded", "a throwing jobs fetch fails open"
    )
    gate.assert_contains(
        thrown,
        "gitlinks:false:gitlink-unreadable:api exploded",
        "a throwing gitlink fetch fails open",
    )
    gate.assert_contains(
        thrown,
        "closureHash:false:closure-unreadable:api exploded",
        "a throwing closure fetch fails open",
    )
    gate.log_pass("absence, bad input and a throwing API all fail open to no greenlight (case 5)")


# ---------------------------------------------------------------------------
# install_fake_gh -- put a working fake `gh` on PATH at <work>/bin.
#
# It serves this repo's REAL tree as the candidate's content, so the fixture
# cannot rot: whatever HEAD holds, the candidate holds the same, and a
# greenlight is due. Each CLI-level case then flips exactly ONE fact and asserts
# the greenlight withdraws.
#
# Every case that uses it calls it first, deliberately. One case replaces the
# binary with a deliberately broken one, and a later case that inherited that
# would pass for the wrong reason while looking like a real control. The port
# keeps the explicit call even though each case already has its own temp dir:
# the ordering hazard is the thing being documented, and a reader comparing the
# two files should not have to notice that Python made it moot.
# ---------------------------------------------------------------------------

FAKE_GH_BACKEND = r"""const { execFileSync } = require('child_process');
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
"""


def install_fake_gh(work) -> pathlib.Path:
    bindir = work / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    backend = work / "fake-gh.cjs"
    backend.write_text(FAKE_GH_BACKEND, encoding="utf-8")
    gh = bindir / "gh"
    gh.write_text('#!/bin/bash\nexec node "%s" "$@"\n' % backend, encoding="utf-8")
    gh.chmod(0o755)
    return bindir


def run_cli(gate, bindir, **extra) -> harness.RunResult:
    """`PATH=<bin>:$PATH node "$ENGINE" --key renet --repo owner/name --limit 1`."""
    node = require_engine(gate)
    env = {"PATH": "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", ""))}
    env.update(extra)
    return harness.run(
        [node, os.fspath(ENGINE), "--key", "renet", "--repo", "owner/name", "--limit", "1"],
        env=env,
    )


# ---------------------------------------------------------------------------
# Case 6: the CLI's emit, end to end and offline.
#
# The property asserted is the fail-open asymmetry: stdout may carry
# `run_<key>=false` and may never carry `run_<key>=true`, because `=false` is
# the only value that can shrink a round and there is no `=true` form to get
# wrong.
# ---------------------------------------------------------------------------


def test_cli_emit_is_false_only(gate):
    with harness.temp_dir() as work:
        bindir = install_fake_gh(work)

        out = captured(run_cli(gate, bindir, GL_REPO_ROOT=os.fspath(REPO_ROOT)))
        gate.assert_contains(out, "run_renet=false", "a due greenlight emits run_renet=false")
        gate.assert_not_contains(out, "run_renet=true", "and NEVER emits run_renet=true")
        gate.assert_not_contains(out, "=true", "the CLI has no =true emit form at all")
        gate.assert_contains(out, "evidence_renet=555001", "naming the run that is the evidence")

        # CONTROL 1: the same fixture with the job skipped emits NOTHING. This is
        # case 3 again at CLI level, where it decides real jobs.
        out = captured(
            run_cli(gate, bindir, GL_REPO_ROOT=os.fspath(REPO_ROOT), GL_CONCLUSION="skipped")
        )
        gate.assert_eq(out, "", "a skipped candidate job emits no output line at all")

        # CONTROL 2: one console-side closure blob moved, everything else identical.
        out = captured(
            run_cli(gate, bindir, GL_REPO_ROOT=os.fspath(REPO_ROOT), GL_PERTURB="run-renet.sh")
        )
        gate.assert_eq(out, "", "a single changed closure file withdraws the greenlight")

        # CONTROL 3: a gh that fails outright. The engine must stay silent and
        # exit 0, because a crash inside `initialize` stalls every job that needs
        # it, and this engine must never be the thing that fails.
        broken = bindir / "gh"
        broken.write_text('#!/bin/bash\necho "gh: boom" >&2\nexit 1\n', encoding="utf-8")
        broken.chmod(0o755)
        result = run_cli(gate, bindir)
        gate.assert_eq(result.rc, 0, "a broken gh must still exit 0")
        gate.assert_eq(captured(result), "", "and emit nothing")
        gate.log_pass("the CLI emits run_<key>=false or nothing, never =true (case 6)")


# ---------------------------------------------------------------------------
# Case 7: THE SUBMODULE POINTER RULE, stated by the operator as the core
# soundness requirement of the whole feature: a suite may be skipped ONLY when
# the submodule points at the exact hash some job-green run already tested. Any
# submodule change, however small, means the related tests run.
#
# It gets its own case because it is the rule most likely to be quietly weakened
# later. It is also the only rule that a plausible-sounding "optimisation" would
# break: accepting an ANCESTOR of the tested commit, or a pointer that merely
# resolves to the same branch, both read as reasonable and both let untested
# submodule code merge. The comparison is hash equality and nothing else.
#
# PLANTED-DEFECT PROOF, executed 2026-07-31 on the twin. Rule 2 in
# greenlight.cjs::evaluateCandidate was weakened from full equality to a
# 4-character prefix comparison, the shape a "cheap early-out" would take.
# With that one edit:
#   - this case FAILED, on the near-miss assertion specifically, with
#       FAIL: a pointer differing in one character must refuse: expected 'false', got 'true'
#   - cases 1 to 6 ALL still passed, so a weakened pointer rule is invisible to
#     every other property in this file and visible to this one.
# The engine was restored and re-verified byte-identical by md5
# (8b35c56e7f5ca90c959f90ac7db029b9 before and after).
# ---------------------------------------------------------------------------


def test_moved_pointer_refuses(gate):
    # FIRE: everything else is a perfect match. Job green, closure identical,
    # and ONLY the gitlink moved.
    cand = candidate(
        31, "Tests + Infra / Renet", "success", '{"private/renet":"%s"}' % SHA_B, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "a moved submodule pointer must never greenlight")
    gate.assert_eq(jget(v, "runId"), "null", "and must name no evidence run")
    gate.assert_contains(jget(v, "trail"), "pointer-differs", "refused as pointer-differs")

    # CONTROL: restore the pointer, change nothing else, and the same fixture
    # greenlights. Without this the refusal above could come from any field.
    cand = candidate(
        31, "Tests + Infra / Renet", "success", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(
        jget(v, "greenlit"), "true", "the same fixture with the matching pointer DOES greenlight"
    )

    # A one-character difference is a difference. Equality is over the whole
    # hash, not a prefix, so a near-miss cannot be read as a match.
    near = SHA_A[:39] + "9"
    cand = candidate(
        32, "Tests + Infra / Renet", "success", '{"private/renet":"%s"}' % near, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "a pointer differing in one character must refuse")

    # An absent gitlink (the candidate commit did not carry that submodule) is a
    # difference too, not a free pass.
    cand = candidate(33, "Tests + Infra / Renet", "success", "{}", HASH_A)
    v = ev(gate, want("[%s]" % cand))
    gate.assert_contains(
        jget(v, "trail"), "pointer-differs", "an absent gitlink refuses as pointer-differs"
    )

    # AND IT CHANGES NOTHING, proven at CLI level against the real tree: the fake
    # gh serves this repo's own content, so everything matches and a greenlight
    # is due, except that private/renet's gitlink is reported moved. The emit
    # must be empty, which is the state in which ci.yml runs the job.
    with harness.temp_dir() as work:
        bindir = install_fake_gh(work)
        out = captured(run_cli(gate, bindir, GL_REPO_ROOT=os.fspath(REPO_ROOT), GL_PERTURB="renet"))
        gate.assert_eq(out, "", "a moved private/renet pointer emits nothing, so the suite runs")

        # CONTROL for that emit: the same invocation WITHOUT the perturbation
        # does greenlight, so the empty output above is the moved pointer and not
        # a broken harness quietly emitting nothing for every input.
        out = captured(run_cli(gate, bindir, GL_REPO_ROOT=os.fspath(REPO_ROOT)))
        gate.assert_contains(out, "run_renet=false", "the unperturbed pointer still greenlights")
    gate.log_pass("the skip requires the EXACT submodule hash; any move runs the tests (case 7)")


# ---------------------------------------------------------------------------
# The job-name hazard, live-derived. A real run of rediacc/console carries all
# of "Tests + Infra / Renet" (the suite), "Build (Renet) / Renet (cached)" and
# "Build (Docker Fast) / Renet Docker". A prefix or substring match would read a
# cache-hit build job as proof that a 90-minute test suite passed.
# ---------------------------------------------------------------------------


def test_job_name_leaf_must_match_exactly(gate):
    for decoy in (
        "Build (Renet) / Renet (cached)",
        "Build (Docker Fast) / Renet Docker",
        "Tests + Infra / Renet Extra",
    ):
        cand = candidate(21, decoy, "success", '{"private/renet":"%s"}' % SHA_A, HASH_A)
        v = ev(gate, want("[%s]" % cand))
        gate.assert_eq(
            jget(v, "greenlit"), "false", "'%s' must not be read as the Renet suite" % decoy
        )

    # CONTROL: the real name, under a DIFFERENT caller prefix, still matches.
    # Only the leaf is ct-tests.yml's to control, so only the leaf is matched.
    cand = candidate(
        22, "Some Other Caller / Renet", "success", '{"private/renet":"%s"}' % SHA_A, HASH_A
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_eq(
        jget(v, "greenlit"), "true", "the leaf name matches regardless of the caller prefix"
    )

    # Two jobs answering to one name means the name no longer identifies the
    # suite, so neither reading is evidence.
    cand = (
        '{"runId":23,"jobs":[{"name":"A / Renet","conclusion":"success"},'
        '{"name":"B / Renet","conclusion":"success"}],'
        '"gitlinks":{"private/renet":"%s"},"closureHash":"%s"}' % (SHA_A, HASH_A)
    )
    v = ev(gate, want("[%s]" % cand))
    gate.assert_contains(
        jget(v, "trail"), "job-ambiguous", "two jobs of one name refuse as job-ambiguous"
    )
    gate.log_pass("only an exact job leaf name is evidence, and only when it is unique")


# ---------------------------------------------------------------------------
# ANTI-VACUITY on the closure table itself. A declared path that no longer
# exists would be hashed by nobody and noticed by nothing; the table would
# quietly stop covering the input it names. Assert the paths are real, and that
# both keys declare a non-trivial closure.
# ---------------------------------------------------------------------------

CLOSURE_PATHS_JS = r"""
const { CLOSURES } = require(process.argv[1]);
const lines = [];
for (const [key, c] of Object.entries(CLOSURES)) {
  for (const p of c.submodules) lines.push(`${key}\t${p}`);
  for (const p of c.paths) lines.push(`${key}\t${p}`);
}
process.stdout.write(`${lines.join("\n")}\n`);
"""


def ls_tree_lines(gate, spec: str) -> int:
    """`git -C <root> ls-tree HEAD -- <spec> | wc -l`."""
    git = harness.require_tool("git", "install git; the closure paths are checked against HEAD")
    result = harness.run([git, "-C", os.fspath(REPO_ROOT), "ls-tree", "HEAD", "--", spec])
    if result.rc != 0:
        gate.log_fail(
            "git ls-tree could not be run for %r (rc=%s): %s"
            % (spec, harness.describe_exit(result.rc), result.err)
        )
    return len([ln for ln in result.out.split("\n") if ln != ""])


def test_declared_closure_paths_exist(gate):
    result = node_eval(gate, CLOSURE_PATHS_JS, os.fspath(ENGINE))
    if result.rc != 0:
        gate.log_fail(
            "the closure table could not be read at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )

    count = 0
    for line in result.out.split("\n"):
        if "\t" not in line:
            continue
        key, _, path = line.partition("\t")
        if not path:
            continue
        gate.assert_eq(
            ls_tree_lines(gate, path), 1, "closure path for %s must exist in HEAD: %s" % (key, path)
        )
        count += 1
    # The floor sits JUST BELOW the real total (408 across 18 keys as of
    # 2026-08-08), not at some token value: a `> 15` floor survived a table that
    # had lost every key but one. At 400 a parse break reads as 0 and a dropped
    # VM/E2E key costs 30 entries, both of which fire this; trimming a path or
    # two during honest maintenance does not.
    gate.assert_eq(
        1 if count > 400 else 0,
        1,
        "the table must stay whole (%d entries seen, floor 400)" % count,
    )

    # CONTROL: the same assertion applied to a path that does NOT exist must
    # fail, or the loop above proves only that the loop ran.
    gate.assert_eq(
        ls_tree_lines(gate, ".ci/scripts/private/no-such-file.sh"),
        0,
        "the existence probe returns 0 lines for a path that is not there",
    )
    gate.log_pass("every declared closure path exists in HEAD (%d entries)" % count)


# ---------------------------------------------------------------------------
# Case 10: MATRIX EVIDENCE. e2e_workers is five API jobs, one per distro. The
# property is that ALL FIVE must have run green: a candidate carrying four of
# them, or five with one skipped, proves nothing about the missing leg, and
# accepting it would let exactly the distro a PR breaks be the one never run.
#
# This is rule 1 restated for the matrix case, and it is the reason `jobNames`
# is a list rather than a name plus a count.
# ---------------------------------------------------------------------------

LEGS_JS = """
const { CLOSURES } = require(process.argv[1]);
process.stdout.write(CLOSURES.e2e_workers.jobNames.join("\\n"));
"""

# The twin builds this candidate through `node -e <mk> -- <leg>...` and records
# a real trap in its comment: `node -e <code> -- a b` puts `a` at argv[1], not
# argv[2], because node consumes the `--` itself, and slicing from 2 silently
# dropped the first leg while reading as a real refusal. The port sidesteps the
# argv question entirely by building the JSON here, which cannot lose a leg
# without the list below visibly losing one.
MATRIX_GITLINKS = {
    "private/renet": SHA_A,
    "private/account": SHA_A,
    "private/elite": SHA_A,
    "private/homebrew-tap": SHA_A,
}


def matrix_candidate(*legs: str) -> str:
    """`<leaf>=<conclusion>` per leg, as the twin's `mk` helper takes them."""
    jobs = []
    for leg in legs:
        leaf, _, conclusion = leg.rpartition("=")
        jobs.append({"name": "Tests + Infra / %s" % leaf, "conclusion": conclusion})
    return json.dumps(
        {"runId": 60, "jobs": jobs, "gitlinks": MATRIX_GITLINKS, "closureHash": HASH_A}
    )


def want_workers(cand: str, gitlinks: dict | None = None) -> str:
    """The evaluateGreenlight input for the four-submodule VM/E2E shape."""
    return '{"key":"e2e_workers","wantGitlinks":%s,"wantClosureHash":"%s","candidates":[%s]}' % (
        json.dumps(gitlinks if gitlinks is not None else MATRIX_GITLINKS),
        HASH_A,
        cand,
    )


ALL_FIVE = (
    "E2E Workers (ubuntu-24.04)=success",
    "E2E Workers (debian-13)=success",
    "E2E Workers (fedora-43)=success",
    "E2E Workers (opensuse-16.0)=success",
    "E2E Workers (oracle-10)=success",
)


def test_matrix_key_needs_every_leg(gate):
    result = node_eval(gate, LEGS_JS, os.fspath(ENGINE))
    if result.rc != 0:
        gate.log_fail(
            "the matrix leg list could not be read at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    # `wc -l` on the twin's `printf '%s\n'` counts the legs, one per line.
    gate.assert_eq(
        len([ln for ln in result.out.split("\n") if ln != ""]),
        5,
        "e2e_workers declares five matrix legs",
    )

    # FIRE 1: one leg absent from the run entirely.
    cand = matrix_candidate(*ALL_FIVE[:4])
    v = ev(gate, want_workers(cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "four green legs out of five must NOT greenlight")
    gate.assert_contains(
        jget(v, "trail"),
        "job-not-run@E2E Workers (oracle-10)",
        "and the trail must name the leg that was missing",
    )

    # FIRE 2: all five present, one of them SKIPPED. This is the shape a reduced
    # run leaves behind, and it is the one that must never chain.
    cand = matrix_candidate(
        "E2E Workers (ubuntu-24.04)=success",
        "E2E Workers (debian-13)=success",
        "E2E Workers (fedora-43)=skipped",
        "E2E Workers (opensuse-16.0)=success",
        "E2E Workers (oracle-10)=success",
    )
    v = ev(gate, want_workers(cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "one skipped leg out of five must NOT greenlight")
    gate.assert_contains(
        jget(v, "trail"),
        "job-not-run@E2E Workers (fedora-43)",
        "named as the skipped leg, not as a generic refusal",
    )

    # FIRE 3: one leg red.
    cand = matrix_candidate(
        "E2E Workers (ubuntu-24.04)=success",
        "E2E Workers (debian-13)=failure",
        "E2E Workers (fedora-43)=success",
        "E2E Workers (opensuse-16.0)=success",
        "E2E Workers (oracle-10)=success",
    )
    v = ev(gate, want_workers(cand))
    gate.assert_eq(jget(v, "greenlit"), "false", "one failed leg out of five must NOT greenlight")

    # CONTROL: all five green, nothing else changed, and the same shape DOES
    # greenlight. Without it every assertion above could be a broken fixture.
    cand = matrix_candidate(*ALL_FIVE)
    v = ev(gate, want_workers(cand))
    gate.assert_eq(jget(v, "greenlit"), "true", "all five legs green DOES greenlight")
    gate.assert_eq(jget(v, "runId"), "60", "naming the run that proved it")

    # And a moved pointer on ANY ONE of the four pinned submodules withdraws it,
    # so the multi-submodule rule 2 is not satisfied by the first entry.
    one_moved = dict(MATRIX_GITLINKS)
    one_moved["private/elite"] = SHA_B
    v = ev(gate, want_workers(cand, one_moved))
    gate.assert_eq(
        jget(v, "greenlit"), "false", "one moved pointer of four withdraws the greenlight"
    )
    gate.assert_contains(jget(v, "trail"), "pointer-differs", "refused as pointer-differs")
    gate.log_pass("a matrix key needs every leg green; four of five is not evidence (case 10)")


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
# happens to have one, and dropping the assertion would have left that behaviour
# unpinned while looking like a tidy-up.
# ---------------------------------------------------------------------------

PACKAGE_TESTS_PINS_JS = """
const { CLOSURES } = require(process.argv[1]);
process.stdout.write(String(CLOSURES.package_tests.submodules.length));
"""


def test_empty_submodule_list_is_vacuous_not_broken(gate):
    result = node_eval(gate, PACKAGE_TESTS_PINS_JS, os.fspath(ENGINE))
    if result.rc != 0:
        gate.log_fail(
            "the package_tests pin count could not be read at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    gate.assert_eq(result.out, "0", "the package_tests key declares no submodules at all")

    cand = (
        '{"runId":70,"jobs":[{"name":"Linux Packages","conclusion":"success"}],'
        '"gitlinks":{},"closureHash":"%s"}' % HASH_A
    )
    v = ev(
        gate,
        '{"key":"package_tests","wantGitlinks":{},"wantClosureHash":"%s","candidates":[%s]}'
        % (HASH_A, cand),
    )
    gate.assert_eq(
        jget(v, "greenlit"), "true", "an empty pin list still greenlights on rules 1 and 3"
    )
    gate.assert_eq(jget(v, "runId"), "70", "naming the evidence run")

    # CONTROL 1: rule 3 still decides for a key with no pins, so the pass above
    # is not "empty submodules disables every rule".
    cand = (
        '{"runId":71,"jobs":[{"name":"Linux Packages","conclusion":"success"}],'
        '"gitlinks":{},"closureHash":"%s"}' % HASH_B
    )
    v = ev(
        gate,
        '{"key":"package_tests","wantGitlinks":{},"wantClosureHash":"%s","candidates":[%s]}'
        % (HASH_A, cand),
    )
    gate.assert_eq(jget(v, "greenlit"), "false", "a differing closure still refuses a pinless key")
    gate.assert_contains(jget(v, "trail"), "closure-differs", "named as closure-differs")

    # CONTROL 2: rule 1 still decides too.
    cand = (
        '{"runId":72,"jobs":[{"name":"Linux Packages","conclusion":"skipped"}],'
        '"gitlinks":{},"closureHash":"%s"}' % HASH_A
    )
    v = ev(
        gate,
        '{"key":"package_tests","wantGitlinks":{},"wantClosureHash":"%s","candidates":[%s]}'
        % (HASH_A, cand),
    )
    gate.assert_eq(jget(v, "greenlit"), "false", "a skipped job still refuses a pinless key")

    # CONTROL 3: the emptiness is a property of THAT key, not of the check. A key
    # that DOES declare pins and cannot read one of them must still refuse with
    # no-local-gitlink rather than proceeding on a short map.
    v = ev(
        gate,
        '{"key":"e2e_workers","wantGitlinks":{"private/renet":"%s"},"wantClosureHash":"%s",'
        '"candidates":[]}' % (SHA_A, HASH_A),
    )
    gate.assert_eq(
        jget(v, "reason"),
        "no-local-gitlink",
        "a key with unread pins refuses rather than comparing a short map",
    )
    gate.log_pass("an empty submodule list is vacuous for that key and only that key (case 11)")


# ---------------------------------------------------------------------------
# Case 12: KEY ORDER IS COST-DESCENDING. scope-shadow.sh passes the pending keys
# through in CLOSURES' own order and the walk budget is per invocation, so the
# tail of this list is what a timeout abandons. Pin both ends: the most
# expensive key first, the cheapest last. Inserting a new key at the top of the
# table (the natural place to paste one) would fire this.
# ---------------------------------------------------------------------------

KEY_ORDER_JS = """
const { CLOSURES } = require(process.argv[1]);
process.stdout.write(Object.keys(CLOSURES).join(" "));
"""

# `^\s*if ! bounded node "\$GREENLIGHT"`, the twin's grep. Written as a Python
# regex on purpose: CLAUDE.md records that ugrep's `-E` returns silent false
# zeros when `^` is alternated with a negated class, and a sweep that reports
# "no findings" for the wrong reason is exactly what this case exists to catch.
INVOCATION_RE = re.compile(r'^\s*if ! bounded node "\$GREENLIGHT"')


def read_scope_shadow(gate) -> str:
    if not SCOPE_SHADOW.is_file():
        gate.log_fail(
            "%s is missing, so the three cases that read it would assert nothing" % SCOPE_SHADOW_REL
        )
    return SCOPE_SHADOW.read_text(encoding="utf-8")


def test_key_order_is_cost_descending(gate):
    result = node_eval(gate, KEY_ORDER_JS, os.fspath(ENGINE))
    if result.rc != 0:
        gate.log_fail(
            "the key order could not be read at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    keys = result.out
    first = keys.split(" ")[0]
    last = keys.split(" ")[-1]
    gate.assert_eq(
        first, "e2e_workers", "the first key must be the most expensive one (five 90-minute legs)"
    )
    gate.assert_eq(
        last, "unit", "the last key must be the cheapest one, so a dead budget starves it"
    )

    # CONTROL: the probe reads the real order rather than echoing its argument.
    gate.assert_not_contains(first, "unit", "the first key is not the last one")

    # scope-shadow.sh must be the consumer of that order, and must ask for the
    # raised budget. Asserted against the INVOCATION LINE, not the file: the
    # first version of this grepped the whole file for '--budget 90', and the
    # mutation proof caught it passing with the flag deleted from the command,
    # because the comment ABOVE the command explains the flag and still says
    # '--budget 90'. A gate satisfied by its own prose cannot fire.
    invocation = "\n".join(
        line for line in read_scope_shadow(gate).splitlines() if INVOCATION_RE.match(line)
    )
    gate.assert_contains(
        invocation,
        "--budget 90",
        "the scope-shadow greenlight INVOCATION must raise the walk budget",
    )
    gate.log_pass(
        "the key order is cost-descending and scope-shadow.sh raises the budget (case 12)"
    )


# ---------------------------------------------------------------------------
# Case 13: THE TRAIL MUST STAY READABLE. The trail is the only thing that makes
# a non-greenlight diagnosable, and it is surfaced through a step summary with a
# byte cap. At two keys the raw dump fitted; at eighteen keys against a
# 25-candidate list it is ~450 rows and it truncated MID-LINE inside the second
# key, so sixteen keys' diagnostics were simply absent. scope-shadow.sh's
# greenlight_digest exists to condense it, and this case is what stops the
# digest silently dropping keys as the table grows again.
# ---------------------------------------------------------------------------


def extract_digest_fn(gate) -> str:
    """`sed -n '/^greenlight_digest() {/,/^}$/p'` over scope-shadow.sh."""
    lines = read_scope_shadow(gate).splitlines()
    out, inside = [], False
    for line in lines:
        if not inside and line.startswith("greenlight_digest() {"):
            inside = True
        if inside:
            out.append(line)
            if line == "}":
                break
    return "".join(line + "\n" for line in out)


def run_digest(gate, fn_file, raw_file) -> str:
    """Source the extracted function and call it, exactly as the twin does.

    BLOCKER: the function under test is defined in scope-shadow.sh, which cannot
    be sourced whole because sourcing it runs the scope engine.
    """
    bash = harness.require_tool("bash", "install bash; greenlight_digest IS a shell function")
    result = harness.run(
        [
            bash,
            "-c",
            'source "$1"; greenlight_digest "$2"',
            "_",
            os.fspath(fn_file),
            os.fspath(raw_file),
        ]
    )
    if result.rc != 0:
        gate.log_fail(
            "greenlight_digest could not be run at all (rc=%s): %s"
            % (harness.describe_exit(result.rc), result.combined)
        )
    return result.out.rstrip("\n")


def test_the_trail_digest_names_every_key(gate):
    with harness.temp_dir() as work:
        fn = work / "digest.sh"
        body = extract_digest_fn(gate)
        fn.write_text(body, encoding="utf-8")
        gate.assert_contains(
            body, "awk", "greenlight_digest must be extractable from scope-shadow.sh"
        )

        # A synthetic trail in the engine's exact debug shape: three keys, each
        # with a header block and a multi-row candidate table.
        raw = work / "trail.err"
        chunks = ["greenlight: repo=owner/name candidates=3 budget=90s"]
        for k in ("alpha", "beta", "gamma"):
            chunks.extend(
                [
                    "",
                    "greenlight[%s] jobs='Some Job'" % k,
                    "greenlight[%s] pins=private/renet=abcdef12" % k,
                    "greenlight[%s] closure=%s0000000000000000000000 (26 paths)" % (k, k),
                    "  run id        head      verdict",
                    "  900000001     11111111  pointer-differs",
                    "  900000002     22222222  closure-differs",
                    "  900000003     33333333  job-not-run@E2E Workers (oracle-10)",
                    "greenlight[%s] VERDICT: no (no-usable-candidate)" % k,
                    "greenlight[%s]: no greenlight (no-usable-candidate)" % k,
                ]
            )
        chunks.append("greenlight[delta]: local inputs unreadable (boom), nothing is greenlit")
        raw.write_text("".join(line + "\n" for line in chunks), encoding="utf-8")

        digest = run_digest(gate, fn, raw)

        # Every key survives, with its verdict and the newest candidate's reason.
        for k in ("alpha", "beta", "gamma"):
            gate.assert_contains(digest, k, "the digest must name key %s" % k)
        gate.assert_contains(digest, "walked=3", "and must say how many candidates were walked")
        gate.assert_contains(
            digest,
            "newest 900000001 pointer-differs",
            "and must carry the NEWEST candidate's reason, which is the one that matters",
        )

        # A reason containing spaces (the matrix form) must survive whole.
        wide = work / "trail-matrix.err"
        wide.write_text(
            "".join(
                line + "\n"
                for line in (
                    "greenlight[m] closure=aaaa000000000000 (26 paths)",
                    "  run id        head      verdict",
                    "  900000009     99999999  job-not-run@E2E Workers (oracle-10)",
                    "greenlight[m] VERDICT: no (no-usable-candidate)",
                )
            ),
            encoding="utf-8",
        )
        gate.assert_contains(
            run_digest(gate, fn, wide),
            "job-not-run@E2E Workers (oracle-10)",
            "a matrix refusal keeps the leg name, spaces and all",
        )

        # An unrecognised line is PASSED THROUGH, never filtered into silence.
        gate.assert_contains(
            digest,
            "local inputs unreadable (boom)",
            "a line the digest does not recognise must survive verbatim",
        )

        # CONTROL: the digest is a real reduction. Against the LIVE-shaped input
        # it must be far smaller than the raw trail, or it is not solving the
        # problem it was written for.
        rawbytes = raw.stat().st_size
        digestbytes = len(digest.encode("utf-8"))
        gate.assert_eq(
            1 if digestbytes < rawbytes else 0,
            1,
            "the digest must be smaller than the raw trail (%d vs %d bytes)"
            % (digestbytes, rawbytes),
        )
        gate.log_pass("the trail digest names every key and survives a growing table (case 13)")


# ---------------------------------------------------------------------------
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
# ---------------------------------------------------------------------------

# THE TWIN RUNS TWO DIFFERENT PIPELINES HERE, AND THAT IS PRESERVED, NOT TIDIED.
#
# The real extractor is
#     grep -n -- '--limit' <file> | grep -v '^[[:space:]]*#' | grep 'GREENLIGHT'
# and its middle stage is INERT: `grep -n` prefixes every line with `<n>:`, so a
# pattern anchored at `^` followed by optional whitespace and `#` can never
# match. Measured on the real file today: stage 2 passes BOTH lines through
# (422, the comment, and 436, the invocation) and only stage 3 drops the comment,
# because that comment says "GREENLIT" rather than "GREENLIGHT".
#
# The second CONTROL below uses a DIFFERENT and correct filter,
# `grep -vE '^[0-9]+:[[:space:]]*#'`, which does anchor after the line number. So
# the control proves a comment filter the real path does not use. The twin's own
# comment describes the hazard exactly ("the trailing GREENLIGHT match hides the
# rot until someone writes that literal in a comment near --limit"), so this is a
# known shape rather than a discovery, and unifying the two here would CHANGE THE
# VERDICT on a tree where a comment near `--limit` mentions GREENLIGHT. A port
# does not get to fix its subject. Both pipelines are therefore transcribed as
# they are, and the divergence is reported rather than absorbed.
POSIX_SPACE = " \t\n\r\f\v"
LIMIT_VALUE_RE = re.compile(r".*--limit\s+([0-9]+).*")
# `^[[:space:]]*#` applied to `<n>:<text>`: inert, and deliberately so.
INERT_COMMENT_RE = re.compile(r"^[%s]*#" % re.escape(POSIX_SPACE))
# `^[0-9]+:[[:space:]]*#`: the corrected form, used only by the control.
NUMBERED_COMMENT_RE = re.compile(r"^[0-9]+:[%s]*#" % re.escape(POSIX_SPACE))


def grep_n(text: str, needle: str) -> list[str]:
    """`grep -n -- <needle>`: matching lines as `<lineno>:<text>`."""
    return [
        "%d:%s" % (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if needle in line
    ]


def limit_lines(text: str) -> list[str]:
    """The REAL extractor, inert middle stage included."""
    return [
        row
        for row in grep_n(text, "--limit")
        if not INERT_COMMENT_RE.match(row) and "GREENLIGHT" in row
    ]


def limit_lines_control(text: str) -> int:
    """The control's extractor, with the comment filter that actually anchors."""
    return len(
        [
            row
            for row in grep_n(text, "--limit")
            if not NUMBERED_COMMENT_RE.match(row) and "GREENLIGHT" in row
        ]
    )


def test_candidate_window_is_widened(gate):
    lines = limit_lines(read_scope_shadow(gate))
    if not lines:
        gate.log_fail(
            "scope-shadow.sh no longer passes --limit, so the engine falls back to 25 and the "
            "window can silently close"
        )

    # `sed -E 's/.*--limit +([0-9]+).*/\1/'` over the whole capture. The twin
    # feeds it every surviving line at once; there is exactly one today, and a
    # second would make the value ambiguous, so that is asserted rather than
    # silently resolved by taking the first.
    gate.assert_eq(len(lines), 1, "exactly one GREENLIGHT invocation may carry --limit: %r" % lines)
    match = LIMIT_VALUE_RE.match(lines[0])
    if match is None:
        gate.log_fail("could not read the --limit value from: %s" % lines[0])
    limit = int(match.group(1))
    if limit < 40:
        gate.log_fail(
            "--limit is %d; the observed walk already reached 21 of 24, so anything near the "
            "default reopens the cliff" % limit
        )

    # CONTROL, by construction: the same extractor must REFUSE an invocation that
    # omits --limit. Without this the assertion above passes trivially the day
    # someone drops the flag and the grep returns nothing... which is what the
    # first branch checks, so prove that branch can actually distinguish.
    if limit_lines('bounded node "$GREENLIGHT" --repo x --budget 90 --debug\n'):
        gate.log_fail("CONTROL DID NOT FIRE: an invocation with no --limit read as compliant")

    # CONTROL: the comment filter must actually EXCLUDE a comment. Without this
    # it can rot back to dead code unnoticed -- the trailing GREENLIGHT match
    # hides the rot until someone writes that literal in a comment near --limit,
    # which is exactly how the first version shipped.
    kept = limit_lines_control(
        "    # note: pass --limit to GREENLIGHT here\n"
        '    bounded node "$GREENLIGHT" --limit 60 --budget 90\n'
    )
    if kept != 1:
        gate.log_fail(
            "the comment filter is dead: expected 1 code line, kept %d (a comment slipped "
            "through)" % kept
        )

    gate.log_pass("candidate window widened to %d (default 25 would close silently)" % limit)
