#!/bin/bash
# Unit test for VERIFY-AT-READ baseline attestation in the CI scope engine:
# .ci/scripts/ci/scope-engine.cjs (attestPlan + createRepoIo).
#
# WHAT THIS GUARDS. A baseline is the claim "this ancestor already ran the
# whole suite green, so the delta since is all that needs running". Everything
# a reduced round skips rests on that claim. The plan artifact alone cannot
# support it: a plan states INTENT, and a run whose watchdog rerun skipped
# half the fleet leaves behind a plan that looks identical to an honest one.
#
# So nobody writes a `reconciled` marker and nobody is trusted to. The READER
# downloads the plan, fetches THAT run's per-job outcomes from the Jobs API,
# runs the existing pure reconcile() itself, and only then may set the flag.
# The self-declared field in the downloaded bytes is DELETED before anything
# reads it, which is why case (c) below plants `"reconciled": true` in the
# artifact and still expects a refusal.
#
# POLARITY: fail-open. Every refusal here costs one full CI round, never a red
# check. That is the opposite of the reconciler's polarity and is the reason
# the reconciler's verdict is safe to consume from this side.
#
# Every planted defect is PAIRED with the control that proves the mechanism
# can still say yes, because a gate stuck at "refuse" would pass every failure
# case in this file while being exactly as broken as one stuck at "accept".
# The control in case (a) is the strongest available: the whole pipeline, from
# `gh run list` to a REDUCED plan, over faked I/O only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

