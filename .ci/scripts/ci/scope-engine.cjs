#!/usr/bin/env node
// The CI scope engine: the one baseline-and-net-delta mechanism that will
// replace detect-pointer-bump.sh (whose ancestor walk NEVER fired on a
// pull_request: HEAD there is the synthetic 2-parent refs/pull/N/merge commit,
// so the walk aborted on its first step, defect D9).
//
// THIS CHUNK IS THE PURE CORE ONLY. The only wired mode is --classify, which
// reads a file list and prints a JSON plan; it performs no network call, no
// git command, no GitHub API access (its only I/O is reading the file list
// and, for edge case 24, the local .github/workflows/*.yml text). Nothing in
// CI consumes the output yet, so landing this cannot change CI behaviour.
// Baseline resolution (finding the nearest green FULL run to diff against) is
// exported as pure decision helpers for unit testing but deliberately not
// wired to any mode: the harvesting side needs gh/git and belongs to the next
// chunk, behind its own mode, so --classify stays testable offline.
//
// Usage:
//   scope-engine.cjs --classify [--files <path>]
//     Reads newline-delimited changed paths from <path> or stdin and prints
//     the plan JSON. Accepted line shapes:
//       - a plain repo-relative path (spaces and unicode are fine)
//       - a git C-quoted path ("docs/f\303\274r.md"), as `git diff` emits
//         under the default core.quotepath
//       - a `git diff-tree -r --raw` line (":100644 100644 <sha> <sha> M\tpath",
//         renames carry both paths and BOTH classify, edge case 20; a deleted
//         file is a path like any other, edge case 19)
//     Any line the parser cannot understand stays a single opaque path, which
//     no rule matches, which is full CI: unsupported input degrades to more
//     CI, never to a wrong reduced run.
//
// The classification table and the fail-closed semantics live in
// scope-map.cjs; the edge-case numbers cited in both files refer to the Wave B
// edge-case matrix.

'use strict';

const fs = require('fs');
const path = require('path');

const scopeMap = require('./scope-map.cjs');

// ---------------------------------------------------------------------------
// File-list parsing (edge cases 19, 20, 21)
// ---------------------------------------------------------------------------

// Decode a git C-quoted path ("...") into a real string: git escapes bytes
// outside ASCII as \NNN octal (UTF-8 bytes) and the usual \t \n \" \\ forms.
// Returns null on anything malformed; the caller then keeps the raw line,
// which classifies as unclassified = full (fail-closed, never a silent drop).
function unquoteCPath(quoted) {
  if (quoted.length < 2 || !quoted.startsWith('"') || !quoted.endsWith('"')) return null;
  const inner = quoted.slice(1, -1);
  const bytes = [];
  const SIMPLE = { n: 0x0a, t: 0x09, r: 0x0d, f: 0x0c, b: 0x08, v: 0x0b, a: 0x07, '"': 0x22, '\\': 0x5c };
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i];
    if (ch !== '\\') {
      for (const b of Buffer.from(ch, 'utf8')) bytes.push(b);
      continue;
    }
    const next = inner[++i];
    if (next === undefined) return null;
    if (next in SIMPLE) {
      bytes.push(SIMPLE[next]);
      continue;
    }
    if (next >= '0' && next <= '7') {
      let oct = next;
      while (oct.length < 3 && inner[i + 1] >= '0' && inner[i + 1] <= '7') oct += inner[++i];
      bytes.push(parseInt(oct, 8));
      continue;
    }
    return null;
  }
  return Buffer.from(bytes).toString('utf8');
}

// One raw or plain line -> array of repo-relative paths (renames yield two).
function parseLine(line) {
  if (line.startsWith(':')) {
    // `git diff-tree -r --raw`: ":<old> <new> <sha> <sha> <status>\tpath[\tpath]".
    // Tab-separated, so paths with spaces survive; a rename/copy carries both
    // sides and both are returned (edge case 20: union wins).
    const fields = line.split('\t');
    if (fields.length < 2) return [line]; // malformed raw line: opaque => full
    return fields.slice(1);
  }
  return [line];
}

function normalizePath(p) {
  const unquoted = p.startsWith('"') ? unquoteCPath(p) : null;
  const value = unquoted !== null ? unquoted : p;
  return value.startsWith('./') ? value.slice(2) : value;
}

// parseFileList(text) -> array of paths, one per changed file side.
function parseFileList(text) {
  return String(text)
    .split('\n')
    .map((line) => line.replace(/\r$/, ''))
    .filter((line) => line.length > 0)
    .flatMap(parseLine)
    .map(normalizePath)
    .filter((p) => p.length > 0);
}

// ---------------------------------------------------------------------------
// Workflow closure (edge case 24)
// ---------------------------------------------------------------------------

