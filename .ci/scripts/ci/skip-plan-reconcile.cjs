#!/usr/bin/env node
// Reconcile the attested skip-plan against what actually ran, at JOB level,
// never caller level. This is the piece that makes scope-based skipping safe
// to wire at all: until this provably hard-fails on a planted mismatch, the
// engine's run_* vector must never gate a real job.
//
// WHY CALLER-LEVEL ASSERTION IS STRUCTURALLY BLIND. `ci-complete` sees only
// the 18 `needs.<job>.result` scalars. For a reusable-workflow caller that
// scalar is an aggregate: `success` when every inner job either succeeded OR
// self-skipped. Per-inner-job conclusions are not exposed to a sibling job by
// ANY expression, so the data a caller-level assertion would need does not
// exist in its interface. Only the Jobs API carries it. Observed live on run
// 30307775327: ELEVEN inner jobs skipped against zero failures, every one
// legitimate (cached-vs-uncached variants, unexpanded matrix legs, one
// push-gated job), and the caller scalars were right to read success.
//
// THE PLAN IS THE ALLOWLIST. That healthy state and the invisible-cell
// failure state are indistinguishable at caller level, so a reconciler that
// flagged every skipped inner job would fire on all eleven of those on a
// perfectly healthy run and be switched off within a day. Only jobs the plan
// explicitly marked `run` may raise `planned-run-but-skipped`; anything the
// plan does not name is simply not the reconciler's business.
//
// POLARITY, spelled out because it INVERTS the engine's. The scope ENGINE
// degrades toward more CI: any doubt, any missing input, yields a full run.
// The RECONCILER degrades toward red: a missing plan artifact, an unreadable
// jobs payload, a plan key it cannot map, all HARD FAIL. They fail in
// opposite directions on purpose. A reconciler that shrugged at a missing
// plan would let the exact failure it exists to catch (a skip nobody
// attested) read as green.
//
// Usage:
//   skip-plan-reconcile.cjs --plan <plan.json> --jobs <jobs.json> --run-id <id>
//     plan.json: the attested skip-plan artifact (run_id, mode, jobs{key:
//       {run, reason}}), as written by initialize in a later chunk.
//     jobs.json: the Jobs API payload for the current run ({jobs:[...]} as
//       `gh api repos/.../actions/runs/<id>/jobs` returns it, or a bare
//       array). Fetching it is the caller's job; this script does no network.
//
// Exit: 0 clean (warnings allowed), 1 any hard failure, 2 usage error.

'use strict';

const fs = require('fs');

const scopeMap = require('./scope-map.cjs');

// ---------------------------------------------------------------------------
// Plan key -> display names in the Jobs API. AN EXPLICIT TABLE, deliberately
// not inferred from `caller / job` name shape, because the tree lies in both
// directions (naming trap, edge case 31):
//   - ci.yml has TOP-LEVEL jobs display-named `Tests + Infra / Update Flow`
//     (a caller: its real leaves are `Tests + Infra / Update Flow / Update
//     flow (Linux x64)`) and `Tests + Infra / Linux Packages` (a plain job,
//     exactly that name, NOT inside ct-tests.yml).
//   - so a reconciler parsing names into a structure would mis-bucket both.
//
// Matching rule (edge case 32): a job matches an expected name when the name
// is EQUAL to it, or starts with it followed by ` (`. That covers matrix legs
// (`E2E Workers (ubuntu-24.04)`) and the unexpanded-template form a skipped
// matrix reports (`Procwalk (${{ matrix.os }})`, seen live on 30307775327),
// while `E2E Ceph` can never swallow `E2E Ceph Workers`: the next character
// there is ` W`, not ` (`. Never bare startsWith.
//
// A renamed job stops matching and a planned-run key then hard-fails as
// planned-job-missing: renames break loudly here, by design.
//
// migration-test is deliberately absent, mirroring scope-map's JOB_SURFACES:
// it is unconditional (edge case 26), never planned, never reconciled.
// ---------------------------------------------------------------------------
const EXPECTED_JOB_NAMES = {
  unit: ['Tests + Infra / Unit'],
  e2e_workers: ['Tests + Infra / E2E Workers'],
  e2e_ceph: ['Tests + Infra / E2E Ceph'],
  e2e_ceph_workers: ['Tests + Infra / E2E Ceph Workers'],
  e2e_k8s: ['Tests + Infra / E2E K8s'],
  e2e_k8s_ceph: ['Tests + Infra / E2E K8s Ceph'],
  e2e_k8s_multinode: ['Tests + Infra / E2E K8s Multinode'],
  e2e_migrate: ['Tests + Infra / E2E Migrate'],
  fork_isolation: ['Tests + Infra / Concurrent Fork Isolation'],
  renet: ['Tests + Infra / Renet'],
  license_enforcement: ['Tests + Infra / License Enforcement'],
  account_e2e: ['Tests + Infra / Account E2E'],
  ops: ['OPS Tests / OPS Provision', 'OPS Tests / OPS Check'],
  elite_run: ['Elite Run'],
  update_flow: ['Tests + Infra / Update Flow / Update flow'],
  package_tests: ['Tests + Infra / Linux Packages'],
  install_methods: [
    'Validate Install Methods / Linux',
    'Validate Install Methods / macOS',
    'Validate Install Methods / Windows',
  ],
};

