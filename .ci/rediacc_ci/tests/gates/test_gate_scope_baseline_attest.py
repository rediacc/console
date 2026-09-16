"""Port of `.ci/scripts/test/gates/test-scope-baseline-attest.sh`.

Unit test for VERIFY-AT-READ baseline attestation in the CI scope engine:
`.ci/scripts/ci/scope-engine.cjs` (`attestPlan` + `createRepoIo` + the fenced walk).

WHAT THIS GUARDS. A baseline is the claim "this ancestor already ran the whole suite
green, so the delta since is all that needs running". Everything a reduced round skips
rests on that claim. The plan artifact alone cannot support it: a plan states INTENT,
and a run whose watchdog rerun skipped half the fleet leaves behind a plan that looks
identical to an honest one.

So nobody writes a `reconciled` marker and nobody is trusted to. The READER downloads
the plan, fetches THAT run's per-job outcomes from the Jobs API, runs the existing pure
`reconcile()` itself, and only then may set the flag. The self-declared field in the
downloaded bytes is DELETED before anything reads it, which is why case (c) plants a
self-declared reconciled flag in the artifact and still expects a refusal.

THE WALK IS FENCED, NOT COUNTED (candidate C). A fixed candidate count lost twice in
one night (limit 5 vs a green 7 back on run 30478917957, limit 20 vs a green 23 back
after a twelve-run red streak), each time manufacturing a "no baseline" verdict
indistinguishable from a considered one. The walk's domain is now the commits the PR
owns (`rev-list head ^mergeParent`), run lookups ride ONE paginated branch listing so a
red candidate costs zero API calls, green attestation attempts are bounded by
`GREEN_ATTEST_BUDGET`, and `DEFAULT_CANDIDATE_LIMIT` survives only as a safety valve.
Cases (n) through (t) prove each bound in BOTH directions, and (r) is the cost lock:
run listing must scale with PAGES, never with candidates, or candidate C silently
degrades back into the per-commit walk it replaced.

POLARITY: fail-open. Every refusal here costs one full CI round, never a red check.
That is the opposite of the reconciler's polarity and is the reason the reconciler's
verdict is safe to consume from this side.

Every planted defect is PAIRED with the control that proves the mechanism can still say
yes, because a gate stuck at "refuse" would pass every failure case in this file while
being exactly as broken as one stuck at "accept".

WHY THE HARNESS STAYS JAVASCRIPT, verbatim from the twin. It is not a fixture, it is a
MODEL of git and gh: `rev-list` honours `--max-count` and `^fence` exclusion, and the
branch run listing paginates at 100 per page exactly as the Actions API does. The mock
used to return every candidate whatever the caller asked for, and walk depth was
invisible to the entire suite until it stopped. Re-expressing that model in Python
would be a SECOND model of the same two tools, and the expensive half of two models is
that both look right. The port therefore writes the same `harness.js` into pytest's
`tmp_path` and drives it with node, which also keeps every scenario's mutation string
byte-identical to the twin's.

WHAT THE PORT DOES CHANGE. The twin reads result fields through an `rget` helper that
evaluates a JS expression in a nested `node`; here the harness's JSON is parsed by
Python once per scenario and read as data. Streams stay SEPARATE, as the twin keeps
them: two cases assert stderr is EMPTY, and an engine that throws instead of answering
must be visible as an exit code rather than folded into stdout.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-scope-baseline-attest.sh"

ENGINE = paths.from_root(".ci", "scripts", "ci", "scope-engine.cjs")
MAP = paths.from_root(".ci", "scripts", "ci", "scope-map.cjs")
RECONCILE = paths.from_root(".ci", "scripts", "ci", "skip-plan-reconcile.cjs")
SHADOW = paths.from_root(".ci", "scripts", "ci", "scope-shadow.sh")

HARNESS_JS = r"""'use strict';
const fs = require('fs');
const path = require('path');

const engine = require(process.env.ENGINE);
const scopeMap = require(process.env.MAP);
const reconciler = require(process.env.RECONCILE);

const HEAD = 'HEAD1';
const CAND = 'CAND1';
const MERGE = 'MERGE1';
const BASE = 'BASE1';
const RUN_A = '1001';

const S = (name) => ({ name, conclusion: 'success' });
const K = (name) => ({ name, conclusion: 'skipped' });

// Run 30307775327's shape: a leaf for every planned key (matrix legs and all),
// the eleven structural skips that a healthy run really carries, and unplanned
// extras the reconciler must ignore.
const healthyJobs = () => [
  S('Initialize'),
  S('Tests + Infra / Unit'),
  S('Tests + Infra / E2E Workers (ubuntu-24.04)'),
  S('Tests + Infra / E2E Workers (fedora-43)'),
  S('Tests + Infra / E2E Ceph'),
  S('Tests + Infra / E2E Ceph Workers'),
  S('Tests + Infra / E2E K8s'),
  S('Tests + Infra / E2E K8s Ceph'),
  S('Tests + Infra / E2E K8s Multinode'),
  S('Tests + Infra / E2E Migrate'),
  S('Tests + Infra / Concurrent Fork Isolation'),
  S('Tests + Infra / Renet'),
  S('Tests + Infra / License Enforcement'),
  S('Tests + Infra / Account E2E'),
  S('Tests + Infra / Drills'),
  S('Tests + Infra / Migration Test'),
  S('OPS Tests / OPS Provision (linux-amd64)'),
  S('OPS Tests / OPS Check (linux-arm64)'),
  S('Elite Run'),
  S('Tests + Infra / Update Flow / Update flow (Linux x64)'),
  S('Tests + Infra / Linux Packages'),
  S('Validate Install Methods / Linux (x64)'),
  S('Validate Install Methods / macOS (ARM64)'),
  S('Validate Install Methods / Windows (x64)'),
  K('Build (Renet) / Procwalk (${{ matrix.os }})'),
  K('Build (Renet) / Renet (Full)'),
  K('Build (Docker Fast) / Renet Docker'),
  K('Build (Docker Fast) / CLI Docker'),
  K('Build (Docker Fast) / JSON'),
  K('Build (Docker Fast) / CLI Docker (cached)'),
  K('Build (Docker Fast) / Server Docker (cached)'),
  K('Build (Docker Fast) / Devcontainer (amd64)'),
  K('Build (Docker Fast) / Devcontainer (arm64)'),
  K('Build (Docker Fast) / Devcontainer Manifest'),
  K('Check Release State'),
];