// Compute the set of workflow paths reachable from ci.yml by literally
// iterating `uses: ./.github/workflows/<x>.yml` references, transitively.
// NEVER a name pattern: ci.yml calls cd-stage.yml, so a `cd-*` exclusion
// would drop a workflow that IS in the CI closure. Local fs reads only.
// An unreadable entry yields an empty closure, which classifies every
// workflow change as non-closure: still full, only the reason degrades.
function computeWorkflowClosure(repoRoot, entry = 'ci.yml') {
  const closure = new Set();
  const queue = [`.github/workflows/${entry}`];
  const USES_RE = /uses:\s*['"]?\.\/(\.github\/workflows\/[A-Za-z0-9._-]+\.ya?ml)/g;
  while (queue.length > 0) {
    const wf = queue.pop();
    if (closure.has(wf)) continue;
    let text;
    try {
      text = fs.readFileSync(path.join(repoRoot, wf), 'utf8');
    } catch {
      continue; // referenced but absent: nothing to add, nothing to exclude
    }
    closure.add(wf);
    for (const m of text.matchAll(USES_RE)) queue.push(m[1]);
  }
  return closure;
}

// ---------------------------------------------------------------------------
// Baseline-resolution decision helpers (edge cases 1, 2, 4, 5). PURE and
// exported for unit tests; NOT wired to any CLI mode yet. The harvesting side
// (walking ancestors, downloading the attested plan artifact, reading the
// merge commit's first parent) needs gh and git and will arrive as its own
// mode in the next chunk.
// ---------------------------------------------------------------------------

// A usable baseline is a GREEN run whose attested skip-plan exists, says
// mode 'full', and whose reconciler confirmed the outcome. Anything less and
// evidence would chain across reduced runs (case 1), or rest on a run that
// cannot prove what it ran (case 2: pre-engine or expired artifact reads as
// absent, case 3), or on a plan whose jobs were skipped by a watchdog rerun
// rather than by scope (case 4: intent is not outcome).
function evaluateBaselineCandidate(candidate) {
  if (!candidate || candidate.conclusion !== 'success') {
    return { usable: false, reason: 'not-green' };
  }
  if (!candidate.plan) {
    return { usable: false, reason: 'no-skip-plan' };
  }
  if (candidate.plan.mode !== 'full') {
    return { usable: false, reason: 'reduced-baseline' };
  }
  if (candidate.plan.reconciled !== true) {
    // The leading token stays exactly 'unreconciled-outcome' whether or not a
    // reason is available: the trail is read by eye and by string match, and
    // an unconditional suffix would change the verdict's identity rather than
    // annotate it. attestPlan's refusal reason is appended when there is one.
    const why = candidate.plan.attest_reason;
    return { usable: false, reason: why ? `unreconciled-outcome:${why}` : 'unreconciled-outcome' };
  }
  return { usable: true, reason: 'full-green-attested' };
}

// ---------------------------------------------------------------------------
// Attestation, VERIFY-AT-READ. Pure, and exported for unit tests.
//
// NOBODY WRITES `reconciled`, the READER derives it. The alternative design,
// where the run that produced the plan marks its own artifact once its
// reconciler passes, mints a trust token that then travels forward in time:
// every later reader has to believe a claim it cannot check, and the check
// would have to live in `ci-complete` (the pipeline's single required check,
// on ubuntu-slim with timeout-minutes: 5) where a slow artifact write costs
// every PR. Here the consumer already holds the plan, can fetch that run's
// per-job outcomes, and can run the EXISTING pure reconcile() itself. Nothing
// is carried forward, and the verdict lands on the FAIL-OPEN side: a wrong
// refusal costs one full CI round, not a red required check.
//
// SELF-DECLARATION IS DELETED, NOT BLACKLISTED. The downloaded bytes come from
// a different run and `reconciled` is now load-bearing, so whatever the
// artifact says about itself is dropped before anything reads it; only the
// recomputation below may put it back. A blacklist would have to enumerate the
// ways a writer could vouch for itself; deleting the field enumerates nothing.
//
// `jobs` may be an ARRAY or a zero-argument function returning one. The
// function form is what makes the cheap-first ordering real rather than
// stylistic: a candidate that is reduced, or carries another run's id, is
// refused without ever paying for a Jobs API round trip, and there is one such
// round trip per candidate walked.
//
// It never throws. Every refusal is a plan WITHOUT `reconciled`, carrying
// `attest_reason`, which evaluateBaselineCandidate then reads as unusable.
// ---------------------------------------------------------------------------
function attestPlan({ plan, jobs, runId, sha, reconcile }) {
  if (!plan || typeof plan !== 'object') return plan;
  delete plan.reconciled;
  delete plan.attest_reason;

  const refuse = (reason) => {
    plan.attest_reason = reason;
    return plan;
  };
  const msg = (e) => (e && e.message ? e.message : String(e));

  try {
    // Cheapest first, and the order is a cost decision, not a style one.
    // A non-full plan can never be a baseline whatever the reconciler says
    // (case 1: evidence does not chain across reduced rounds), so asking the
    // Jobs API about it would be a round trip spent on a foregone conclusion.
    if (plan.mode !== 'full') return refuse('not-full-plan');
    // Case 30 again, but at READ time: a plan that does not name the run we
    // downloaded it from is stale or substituted evidence.
    // The `!plan.run_id` half is load-bearing: without it a plan carrying NO
    // run_id, read for a runId that is itself missing, would compare
    // String(undefined) to String(undefined) and pass a check it should fail.
    if (!plan.run_id || String(plan.run_id) !== String(runId)) return refuse('run-id-mismatch');
    // The plan describes one commit's delta. If it names a different head than
    // the candidate we are considering, it is not that candidate's proof.
    if (plan.head_sha && plan.head_sha !== sha) return refuse('head-sha-mismatch');
    // The reconciler is lazily required by the caller and may be unavailable
    // (its name table throws at load on drift). No verifier, no attestation.
    if (typeof reconcile !== 'function') return refuse('reconciler-unavailable');

    let payload;
    try {
      payload = typeof jobs === 'function' ? jobs() : jobs;
    } catch (e) {
      return refuse(`jobs-unreadable:${msg(e)}`);
    }
    const observed = Array.isArray(payload) ? payload : payload && payload.jobs;
    const list = Array.isArray(observed) ? observed.filter((j) => j && typeof j.name === 'string') : null;
    // An EMPTY job list is unusable evidence, not a clean bill of health: it
    // is what an unreadable payload and a run that never materialised both
    // look like, and reconcile() would happily report ok on it.
    if (!list || list.length === 0) return refuse('jobs-unreadable');

    const r = reconcile(plan, list, { runId });
    if (r && r.ok === true) {
      plan.reconciled = true; // THE one and only assignment.
      return plan;
    }
    return refuse(`reconcile:${(r && r.failures && r.failures[0]) || 'refused-without-a-reason'}`);
  } catch (e) {
    // An unexpected throw must degrade to "not attested", never to a crash and
    // never to an attestation: the engine runs inside `initialize`, which
    // every other job depends on.
    return refuse(`attest-threw:${msg(e)}`);
  }
}

// Case 5: CI validates the MERGE commit, so the proof requires the base to be
// unchanged since the baseline: plan.base_sha must equal M^1 (what the merge
// actually used, more precise than the event payload's ref-tip base.sha).
// Any mismatch, or either value missing, means main moved: full CI.
function isBaseUnchanged({ planBaseSha, mergeParentSha }) {
  return Boolean(planBaseSha) && Boolean(mergeParentSha) && planBaseSha === mergeParentSha;
}

// ---------------------------------------------------------------------------
// Baseline harvesting: the --resolve-baseline mode (edge cases 1 to 5, 22, 23)
//
// This is the half the headline case needs: "CI went green on a full round,
// then a one-line change was pushed, so the next round should not be full
// again". A MERGE BASE cannot express that. The merge base does not move when
// a second commit lands on the PR branch, so every push re-diffs the entire
// branch and the tenth push costs exactly what the first did. The baseline
// that CAN express it is the newest ANCESTOR OF HEAD whose own run was green,
// ran a FULL suite, and proved it with a reconciled skip-plan.
//
// Everything here fails OPEN. A shallow clone, an unwalkable history, a
// missing or unreadable plan artifact, a base that moved under us, a
// truncated file list: all converge on one outcome, which is to run
// everything and say which of them happened. The only direction this
// mechanism can be wrong in is running MORE CI than needed.
//
// Like --classify, this mode lands INERT, and it stays inert even now that
// baselines can become usable: NOTHING consumes the engine's output. No job
// `if:` in any workflow references a scope value, so a resolved baseline
// changes a shadow artifact and nothing else. It cannot change CI behaviour
// until someone wires the vector to a job condition, which is deliberate: it
// means this can be landed and observed before it is trusted.
//
// Candidates USED to resolve to 'no-skip-plan' unconditionally, because
// nothing wrote the artifact. The shadow step in `initialize` now uploads
// `ci-skip-plan` on every PR run, so the artifact exists and the question has
// moved from "is there a plan" to "does that plan describe what that run
// actually did". That is attestPlan's job, at READ time, per candidate.
//
// WIRING PRECONDITION, and it is not optional. `initialize` checks out with
// `fetch-tags: true` and NO `fetch-depth` (ci.yml:128-131), which is a depth-1
// shallow clone. Wired there as it stands, this mode would answer
// 'baseline:shallow-clone' on every single run and go full forever, while
// looking perfectly healthy from the outside. That is D9's exact failure
// shape, so whoever wires it must add `fetch-depth: 0` plus `filter:
// blob:none` to that ONE job (blob:none keeps it cheap: commits and trees
// only, no historical file contents), and must then confirm a reduced run on
// real traffic rather than assuming one.
// ---------------------------------------------------------------------------

// GitHub truncates a compare file list at 300 entries. Past that the list is
// a lie by omission, and an omission classifies as REDUCED (the missing paths
// simply do not vote), so the cap is a fail-open trigger and not a display
// limit.
const DIFF_FILE_CAP = 300;

// THE WALK IS FENCED AT THE MERGE BOUNDARY, NOT AT A COUNT. Any fixed count
// eventually loses to a long enough red streak, and lost twice in one night:
// at limit 5 the only green sat SEVEN back (run 30478917957, green 2469e5d72
// one row past the cap), and after the raise to 20 a twelve-run red streak
// pushed the green to 23 back (681443ad3, `git rev-list --count` = 23) and it
// was gone again. Both times "no baseline" was manufactured by the bound while
// a perfectly good baseline existed, and that verdict is indistinguishable
// from a considered one. So the walk's domain is now the commits this PR OWNS
// (`rev-list --first-parent head ^mergeParent`): it grows only when the
// operator grows the branch, and candidates past the boundary were dead weight
// anyway, since only PR runs upload a ci-skip-plan and a main commit's
// push-run green downloads to no-plan every time.
//
// What keeps the fenced walk affordable is that candidates are now CHEAP: one
// paginated run listing per resolve (RUNS_LIST_MAX_PAGES pages of 100) is
// joined locally against the walked shas, so a red candidate costs ZERO API
// calls and the streak length drops out of the cost function entirely. The
// expensive class, green candidates whose plans must be downloaded and
// attested, is bounded separately by GREEN_ATTEST_BUDGET: attestation
// failures are systematic (artifact retention, plan-format drift, reconciler
// drift), so after three green candidates in a row fail to attest a fourth
// try is not going to differ, and artifact retention already bounds how far
// back an attestable green can exist at all.
//
// DEFAULT_CANDIDATE_LIMIT is therefore a SAFETY VALVE, not the bound: it only
// exists so a wrong or unrelated fence cannot turn rev-list into all of
// history, and `--limit` remains the explicit override for it.
const DEFAULT_CANDIDATE_LIMIT = 200;

// Distinct green candidates whose runs may be attestation-attempted per walk.
const GREEN_ATTEST_BUDGET = 3;

// Pages of the branch run listing (100 runs each). A green older than 300
// runs is almost certainly past artifact retention too, so paging further
// buys candidates that cannot attest.
const RUNS_LIST_MAX_PAGES = 3;

// Walk candidates newest-first, returning the first usable baseline and the
// complete rejection trail. The trail is the load-bearing part: when a round
// runs full, the operator has to be able to see why every NEARER candidate
// was refused, because a permanently-full pipeline and a correctly-full one
// look identical from the outside. D9 stayed false for twelve runs precisely
// because nothing printed its reason.
function selectBaseline(candidates) {
  const trail = [];
  for (const candidate of candidates || []) {
    const verdict = evaluateBaselineCandidate(candidate);
    trail.push({
      sha: candidate && candidate.sha ? candidate.sha : null,
      usable: verdict.usable,
      reason: verdict.reason,
    });
    if (verdict.usable) return { baseline: candidate, trail };
  }
  return { baseline: null, trail };
}

// Case 5. The baseline proved head-at-that-time against one specific main
// tip. If main has moved since, that proof no longer covers what CI will
// actually merge, so either main's own delta folds into the net diff or the
// round goes full. Missing information is never read as 'unchanged'.
function decideBaseMove({ planBaseSha, mergeParentSha, mainDeltaAvailable }) {
  if (!planBaseSha || !mergeParentSha) {
    return { action: 'full', reason: 'base-sha-unknown' };
  }
  if (isBaseUnchanged({ planBaseSha, mergeParentSha })) {
    return { action: 'proceed', reason: 'base-unchanged' };
  }
  return mainDeltaAvailable
    ? { action: 'fold', reason: 'base-moved:fold-main-delta' }
    : { action: 'full', reason: 'base-moved' };
}

// A full plan carrying one machine-readable reason. Built THROUGH buildPlan
// rather than hand-rolled, so the job table can never drift from the one the
// reduced path emits.
function forcedFullPlan(reason) {
  return scopeMap.buildPlan({
    modules: new Set(),
    reasons: [],
    mode: 'full',
    full_reasons: [reason],
  });
}

// io is injected so every decision above is testable with no git, no gh and
// no network. Each io call is wrapped: a throw becomes an ANSWER ('full'),
// never an exception, because a scope engine that crashes inside `initialize`
// would take the whole run down in exchange for an optimisation.
function resolveBaseline(opts, io) {
  const { head, mergeSha, limit = DEFAULT_CANDIDATE_LIMIT, workflowClosure } = opts || {};
  const notes = [];
  // io-side degradations (the one-shot run listing falling back to per-commit
  // lookups) surface through this sink into `notes`, which main() emits as
  // baseline_notes and scope-shadow.sh writes into the shadow artifact: the
  // place someone actually looks. Without it, "the cheap path silently
  // stopped being cheap" shows up only in API-call patterns nobody watches.
  // An io without a sink (injected test doubles) simply stays silent.
  if (typeof io.setNoteSink === 'function') io.setNoteSink((m) => notes.push(m));
  const fail = (reason, baseline = null, trail = []) => ({
    baseline,
    trail,
    notes,
    plan: forcedFullPlan(reason),
  });
  const msg = (e) => (e && e.message ? e.message : String(e));

  if (!head) return fail('baseline:head-sha-missing');

  // A shallow superproject cannot be walked. A PARTIAL walk is the dangerous
  // case, not the empty one: it would find no green ancestor and report
  // 'none-usable', which reads as a considered verdict rather than as a
  // truncated history.
  try {
    if (io.isShallow()) return fail('baseline:shallow-clone');
  } catch (e) {
    return fail(`baseline:shallow-probe-failed:${msg(e)}`);
  }

  // Two walk shapes, capability-detected. The MODERN one (createRepoIo) is
  // candidate C: fenced at the merge boundary, one-shot run listing, lazy
  // per-candidate attestation under GREEN_ATTEST_BUDGET. The LEGACY one keeps
  // the eager listCandidates(head, limit) contract byte-for-byte, because
  // injected-io consumers (test-scope-engine.sh's fail-open matrix) hold that
  // interface and its reason strings.
  const modern = typeof io.walkShas === 'function' && typeof io.candidateFor === 'function';
  let baseline = null;
  let trail = [];
  let mergeParentSha = null;

  if (modern) {
    // THE FENCE IS OBTAINED BEFORE THE WALK, and an unreadable merge parent
    // DEGRADES TO A VALVE-ONLY WALK WITH A NOTE, never to full: a bad
    // mergeSha must not turn every round full while the walk itself is fine.
    // (The baseline it finds will still fail decideBaseMove as
    // base-sha-unknown, which is the correct, correctly-attributed verdict.)
    if (mergeSha) {
      try {
        mergeParentSha = io.firstParent(mergeSha);
      } catch (e) {
        notes.push(`merge-parent-unreadable:${msg(e)}`);
      }
    }
    let walk;
    try {
      walk = io.walkShas(head, { fence: mergeParentSha, valve: limit });
    } catch (e) {
      return fail(`baseline:candidate-walk-failed:${msg(e)}`);
    }
    const shas = (walk && walk.shas) || [];
    if (shas.length === 0) return fail('baseline:no-candidates');

    let budgetSpent = 0;
    for (const sha of shas) {
      const candidate = io.candidateFor(sha);
      const verdict = evaluateBaselineCandidate(candidate);
      trail.push({ sha, usable: verdict.usable, reason: verdict.reason });
      if (verdict.usable) {
        baseline = candidate;
        break;
      }
      // Only candidates that actually paid for attestation attempts consume
      // budget; red candidates are free and the streak can be any length.
      if (candidate && candidate.attestsTried > 0) {
        budgetSpent += 1;
        if (budgetSpent >= GREEN_ATTEST_BUDGET) {
          return fail('baseline:attest-budget-exhausted', null, trail);
        }
      }
    }
    if (!baseline) {
      // The exhausted reason states WHICH bound ended the walk, because a
      // permanently full pipeline is only diagnosable from that distinction.
      if (walk.truncated) return fail('baseline:walk-valve', null, trail);
      if (mergeParentSha) return fail('baseline:merge-base-reached', null, trail);
      return fail('baseline:none-usable', null, trail);
    }
  } else {
    let candidates;
    try {
      candidates = io.listCandidates(head, limit);
    } catch (e) {
      return fail(`baseline:candidate-walk-failed:${msg(e)}`);
    }
    if (!candidates || candidates.length === 0) return fail('baseline:no-candidates');

    ({ baseline, trail } = selectBaseline(candidates));
    if (!baseline) return fail('baseline:none-usable', null, trail);

    if (mergeSha) {
      try {
        mergeParentSha = io.firstParent(mergeSha);
      } catch (e) {
        notes.push(`merge-parent-unreadable:${msg(e)}`);
      }
    }
  }

  const move = decideBaseMove({
    planBaseSha: baseline.plan.base_sha,
    mergeParentSha,
    mainDeltaAvailable: Boolean(mergeParentSha),
  });
  if (move.action === 'full') return fail(`baseline:${move.reason}`, baseline, trail);

  let paths;
  try {
    paths = io.diffPaths(baseline.sha, head);
    if (move.action === 'fold') {
      notes.push(move.reason);
      paths = paths.concat(io.diffPaths(baseline.plan.base_sha, mergeParentSha));
    }
  } catch (e) {
    return fail(`baseline:diff-failed:${msg(e)}`, baseline, trail);
  }

  // Checked BEFORE classify, because classify would happily reduce on a list
  // it does not know is incomplete.
  if (paths.length > DIFF_FILE_CAP) {
    return fail(`baseline:diff-truncated:${paths.length}`, baseline, trail);
  }

  const plan = scopeMap.buildPlan(scopeMap.classify(paths, { workflowClosure }));
  return { baseline, trail, notes, plan };
}

// ---------------------------------------------------------------------------
// The real io: git for history, gh for runs and the attested plan artifact.
// ---------------------------------------------------------------------------

function defaultRun(cmd, args) {
  const { execFileSync } = require('child_process');
  return execFileSync(cmd, args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
}

// `gh api --paginate` on an OBJECT-shaped endpoint (the Jobs API returns
// { total_count, jobs: [...] }) concatenates ONE JSON OBJECT PER PAGE. A plain
// JSON.parse succeeds on the single-page case and throws the moment a run has
// more than per_page jobs, which is the shape a growing pipeline drifts into
// silently. Parse the stream properly and merge the pages instead.
function parseJsonStream(text) {
  const values = [];
  let depth = 0;
  let inStr = false;
  let esc = false;
  let start = -1;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (start === -1) {
      if (c !== '{' && c !== '[') continue;
      start = i;
      depth = 0;
    }
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') inStr = true;
    else if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') {
      depth--;
      if (depth === 0) {
        values.push(JSON.parse(text.slice(start, i + 1)));
        start = -1;
      }
    }
  }
  return values;
}