// The name table and scope-map's surface table must cover exactly the same
// plan keys, or a job could be planned that the reconciler cannot verify (or
// verified that can never be planned). Drift in either direction throws at
// load, so an edit to one table without the other is caught before anything
// consumes them.
function validateNameTable(names, surfaces) {
  for (const key of Object.keys(surfaces)) {
    if (!names[key]) throw new Error(`EXPECTED_JOB_NAMES lacks plan key '${key}'`);
  }
  for (const key of Object.keys(names)) {
    if (!surfaces[key]) throw new Error(`EXPECTED_JOB_NAMES has orphan key '${key}'`);
  }
}
validateNameTable(EXPECTED_JOB_NAMES, scopeMap.JOB_SURFACES);

// matchJobName(name, expected) -> equal, or expected followed by a matrix or
// variant parenthesis. See the table comment for why never bare startsWith.
function matchJobName(name, expected) {
  return name === expected || name.startsWith(`${expected} (`);
}

// Accept the Jobs API payload as gh returns it ({jobs:[...]}) or as a bare
// array. Anything else is unusable evidence: null, and the caller hard-fails.
function parseJobsPayload(payload) {
  const jobs = Array.isArray(payload) ? payload : payload && payload.jobs;
  if (!Array.isArray(jobs)) return null;
  return jobs.filter((j) => j && typeof j.name === 'string');
}

