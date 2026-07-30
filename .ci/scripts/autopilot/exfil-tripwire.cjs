#!/usr/bin/env node
// The exfiltration bound for an autopilot round (03-v2-autonomy.md section 6).
//
// THE THREAT: private submodule source is checked out on the runner, console
// is public, and a code-writing model can encode private bytes into a staged
// file on the public branch. That channel is inherent to the design, so it is
// BOUNDED rather than wished away:
//   rule 1  added bytes OUTSIDE the round's implicated paths > 32 KB trips.
//   rule 2  any single NEW file adding > 8 KB trips REGARDLESS of prefix.
//   rule 3  total diff > 256 KB trips.
// On a trip: no commit, no push, escalate. The tripped diff is NEVER uploaded
// as an artifact: console artifacts are publicly downloadable, so uploading
// the very diff suspected of exfiltration would complete the exfiltration.
// This tool therefore prints byte counts and paths only, never diff content.
//
// THE IMPLICATED SET, three hops, first two reused from the scope engine:
//   hop 1  failed job display name -> plan key: EXPECTED_JOB_NAMES +
//          matchJobName from ../ci/skip-plan-reconcile.cjs (imported).
//   hop 2  plan key -> modules: JOB_SURFACES from ../ci/scope-map.cjs.
//   hop 3  module -> path prefixes: scope-map's RULES matchers are opaque
//          closures, so path->module CANNOT be inverted. MODULE_PREFIXES
//          below is a small declarative mirror in the module->path direction,
//          drift-checked by test-autopilot-harness.sh against the exported
//          classify() as an oracle (every (module, prefix) pair must classify
//          back to that module, and every JOB_SURFACES module must have at
//          least one prefix here).
// A failed job that maps to NO plan key (a quality lane, a build job)
// contributes nothing to the implicated set; with an empty set every added
// byte is out-of-scope, which fails in the tighter direction on purpose.
//
// Usage:
//   exfil-tripwire.cjs --diff <unified-diff-file> [--failed-jobs <file>]
//     --failed-jobs: one failed job display name per line.
// Exit: 0 quiet, 1 tripped (reasons on stderr), 2 usage error.

'use strict';

const fs = require('fs');
const path = require('path');

const { EXPECTED_JOB_NAMES, matchJobName } = require(path.join(__dirname, '..', 'ci', 'skip-plan-reconcile.cjs'));
const { JOB_SURFACES } = require(path.join(__dirname, '..', 'ci', 'scope-map.cjs'));

const OUT_OF_SCOPE_BYTES_MAX = 32 * 1024;
const NEW_FILE_BYTES_MAX = 8 * 1024;
const TOTAL_DIFF_BYTES_MAX = 256 * 1024;

// Hop 3: module -> path prefixes, the declarative mirror described above.
// Every module named by any JOB_SURFACES entry must appear here.
const MODULE_PREFIXES = {
  cli: ['packages/cli/'],
  shared: ['packages/shared/'],
  www: ['packages/www/'],
  provisioning: ['packages/provisioning/'],
  e2e: ['packages/e2e-tests/'],
  json: ['packages/json/'],
  workers: ['workers/'],
  tutorials: ['.ci/tutorials/'],
  renet: ['private/renet/'],
  account: ['private/account/'],
  elite: ['private/elite/'],
  'homebrew-tap': ['private/homebrew-tap/'],
};

// failed job display names -> the set of path prefixes their fix may touch.
function implicatedPrefixes(failedJobNames) {
  const prefixes = new Set();
  for (const jobName of failedJobNames) {
    for (const [key, expectedNames] of Object.entries(EXPECTED_JOB_NAMES)) {
      if (!expectedNames.some((e) => matchJobName(jobName, e))) continue;
      for (const mod of JOB_SURFACES[key] || []) {
        for (const p of MODULE_PREFIXES[mod] || []) prefixes.add(p);
      }
    }
  }
  return prefixes;
}

// Parse a unified git diff into per-file { addedBytes, isNew, isBinary }.
// Only '+' payload lines are counted; headers ('+++') are not additions.
function parseDiff(diffText) {
  const files = new Map();
  let current = null;
  const ensure = (p) => {
    if (!files.has(p)) files.set(p, { addedBytes: 0, isNew: false, isBinary: false });
    return files.get(p);
  };
  const unquote = (p) => (p.startsWith('"') && p.endsWith('"') ? JSON.parse(p) : p);
  for (const line of diffText.split('\n')) {
    if (line.startsWith('diff --git ')) {
      // `diff --git a/<p> b/<p>`; the b-side names the post-image.
      const m = line.match(/ b\/(.*)$/);
      current = m ? ensure(unquote(m[1])) : null;
      continue;
    }
    if (line.startsWith('new file mode') && current) {
      current.isNew = true;
      continue;
    }
    if (line.startsWith('+++ b/')) {
      current = ensure(unquote(line.slice(6)));
      continue;
    }
    // A binary payload cannot be measured line-wise; fail closed (rule below).
    if ((line.startsWith('Binary files ') || line === 'GIT binary patch') && current) {
      current.isBinary = true;
      continue;
    }
    if (line.startsWith('+') && !line.startsWith('+++') && current) {
      current.addedBytes += Buffer.byteLength(line, 'utf8') - 1;
    }
  }
  return files;
}

