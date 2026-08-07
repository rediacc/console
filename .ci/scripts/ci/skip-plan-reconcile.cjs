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
// PRE-EXISTING SKIPS ARE NOT SCOPE DECISIONS, and conflating them is what
// would have made this gate unshippable. Long before the scope engine existed,
// ci.yml skipped whole columns for reasons of its own: `full_suite` is false on
// every push-to-main, `pointer_bump_only` cuts the entire expensive pipeline on
// a submodule-pointer PR, and `is_bot` cuts the staging chain. A plan that says
// only "scope wants unit to run" is therefore an incomplete prediction: on a
// pointer-bump PR every one of the 18 keys is planned `run: true` and every one
// of them skips, so a live gate would report eighteen `planned-run-but-skipped`
// failures on a run where nothing whatsoever went wrong. The plan now carries
// the observed condition values (`plan.conditions`) and the reconciler derives
// the exemption itself, per PREEXISTING_CONDITIONS below.
//
// Usage:
//   skip-plan-reconcile.cjs --plan <plan.json> --jobs <jobs.json> --run-id <id>
//     plan.json: the attested skip-plan artifact (run_id, mode, conditions,
//       jobs{key: {run, reason, preexisting_skip}}), as written by
//       scope-shadow.sh via annotatePlan().
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
  drills: ['Tests + Infra / Drills'],
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

// Plan keys whose expected name CONTAINS ' / ' but which are flat top-level
// jobs rather than leaves of a reusable-workflow caller.
//
// Derived, not guessed: parsing ci.yml's top-level jobs for `uses:
// ./.github/workflows/` classifies every job whose display name carries a
// ' / '. Ten are genuine reusable callers (Quality, Build (Renet), Build
// (Docker), Build (Docker Fast), Build (CLI), Tests + Infra / Update Flow,
// Stage Artifacts, Tests + Infra, OPS Tests, Validate Install Methods) and
// exactly ONE is flat: package-tests, named "Tests + Infra / Linux Packages".
//
// Keys with no ' / ' at all need no entry: their derived caller would be their
// own name, and a job with that exact name would already have been matched.
const FLAT_JOB_KEYS = new Set(['package_tests']);

