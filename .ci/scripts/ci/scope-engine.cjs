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
// CLI
// ---------------------------------------------------------------------------

function usage() {
  return [
    'usage: scope-engine.cjs --classify [--files <path>]',
    '',
    '--classify is the only wired mode in this chunk. It reads a newline-',
    'delimited changed-file list from --files or stdin and prints the plan',
    'JSON. Baseline resolution is exported for unit tests only and gets its',
    'own mode (with gh/git access) in a later chunk.',
  ].join('\n');
}

function main(argv) {
  const args = argv.slice(2);
  let mode = null;
  let filesPath = null;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--classify') mode = 'classify';
    else if (args[i] === '--files') filesPath = args[++i];
    else {
      process.stderr.write(`scope-engine: unknown argument '${args[i]}'\n${usage()}\n`);
      return 2;
    }
  }
  if (mode !== 'classify') {
    process.stderr.write(`scope-engine: no mode given\n${usage()}\n`);
    return 2;
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
  classify: scopeMap.classify,
  buildPlan: scopeMap.buildPlan,
  main,
};