// The plan is generated FROM scope-map's keys, so adding a job surface without
// adding its leaf above makes the CONTROL fail. That is the gate working: a
// planned key with no observable leaf is a real defect in a real run.
const basePlan = (runId) => ({
  run_id: runId,
  mode: 'full',
  base_sha: BASE,
  jobs: Object.fromEntries(
    Object.keys(scopeMap.JOB_SURFACES).map((k) => [k, { run: true, reason: 'full' }]),
  ),
});

const baseFixture = () => ({
  head: HEAD,
  mergeSha: MERGE,
  firstParent: BASE,
  firstParentThrow: false,
  // branch powers the one-shot run listing; null exercises the per-commit
  // fallback path, runsListThrow the degraded one.
  branch: 'wave-branch',
  runsListThrow: false,
  diff: 'docs/ci-overhaul/notes.md\n',
  candidates: [CAND],
  runs: { [CAND]: [{ databaseId: Number(RUN_A), status: 'completed', conclusion: 'success' }] },
  // Absent id => the artifact download throws, exactly as `gh run download`
  // does for a run that never uploaded one. A string value is written to
  // plan.json VERBATIM, which is how corrupt bytes are expressed.
  plans: { [RUN_A]: basePlan(RUN_A) },
  jobs: { [RUN_A]: { jobs: healthyJobs() } },
  // Raw text wins over `jobs`, for the concatenated multi-page payload.
  jobsRaw: {},
});

function makeRun(f, calls) {
  return (cmd, args) => {
    if (cmd === 'git') {
      const a = args.slice(2); // drop the leading -C <repoRoot>
      if (a[0] === 'rev-parse' && a[1] === '--is-shallow-repository') {
        calls.push('git is-shallow');
        return 'false\n';
      }
      if (a[0] === 'rev-list') {
        calls.push('git rev-list');
        // HONOUR --max-count AND `^fence`. This mock used to return every
        // candidate whatever the caller asked for, so the walk depth was
        // invisible to the entire suite and a too-small limit could never be
        // caught. Real rev-list truncates and excludes; a fixture that does
        // not is not a model of it. The fence is modelled positionally: a
        // fixture places the fence sha INSIDE candidates and everything from
        // it onward is beyond the boundary.
        const cap = a.map((x) => /^--max-count=(\d+)$/.exec(String(x)))
          .filter(Boolean)
          .map((m) => Number(m[1]))[0];
        const fence = a.filter((x) => String(x).startsWith('^')).map((x) => String(x).slice(1))[0];
        let all = [f.head, ...f.candidates];
        if (fence) {
          const i = all.indexOf(fence);
          if (i >= 0) all = all.slice(0, i);
        }
        return `${(cap ? all.slice(0, cap) : all).join('\n')}\n`;
      }
      if (a[0] === 'rev-parse') {
        calls.push('git first-parent');
        if (f.firstParentThrow) throw new Error('bad mergeSha');
        return `${f.firstParent}\n`;
      }
      if (a[0] === 'diff-tree') {
        calls.push('git diff-tree');
        return f.diff;
      }
      throw new Error(`unexpected git call: ${a.join(' ')}`);
    }
    if (cmd === 'gh' && args[0] === 'api' && /actions\/runs\?/.test(args[1])) {
      // The one-shot branch run listing, paginated at 100 like the real API.
      const page = Number((/[?&]page=(\d+)/.exec(args[1]) || [])[1] || 1);
      calls.push(`gh api runs-list p${page}`);
      if (f.runsListThrow) throw new Error('listing unavailable');
      const flat = [];
      for (const [sha, runs] of Object.entries(f.runs)) {
        for (const r of runs) {
          flat.push({ id: r.databaseId, name: 'Console CI', head_sha: sha, status: r.status, conclusion: r.conclusion });
        }
      }
      return JSON.stringify({ workflow_runs: flat.slice((page - 1) * 100, page * 100) });
    }
    if (cmd === 'gh' && args[0] === 'run' && args[1] === 'list') {
      const sha = args[args.indexOf('--commit') + 1];
      calls.push(`gh run list ${sha}`);
      return JSON.stringify(f.runs[sha] || []);
    }
    if (cmd === 'gh' && args[0] === 'run' && args[1] === 'download') {
      const id = String(args[2]);
      const dir = args[args.indexOf('-D') + 1];
      calls.push(`gh run download ${id}`);
      const p = f.plans[id];
      if (p === undefined) throw new Error('artifact not found: ci-skip-plan');
      fs.writeFileSync(path.join(dir, 'plan.json'), typeof p === 'string' ? p : JSON.stringify(p, null, 2));
      return '';
    }
    if (cmd === 'gh' && args[0] === 'api') {
      const id = /runs\/(\d+)\/jobs/.exec(args[1])[1];
      calls.push(`gh api jobs ${id}`);
      if (f.jobsRaw[id] !== undefined) return f.jobsRaw[id];
      const j = f.jobs[id];
      if (j === 'THROW' || j === undefined) throw new Error('jobs API unavailable');
      return JSON.stringify(j);
    }
    throw new Error(`unexpected call: ${cmd} ${args.join(' ')}`);
  };
}