// ---------------------------------------------------------------------------
// PRE-EXISTING (non-scope) SKIP CONDITIONS.
//
// `activeWhen` is the value of the condition that CAUSES the skip, so
// `full_suite: false` skips and `pointer_bump_only: true` skips. Comparison is
// strict against a real boolean: a condition the plan does not carry, or
// carries as a string or null, is NOT active, so a plan that fails to record a
// condition gets NO exemption and the reconciler stays at its strict default.
// Missing information must never widen an exemption.
//
// Every entry is derived from the tree, with the gate that performs the skip
// named. Ten of the eighteen keys are cut TRANSITIVELY, by a caller or a build
// job going `skipped`, which is why this cannot be read off the leaf's own
// `if:` (the thirteen ct-tests leaves mention only `full_suite`, and never
// `pointer_bump_only`, yet all thirteen skip on a pointer bump).
//
//   full_suite   ci.yml:118, `github.event_name != 'push'`. FALSE only on
//                push-to-main.
//     - the 13 ct-tests leaves: each carries its own `inputs.full_suite ==
//       'true'` clause. Cited by CLAUSE rather than by line number on purpose:
//       the thirteen line numbers that used to sit here went stale the moment
//       ct-tests.yml gained the run_* inputs, and a stale citation is worse
//       than none because it sends the next reader to the wrong job. Find them
//       with `grep -n "full_suite" .github/workflows/ct-tests.yml`.
//     - ops           ci.yml:717   elite_run    ci.yml:739
//     - update_flow   ci.yml:568   package_tests ci.yml:584
//     - install_methods is DELIBERATELY ABSENT: `validate-install`
//       (ci.yml:1081-1083) is gated only on `stage-artifacts`, which has no
//       full_suite clause (ci.yml:658), so the install matrix DOES run on
//       push-to-main. Adding it here would exempt a genuine skip.
//
//   pointer_bump_only  ci.yml:123 <- initialize.sh:85/131-133 and
//                detect-pointer-bump.sh:185. TRUE only on a pull_request whose
//                every commit moves nothing but tree-identical gitlinks.
//                Cuts ALL EIGHTEEN keys:
//     - build-renet skips (ci.yml:493) and everything below it inherits:
//       build-docker-fast (ci.yml:532) -> tests (ci.yml:687) -> the 13 leaves;
//       build-cli (ci.yml:553) -> update_flow (ci.yml:568);
//       build-docker (ci.yml:512) -> stage-artifacts (ci.yml:658) ->
//       install_methods (ci.yml:1083); build-docker-fast -> elite_run
//       (ci.yml:741)
//     - ops and package_tests carry their own explicit clause (ci.yml:719,
//       ci.yml:584), which is load-bearing: neither `if:` references its
//       build need, so under always() they would otherwise RUN and die
//       fetching a missing artifact (the comment at ci.yml:712-714).
//
//   is_bot       ci.yml:105 <- initialize.sh:67-82. TRUE only for a push
//                authored by github-actions[bot] or dependabot[bot].
//     - install_methods ONLY, via stage-artifacts (ci.yml:658). The other
//       seventeen need no entry: is_bot can only be true on a `push`, where
//       full_suite is already false and already exempts them. Listing them
//       would be a second, redundant reason for the same skip and would make
//       the annotation order load-bearing for no gain.
//
// NOT MODELLED, and the omission is deliberate: a planned job can also skip
// because an upstream job FAILED (quality failing skips package_tests,
// ci.yml:584; build-renet failing skips the whole pipeline). Those are not
// exempted, because such a run is ALREADY red at `ci-complete`'s tier check,
// so the extra reconcile failure cannot turn a green run red. The dangerous
// direction, a false red on an otherwise clean run, is only reachable through
// the three conditions above; every other non-failure skip path was checked
// and closed (`ci-build-renet.yml`'s cross-compile-smoke job carries no `if:`
// at all, so that caller can never report `skipped` through all-inner-skipped).
// ---------------------------------------------------------------------------
const CT_TESTS_LEAF_KEYS = [
  'unit',
  'e2e_workers',
  'e2e_ceph',
  'e2e_ceph_workers',
  'e2e_k8s',
  'e2e_k8s_ceph',
  'e2e_k8s_multinode',
  'e2e_migrate',
  'fork_isolation',
  'renet',
  'license_enforcement',
  'account_e2e',
  'drills',
];

const PREEXISTING_CONDITIONS = {
  pointer_bump_only: {
    activeWhen: true,
    keys: [
      ...CT_TESTS_LEAF_KEYS,
      'ops',
      'elite_run',
      'update_flow',
      'package_tests',
      'install_methods',
    ],
  },
  full_suite: {
    activeWhen: false,
    keys: [...CT_TESTS_LEAF_KEYS, 'ops', 'elite_run', 'update_flow', 'package_tests'],
  },
  is_bot: {
    activeWhen: true,
    keys: ['install_methods'],
  },
};

// Fixed evaluation order, so the reported condition is deterministic when two
// are active at once. Most upstream cut first: `pointer_bump_only` is the only
// one of the three that can be active on a pull_request, which is the only
// event that authors a plan today.
const CONDITION_ORDER = ['pointer_bump_only', 'full_suite', 'is_bot'];

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
  // A FLAT_JOB_KEYS entry that no longer names a real plan key is a dead
  // exemption: it would sit there reading as deliberate while suppressing
  // nothing. Fail at load rather than let it rot.
  for (const key of FLAT_JOB_KEYS) {
    if (!names[key]) throw new Error(`FLAT_JOB_KEYS has orphan key '${key}'`);
  }
}
validateNameTable(EXPECTED_JOB_NAMES, scopeMap.JOB_SURFACES);