// ---------------------------------------------------------------------------
// reconcile(plan, jobs, { runId }) -> { ok, failures, warnings }
//
// Pure. failures are the hard-fail reasons (edge cases 25/27/29/30 plus the
// malformed-input guards); warnings are the safe-direction findings (28).
// ---------------------------------------------------------------------------
function reconcile(plan, jobs, ctx = {}) {
  const failures = [];
  const warnings = [];

  // Case 29: no plan means no attestation means nothing can prove the skips
  // were intended. Red, the opposite of the engine's fail-open.
  if (!plan || typeof plan !== 'object') {
    return { ok: false, failures: ['skip-plan-missing: no attested plan to reconcile against'], warnings };
  }

  // Case 30, anti-tamper: the plan must name THIS run. A plan without a
  // run_id, or with someone else's, could be a stale or substituted artifact.
  if (!plan.run_id || !ctx.runId || String(plan.run_id) !== String(ctx.runId)) {
    failures.push(
      `plan-run-id-mismatch: plan carries '${plan.run_id || '<none>'}', current run is '${ctx.runId || '<none>'}'`
    );
  }

  const planJobs = plan.jobs && typeof plan.jobs === 'object' ? Object.entries(plan.jobs) : [];
  if (planJobs.length === 0) {
    failures.push('malformed-plan: plan has no jobs vector');
  }

  if (!jobs) {
    failures.push('jobs-payload-missing: no usable Jobs API payload');
    return { ok: false, failures, warnings };
  }

  for (const [key, planned] of planJobs) {
    const expected = EXPECTED_JOB_NAMES[key];
    if (!expected) {
      // A plan key the table cannot map cannot be verified. Red, not shrug.
      failures.push(`unknown-plan-key: '${key}' has no expected-name entry`);
      continue;
    }
    const matched = jobs.filter((j) => expected.some((e) => matchJobName(j.name, e)));

    if (planned && planned.run === true) {
      if (matched.length === 0) {
        // Case 27: planned to run, absent from the Jobs API entirely (a
        // rename, a dropped call, a DAG break). Nothing validated the delta.
        failures.push(`planned-job-missing: '${key}' matched no job (expected: ${expected.join(' | ')})`);
        continue;
      }
      for (const job of matched) {
        // Case 25, THE invisible cell: the plan said run, the leaf
        // self-skipped, the siblings succeeded, and the caller scalar reads
        // success. Only here does that become red. Any non-skipped
        // conclusion (success, failure, cancelled) counts as "it ran";
        // failures are ci-complete's tiers' business, not a reconcile
        // violation.
        if (job.conclusion === 'skipped') {
          failures.push(`planned-run-but-skipped: '${key}' -> '${job.name}'`);
        }
      }
    } else {
      // Case 28: planned skip, but it ran anyway. Over-running is the safe
      // direction (extra evidence, wasted minutes), so WARN only. Blocking
      // here would punish exactly the fail-open YAML polarity we want.
      for (const job of matched) {
        if (job.conclusion !== 'skipped') {
          warnings.push(`planned-skip-but-ran: '${key}' -> '${job.name}' (${job.conclusion})`);
        }
      }
    }
  }

  return { ok: failures.length === 0, failures, warnings };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function usage() {
  return 'usage: skip-plan-reconcile.cjs --plan <plan.json> --jobs <jobs.json> --run-id <id>';
}

// Read-and-parse with the reconciler's polarity: any problem is a hard
// failure with a named reason, never a silent pass.
function readJson(file, missingReason) {
  try {
    return { value: JSON.parse(fs.readFileSync(file, 'utf8')) };
  } catch (e) {
    return { error: `${missingReason}: ${e.message} (the reconciler degrades to red, not to green)` };
  }
}

function main(argv) {
  const args = argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--plan') opts.plan = args[++i];
    else if (args[i] === '--jobs') opts.jobs = args[++i];
    else if (args[i] === '--run-id') opts.runId = args[++i];
    else {
      process.stderr.write(`skip-plan-reconcile: unknown argument '${args[i]}'\n${usage()}\n`);
      return 2;
    }
  }
  if (!opts.plan || !opts.jobs || !opts.runId) {
    process.stderr.write(`skip-plan-reconcile: --plan, --jobs and --run-id are all required\n${usage()}\n`);
    return 2;
  }

  const planRead = readJson(opts.plan, 'skip-plan-missing');
  if (planRead.error) {
    process.stderr.write(`FAIL: ${planRead.error}\n`);
    return 1;
  }
  const jobsRead = readJson(opts.jobs, 'jobs-payload-missing');
  if (jobsRead.error) {
    process.stderr.write(`FAIL: ${jobsRead.error}\n`);
    return 1;
  }

  const jobs = parseJobsPayload(jobsRead.value);
  const result = reconcile(planRead.value, jobs, { runId: opts.runId });

  // ::warning:: renders as an Actions annotation and is harmless locally.
  for (const w of result.warnings) process.stdout.write(`::warning::${w}\n`);
  for (const f of result.failures) process.stderr.write(`FAIL: ${f}\n`);

  if (!result.ok) {
    process.stderr.write('skip-plan reconciliation FAILED: the run skipped work the plan attested to.\n');
    return 1;
  }
  const planned = planRead.value.jobs ? Object.keys(planRead.value.jobs).length : 0;
  process.stdout.write(
    `skip-plan reconciled: ${planned} planned keys verified against ${jobs ? jobs.length : 0} jobs` +
      ` (${result.warnings.length} warning(s); unplanned jobs are not the reconciler's business).\n`
  );
  return 0;
}

if (require.main === module) {
  process.exit(main(process.argv));
}

module.exports = {
  EXPECTED_JOB_NAMES,
  validateNameTable,
  matchJobName,
  parseJobsPayload,
  reconcile,
  main,
};