// --shape: prove the healthy fixture really covers every planned key, using
// the reconciler's own table and matcher. Without this, every silence
// assertion in this file could be silence over a fixture that matches nothing.
if (process.argv[2] === '--shape') {
  const jobs = healthyJobs();
  const planned = Object.keys(basePlan(RUN_A).jobs);
  const unmatched = planned.filter((k) => {
    const expected = reconciler.EXPECTED_JOB_NAMES[k];
    return !expected || !jobs.some((j) => expected.some((e) => reconciler.matchJobName(j.name, e)));
  });
  process.stdout.write(JSON.stringify({ planned: planned.length, unmatched, skipped: jobs.filter((j) => j.conclusion === 'skipped').length }));
  process.exit(0);
}

const f = baseFixture();
const mutation = process.argv[2] || '';
if (mutation) new Function('f', 'basePlan', 'healthyJobs', mutation)(f, basePlan, healthyJobs);

const calls = [];
const io = engine.createRepoIo({
  repoRoot: '/nonexistent-by-design',
  repo: 'rediacc/console',
  branch: f.branch,
  run: makeRun(f, calls),
});
const result = engine.resolveBaseline(
  {
    head: f.head,
    mergeSha: f.mergeSha,
    // Valve 5 unless the case asks for the ENGINE's default, which is what the
    // walk-depth and cost-lock cases need to exercise.
    limit: process.env.USE_ENGINE_DEFAULT_LIMIT ? undefined : 5,
    workflowClosure: new Set(),
  },
  io,
);
process.stdout.write(
  `${JSON.stringify(
    {
      reason0: result.trail[0] ? result.trail[0].reason : null,
      usable0: result.trail[0] ? result.trail[0].usable : null,
      baselineRunId: result.baseline ? result.baseline.runId : null,
      reconciled: result.baseline && result.baseline.plan ? result.baseline.plan.reconciled : null,
      mode: result.plan.mode,
      full_reasons: result.plan.full_reasons || [],
      notes: result.notes || [],
      trailLen: result.trail.length,
      calls,
      jobsCalls: calls.filter((c) => c.startsWith('gh api jobs')).length,
      downloadCalls: calls.filter((c) => c.startsWith('gh run download')).length,
      runsListCalls: calls.filter((c) => c.startsWith('gh api runs-list')).length,
      perCommitCalls: calls.filter((c) => c.startsWith('gh run list')).length,
    },
    null,
    2,
  )}\n`,
)"""


class Scenario:
    """One `drive` call: the exit code, the parsed result, and stderr kept apart."""

    def __init__(self, rc: int, result: dict | None, err: str) -> None:
        self.rc = rc
        self.result = result if result is not None else {}
        self.err = err

    def __getitem__(self, key: str):
        return self.result[key]


def harness_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """`$WORK/harness.js`, written once per test into pytest's own tmp_path."""
    path = tmp_path / "harness.js"
    if not path.is_file():
        for subject in (ENGINE, MAP, RECONCILE):
            if not subject.is_file():
                raise harness.GateAssertionError(
                    "%s is missing; this gate has nothing to drive"
                    % paths.relative_to_root(subject)
                )
        path.write_text(HARNESS_JS, encoding="utf-8")
    return path


def drive(tmp_path: pathlib.Path, mutation: str = "", *, engine_default_limit: bool = False):
    """Run one scenario. `mutation` is a JS statement over the fixture `f`.

    A NON-ZERO EXIT IS RETURNED, NOT RAISED. Six cases assert `rc == 0` explicitly,
    because "the engine answered at all" is a separate claim from "it answered this",
    and an exception escaping into `initialize` is the failure those cases exist for.
    """
    env = {"ENGINE": str(ENGINE), "MAP": str(MAP), "RECONCILE": str(RECONCILE)}
    if engine_default_limit:
        env["USE_ENGINE_DEFAULT_LIMIT"] = "1"
    node = harness.require_tool("node", "install Node 22 (the harness and engine are JS)")
    run = harness.run([node, str(harness_path(tmp_path)), mutation], env=env, timeout=180)
    parsed = None
    if run.rc == 0 and run.out.strip():
        parsed = json.loads(run.out)
    return Scenario(run.rc, parsed, run.err)


def shape(tmp_path: pathlib.Path) -> dict:
    node = harness.require_tool("node", "install Node 22 (the harness and engine are JS)")
    run = harness.run(
        [node, str(harness_path(tmp_path)), "--shape"],
        env={"ENGINE": str(ENGINE), "MAP": str(MAP), "RECONCILE": str(RECONCILE)},
        timeout=180,
    )
    if run.rc != 0:
        raise harness.GateAssertionError(
            "--shape exited %d, so the fixture's own shape could not be read.\n"
            "--- stderr ---\n%s" % (run.rc, run.err)
        )
    return json.loads(run.out)