// Same discipline for the condition table, and for the same reason: an entry
// naming a key that no longer exists is an exemption that can never apply, and
// a condition missing from CONDITION_ORDER would be evaluated by nothing while
// sitting there reading as deliberate. Both are silent, both are rot, both
// throw at load rather than degrade quietly.
function validateConditionTable(conditions, order, names) {
  for (const [cond, spec] of Object.entries(conditions)) {
    if (typeof spec.activeWhen !== 'boolean') {
      throw new Error(`PREEXISTING_CONDITIONS.${cond} has a non-boolean activeWhen`);
    }
    if (!order.includes(cond)) {
      throw new Error(`CONDITION_ORDER omits '${cond}', so it would never be evaluated`);
    }
    for (const key of spec.keys) {
      if (!names[key])
        throw new Error(`PREEXISTING_CONDITIONS.${cond} names unknown plan key '${key}'`);
    }
  }
  for (const cond of order) {
    if (!conditions[cond]) throw new Error(`CONDITION_ORDER has orphan condition '${cond}'`);
  }
}
validateConditionTable(PREEXISTING_CONDITIONS, CONDITION_ORDER, EXPECTED_JOB_NAMES);

// preexistingSkip(key, conditions) -> the name of the first ACTIVE condition
// that skips this key, or null. `conditions` is the plan's observed values.
// Strict boolean comparison: absent, null, or the string 'true' all count as
// NOT active, so an incomplete plan gets no exemption.
function preexistingSkip(key, conditions) {
  if (!conditions || typeof conditions !== 'object') return null;
  for (const cond of CONDITION_ORDER) {
    const spec = PREEXISTING_CONDITIONS[cond];
    if (conditions[cond] !== spec.activeWhen) continue;
    if (spec.keys.includes(key)) return cond;
  }
  return null;
}