function createRepoIo({ repoRoot, repo, branch = null, workflow = 'Console CI', artifactName = 'ci-skip-plan', run = defaultRun }) {
  const git = (...args) => run('git', ['-C', repoRoot, ...args]);
  const gh = (...args) => run('gh', args);

  // The per-job outcomes for one run. THROWS on anything unusable, and the
  // throw is the interface: attestPlan turns it into 'jobs-unreadable', which
  // refuses the baseline. Returning an empty list instead would read as "that
  // run skipped nothing", which is the one answer this must never fabricate.
  const readJobsForRun = (runId) => {
    const text = gh('api', `repos/${repo}/actions/runs/${runId}/jobs?per_page=100`, '--paginate');
    const pages = parseJsonStream(text);
    if (pages.length === 0) throw new Error('jobs payload carried no JSON');
    if (pages.length === 1) return pages[0];
    return { jobs: pages.flatMap((p) => (Array.isArray(p) ? p : (p && p.jobs) || [])) };
  };

  const downloadPlan = (runId) => {
    const os = require('os');
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'scope-plan-'));
    try {
      try {
        gh('run', 'download', String(runId), '--repo', repo, '-n', artifactName, '-D', dir);
      } catch {
        // Absent or expired reads exactly like never-attested (case 3), which
        // is the correct conflation: neither can prove what that run executed.
        return null;
      }
      for (const f of ['plan.json', 'skip-plan.json']) {
        try {
          return JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
        } catch {
          continue;
        }
      }
      return null;
    } finally {
      // The walk downloads up to `limit` plans per invocation and this used to
      // leak every one of them into the runner's tmpdir.
      try {
        fs.rmSync(dir, { recursive: true, force: true });
      } catch {
        /* a tmpdir we cannot remove is not worth failing a CI round over */
      }
    }
  };

  // Download the plan, then PROVE it against what that run actually did.
  // Returns an attested plan, an un-attested plan carrying attest_reason, or
  // null when there is no plan at all.
  const readAttestedPlanForRun = (runId, sha) => {
    const plan = downloadPlan(runId);
    if (!plan) return null;
    // LAZY, and inside a try. skip-plan-reconcile.cjs runs validateNameTable at
    // module load and THROWS on table drift; required at the top of this file,
    // that throw would take down the whole engine (including --classify, which
    // has nothing to do with attestation) instead of degrading to full CI.
    let reconcile = null;
    try {
      ({ reconcile } = require('./skip-plan-reconcile.cjs'));
    } catch {
      reconcile = null; // becomes 'reconciler-unavailable' below
    }
    return attestPlan({ plan, jobs: () => readJobsForRun(runId), runId, sha, reconcile });
  };

  // Per-commit run lookup, the FALLBACK cost model: one gh process per
  // candidate. Kept for the no-branch case only; the walk normally joins
  // against the one-shot listing below, where a candidate costs zero calls.
  const runsForShaViaGh = (sha) =>
    JSON.parse(
      gh('run', 'list', '--repo', repo, '--workflow', workflow, '--commit', sha,
        '--json', 'databaseId,conclusion,status', '-L', '5'),
    );

  // One paginated listing of the branch's runs, joined locally. This is what
  // makes the fenced walk affordable: run-listing cost scales with PAGES
  // (RUNS_LIST_MAX_PAGES max), never with candidates, so a red streak of any
  // length adds nothing. `null` until loaded; `false` when the listing failed
  // or no branch is known, which degrades to the per-commit fallback above.
  // Filled by resolveBaseline via setNoteSink; a no-op until then, so calling
  // io functions outside a resolve stays silent rather than crashing.
  let noteSink = () => {};

  let runsBySha = null;
  const loadRunsBySha = () => {
    if (runsBySha !== null) return;
    if (!branch) {
      runsBySha = false;
      noteSink('runs-listing:per-commit-fallback:no-branch');
      return;
    }
    try {
      const map = new Map();
      for (let page = 1; page <= RUNS_LIST_MAX_PAGES; page++) {
        const text = gh(
          'api',
          `repos/${repo}/actions/runs?head_branch=${encodeURIComponent(branch)}&per_page=100&page=${page}`,
        );
        const payload = JSON.parse(text);
        const runs = (payload && payload.workflow_runs) || [];
        for (const r of runs) {
          if (r.name !== workflow) continue;
          const list = map.get(r.head_sha) || [];
          list.push({ databaseId: r.id, status: r.status, conclusion: r.conclusion });
          map.set(r.head_sha, list);
        }
        if (runs.length < 100) break;
      }
      runsBySha = map;
    } catch (e) {
      runsBySha = false; // correctness over cost: fall back to per-commit
      noteSink(`runs-listing-degraded:per-commit:${e && e.message ? e.message : String(e)}`);
    }
  };

  const runsForSha = (sha) => {
    loadRunsBySha();
    if (runsBySha instanceof Map) return runsBySha.get(sha) || [];
    return runsForShaViaGh(sha);
  };

  // One walked sha -> one candidate, lazily and never throwing. attestsTried
  // counts the plan downloads paid for this sha; resolveBaseline's
  // GREEN_ATTEST_BUDGET consumes it.
  const candidateFor = (sha) => {
    let runs = [];
    try {
      runs = runsForSha(sha);
    } catch {
      return { sha, conclusion: null, plan: null, attestsTried: 0 };
    }
    const done = (runs || []).filter((r) => r && r.status === 'completed');
    if (done.length === 0) return { sha, conclusion: null, plan: null, attestsTried: 0 };
    // ONE sha can carry SEVERAL green runs of the same workflow: the
    // pull_request run and the push run for the same commit are distinct
    // runs, and only the pull_request one uploads a ci-skip-plan. Picking
    // a single green run and asking it for a plan therefore lost the
    // baseline whenever the wrong one happened to sort first, and reported
    // 'no-skip-plan' for a commit that had a perfectly good plan.
    const greens = done.filter((r) => r.conclusion === 'success');
    let attestsTried = 0;
    for (const g of greens) {
      attestsTried += 1;
      const plan = readAttestedPlanForRun(g.databaseId, sha);
      if (plan) return { sha, conclusion: 'success', runId: g.databaseId, plan, attestsTried };
    }
    if (greens.length > 0) {
      return { sha, conclusion: 'success', runId: greens[0].databaseId, plan: null, attestsTried };
    }
    // No green run at all: report the red one and download nothing. A run
    // that failed cannot be a baseline whatever its plan says, so paying
    // for the artifact would buy an answer nobody reads.
    return { sha, conclusion: done[0].conclusion, runId: done[0].databaseId, plan: null, attestsTried: 0 };
  };

  return {
    setNoteSink: (fn) => {
      noteSink = typeof fn === 'function' ? fn : () => {};
    },

    isShallow: () => git('rev-parse', '--is-shallow-repository').trim() === 'true',

    firstParent: (sha) => git('rev-parse', `${sha}^1`).trim(),

    // `git diff-tree -r --raw` rather than --name-only: renames carry both
    // sides and parseLine unions them (case 20), which --name-only cannot say.
    diffPaths: (from, to) =>
      parseFileList(git('diff-tree', '-r', '--raw', '--no-commit-id', from, to)),

    // The fenced sha walk (candidate C). `^fence` scopes the domain to the
    // commits this PR owns; the valve only guards against a wrong fence.
    // `truncated` is conservative: a branch exactly valve-long reads as
    // truncated, which costs a pinned walk-valve reason instead of a wrong
    // merge-base-reached one.
    walkShas: (head, { fence, valve }) => {
      const args = ['rev-list', '--first-parent', `--max-count=${Number(valve) + 1}`, head];
      if (fence) args.push(`^${fence}`);
      const shas = git(...args)
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
        .filter((s) => s !== head); // head is not its own baseline
      return { shas, truncated: shas.length >= Number(valve) };
    },

    candidateFor,

    // Legacy eager walk, unchanged: per-commit lookups with inline
    // attestation. resolveBaseline no longer calls it when walkShas is
    // available, but the contract stays for injected-io consumers.
    listCandidates: (head, limit) => {
      const shas = git('rev-list', '--first-parent', `--max-count=${Number(limit) + 1}`, head)
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
        .filter((s) => s !== head);
      return shas.map((sha) => {
        const c = candidateFor(sha);
        delete c.attestsTried;
        return c;
      });
    },
  };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function usage() {
  return [
    'usage: scope-engine.cjs --classify [--files <path>]',
    '       scope-engine.cjs --resolve-baseline --head <sha> [--merge-sha <sha>]',
    '                        [--repo <owner/name>] [--branch <head-branch>]',
    '                        [--limit <valve>] [--workflow <name>]',
    '',
    '--classify reads a newline-delimited changed-file list from --files or',
    'stdin and prints the plan JSON. It performs no I/O beyond that read.',
    '',
    '--resolve-baseline finds the newest ancestor of --head whose run was green,',
    'ran a full suite and whose skip-plan reconciles against the per-job outcomes',
    'that run actually produced (verified here, at read time), then classifies the NET',
    'delta from there. It needs git and gh. Every failure mode resolves to full',
    'CI with a stated reason; it never resolves to a smaller run on bad input.',
  ].join('\n');
}