def dumps(value: object) -> str:
    """JS `JSON.stringify` shape, for the assertions the twin makes against a
    stringified array."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def reason0(sc: Scenario) -> str:
    return "" if sc["reason0"] is None else str(sc["reason0"])


# ---------------------------------------------------------------------------


def test_control_green_full_attested_baseline(gate, tmp_path):
    """(a) THE CONTROL, first because every refusal below is meaningless without it."""
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "the happy path answers without throwing")
    gate.assert_eq(
        reason0(sc),
        "full-green-attested",
        "a green full run whose outcomes reconcile IS a usable baseline",
    )
    gate.assert_eq(dumps(sc["usable0"]), "true", "and is marked usable in the trail")
    gate.assert_eq(
        dumps(sc["reconciled"]),
        "true",
        "with reconciled DERIVED by the reader (nothing wrote it)",
    )
    gate.assert_eq(dumps(sc["baselineRunId"]), "1001", "naming the run it was proven against")
    # The end of the mechanism, not just its middle. Without this the file would prove
    # attestation works and never that anything is gained by it.
    gate.assert_eq(sc["mode"], "reduced", "and the round reduces off that baseline")
    gate.assert_eq(sc["jobsCalls"], 1, "the Jobs API was consulted exactly once")
    gate.assert_eq(sc["downloadCalls"], 1, "and the plan downloaded exactly once")
    gate.assert_eq(
        sc["perCommitCalls"], 0, "run lookups rode the one-shot listing, not per-commit queries"
    )
    gate.log_pass("(a) control: a green, full, reconcilable run attests and reduces the round")


def test_planted_invisible_cell_refuses_baseline(gate, tmp_path):
    """(b) The defect the whole mechanism exists for: the plan says Unit runs, the leaf
    self-skipped, every sibling passed, so the run is GREEN and its caller scalars all
    read success."""
    sc = drive(
        tmp_path,
        'f.jobs["1001"].jobs.find((j) => j.name === "Tests + Infra / Unit").conclusion = "skipped"',
    )
    gate.assert_eq(sc.rc, 0, "a run with a planted invisible cell still answers")
    gate.assert_contains(
        reason0(sc),
        "unreconciled-outcome:reconcile:planned-run-but-skipped",
        "and is refused as a baseline, naming the reconciler's finding",
    )
    gate.assert_contains(reason0(sc), "'unit'", "with the offending plan key")
    gate.assert_eq(sc["mode"], "full", "so the round goes full")
    gate.assert_contains(
        dumps(sc["full_reasons"]), "baseline:merge-base-reached", "with the bound stated"
    )
    # CONTROL: flip the same leaf back and the same fixture is usable again.
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(
        reason0(sc),
        "full-green-attested",
        "the identical pipeline with the leaf green attests fine",
    )
    gate.log_pass("(b) a planted invisible cell refuses the baseline; the unplanted one is usable")


def test_self_declared_reconciled_is_recomputed_not_trusted(gate, tmp_path):
    """(c) The anti-self-vouching property, as a behaviour rather than a comment."""
    sc = drive(
        tmp_path,
        'f.plans["1001"].reconciled = true;'
        'f.jobs["1001"].jobs.find((j) => j.name === "Tests + Infra / E2E Ceph").conclusion = "skipped"',
    )
    gate.assert_eq(sc.rc, 0, "a self-declared plan with a planted skip still answers")
    gate.assert_contains(
        reason0(sc),
        "unreconciled-outcome:reconcile:planned-run-but-skipped",
        "and is REFUSED: the writer does not get to vouch for itself",
    )
    gate.assert_contains(reason0(sc), "'e2e_ceph'", "the real outcome is what decides")
    # CONTROL, the half that proves the field is RECOMPUTED rather than blacklisted.
    sc = drive(tmp_path, 'f.plans["1001"].reconciled = true')
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(
        reason0(sc),
        "full-green-attested",
        "a self-declared plan whose outcomes DO reconcile is usable",
    )
    gate.assert_eq(dumps(sc["reconciled"]), "true", "on the reader's own evidence")
    gate.log_pass("(c) a self-declared reconciled flag is deleted and recomputed, never trusted")


def test_run_id_mismatch_refuses(gate, tmp_path):
    """(d) Anti-tamper at read time: a plan that does not name the run it was downloaded
    from is a stale or substituted artifact."""
    sc = drive(tmp_path, 'f.plans["1001"].run_id = "424242"')
    gate.assert_eq(sc.rc, 0, "a mismatched plan still answers")
    gate.assert_eq(
        reason0(sc), "unreconciled-outcome:run-id-mismatch", "refused with its own distinct token"
    )
    gate.assert_eq(sc["jobsCalls"], 0, "and refused CHEAPLY: no Jobs API round trip is spent on it")
    # CONTROL: the matching id (numeric on the API side, string in the plan) attests,
    # so the check is about identity, not about types.
    sc = drive(tmp_path, 'f.plans["1001"].run_id = 1001')
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(
        reason0(sc), "full-green-attested", "a numeric run_id matching the same id attests"
    )
    gate.log_pass("(d) a plan naming another run is refused, before any Jobs API call")


def test_head_sha_mismatch_refuses(gate, tmp_path):
    """(e) A plan describes ONE commit's delta. If it names a different head than the
    candidate under consideration, it is not that candidate's proof."""
    sc = drive(tmp_path, 'f.plans["1001"].head_sha = "SOMEOTHERCOMMIT"')
    gate.assert_eq(sc.rc, 0, "a plan naming another head still answers")
    gate.assert_eq(
        reason0(sc), "unreconciled-outcome:head-sha-mismatch", "refused with its own distinct token"
    )
    gate.assert_eq(sc["jobsCalls"], 0, "also cheaply")
    # CONTROL: the candidate's own sha attests. Absent head_sha is the base fixture and
    # is covered by every other control: the field is optional because nothing writes it
    # yet, so its ABSENCE must not refuse.
    sc = drive(tmp_path, 'f.plans["1001"].head_sha = "CAND1"')
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(reason0(sc), "full-green-attested", "a plan naming the candidate commit attests")
    gate.log_pass("(e) a plan naming another head is refused; the matching one attests")