// evaluate(files, totalBytes, prefixes) -> { tripped: [...], summary }
function evaluate(files, totalBytes, prefixes) {
  const tripped = [];
  let outOfScopeBytes = 0;
  const outOfScopePaths = [];
  for (const [p, info] of files) {
    if (info.isBinary) {
      tripped.push(`binary-unmeasurable: '${p}' carries a binary payload whose added bytes cannot be bounded`);
      continue;
    }
    if (info.isNew && info.addedBytes > NEW_FILE_BYTES_MAX) {
      tripped.push(`new-file-over-8kb: '${p}' is a new file adding ${info.addedBytes} bytes (cap ${NEW_FILE_BYTES_MAX}, applies regardless of prefix)`);
    }
    const inScope = [...prefixes].some((pre) => p.startsWith(pre));
    if (!inScope) {
      outOfScopeBytes += info.addedBytes;
      outOfScopePaths.push(p);
    }
  }
  if (outOfScopeBytes > OUT_OF_SCOPE_BYTES_MAX) {
    tripped.push(
      `out-of-scope-bytes: ${outOfScopeBytes} added bytes outside the implicated prefixes ` +
        `(cap ${OUT_OF_SCOPE_BYTES_MAX}) across: ${outOfScopePaths.join(', ')}`
    );
  }
  if (totalBytes > TOTAL_DIFF_BYTES_MAX) {
    tripped.push(`total-diff-over-256kb: ${totalBytes} bytes total (cap ${TOTAL_DIFF_BYTES_MAX})`);
  }
  return { tripped, outOfScopeBytes, fileCount: files.size };
}

function main(argv) {
  const args = argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--diff') opts.diff = args[++i];
    else if (args[i] === '--failed-jobs') opts.failedJobs = args[++i];
    else {
      process.stderr.write(`exfil-tripwire: unknown argument '${args[i]}'\n`);
      return 2;
    }
  }
  if (!opts.diff) {
    process.stderr.write('usage: exfil-tripwire.cjs --diff <file> [--failed-jobs <file>]\n');
    return 2;
  }
  let diffBuf;
  try {
    diffBuf = fs.readFileSync(opts.diff);
  } catch (e) {
    // A missing diff is unusable evidence, and the tripwire fails closed.
    process.stderr.write(`TRIPWIRE: diff-missing: cannot read '${opts.diff}': ${e.message}\n`);
    return 1;
  }
  let failedJobNames = [];
  if (opts.failedJobs) {
    try {
      failedJobNames = fs
        .readFileSync(opts.failedJobs, 'utf8')
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean);
    } catch (e) {
      process.stderr.write(`TRIPWIRE: failed-jobs-unreadable: ${e.message}\n`);
      return 1;
    }
  }

  const prefixes = implicatedPrefixes(failedJobNames);
  const files = parseDiff(diffBuf.toString('utf8'));
  const { tripped, outOfScopeBytes, fileCount } = evaluate(files, diffBuf.length, prefixes);

  if (tripped.length > 0) {
    for (const t of tripped) process.stderr.write(`TRIPWIRE: ${t}\n`);
    process.stderr.write(
      'exfil-tripwire TRIPPED: no commit, no push; escalate with these byte counts and paths only.\n' +
        'Do NOT upload the diff as an artifact: console artifacts are public, and uploading the\n' +
        'suspected diff would complete the exfiltration it exists to stop.\n'
    );
    return 1;
  }
  process.stdout.write(
    `exfil-tripwire quiet: ${fileCount} file(s), ${diffBuf.length} diff bytes, ` +
      `${outOfScopeBytes} out-of-scope added bytes, ${prefixes.size} implicated prefix(es).\n`
  );
  return 0;
}

if (require.main === module) {
  process.exit(main(process.argv));
}

module.exports = {
  MODULE_PREFIXES,
  implicatedPrefixes,
  parseDiff,
  evaluate,
  main,
  OUT_OF_SCOPE_BYTES_MAX,
  NEW_FILE_BYTES_MAX,
  TOTAL_DIFF_BYTES_MAX,
};