function main(argv) {
  const args = argv.slice(2);
  let mode = null;
  let filesPath = null;
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--classify') mode = 'classify';
    else if (args[i] === '--resolve-baseline') mode = 'resolve-baseline';
    else if (args[i] === '--files') filesPath = args[++i];
    else if (args[i] === '--head') opts.head = args[++i];
    else if (args[i] === '--merge-sha') opts.mergeSha = args[++i];
    else if (args[i] === '--repo') opts.repo = args[++i];
    else if (args[i] === '--branch') opts.branch = args[++i];
    else if (args[i] === '--workflow') opts.workflow = args[++i];
    else if (args[i] === '--limit') opts.limit = Number(args[++i]);
    else {
      process.stderr.write(`scope-engine: unknown argument '${args[i]}'\n${usage()}\n`);
      return 2;
    }
  }
  if (mode === null) {
    process.stderr.write(`scope-engine: no mode given\n${usage()}\n`);
    return 2;
  }

  if (mode === 'resolve-baseline') {
    const repoRoot = path.resolve(__dirname, '../../..');
    // A missing --repo is a CALLER bug, not a CI condition, so it is a usage
    // error rather than a fail-open-to-full: silently running full CI forever
    // because a flag was misspelled is exactly the D9 failure shape.
    if (!opts.repo) {
      process.stderr.write(`scope-engine: --resolve-baseline needs --repo\n${usage()}\n`);
      return 2;
    }
    // The branch powers the one-shot run listing (candidate C's cost model).
    // GITHUB_HEAD_REF is the PR head branch on pull_request-family events, so
    // existing callers (scope-shadow.sh) get the cheap path with no flag; when
    // neither is present the io degrades to per-commit lookups, which is a
    // cost regression only, never a correctness one.
    const io = createRepoIo({
      repoRoot,
      repo: opts.repo,
      branch: opts.branch || process.env.GITHUB_HEAD_REF || null,
      ...(opts.workflow ? { workflow: opts.workflow } : {}),
    });
    const result = resolveBaseline(
      {
        head: opts.head,
        mergeSha: opts.mergeSha,
        limit: Number.isFinite(opts.limit) ? opts.limit : DEFAULT_CANDIDATE_LIMIT,
        workflowClosure: computeWorkflowClosure(repoRoot),
      },
      io,
    );
    process.stdout.write(
      `${JSON.stringify(
        {
          ...result.plan,
          baseline: result.baseline
            ? { sha: result.baseline.sha, run_id: result.baseline.runId || null }
            : null,
          baseline_trail: result.trail,
          baseline_notes: result.notes,
        },
        null,
        2,
      )}\n`,
    );
    return 0;
  }
  if (filesPath === null || filesPath === undefined) {
    // No --files: stdin. fd 0 read synchronously, same as every gate script.
    filesPath = 0;
  }

  let text;
  try {
    text = fs.readFileSync(filesPath, 'utf8');
  } catch (e) {
    process.stderr.write(`scope-engine: cannot read file list: ${e.message}\n`);
    return 2;
  }

  const repoRoot = path.resolve(__dirname, '../../..');
  const workflowClosure = computeWorkflowClosure(repoRoot);
  const paths = parseFileList(text);
  const plan = scopeMap.buildPlan(scopeMap.classify(paths, { workflowClosure }));
  process.stdout.write(`${JSON.stringify(plan, null, 2)}\n`);
  return 0;
}

if (require.main === module) {
  process.exit(main(process.argv));
}

module.exports = {
  unquoteCPath,
  parseFileList,
  computeWorkflowClosure,
  evaluateBaselineCandidate,
  attestPlan,
  parseJsonStream,
  isBaseUnchanged,
  selectBaseline,
  decideBaseMove,
  forcedFullPlan,
  resolveBaseline,
  createRepoIo,
  DIFF_FILE_CAP,
  DEFAULT_CANDIDATE_LIMIT,
  GREEN_ATTEST_BUDGET,
  RUNS_LIST_MAX_PAGES,
  classify: scopeMap.classify,
  buildPlan: scopeMap.buildPlan,
  main,
};