def test_jobs_api_failure_is_an_answer_not_an_exception(gate, tmp_path):
    """(f) The Jobs API is the one NEW dependency this design takes on. An exception
    here would escape into `initialize`, which every other job depends on."""
    sc = drive(tmp_path, 'f.jobs["1001"] = "THROW"')
    gate.assert_eq(sc.rc, 0, "a throwing Jobs API must not crash the engine")
    gate.assert_contains(
        reason0(sc), "unreconciled-outcome:jobs-unreadable", "it is refused as jobs-unreadable"
    )
    gate.assert_eq(sc["mode"], "full", "and the round goes full")
    gate.assert_eq(sc.err, "", "with nothing spilled on stderr")
    # An EMPTY payload is unusable evidence too, not a clean bill of health:
    # reconcile() would report ok against zero observed jobs.
    sc = drive(tmp_path, 'f.jobs["1001"] = { jobs: [] }')
    gate.assert_eq(sc.rc, 0, "an empty payload answers")
    gate.assert_eq(
        reason0(sc),
        "unreconciled-outcome:jobs-unreadable",
        "an empty jobs list is unreadable evidence, never 'nothing was skipped'",
    )
    # CONTROL: the readable payload attests.
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(reason0(sc), "full-green-attested", "a readable payload attests")
    gate.log_pass("(f) an unreadable or empty Jobs API answers full, never throws")


def test_missing_artifact_reads_as_no_plan(gate, tmp_path):
    """(g) Absent, expired and never-attested are the same thing: none can prove what
    that run executed."""
    sc = drive(tmp_path, 'delete f.plans["1001"]')
    gate.assert_eq(sc.rc, 0, "a run with no artifact answers")
    gate.assert_eq(reason0(sc), "no-skip-plan", "as no-skip-plan")
    gate.assert_eq(sc["jobsCalls"], 0, "and costs no Jobs API call")
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(reason0(sc), "full-green-attested", "with the artifact present it attests")
    gate.log_pass("(g) a missing plan artifact reads as no-skip-plan")


def test_corrupt_plan_bytes_read_as_no_plan(gate, tmp_path):
    """(h) A truncated or half-written artifact must read as absent, not crash the parse
    and not be half-believed."""
    sc = drive(tmp_path, 'f.plans["1001"] = "{not json at all"')
    gate.assert_eq(sc.rc, 0, "corrupt plan bytes must not crash the engine")
    gate.assert_eq(reason0(sc), "no-skip-plan", "they read as no plan")
    gate.assert_eq(sc.err, "", "with nothing on stderr")
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(reason0(sc), "full-green-attested", "valid bytes attest")
    gate.log_pass("(h) corrupt plan bytes read as no-skip-plan without crashing")


def test_reduced_baseline_refused_before_any_jobs_call(gate, tmp_path):
    """(i) Case 1: evidence does not chain across reduced rounds, so asking the Jobs API
    about a reduced plan would be a round trip spent on a foregone conclusion. This
    asserts the ORDERING, which bounds the cost of every attestation.

    THE MUTATION SETS A SKIPPED KEY, not just the mode label, and since 2026-08-05 that
    is the load-bearing half: coverage is read per key, so a plan whose every key still
    ran is full coverage whatever its label says."""
    scope_reduced = (
        'f.plans["1001"].mode = "reduced";'
        'f.plans["1001"].jobs.unit = { run: false, reason: "out-of-scope" }'
    )
    sc = drive(tmp_path, scope_reduced)
    gate.assert_eq(sc.rc, 0, "a scope-reduced plan answers")
    gate.assert_eq(reason0(sc), "reduced-baseline", "and is refused as reduced-baseline")
    gate.assert_eq(sc["jobsCalls"], 0, "with ZERO Jobs API calls: the cheap checks come first")
    gate.assert_eq(sc["downloadCalls"], 1, "though the plan itself was read")

    # THE PAIR THAT SEPARATES THE TWO KINDS OF SKIP. Identical mode, identical shape,
    # and the only difference is WHY the key did not run.
    greenlit = (
        'f.plans["1001"].mode = "reduced";'
        'f.plans["1001"].jobs.renet = { run: false, reason: "greenlight:30968082228" }'
    )
    sc = drive(tmp_path, greenlit)
    gate.assert_eq(sc.rc, 0, "a greenlight-only reduced plan answers")
    gate.assert_eq(
        reason0(sc),
        "full-green-attested",
        "and IS a usable baseline: every key either ran or holds greenlight evidence",
    )
    gate.assert_eq(sc["mode"], "reduced", "so the round reduces off it")
    # CONTROL: the same fixture in full mode DOES make the call.
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(sc["jobsCalls"], 1, "a full plan does consult the Jobs API")
    gate.log_pass("(i) a reduced plan is refused before any Jobs API call is paid for")


def test_red_run_costs_nothing(gate, tmp_path):
    """(j) A failed run cannot be a baseline whatever its plan says."""
    sc = drive(tmp_path, 'f.runs.CAND1[0].conclusion = "failure"')
    gate.assert_eq(sc.rc, 0, "a red candidate answers")
    gate.assert_eq(reason0(sc), "not-green", "as not-green")
    gate.assert_eq(sc["downloadCalls"], 0, "with no artifact download")
    gate.assert_eq(sc["jobsCalls"], 0, "and no Jobs API call")
    gate.assert_eq(sc["perCommitCalls"], 0, "and no per-commit run lookup either")
    gate.assert_contains(
        dumps(sc["calls"]),
        "gh api runs-list p1",
        "though the branch listing itself did happen (the log is not simply empty)",
    )
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(sc["downloadCalls"], 1, "a green candidate does download")
    gate.log_pass("(j) a red candidate is rejected without downloading or querying anything")