export ENGINE="$REPO_ROOT/.ci/scripts/ci/scope-engine.cjs"
export MAP="$REPO_ROOT/.ci/scripts/ci/scope-map.cjs"
export RECONCILE="$REPO_ROOT/.ci/scripts/ci/skip-plan-reconcile.cjs"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# The harness. It drives the REAL createRepoIo with an injected `run`, so every
# git and gh call is a fake that dispatches on argv, serves fixtures, and
# RECORDS the call in order. The recording is not decoration: cases (i) and (j)
# assert on the ABSENCE of a Jobs API call, and an absence is only evidence
# when the log that would have contained it is proven to work (case (a) shows
# the same log carrying one).
#
# Fixtures are built in-test from scope-map's JOB_SURFACES (plan side) and a
# literal job list taken from run 30307775327 (outcome side), the same pairing
# test-skip-plan-reconcile.sh uses. Case (l) asserts the two actually line up.
# ---------------------------------------------------------------------------
cat >"$WORK/harness.js" <<'HARNESS'
'use strict';
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
        // HONOUR --max-count. This mock used to return every candidate whatever
        // the caller asked for, so the walk depth was invisible to the entire
        // suite and a too-small DEFAULT_CANDIDATE_LIMIT could never be caught.
        // Real rev-list truncates; a fixture that does not is not a model of it.
        const cap = a.map((x) => /^--max-count=(\d+)$/.exec(String(x)))
          .filter(Boolean)
          .map((m) => Number(m[1]))[0];
        const all = [f.head, ...f.candidates];
        return `${(cap ? all.slice(0, cap) : all).join('\n')}\n`;
      }
      if (a[0] === 'rev-parse') {
        calls.push('git first-parent');
        return `${f.firstParent}\n`;
      }
      if (a[0] === 'diff-tree') {
        calls.push('git diff-tree');
        return f.diff;
      }
      throw new Error(`unexpected git call: ${a.join(' ')}`);
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
  run: makeRun(f, calls),
});
const result = engine.resolveBaseline(
  {
    head: f.head,
    mergeSha: f.mergeSha,
    // Default 5 unless the case asks for the ENGINE's default, which is what the
    // walk-depth control needs to exercise.
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
      calls,
      jobsCalls: calls.filter((c) => c.startsWith('gh api jobs')).length,
      downloadCalls: calls.filter((c) => c.startsWith('gh run download')).length,
    },
    null,
    2,
  )}\n`,
)
HARNESS

# drive [<js mutation over `f`>] -- run one scenario; prints the exit code.
# stdout and stderr are captured SEPARATELY: an engine that throws instead of
# answering must be visible as an exit code, not hidden in a merged stream.
drive() {
    local rc=0
    node "$WORK/harness.js" "${1:-}" >"$WORK/res.json" 2>"$WORK/err.txt" || rc=$?
    echo "$rc"
}

# rget <js-expr over `r`> -- read a field out of the captured result
rget() {
    node -e '
const r = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
const get = new Function("r", "return (" + process.argv[2] + ");");
const v = get(r);
process.stdout.write(typeof v === "string" ? v : JSON.stringify(v));
' "$WORK/res.json" "$1"
}

err() { cat "$WORK/err.txt"; }

# ---------------------------------------------------------------------------

test_control_green_full_attested_baseline() {
    # (a) THE CONTROL, and it comes first because every refusal below is
    # meaningless without it. A green run, a full plan naming that run, and
    # job outcomes that reconcile: the plan must come back with reconciled
    # true, the candidate must be usable, and the round must actually REDUCE.
    assert_eq "$(drive)" "0" "the happy path answers without throwing"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" \
        "a green full run whose outcomes reconcile IS a usable baseline"
    assert_eq "$(rget 'r.usable0')" "true" "and is marked usable in the trail"
    assert_eq "$(rget 'r.reconciled')" "true" \
        "with reconciled DERIVED by the reader (nothing wrote it)"
    assert_eq "$(rget 'r.baselineRunId')" "1001" "naming the run it was proven against"
    # The end of the mechanism, not just its middle: a docs-only delta against
    # that baseline produces a REDUCED plan. Without this the file would prove
    # attestation works and never that anything is gained by it.
    assert_eq "$(rget 'r.mode')" "reduced" "and the round reduces off that baseline"
    assert_eq "$(rget 'r.jobsCalls')" "1" "the Jobs API was consulted exactly once"
    assert_eq "$(rget 'r.downloadCalls')" "1" "and the plan downloaded exactly once"
    log_pass "(a) control: a green, full, reconcilable run attests and reduces the round"
}

test_planted_invisible_cell_refuses_baseline() {
    # (b) The defect the whole mechanism exists for: the plan says Unit runs,
    # the leaf self-skipped, every sibling passed, so the run is GREEN and its
    # caller scalars all read success. Trusting the plan here would skip work
    # on the strength of a suite that never ran.
    assert_eq "$(drive 'f.jobs["1001"].jobs.find((j) => j.name === "Tests + Infra / Unit").conclusion = "skipped"')" "0" \
        "a run with a planted invisible cell still answers"
    assert_contains "$(rget 'r.reason0')" "unreconciled-outcome:reconcile:planned-run-but-skipped" \
        "and is refused as a baseline, naming the reconciler's finding"
    assert_contains "$(rget 'r.reason0')" "'unit'" "with the offending plan key"
    assert_eq "$(rget 'r.mode')" "full" "so the round goes full"
    assert_contains "$(rget 'r.full_reasons')" "baseline:none-usable" "with the reason stated"
    # CONTROL: flip the same leaf back and the same fixture is usable again.
    assert_eq "$(drive)" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" \
        "the identical pipeline with the leaf green attests fine"
    log_pass "(b) a planted invisible cell refuses the baseline; the unplanted one is usable"
}

test_self_declared_reconciled_is_recomputed_not_trusted() {
    # (c) The anti-self-vouching property, stated as a behaviour rather than as
    # a comment. A downloaded artifact claiming `"reconciled": true` about
    # ITSELF must carry no weight: the field is deleted on arrival and only the
    # reader's own recomputation may restore it.
    assert_eq "$(drive 'f.plans["1001"].reconciled = true;
        f.jobs["1001"].jobs.find((j) => j.name === "Tests + Infra / E2E Ceph").conclusion = "skipped"')" "0" \
        "a self-declared plan with a planted skip still answers"
    assert_contains "$(rget 'r.reason0')" "unreconciled-outcome:reconcile:planned-run-but-skipped" \
        "and is REFUSED: the writer does not get to vouch for itself"
    assert_contains "$(rget 'r.reason0')" "'e2e_ceph'" "the real outcome is what decides"
    # CONTROL, and it is the half that proves the field is RECOMPUTED rather
    # than blacklisted: the same self-declared plan with honest outcomes is
    # usable. A reader that simply distrusted plans carrying the field would
    # fail this line.
    assert_eq "$(drive 'f.plans["1001"].reconciled = true')" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" \
        "a self-declared plan whose outcomes DO reconcile is usable"
    assert_eq "$(rget 'r.reconciled')" "true" "on the reader's own evidence"
    log_pass "(c) a self-declared reconciled flag is deleted and recomputed, never trusted"
}

test_run_id_mismatch_refuses() {
    # (d) Anti-tamper at read time: a plan that does not name the run it was
    # downloaded from is a stale or substituted artifact.
    assert_eq "$(drive 'f.plans["1001"].run_id = "424242"')" "0" "a mismatched plan still answers"
    assert_eq "$(rget 'r.reason0')" "unreconciled-outcome:run-id-mismatch" \
        "refused with its own distinct token"
    assert_eq "$(rget 'r.jobsCalls')" "0" \
        "and refused CHEAPLY: no Jobs API round trip is spent on it"
    # CONTROL: the matching id (numeric on the API side, string in the plan)
    # attests, so the check is about identity, not about types.
    assert_eq "$(drive 'f.plans["1001"].run_id = 1001')" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" \
        "a numeric run_id matching the same id attests"
    log_pass "(d) a plan naming another run is refused, before any Jobs API call"
}

test_head_sha_mismatch_refuses() {
    # (e) A plan describes ONE commit's delta. If it names a different head
    # than the candidate under consideration, it is not that candidate's proof.
    assert_eq "$(drive 'f.plans["1001"].head_sha = "SOMEOTHERCOMMIT"')" "0" \
        "a plan naming another head still answers"
    assert_eq "$(rget 'r.reason0')" "unreconciled-outcome:head-sha-mismatch" \
        "refused with its own distinct token"
    assert_eq "$(rget 'r.jobsCalls')" "0" "also cheaply"
    # CONTROL: the candidate's own sha attests. (Absent head_sha is the base
    # fixture and is covered by every other control: the field is optional
    # because nothing writes it yet, so its ABSENCE must not refuse.)
    assert_eq "$(drive 'f.plans["1001"].head_sha = "CAND1"')" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" \
        "a plan naming the candidate commit attests"
    log_pass "(e) a plan naming another head is refused; the matching one attests"
}

test_jobs_api_failure_is_an_answer_not_an_exception() {
    # (f) The Jobs API is the one NEW dependency this design takes on. When it
    # is unavailable the engine must degrade to full CI with a stated reason.
    # An exception here would escape into `initialize`, which every other job
    # depends on, and cost the pipeline far more than the optimisation is worth.
    assert_eq "$(drive 'f.jobs["1001"] = "THROW"')" "0" \
        "a throwing Jobs API must not crash the engine"
    assert_contains "$(rget 'r.reason0')" "unreconciled-outcome:jobs-unreadable" \
        "it is refused as jobs-unreadable"
    assert_eq "$(rget 'r.mode')" "full" "and the round goes full"
    assert_eq "$(err)" "" "with nothing spilled on stderr"
    # An EMPTY payload is unusable evidence too, not a clean bill of health:
    # reconcile() would report ok against zero observed jobs.
    assert_eq "$(drive 'f.jobs["1001"] = { jobs: [] }')" "0" "an empty payload answers"
    assert_eq "$(rget 'r.reason0')" "unreconciled-outcome:jobs-unreadable" \
        "an empty jobs list is unreadable evidence, never 'nothing was skipped'"
    # CONTROL: the readable payload attests.
    assert_eq "$(drive)" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" "a readable payload attests"
    log_pass "(f) an unreadable or empty Jobs API answers full, never throws"
}

test_missing_artifact_reads_as_no_plan() {
    # (g) Absent, expired and never-attested are the same thing: none of them
    # can prove what that run executed.
    assert_eq "$(drive 'delete f.plans["1001"]')" "0" "a run with no artifact answers"
    assert_eq "$(rget 'r.reason0')" "no-skip-plan" "as no-skip-plan"
    assert_eq "$(rget 'r.jobsCalls')" "0" "and costs no Jobs API call"
    # CONTROL: present is what makes the difference.
    assert_eq "$(drive)" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" "with the artifact present it attests"
    log_pass "(g) a missing plan artifact reads as no-skip-plan"
}

test_corrupt_plan_bytes_read_as_no_plan() {
    # (h) A truncated or half-written artifact must read as absent, not crash
    # the parse and not be half-believed.
    assert_eq "$(drive 'f.plans["1001"] = "{not json at all"')" "0" \
        "corrupt plan bytes must not crash the engine"
    assert_eq "$(rget 'r.reason0')" "no-skip-plan" "they read as no plan"
    assert_eq "$(err)" "" "with nothing on stderr"
    # CONTROL: valid bytes at the same path attest.
    assert_eq "$(drive)" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" "valid bytes attest"
    log_pass "(h) corrupt plan bytes read as no-skip-plan without crashing"
}

test_reduced_baseline_refused_before_any_jobs_call() {
    # (i) Case 1: evidence does not chain across reduced rounds. A reduced plan
    # can never be a baseline however perfectly it reconciles, so asking the
    # Jobs API about it would be a round trip spent on a foregone conclusion.
    # This asserts the ORDERING, which is the only thing that makes the walk's
    # cost bounded: one such call per candidate, times `limit` candidates.
    assert_eq "$(drive 'f.plans["1001"].mode = "reduced"')" "0" "a reduced plan answers"
    assert_eq "$(rget 'r.reason0')" "reduced-baseline" "and is refused as reduced-baseline"
    assert_eq "$(rget 'r.jobsCalls')" "0" \
        "with ZERO Jobs API calls: the cheap checks come first"
    assert_eq "$(rget 'r.downloadCalls')" "1" "though the plan itself was read"
    # CONTROL: the same fixture in full mode DOES make the call, so the zero
    # above is an ordering decision rather than a Jobs API that never fires.
    assert_eq "$(drive)" "0" "control runs"
    assert_eq "$(rget 'r.jobsCalls')" "1" "a full plan does consult the Jobs API"
    log_pass "(i) a reduced plan is refused before any Jobs API call is paid for"
}

test_red_run_costs_nothing() {
    # (j) A failed run cannot be a baseline whatever its plan says, so neither
    # the artifact nor the Jobs API should be touched for it.
    assert_eq "$(drive 'f.runs.CAND1[0].conclusion = "failure"')" "0" "a red candidate answers"
    assert_eq "$(rget 'r.reason0')" "not-green" "as not-green"
    assert_eq "$(rget 'r.downloadCalls')" "0" "with no artifact download"
    assert_eq "$(rget 'r.jobsCalls')" "0" "and no Jobs API call"
    assert_contains "$(rget 'r.calls')" "gh run list CAND1" \
        "though the run lookup itself did happen (the log is not simply empty)"
    # CONTROL: green pays for both calls, so the two zeros above are decisions.
    assert_eq "$(drive)" "0" "control runs"
    assert_eq "$(rget 'r.downloadCalls')" "1" "a green candidate does download"
    log_pass "(j) a red candidate is rejected without downloading or querying anything"
}

test_second_green_run_on_the_same_sha_is_found() {
    # (k) ONE commit can carry SEVERAL completed green runs of the same
    # workflow: the pull_request run and the push run are distinct runs, and
    # only one of them uploads a ci-skip-plan. Picking a single green run and
    # asking it for a plan lost the baseline whenever the wrong one sorted
    # first, and reported 'no-skip-plan' for a commit that had a perfect plan.
    assert_eq "$(drive 'f.runs.CAND1 = [
            { databaseId: 1001, status: "completed", conclusion: "success" },
            { databaseId: 1002, status: "completed", conclusion: "success" },
        ];
        delete f.plans["1001"];
        f.plans["1002"] = basePlan("1002");
        f.jobs["1002"] = { jobs: healthyJobs() }')" "0" "two green runs on one sha answer"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" \
        "the walk keeps going past the run with no plan"
    assert_eq "$(rget 'r.baselineRunId')" "1002" "and attests against the run that HAS one"
    assert_contains "$(rget 'r.calls')" "gh run download 1001" "having tried the first"
    # CONTROL: when NEITHER green run has a plan, the answer is still an honest
    # no-skip-plan rather than an attestation conjured from nothing.
    assert_eq "$(drive 'f.runs.CAND1 = [
            { databaseId: 1001, status: "completed", conclusion: "success" },
            { databaseId: 1002, status: "completed", conclusion: "success" },
        ];
        delete f.plans["1001"]')" "0" "control runs"
    assert_eq "$(rget 'r.reason0')" "no-skip-plan" "two planless green runs read as no-skip-plan"
    log_pass "(k) a second green run on the same sha is still searched for a plan"
}

test_multi_page_jobs_payload_is_merged() {
    # `gh api --paginate` on the Jobs API (an OBJECT-shaped endpoint)
    # concatenates one JSON object PER PAGE. A plain JSON.parse succeeds today
    # and starts throwing the moment a run exceeds per_page jobs, which reads
    # as jobs-unreadable and would silently pin CI to full forever: D9's exact
    # failure shape. The pages must be merged.
    assert_eq "$(drive 'const all = healthyJobs();
        const half = Math.ceil(all.length / 2);
        f.jobsRaw["1001"] = JSON.stringify({ total_count: all.length, jobs: all.slice(0, half) })
            + "\n" + JSON.stringify({ total_count: all.length, jobs: all.slice(half) });')" "0" \
        "a two-page jobs payload answers"
    assert_eq "$(rget 'r.reason0')" "full-green-attested" \
        "and reconciles: the pages are merged, not truncated to the first"
    # CONTROL: truncating to ONE page must NOT attest, or the merge above would
    # be indistinguishable from reading page one and ignoring the rest.
    assert_eq "$(drive 'const all = healthyJobs();
        const half = Math.ceil(all.length / 2);
        f.jobsRaw["1001"] = JSON.stringify({ total_count: all.length, jobs: all.slice(0, half) });')" "0" \
        "control runs"
    assert_contains "$(rget 'r.reason0')" "unreconciled-outcome:reconcile:planned-job-missing" \
        "one page alone is missing planned jobs and must refuse"
    log_pass "a concatenated multi-page Jobs API payload is merged, not silently truncated"
}

test_fixture_shape_is_asserted_not_assumed() {
    # (l) Every silence assertion above rests on the healthy fixture really
    # covering every planned key. Assert that with the RECONCILER's own table
    # and matcher, not by eye: a fixture that matched nothing would make
    # 'full-green-attested' unreachable and 'planned-job-missing' universal,
    # and half this file would still look like it passed.
    local shape
    shape="$(node "$WORK/harness.js" --shape)"
    assert_contains "$shape" '"unmatched":[]' \
        "the healthy jobs fixture carries a leaf for EVERY planned key"
    local planned
    planned="$(node -e '
const s = JSON.parse(process.argv[1]);
process.stdout.write(String(s.planned));
' "$shape")"
    # A fixture over zero planned keys would trivially have no unmatched keys.
    assert_eq "$([[ "$planned" -ge 15 ]] && echo yes || echo no)" "yes" \
        "over a non-trivial plan (>= 15 keys; the table has $planned)"
    assert_contains "$shape" '"skipped":11' \
        "and carries the eleven structural skips a healthy run really has"
    log_pass "(l) the fixture's shape is asserted: the silences above are over real coverage"
}

test_walk_depth_reaches_a_realistic_green() {
    # (m) THE WALK DEPTH IS PART OF CORRECTNESS, not just latency. Measured on
    # run 30478917957: five candidates all answered `not-green` while the real
    # green commit 2469e5d72 sat SEVEN steps back, one row past the old cap of
    # 5. A baseline that exists but cannot be reached reads exactly like a
    # baseline that does not exist, so this pins the depth with a fixture whose
    # only green ancestor is deliberately out of reach of the old value.
    local chain='f.candidates = ["C1","C2","C3","C4","C5","C6","C7"];
        ["C1","C2","C3","C4","C5","C6"].forEach(function (c) {
            f.runs[c] = [{ databaseId: 900, status: "completed", conclusion: "failure" }];
        });
        f.runs.C7 = [{ databaseId: 1001, status: "completed", conclusion: "success" }];'
    # CONTROL FIRST: with the OLD cap of 5, this fixture must NOT find it. If it
    # did, the case would prove nothing about depth.
    assert_eq "$(drive "$chain")" "0" "a seven-deep chain answers under the old cap"
    assert_eq "$(rget 'r.baselineRunId')" "null" "CONTROL: at limit 5 the green ancestor at depth 7 is unreachable"
    # Now the engine's own default, which is the thing under test.
    assert_eq "$(USE_ENGINE_DEFAULT_LIMIT=1 drive "$chain")" "0" "the same chain answers at the engine default"
    assert_eq "$(rget 'r.baselineRunId')" "1001" "and the default walk REACHES the green ancestor at depth 7"
}

log_test "test-scope-baseline-attest"
test_control_green_full_attested_baseline
test_planted_invisible_cell_refuses_baseline
test_self_declared_reconciled_is_recomputed_not_trusted
test_run_id_mismatch_refuses
test_head_sha_mismatch_refuses
test_jobs_api_failure_is_an_answer_not_an_exception
test_missing_artifact_reads_as_no_plan
test_corrupt_plan_bytes_read_as_no_plan
test_reduced_baseline_refused_before_any_jobs_call
test_red_run_costs_nothing
test_second_green_run_on_the_same_sha_is_found
test_multi_page_jobs_payload_is_merged
test_fixture_shape_is_asserted_not_assumed
test_walk_depth_reaches_a_realistic_green
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