// annotatePlan(plan, conditions) -> the same plan, with the observed condition
// values recorded at the top level and each job entry carrying the condition
// that will skip it (or nothing). Called by the plan WRITER
// (.ci/scripts/ci/scope-shadow.sh) so that writer and reader share one table
// rather than two that can drift; the reader re-derives anyway and hard-fails
// on disagreement, which is what catches a hand-edited artifact.
//
// Only real booleans are recorded. A condition the caller could not determine
// is OMITTED rather than defaulted, because both defaults are wrong: defaulting
// `full_suite` to false would exempt seventeen keys on no evidence at all.
function annotatePlan(plan, conditions) {
  if (!plan || typeof plan !== 'object') return plan;
  const observed = {};
  for (const cond of CONDITION_ORDER) {
    if (conditions && typeof conditions[cond] === 'boolean') observed[cond] = conditions[cond];
  }
  plan.conditions = observed;
  for (const [key, entry] of Object.entries(plan.jobs || {})) {
    if (!entry || typeof entry !== 'object') continue;
    const cond = preexistingSkip(key, observed);
    if (cond) entry.preexisting_skip = cond;
    else delete entry.preexisting_skip;
  }
  return plan;
}

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
// reconcile(plan, jobs, { runId, honorPreexisting }) -> { ok, failures,
//   warnings, exempt }
//
// Pure. failures are the hard-fail reasons (edge cases 25/27/29/30 plus the
// malformed-input guards); warnings are the safe-direction findings (28);
// exempt lists the keys a pre-existing condition accounts for.
//
// honorPreexisting DEFAULTS TO FALSE, and the default is the interesting half,
// because the two consumers of this function want OPPOSITE things:
//
//   - THE GATE (the CLI, via scope-reconcile-shadow.sh) must not red a run for
//     a skip the workflow performs on every run of that shape. It passes true.
//   - THE BASELINE READER (scope-engine.cjs's attestPlan, which calls this
//     module's reconcile() over a plan downloaded from an EARLIER run) must not
//     accept such a run as proof. A baseline is "the last run where everything
//     passed"; a pointer-bump run where all eighteen keys skipped passed
//     nothing, and treating it as a baseline would let the delta since then go
//     unvalidated. It passes nothing, so it gets the strict reading and refuses
//     the candidate with `reconcile:planned-run-but-skipped` exactly as before.
//
// So the exemption is opt-in, and the caller that never heard of it keeps the
// stricter behaviour. Adding it as an opt-OUT would have silently widened what
// counts as a usable baseline.
// ---------------------------------------------------------------------------
function reconcile(plan, jobs, ctx = {}) {
  const failures = [];
  const warnings = [];
  const exempt = [];
  const honorPreexisting = ctx.honorPreexisting === true;

  // Case 29: no plan means no attestation means nothing can prove the skips
  // were intended. Red, the opposite of the engine's fail-open.
  if (!plan || typeof plan !== 'object') {
    return {
      ok: false,
      failures: ['skip-plan-missing: no attested plan to reconcile against'],
      warnings,
      exempt,
    };
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
    return { ok: false, failures, warnings, exempt };
  }

  for (const [key, planned] of planJobs) {
    const expected = EXPECTED_JOB_NAMES[key];
    if (!expected) {
      // A plan key the table cannot map cannot be verified. Red, not shrug.
      failures.push(`unknown-plan-key: '${key}' has no expected-name entry`);
      continue;
    }
    const matched = jobs.filter((j) => expected.some((e) => matchJobName(j.name, e)));

    // The exemption is DERIVED from the plan's recorded condition values, never
    // taken from the per-job field. The field is checked against the derivation
    // and any disagreement is a hard failure, in BOTH modes: a hand-edited
    // artifact claiming `preexisting_skip` on a key no active condition covers
    // would otherwise buy itself a free pass on the one check that can see an
    // invisible cell. Writer/reader drift lands here too, which is the point.
    const derivedCond = preexistingSkip(key, plan.conditions);
    const claimedCond =
      planned && typeof planned.preexisting_skip === 'string' ? planned.preexisting_skip : null;
    if (claimedCond !== derivedCond) {
      failures.push(
        `preexisting-claim-mismatch: '${key}' claims '${claimedCond || '<none>'}',` +
          ` the plan's conditions yield '${derivedCond || '<none>'}'`
      );
      continue;
    }

    if (planned && planned.run === true && derivedCond && honorPreexisting) {
      // Planned to run by SCOPE, but the workflow's own long-standing gate
      // skips it regardless. Not a scope mismatch, so neither a failure nor a
      // warning: the run behaved exactly as the plan predicted.
      exempt.push(`${key} (${derivedCond})`);
      // Running anyway IS worth a note, in the safe direction: it means this
      // table over-claims and an exemption is being handed out that nothing
      // needs. It can never mask a failure, because there is no failure to
      // mask when a planned-run job ran.
      for (const job of matched) {
        if (job.conclusion !== 'skipped') {
          warnings.push(
            `preexisting-exempt-but-ran: '${key}' -> '${job.name}' (${job.conclusion})` +
              ` despite ${derivedCond}; the condition table may be over-broad`
          );
        }
      }
      continue;
    }

    if (planned && planned.run === true) {
      // STRICT mode reaching here with an active condition is the baseline
      // reader refusing a run that skipped work. The condition is no excuse,
      // but it IS the explanation, and the reader only ever surfaces the FIRST
      // failure string (`reconcile:<...>`, scope-engine.cjs:249). Naming it
      // turns an opaque refusal into an actionable one. The leading token is
      // deliberately unchanged: the trail is read by string match.
      const strictNote = derivedCond
        ? ` (pre-existing condition ${derivedCond} was active, so this run is not proof that it ran)`
        : '';
      if (matched.length === 0) {
        // A SKIPPED REUSABLE CALLER is not a missing job. When the caller of a
        // reusable workflow is skipped, GitHub materialises only the caller
        // ("OPS Tests") and never its inner jobs ("OPS Tests / OPS Provision
        // (linux-amd64)"), so a table keyed on inner names matches nothing and
        // this would report planned-job-missing for what is really a skip.
        //
        // Found by the shadow reconciler on run 30388401305, which is exactly
        // the false-fire it was built to surface before the gate went live.
        // Reported as planned-run-but-skipped, the same finding a directly
        // skipped leaf produces, because that is what actually happened.
        // Derive the caller ONLY for keys that really are reusable-workflow
        // leaves. `package_tests` shares the "Tests + Infra" prefix by
        // coincidence: it is a FLAT top-level job (ci.yml:572-573,
        // `needs: [initialize, quality]`), not a leaf of the `tests` caller
        // whose own display name is exactly "Tests + Infra" (ci.yml:673-674).
        // Splitting on ' / ' regardless would hand back 'Tests + Infra' and
        // then blame the unrelated `tests` job for `package_tests` going
        // missing, turning a real case-27 rename or DAG break into a bogus
        // case-25 caller-skip. The header two screens up already warns about
        // this exact name, which is how it was caught.
        const callers = FLAT_JOB_KEYS.has(key)
          ? []
          : [...new Set(expected.map((e) => e.split(' / ')[0]))];
        const skippedCaller = jobs.find(
          (j) => callers.includes(j.name) && j.conclusion === 'skipped'
        );
        if (skippedCaller) {
          failures.push(
            `planned-run-but-skipped: '${key}' -> reusable caller '${skippedCaller.name}' was skipped, so its inner jobs never ran${strictNote}`
          );
          continue;
        }
        // Case 27: planned to run, absent from the Jobs API entirely (a
        // rename, a dropped call, a DAG break). Nothing validated the delta.
        failures.push(
          `planned-job-missing: '${key}' matched no job (expected: ${expected.join(' | ')})${strictNote}`
        );
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
          failures.push(`planned-run-but-skipped: '${key}' -> '${job.name}'${strictNote}`);
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

  return { ok: failures.length === 0, failures, warnings, exempt };
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
    return {
      error: `${missingReason}: ${e.message} (the reconciler degrades to red, not to green)`,
    };
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
    process.stderr.write(
      `skip-plan-reconcile: --plan, --jobs and --run-id are all required\n${usage()}\n`
    );
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
  // honorPreexisting: the CLI IS the gate. See reconcile()'s header for why the
  // module default is the opposite and must stay that way.
  const result = reconcile(planRead.value, jobs, { runId: opts.runId, honorPreexisting: true });

  // ::warning:: renders as an Actions annotation and is harmless locally.
  for (const w of result.warnings) process.stdout.write(`::warning::${w}\n`);
  for (const f of result.failures) process.stderr.write(`FAIL: ${f}\n`);

  // The exempt list goes to stdout unconditionally, including on failure. It is
  // the difference between "this run verified sixteen keys" and "this run
  // verified one and excused sixteen", and a reconcile whose exempt list is
  // long is a VACUOUS pass however green it looks. Printing the count only on
  // success would hide exactly the runs worth doubting.
  if (result.exempt.length > 0) {
    process.stdout.write(
      `pre-existing skips (not scope decisions, not verified by this run): ${result.exempt.join(', ')}\n`
    );
  }

  if (!result.ok) {
    process.stderr.write(
      'skip-plan reconciliation FAILED: the run skipped work the plan attested to.\n'
    );
    return 1;
  }
  const planned = planRead.value.jobs ? Object.keys(planRead.value.jobs).length : 0;
  process.stdout.write(
    `skip-plan reconciled: ${planned - result.exempt.length} of ${planned} planned keys verified against` +
      ` ${jobs ? jobs.length : 0} jobs (${result.exempt.length} exempt, ${result.warnings.length} warning(s);` +
      ` unplanned jobs are not the reconciler's business).\n`
  );
  return 0;
}

if (require.main === module) {
  process.exit(main(process.argv));
}

module.exports = {
  EXPECTED_JOB_NAMES,
  PREEXISTING_CONDITIONS,
  CONDITION_ORDER,
  validateNameTable,
  validateConditionTable,
  preexistingSkip,
  annotatePlan,
  matchJobName,
  parseJobsPayload,
  reconcile,
  main,
};
