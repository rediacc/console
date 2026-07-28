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
    return { usable: false, reason: 'unreconciled-outcome' };
  }
  return { usable: true, reason: 'full-green-attested' };
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
// Like --classify, this mode lands INERT. Nothing in CI produces an attested
// skip-plan artifact yet, so every candidate today resolves to 'no-skip-plan'
// and the answer is full CI with that reason. It cannot change CI behaviour
// until the attestation side is wired, which is deliberate: it means this can
// be landed and observed before it is trusted.
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

// How many ancestors to interrogate before giving up. Each candidate costs at
// least one API round trip, and the headline case is satisfied by the FIRST
// candidate (the commit immediately before this push), so a small number is
// right: a deep walk mostly buys latency on branches that were never going to
// find a green full baseline anyway.
const DEFAULT_CANDIDATE_LIMIT = 5;

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

  let candidates;
  try {
    candidates = io.listCandidates(head, limit);
  } catch (e) {
    return fail(`baseline:candidate-walk-failed:${msg(e)}`);
  }
  if (!candidates || candidates.length === 0) return fail('baseline:no-candidates');

  const { baseline, trail } = selectBaseline(candidates);
  if (!baseline) return fail('baseline:none-usable', null, trail);

  let mergeParentSha = null;
  if (mergeSha) {
    try {
      mergeParentSha = io.firstParent(mergeSha);
    } catch (e) {
      notes.push(`merge-parent-unreadable:${msg(e)}`);
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

function createRepoIo({ repoRoot, repo, workflow = 'Console CI', artifactName = 'ci-skip-plan', run = defaultRun }) {
  const git = (...args) => run('git', ['-C', repoRoot, ...args]);
  const gh = (...args) => run('gh', args);

  const readPlanForRun = (runId) => {
    const os = require('os');
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'scope-plan-'));
    try {
      gh('run', 'download', String(runId), '--repo', repo, '-n', artifactName, '-D', dir);
    } catch {
      // Absent or expired reads exactly like never-attested (case 3), which is
      // the correct conflation: neither can prove what that run executed.
      return null;
    }
    const candidatePaths = ['plan.json', 'skip-plan.json'].map((f) => path.join(dir, f));
    for (const p of candidatePaths) {
      try {
        return JSON.parse(fs.readFileSync(p, 'utf8'));
      } catch {
        continue;
      }
    }
    return null;
  };

  return {
    isShallow: () => git('rev-parse', '--is-shallow-repository').trim() === 'true',

    firstParent: (sha) => git('rev-parse', `${sha}^1`).trim(),

    // `git diff-tree -r --raw` rather than --name-only: renames carry both
    // sides and parseLine unions them (case 20), which --name-only cannot say.
    diffPaths: (from, to) =>
      parseFileList(git('diff-tree', '-r', '--raw', '--no-commit-id', from, to)),

    listCandidates: (head, limit) => {
      const shas = git('rev-list', '--first-parent', `--max-count=${Number(limit) + 1}`, head)
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
        .filter((s) => s !== head); // head is not its own baseline
      return shas.map((sha) => {
        let runs = [];
        try {
          runs = JSON.parse(
            gh('run', 'list', '--repo', repo, '--workflow', workflow, '--commit', sha,
              '--json', 'databaseId,conclusion,status', '-L', '5'),
          );
        } catch {
          return { sha, conclusion: null, plan: null };
        }
        const done = runs.filter((r) => r.status === 'completed');
        if (done.length === 0) return { sha, conclusion: null, plan: null };
        const green = done.find((r) => r.conclusion === 'success') || done[0];
        return {
          sha,
          conclusion: green.conclusion,
          runId: green.databaseId,
          plan: green.conclusion === 'success' ? readPlanForRun(green.databaseId) : null,
        };
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
    '                        [--repo <owner/name>] [--limit <n>] [--workflow <name>]',
    '',
    '--classify reads a newline-delimited changed-file list from --files or',
    'stdin and prints the plan JSON. It performs no I/O beyond that read.',
    '',
    '--resolve-baseline finds the newest ancestor of --head whose run was green,',
    'ran a full suite and left a reconciled skip-plan, then classifies the NET',
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
    const io = createRepoIo({
      repoRoot,
      repo: opts.repo,
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
  isBaseUnchanged,
  selectBaseline,
  decideBaseMove,
  forcedFullPlan,
  resolveBaseline,
  createRepoIo,
  DIFF_FILE_CAP,
  DEFAULT_CANDIDATE_LIMIT,
  classify: scopeMap.classify,
  buildPlan: scopeMap.buildPlan,
  main,
};