def test_second_green_run_on_the_same_sha_is_found(gate, tmp_path):
    """(k) ONE commit can carry SEVERAL completed green runs of the same workflow, and
    only one of them uploads a ci-skip-plan."""
    two_runs = (
        "f.runs.CAND1 = ["
        '{ databaseId: 1001, status: "completed", conclusion: "success" },'
        '{ databaseId: 1002, status: "completed", conclusion: "success" },'
        "];"
    )
    sc = drive(
        tmp_path,
        two_runs + 'delete f.plans["1001"];'
        'f.plans["1002"] = basePlan("1002");'
        'f.jobs["1002"] = { jobs: healthyJobs() }',
    )
    gate.assert_eq(sc.rc, 0, "two green runs on one sha answer")
    gate.assert_eq(
        reason0(sc), "full-green-attested", "the walk keeps going past the run with no plan"
    )
    gate.assert_eq(dumps(sc["baselineRunId"]), "1002", "and attests against the run that HAS one")
    gate.assert_contains(dumps(sc["calls"]), "gh run download 1001", "having tried the first")
    # CONTROL: when NEITHER green run has a plan, the answer is still an honest
    # no-skip-plan rather than an attestation conjured from nothing.
    sc = drive(tmp_path, two_runs + 'delete f.plans["1001"]')
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(reason0(sc), "no-skip-plan", "two planless green runs read as no-skip-plan")
    gate.log_pass("(k) a second green run on the same sha is still searched for a plan")


def test_multi_page_jobs_payload_is_merged(gate, tmp_path):
    """`gh api --paginate` on the Jobs API (an OBJECT-shaped endpoint) concatenates one
    JSON object PER PAGE. A plain JSON.parse succeeds today and starts throwing the
    moment a run exceeds per_page jobs, which reads as jobs-unreadable and would
    silently pin CI to full forever: D9's exact failure shape."""
    sc = drive(
        tmp_path,
        "const all = healthyJobs();"
        "const half = Math.ceil(all.length / 2);"
        'f.jobsRaw["1001"] = JSON.stringify({ total_count: all.length, jobs: all.slice(0, half) })'
        ' + "\\n" + JSON.stringify({ total_count: all.length, jobs: all.slice(half) });',
    )
    gate.assert_eq(sc.rc, 0, "a two-page jobs payload answers")
    gate.assert_eq(
        reason0(sc),
        "full-green-attested",
        "and reconciles: the pages are merged, not truncated to the first",
    )
    # CONTROL: truncating to ONE page must NOT attest, or the merge above would be
    # indistinguishable from reading page one and ignoring the rest.
    sc = drive(
        tmp_path,
        "const all = healthyJobs();"
        "const half = Math.ceil(all.length / 2);"
        'f.jobsRaw["1001"] = JSON.stringify({ total_count: all.length, jobs: all.slice(0, half) });',
    )
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_contains(
        reason0(sc),
        "unreconciled-outcome:reconcile:planned-job-missing",
        "one page alone is missing planned jobs and must refuse",
    )
    gate.log_pass("a concatenated multi-page Jobs API payload is merged, not silently truncated")


def test_fixture_shape_is_asserted_not_assumed(gate, tmp_path):
    """(l) Every silence assertion above rests on the healthy fixture really covering
    every planned key. Assert that with the RECONCILER's own table and matcher, not by
    eye: a fixture that matched nothing would make 'full-green-attested' unreachable and
    'planned-job-missing' universal, and half this file would still look like it passed."""
    result = shape(tmp_path)
    gate.assert_eq(
        dumps(result["unmatched"]),
        "[]",
        "the healthy jobs fixture carries a leaf for EVERY planned key",
    )
    # A fixture over zero planned keys would trivially have no unmatched keys.
    gate.assert_eq(
        "yes" if result["planned"] >= 15 else "no",
        "yes",
        "over a non-trivial plan (>= 15 keys; the table has %d)" % result["planned"],
    )
    gate.assert_eq(
        result["skipped"], 11, "and carries the eleven structural skips a healthy run really has"
    )
    gate.log_pass("(l) the fixture's shape is asserted: the silences above are over real coverage")


DEEP_CHAIN = (
    'f.candidates = ["C1","C2","C3","C4","C5","C6","C7"];'
    '["C1","C2","C3","C4","C5","C6"].forEach(function (c) {'
    ' f.runs[c] = [{ databaseId: 900, status: "completed", conclusion: "failure" }];'
    "});"
    "delete f.runs.CAND1;"
    'f.runs.C7 = [{ databaseId: 1001, status: "completed", conclusion: "success" }];'
)


def test_walk_depth_honours_the_explicit_valve(gate, tmp_path):
    """(m) `--limit` survives as the explicit valve override, and the mock honours
    `--max-count`, so a deliberately small valve still truncates."""
    sc = drive(tmp_path, DEEP_CHAIN)
    gate.assert_eq(sc.rc, 0, "a seven-deep chain answers under valve 5")
    gate.assert_eq(
        dumps(sc["baselineRunId"]),
        "null",
        "CONTROL: at valve 5 the green ancestor at depth 7 is unreachable",
    )
    gate.assert_contains(
        dumps(sc["full_reasons"]),
        "baseline:walk-valve",
        "and the reason names the valve, so the truncation is diagnosable",
    )
    # The engine's own default valve is what the thing under test rides on.
    sc = drive(tmp_path, DEEP_CHAIN, engine_default_limit=True)
    gate.assert_eq(sc.rc, 0, "the same chain answers at the engine default")
    gate.assert_eq(
        dumps(sc["baselineRunId"]),
        "1001",
        "and the default walk REACHES the green ancestor at depth 7",
    )
    gate.log_pass("(m) the explicit valve truncates with a pinned reason; the default does not")


def test_deep_green_regression_no_fixed_count(gate, tmp_path):
    """(n) THE REGRESSION FOR THE TWO INCIDENTS, fire-proofed against the PRE-CHANGE
    engine before it landed: with 29 red ancestors and the only attested green at depth
    30, the old DEFAULT_CANDIDATE_LIMIT of 20 answered candidates_seen 20, baseline
    null, mode full, reason baseline:none-usable (measured 2026-07-30)."""
    deep = (
        "f.candidates = [];"
        "delete f.runs.CAND1;"
        "for (let i = 1; i <= 29; i++) {"
        ' const sha = "RED" + i;'
        " f.candidates.push(sha);"
        ' f.runs[sha] = [{ databaseId: 8000 + i, status: "completed", conclusion: "failure" }];'
        "}"
        'f.candidates.push("GREEN30");'
        'f.runs.GREEN30 = [{ databaseId: 1001, status: "completed", conclusion: "success" }];'
    )
    sc = drive(tmp_path, deep, engine_default_limit=True)
    gate.assert_eq(sc.rc, 0, "a thirty-deep chain answers")
    gate.assert_eq(
        dumps(sc["baselineRunId"]),
        "1001",
        "the green at depth 30 IS reached: no fixed count manufactured a no-baseline verdict",
    )
    gate.assert_eq(sc["mode"], "reduced", "and the round reduces off it")
    gate.assert_eq(sc["trailLen"], 30, "having walked every PR-owned commit before it")
    gate.assert_eq(sc["perCommitCalls"], 0, "at zero per-candidate API cost")
    gate.log_pass(
        "(n) the green past every historical fixed limit is reached (regression for both incidents)"
    )


def test_fence_stops_the_walk_at_the_merge_boundary(gate, tmp_path):
    """(o) Candidates past the merge boundary are main-history commits whose runs never
    carry a ci-skip-plan, so the walk must not consider them."""
    fenced = (
        'f.candidates = ["C1", "BASE1", "PASTGREEN"];'
        "delete f.runs.CAND1;"
        'f.runs.C1 = [{ databaseId: 900, status: "completed", conclusion: "failure" }];'
        'f.runs.PASTGREEN = [{ databaseId: 1001, status: "completed", conclusion: "success" }];'
    )
    sc = drive(tmp_path, fenced)
    gate.assert_eq(sc.rc, 0, "a fenced chain answers")
    gate.assert_eq(
        dumps(sc["baselineRunId"]),
        "null",
        "the green PAST the merge boundary is never considered",
    )
    gate.assert_eq(sc["trailLen"], 1, "the walk saw only the PR-owned commit")
    gate.assert_eq(sc["downloadCalls"], 0, "and paid nothing for the out-of-domain green")
    gate.assert_contains(
        dumps(sc["full_reasons"]),
        "baseline:merge-base-reached",
        "with the fence named as what ended the walk",
    )
    # CONTROL, the other direction: the same green INSIDE the fence resolves, so the
    # exclusion above is the fence working and not a dead walk.
    inside = (
        'f.candidates = ["C1", "NEARGREEN", "BASE1"];'
        "delete f.runs.CAND1;"
        'f.runs.C1 = [{ databaseId: 900, status: "completed", conclusion: "failure" }];'
        'f.runs.NEARGREEN = [{ databaseId: 1001, status: "completed", conclusion: "success" }];'
    )
    sc = drive(tmp_path, inside)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(dumps(sc["baselineRunId"]), "1001", "a green inside the boundary still resolves")
    gate.log_pass("(o) the walk is fenced at the merge boundary, in both directions")


def test_green_attestation_budget_binds_both_ways(gate, tmp_path):
    """(p) Attestation is the expensive class (a download plus a jobs read per green),
    and its failures are systematic: retention, format drift, reconciler drift."""
    exhausted = (
        'f.candidates = ["G1", "G2", "G3", "G4"];'
        "delete f.runs.CAND1;"
        '[["G1", 9001], ["G2", 9002], ["G3", 9003]].forEach(function (g) {'
        ' f.runs[g[0]] = [{ databaseId: g[1], status: "completed", conclusion: "success" }];'
        "});"
        'f.runs.G4 = [{ databaseId: 1004, status: "completed", conclusion: "success" }];'
        'f.plans["1004"] = basePlan("1004");'
        'f.jobs["1004"] = { jobs: healthyJobs() };'
    )
    sc = drive(tmp_path, exhausted)
    gate.assert_eq(sc.rc, 0, "a chain of planless greens answers")
    gate.assert_contains(
        dumps(sc["full_reasons"]),
        "baseline:attest-budget-exhausted",
        "three failed attestations exhaust the budget, with the pinned reason",
    )
    gate.assert_eq(sc["downloadCalls"], 3, "exactly three downloads were paid for")
    gate.assert_eq(dumps(sc["baselineRunId"]), "null", "and the fourth green was never tried")
    # CONTROL, the other direction: two failures then an attestable third must RESOLVE,
    # so the budget is not merely a smaller fixed count in disguise.
    within = (
        'f.candidates = ["G1", "G2", "G3"];'
        "delete f.runs.CAND1;"
        '[["G1", 9001], ["G2", 9002]].forEach(function (g) {'
        ' f.runs[g[0]] = [{ databaseId: g[1], status: "completed", conclusion: "success" }];'
        "});"
        'f.runs.G3 = [{ databaseId: 1003, status: "completed", conclusion: "success" }];'
        'f.plans["1003"] = basePlan("1003");'
        'f.jobs["1003"] = { jobs: healthyJobs() };'
    )
    sc = drive(tmp_path, within)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(dumps(sc["baselineRunId"]), "1003", "the third green attests within the budget")
    gate.log_pass(
        "(p) the attestation budget stops the fourth failure and admits the third success"
    )


def test_cost_lock_pages_not_candidates(gate, tmp_path):
    """(r) THE COST LOCK, the control that keeps candidate C true over time. A
    112-commit all-red streak must cost run-listing calls that scale with PAGES of the
    branch listing (112 runs = 2 pages of 100), NEVER one call per candidate."""
    streak = (
        "f.candidates = [];"
        "delete f.runs.CAND1;"
        "for (let i = 1; i <= 112; i++) {"
        ' const sha = "R" + i;'
        " f.candidates.push(sha);"
        ' f.runs[sha] = [{ databaseId: 7000 + i, status: "completed", conclusion: "failure" }];'
        "}"
    )
    sc = drive(tmp_path, streak, engine_default_limit=True)
    gate.assert_eq(sc.rc, 0, "a 112-commit all-red streak answers")
    gate.assert_eq(sc["trailLen"], 112, "every PR-owned commit was walked")
    gate.assert_eq(sc["runsListCalls"], 2, "at exactly two listing pages (112 runs / 100 per page)")
    gate.assert_eq(sc["perCommitCalls"], 0, "and ZERO per-commit run lookups")
    gate.assert_eq(sc["downloadCalls"], 0, "and zero artifact downloads")
    gate.assert_contains(
        dumps(sc["full_reasons"]), "baseline:merge-base-reached", "ending honestly at the fence"
    )
    gate.log_pass("(r) cost lock: run listing scales with pages, never with candidates")


def test_per_commit_fallback_still_works_without_a_branch(gate, tmp_path):
    """(s) The pair to (r): it proves the fallback exists, so the zeros in (r) are the
    cheap path being chosen rather than run lookups not happening at all."""
    sc = drive(tmp_path, "f.branch = null")
    gate.assert_eq(sc.rc, 0, "the branchless fixture answers")
    gate.assert_eq(dumps(sc["baselineRunId"]), "1001", "and still resolves the baseline")
    gate.assert_eq(sc["perCommitCalls"], 1, "via exactly one per-commit lookup")
    gate.assert_eq(sc["runsListCalls"], 0, "with no branch listing attempted")
    gate.assert_contains(
        dumps(sc["notes"]),
        "runs-listing:per-commit-fallback:no-branch",
        "and the cost mode is SAID in the notes, not left to API-call archaeology",
    )
    gate.log_pass("(s) the per-commit fallback resolves correctly when no branch is known")


def test_degraded_listing_is_noted_not_silent(gate, tmp_path):
    """(u) THE CAVEAT CLOSED. A mid-resolve listing failure degrades to per-commit
    lookups (correctness over cost), and that degradation used to be invisible outside
    API-call patterns nobody watches."""
    sc = drive(tmp_path, "f.runsListThrow = true")
    gate.assert_eq(sc.rc, 0, "a throwing branch listing answers")
    gate.assert_eq(
        dumps(sc["baselineRunId"]),
        "1001",
        "correctness is preserved: the baseline still resolves via per-commit",
    )
    gate.assert_eq(sc["perCommitCalls"], 1, "on the fallback cost model")
    gate.assert_contains(
        dumps(sc["notes"]),
        "runs-listing-degraded:per-commit",
        "and the degradation is SAID, with the pinned note",
    )
    gate.assert_contains(dumps(sc["notes"]), "listing unavailable", "carrying the underlying error")
    # CONTROL, the other direction: a notes field that is always populated is not a signal.
    sc = drive(tmp_path)
    gate.assert_eq(sc.rc, 0, "control runs")
    gate.assert_eq(dumps(sc["notes"]), "[]", "the healthy path's notes are empty")
    gate.log_pass("(u) a degraded listing is noted; the clean path stays silent (both directions)")


def test_notes_reach_the_shadow_artifact(gate):
    """(v) A channel with no listener is the same defect class as a fire-proof behind an
    unused flag, so pin the emit chain. These are structural greps, deliberately cheap:
    if either link is renamed away, this fails and the notes silently stop reaching the
    one place someone looks."""
    engine_source = ENGINE.read_text(encoding="utf-8")
    gate.assert_eq(
        len([ln for ln in engine_source.splitlines() if "baseline_notes: result.notes" in ln]),
        1,
        "the CLI emits result.notes as baseline_notes",
    )
    # The twin's `grep -A2 -- '--resolve-baseline \'`: the matching line plus two after.
    shadow_lines = SHADOW.read_text(encoding="utf-8").splitlines()
    window = []
    for index, line in enumerate(shadow_lines):
        if "--resolve-baseline \\" in line:
            window.extend(shadow_lines[index : index + 3])
    gate.assert_contains(
        "\n".join(window),
        "scope-baseline.json",
        "and scope-shadow.sh writes the engine stdout into the shadow artifact",
    )
    gate.log_pass("(v) the notes channel has a live listener: CLI output into the shadow artifact")


def test_unreadable_merge_parent_degrades_to_valve_only_walk(gate, tmp_path):
    """(t) THE DEGRADATION DIRECTION. A bad mergeSha turning every round full while the
    walk itself was fine is the cry-wolf shape this whole redesign exists to end."""
    sc = drive(tmp_path, "f.firstParentThrow = true")
    gate.assert_eq(sc.rc, 0, "a throwing merge-parent probe answers")
    gate.assert_eq(
        dumps(sc["baselineRunId"]),
        "1001",
        "the walk still found the baseline (valve-only, not dead)",
    )
    gate.assert_eq(sc["mode"], "full", "the round is full")
    gate.assert_contains(
        dumps(sc["full_reasons"]),
        "baseline:base-sha-unknown",
        "because the base cannot be proven unchanged, not because the walk failed",
    )
    gate.assert_contains(
        dumps(sc["notes"]),
        "merge-parent-unreadable",
        "and the notes say why the fence was unavailable",
    )
    gate.log_pass("(t) an unreadable merge parent degrades to a valve-only walk with a note")
