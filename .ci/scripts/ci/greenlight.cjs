#!/usr/bin/env node
// CROSS-PR GREENLIGHT: skip test-renet / account E2E when the exact inputs
// they consume were already executed green by some OTHER run, on ANY branch.
//
// The scope engine answers a narrower question. It skips a job when the delta
// against a LINEAGE-LOCAL baseline does not touch that job's surface, so a PR
// that rebases, or a second PR bumping the same submodule pointer, pays for
// the same 90-minute renet suite again. This engine answers the wider one:
// has this exact input closure ever been green anywhere.
//
// THE ONE HARD RULE: NO STORED MEMO. scope-engine.cjs:177 states the doctrine
// ("NOBODY WRITES `reconciled`, the READER derives it... SELF-DECLARATION IS
// DELETED, NOT BLACKLISTED"): a run that writes its own trust token mints a
// claim later readers cannot check, and a durable memo store would need write
// powers inside a PR-triggered job whose code comes from the PR itself, which
// is the exact bypass .github/actions/app-token/action.yml:13-34 exists to
// remove. So nothing is written. The greenlight is DERIVED FRESH at Initialize
// time from facts nobody had to be trusted to record:
//
//   - the per-JOB conclusion from the Actions API. Run-level "CI Complete"
//     cannot serve here: assert-ci-complete.sh puts TESTS in SOFT_REQUIRED
//     where `skipped` passes identically to `success`, so a green check cannot
//     distinguish an executed job from a scope-skipped one. The job object
//     can, and that difference is the whole evidence base.
//   - the candidate's submodule gitlink, read from
//     GET /repos/{repo}/contents/<path>?ref=<head_sha>, which returns
//     type "submodule" and its sha. Derived from the commit, not from
//     anything the candidate run said about itself.
//   - the candidate's console-side closure, read the same way.
//
// INTENT IS NOT OUTCOME. A candidate that was itself a REDUCED run is a
// perfectly good witness, because rule 1 asks whether the job RAN, not what
// the plan intended. A skipped job is refused precisely so evidence cannot
// chain across runs that skipped their way to green.
//
// FAIL-OPEN IS THE CONTRACT, identical to scope-shadow.sh:9-19. This engine
// may only ever cause a job to be SKIPPED that would otherwise RUN; it has no
// path that turns a skip back into a run, because it emits `run_<key>=false`
// and nothing else. Any error, any timeout, any absence of a match yields no
// emit line at all, which changes nothing, which is a full round.
//
// Usage:
//   greenlight.cjs --key renet [--key account_e2e] [--repo owner/name]
//                  [--limit N] [--budget SECONDS] [--debug]
//
// On stdout, ONLY on a greenlight, one pair of lines per greenlit key:
//   run_<key>=false
//   evidence_<key>=<candidate-run-id>
// Everything else (the candidate table, every refusal reason) goes to stderr,
// so a caller reads stdout as instructions and never has to parse prose.
// Exit status is 0 on every path including failure: like scope-shadow.sh, this
// decides what runs and must never be the thing that fails.

'use strict';

const crypto = require('crypto');

// ---------------------------------------------------------------------------
// THE CLOSURE TABLE. Hand-derived from .github/workflows/ct-tests.yml by
// walking each job's steps and one level into every script it invokes, then
// re-verified against the live tree. A path here is either a file (blob sha)
// or a directory (tree sha); both come back from the same contents listing.
//
// OVER-INCLUSION IS SAFE AND UNDER-INCLUSION IS NOT. Every extra path can only
// make a greenlight rarer (more full rounds); a missing one would let a PR
// that edits a real input inherit somebody else's green. When in doubt the
// path is listed.
// ---------------------------------------------------------------------------
const CLOSURES = {
  // ct-tests.yml:1404 `test-renet`, gate at :1406
  // `inputs.full_suite == 'true' && inputs.run_renet != 'false'`.
  renet: {
    // The API job name is the CALLER's job name plus the callee's, joined by
    // " / ": a live run shows "Tests + Infra / Renet". Matching is on the last
    // segment, which is the only part ct-tests.yml controls. Exactness matters
    // here: the same run also carries "Build (Renet) / Renet (cached)" and
    // "Build (Docker Fast) / Renet Docker", and a prefix or substring match
    // would accept either as evidence for a suite neither of them runs.
    jobName: 'Renet',
    submodule: 'private/renet',
    // Steps at ct-tests.yml:1455 / :1483 / :1489 / :1495 / :1499, plus the two
    // libraries they source: run-renet.sh:12 pulls in lib/common.sh, and
    // renet's own private/renet/.ci/scripts/test/run-tests.sh:15-26 sources
    // the CONSOLE-side infra/ci-env.sh, which is why this job is not
    // submodule-only however much it looks like it.
    paths: [
      '.ci/scripts/private/run-renet.sh',
      '.ci/scripts/private/renet-ebpf-e2e.sh',
      '.ci/scripts/private/renet-root-tests.sh',
      '.ci/scripts/private/renet-csi-sanity.sh',
      '.ci/scripts/private/renet-integration.sh',
      '.ci/scripts/lib/common.sh',
      '.ci/scripts/infra/ci-env.sh',
      // The whole workflow file, not the single job block. Hashing one block
      // means tracking its line range, and the range moves whenever anything
      // above it grows. Over-invalidating on unrelated ct-tests edits is the
      // accepted cost of a key that cannot silently drift off its subject.
      '.github/workflows/ct-tests.yml',
    ],
  },
  // ct-tests.yml:1575 `test-account-e2e`, gate at :1577.
  account_e2e: {
    // Live run shows "Tests + Infra / Account E2E".
    jobName: 'Account E2E',
    submodule: 'private/account',
    // Steps at ct-tests.yml:1592 (setup-workspace with account: 'true'),
    // :1595 (`npm run build:packages`) and :1605 (run-account-e2e.sh).
    //
    // NOT in this list, and the absence is derived rather than overlooked:
    // .ci/scripts/setup/build-packages.sh. setup-workspace only runs it when
    // its `build-packages` input is 'true' (action.yml:91-93) and this job
    // leaves that input unset, calling `npm run build:packages` directly
    // instead. The script is therefore not an input to this job.
    paths: [
      '.ci/scripts/test/run-account-e2e.sh',
      // run-account-e2e.sh:27 sources it.
      '.ci/scripts/lib/common.sh',
      // The cache-miss install path, action.yml:77 and :81.
      '.ci/scripts/setup/install-deps.sh',
      '.github/actions/setup-workspace',
      // Both jobs mint a submodule-capable token through it before checkout.
      '.github/actions/app-token',
      // package.json defines build:packages (package.json:21); the lockfile is
      // what `npm ci` resolves and what keys the node_modules cache.
      'package.json',
      'package-lock.json',
      // scope-map.cjs:231 declares the surface as ['account', 'shared'], the
      // console half of it being packages/shared, wired in by the `file:`
      // dependency at private/account/package.json. provisioning rides along
      // because build:packages builds it in the same step, so a break there
      // fails this job too.
      'packages/shared',
      'packages/provisioning',
      '.github/workflows/ct-tests.yml',
    ],
  },
};

// ---------------------------------------------------------------------------
// PURE CORE. No network, no git, no clock. Everything below the io line feeds
// this; the unit gate (.ci/scripts/test/gates/test-greenlight.sh) drives it
// directly with fixtures.
// ---------------------------------------------------------------------------

// The leaf of a reusable-workflow job name. See CLOSURES.renet.jobName.
function jobLeafName(name) {
  const parts = String(name == null ? '' : name).split(' / ');
  return parts[parts.length - 1].trim();
}

// Resolve a candidate field that may be a value or a zero-argument function.
// The function form is what makes cheap-first ordering real rather than
// stylistic, exactly as in scope-engine.cjs's attestPlan: a candidate refused
// on its job conclusion never pays for the gitlink call, and one refused on
// its gitlink never pays for the closure listing, which is the expensive one.
function pull(field) {
  return typeof field === 'function' ? field() : field;
}

function errText(e) {
  return e && e.message ? e.message : String(e);
}

// One candidate, one verdict. NEVER throws: a throw from any lazy fetch
// becomes a named refusal, because an unreadable candidate and an unusable one
// have the same consequence (no greenlight from this candidate) and only the
// reason string should differ.
function evaluateCandidate(candidate, { jobName, wantSubmoduleSha, wantClosureHash }) {
  if (!candidate || typeof candidate !== 'object') {
    return { usable: false, reason: 'no-candidate' };
  }

  // Rule 1: the job RAN and SUCCEEDED. This is the rule that stops evidence
  // chaining across reduced runs, so it is checked first and refuses loudest.
  let jobs;
  try {
    jobs = pull(candidate.jobs);
  } catch (e) {
    return { usable: false, reason: `jobs-unreadable:${errText(e)}` };
  }
  if (!Array.isArray(jobs)) {
    return { usable: false, reason: 'jobs-unreadable:not-a-list' };
  }
  const matches = jobs.filter((j) => j && jobLeafName(j.name) === jobName);
  if (matches.length === 0) {
    return { usable: false, reason: 'job-not-run' };
  }
  if (matches.length > 1) {
    // Two jobs answering to one name means the name no longer identifies the
    // suite, so no reading of it is evidence. Refusing costs a full round;
    // guessing would spend somebody else's green on an unknown job.
    return { usable: false, reason: 'job-ambiguous' };
  }
  const conclusion = matches[0].conclusion;
  if (conclusion === 'skipped') {
    // The intent-versus-outcome case. A scope-skipped job reports exactly this
    // and is indistinguishable from a green one at run level, which is why
    // greenlight evidence is always the job conclusion.
    return { usable: false, reason: 'job-not-run' };
  }
  if (conclusion !== 'success') {
    return { usable: false, reason: `job-failed:${conclusion == null ? 'null' : conclusion}` };
  }

  // Rule 2: the submodule pointer is the same commit.
  let gitlink;
  try {
    gitlink = pull(candidate.gitlink);
  } catch (e) {
    return { usable: false, reason: `gitlink-unreadable:${errText(e)}` };
  }
  if (!gitlink || gitlink !== wantSubmoduleSha) {
    return { usable: false, reason: 'pointer-differs' };
  }

  // Rule 3: the console-side inputs are byte-identical.
  let closureHash;
  try {
    closureHash = pull(candidate.closureHash);
  } catch (e) {
    return { usable: false, reason: `closure-unreadable:${errText(e)}` };
  }
  if (!closureHash || closureHash !== wantClosureHash) {
    return { usable: false, reason: 'closure-differs' };
  }

  return { usable: true, reason: 'job-green-same-inputs' };
}

// The whole decision for one key. Returns the first usable candidate; the
// caller orders candidates newest-first, so "first" means "most recent proof".
//
// `trail` records every candidate examined with its refusal reason. It is the
// only thing that makes a non-greenlight diagnosable: without it, "no match"
// and "the API returned nothing" read identically in the job log, which is the
// unreadable-instrument failure scope-shadow.sh:96-104 was written to fix.
function evaluateGreenlight({ key, wantSubmoduleSha, wantClosureHash, candidates }) {
  const trail = [];
  const closure = CLOSURES[key];
  if (!closure) {
    return { greenlit: false, reason: `unknown-key:${key}`, trail };
  }
  if (!wantSubmoduleSha) {
    return { greenlit: false, reason: 'no-local-gitlink', trail };
  }
  if (!wantClosureHash) {
    return { greenlit: false, reason: 'no-local-closure', trail };
  }
  const list = Array.isArray(candidates) ? candidates : [];
  if (list.length === 0) {
    return { greenlit: false, reason: 'no-candidates', trail };
  }
  for (const candidate of list) {
    const verdict = evaluateCandidate(candidate, {
      jobName: closure.jobName,
      wantSubmoduleSha,
      wantClosureHash,
    });
    trail.push({ run_id: candidate && candidate.runId, ...verdict });
    if (verdict.usable) {
      return { greenlit: true, runId: candidate.runId, reason: verdict.reason, trail };
    }
  }
  return { greenlit: false, reason: 'no-usable-candidate', trail };
}

// Hash a { path -> object-sha } map into one key. Sorted so the map's
// iteration order cannot change the answer, and NUL-delimited so no path can
// forge a different map's serialization by containing the delimiter.
function closureHashOf(shaByPath) {
  const h = crypto.createHash('sha256');
  for (const p of Object.keys(shaByPath).sort()) {
    h.update(p);
    h.update('\0');
    h.update(String(shaByPath[p]));
    h.update('\0');
  }
  return h.digest('hex');
}

// ---------------------------------------------------------------------------
// IO. git for the local side, gh for the candidate side.
// ---------------------------------------------------------------------------

function defaultRun(cmd, args, timeoutMs) {
  const { execFileSync } = require('child_process');
  return execFileSync(cmd, args, {
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    timeout: Math.max(1000, timeoutMs),
  });
}

// Concatenated JSON objects, one per --paginate page. Borrowed verbatim in
// spirit from scope-engine.cjs:554: JSON.parse on the raw stream works for a
// single page and throws the moment a run outgrows per_page, which is the
// shape a growing pipeline drifts into silently.
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

// The local half: what THIS checkout is asking to be greenlit for.
//
// It reads HEAD, which under a pull_request is the synthetic merge commit, and
// that is the correct subject: the merge commit's gitlink and closure are what
// the jobs would actually run against.
function createLocalReader({ repoRoot, run = defaultRun }) {
  const git = (...args) => run('git', ['-C', repoRoot, ...args], 15000);

  // `<mode> SP <type> SP <sha> TAB <path>`. Works uniformly for blobs, trees
  // and gitlinks, which is why the closure table can mix files and
  // directories without the caller caring which is which.
  const objectShaAt = (path) => {
    const line = git('ls-tree', 'HEAD', '--', path).split('\n')[0];
    if (!line) return null;
    const m = /^\d+ \w+ ([0-9a-f]{40})\t/.exec(line);
    return m ? m[1] : null;
  };

  return {
    gitlinkSha: (path) => objectShaAt(path),
    // Throws on a path the table declares but the tree does not have. That is
    // a STALE TABLE, not a missing greenlight, and it must be loud: silently
    // hashing an absent path as empty would keep matching other equally stale
    // candidates forever. test-greenlight.sh asserts every declared path
    // exists, so this throw is a backstop rather than the primary detector.
    closureHash: (paths) => {
      const shas = {};
      for (const p of paths) {
        const sha = objectShaAt(p);
        if (!sha) throw new Error(`closure path absent from HEAD: ${p}`);
        shas[p] = sha;
      }
      return closureHashOf(shas);
    },
  };
}

// The candidate half. Every method THROWS on anything unusable, and the throw
// is the interface: evaluateCandidate turns it into a named refusal. Returning
// a benign-looking empty value instead would read as positive evidence of
// absence, which is the one answer this must never fabricate.
function createCandidateReader({ repo, deadline, run = defaultRun }) {
  const remaining = () => deadline - Date.now();
  const gh = (...args) => {
    const left = remaining();
    if (left <= 0) throw new Error('budget exhausted');
    return run('gh', args, left);
  };

  // Caches are keyed by head_sha, not by run id: reruns and several PRs on one
  // commit share every content answer, and the same candidate is examined once
  // per key requested.
  const jobsCache = new Map();
  const contentsCache = new Map();

  const listRuns = (limit) => {
    const text = gh(
      'api',
      `repos/${repo}/actions/workflows/ci.yml/runs?status=completed&per_page=${limit}`
    );
    const pages = parseJsonStream(text);
    if (pages.length === 0) throw new Error('runs payload carried no JSON');
    return pages.flatMap((p) => (Array.isArray(p) ? p : (p && p.workflow_runs) || []));
  };

  const jobsFor = (runId) => {
    if (!jobsCache.has(runId)) {
      const text = gh('api', `repos/${repo}/actions/runs/${runId}/jobs?per_page=100`, '--paginate');
      const pages = parseJsonStream(text);
      if (pages.length === 0) throw new Error('jobs payload carried no JSON');
      jobsCache.set(
        runId,
        pages.flatMap((p) => (Array.isArray(p) ? p : (p && p.jobs) || []))
      );
    }
    return jobsCache.get(runId);
  };

  // One listing per PARENT directory rather than one call per path. The
  // listing carries an object sha for every entry whatever its type (file,
  // dir, submodule), so the eight-path renet closure costs four calls instead
  // of eight and packages/shared is answerable at all: a contents call on a
  // directory returns its entries, never its own tree sha.
  const listDir = (ref, dir) => {
    const cacheKey = `${ref}:${dir}`;
    if (!contentsCache.has(cacheKey)) {
      const suffix = dir ? `/${dir}` : '';
      const text = gh('api', `repos/${repo}/contents${suffix}?ref=${ref}`);
      const pages = parseJsonStream(text);
      const entries = pages.flatMap((p) => (Array.isArray(p) ? p : [p]));
      const byName = new Map();
      for (const e of entries) if (e && e.name) byName.set(e.name, e.sha);
      contentsCache.set(cacheKey, byName);
    }
    return contentsCache.get(cacheKey);
  };

  const shaAt = (ref, path) => {
    const idx = path.lastIndexOf('/');
    const dir = idx === -1 ? '' : path.slice(0, idx);
    const name = idx === -1 ? path : path.slice(idx + 1);
    const entry = listDir(ref, dir).get(name);
    // Absent is a legitimate answer, not an error: the candidate commit simply
    // did not carry that path, which makes its closure differ from ours.
    return entry || null;
  };

  return {
    listRuns,
    jobsFor,
    gitlinkAt: (ref, path) => shaAt(ref, path),
    closureHashAt: (ref, paths) => {
      const shas = {};
      for (const p of paths) shas[p] = shaAt(ref, p) || '';
      return closureHashOf(shas);
    },
    remaining,
  };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function usage() {
  return [
    'usage: greenlight.cjs --key <renet|account_e2e> [--key ...]',
    '                     [--repo owner/name] [--limit N] [--budget SECONDS] [--debug]',
    '',
    'Prints `run_<key>=false` and `evidence_<key>=<run-id>` on stdout for every',
    'key whose exact inputs were already executed green by another run.',
    'Prints nothing on stdout otherwise. Always exits 0.',
  ].join('\n');
}

function main(argv) {
  const keys = [];
  let repo = process.env.GITHUB_REPOSITORY || '';
  let limit = 25;
  let budgetSeconds = 60;
  let debug = false;
  const repoRoot = require('path').resolve(__dirname, '../../..');

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--key') keys.push(argv[++i]);
    else if (a === '--repo') repo = argv[++i];
    else if (a === '--limit') limit = Number(argv[++i]);
    else if (a === '--budget') budgetSeconds = Number(argv[++i]);
    else if (a === '--debug') debug = true;
    else if (a === '--help' || a === '-h') {
      process.stdout.write(`${usage()}\n`);
      return 0;
    } else {
      process.stderr.write(`greenlight: unknown argument ${a}\n${usage()}\n`);
      return 0;
    }
  }

  const note = (s) => process.stderr.write(`${s}\n`);

  if (keys.length === 0) {
    note('greenlight: no --key given, nothing to decide');
    return 0;
  }
  if (!repo) {
    note('greenlight: no --repo and no GITHUB_REPOSITORY, so no candidates are reachable');
    return 0;
  }
  for (const k of keys) {
    if (!CLOSURES[k]) {
      note(`greenlight: unknown key '${k}', refusing to decide anything`);
      return 0;
    }
  }

  // The budget covers the WHOLE invocation, all keys included, because it
  // exists to bound `initialize`, which every other job waits on. Overrunning
  // it stalls the pipeline; giving up early costs one full round.
  const deadline = Date.now() + Math.max(1, budgetSeconds) * 1000;
  const selfRunId = process.env.GITHUB_RUN_ID ? String(process.env.GITHUB_RUN_ID) : null;

  const local = createLocalReader({ repoRoot });
  const reader = createCandidateReader({ repo, deadline });

  let runs;
  try {
    runs = reader.listRuns(limit);
  } catch (e) {
    note(`greenlight: candidate listing failed (${errText(e)}), so nothing is greenlit`);
    return 0;
  }

  // Newest first is what the API already returns; the dedupe keeps that order
  // so the first usable candidate is the most recent proof.
  const seen = new Set();
  const runRows = [];
  for (const r of runs) {
    if (!r || !r.id || !r.head_sha) continue;
    if (selfRunId && String(r.id) === selfRunId) continue;
    if (seen.has(r.head_sha)) continue;
    seen.add(r.head_sha);
    runRows.push({ runId: r.id, headSha: r.head_sha });
  }

  if (debug) {
    note(`greenlight: repo=${repo} candidates=${runRows.length} budget=${budgetSeconds}s`);
  }

  const emit = [];
  for (const key of keys) {
    const closure = CLOSURES[key];

    let wantSubmoduleSha = null;
    let wantClosureHash = null;
    try {
      wantSubmoduleSha = local.gitlinkSha(closure.submodule);
      wantClosureHash = local.closureHash(closure.paths);
    } catch (e) {
      note(`greenlight[${key}]: local inputs unreadable (${errText(e)}), nothing is greenlit`);
      continue;
    }

    const candidates = runRows.map((row) => ({
      runId: row.runId,
      headSha: row.headSha,
      jobs: () => reader.jobsFor(row.runId),
      gitlink: () => reader.gitlinkAt(row.headSha, closure.submodule),
      closureHash: () => reader.closureHashAt(row.headSha, closure.paths),
    }));

    const verdict = evaluateGreenlight({ key, wantSubmoduleSha, wantClosureHash, candidates });

    if (debug) {
      note('');
      note(`greenlight[${key}] job='${closure.jobName}' ${closure.submodule}=${wantSubmoduleSha}`);
      note(`greenlight[${key}] closure=${wantClosureHash}`);
      note(`  ${'run id'.padEnd(13)} ${'head'.padEnd(9)} verdict`);
      for (let i = 0; i < verdict.trail.length; i++) {
        const t = verdict.trail[i];
        const head = (runRows[i] && runRows[i].headSha ? runRows[i].headSha : '').slice(0, 8);
        note(`  ${String(t.run_id).padEnd(13)} ${head.padEnd(9)} ${t.reason}`);
      }
      note(`greenlight[${key}] VERDICT: ${verdict.greenlit ? 'GREENLIT' : 'no'} (${verdict.reason})`);
    }

    if (verdict.greenlit) {
      // The ONLY thing this program ever puts on stdout, and the asymmetry is
      // the fail-open: `=false` is the single value that can shrink a round,
      // so it is the single value emitted. There is deliberately no `=true`
      // form to get wrong.
      emit.push(`run_${key}=false`);
      emit.push(`evidence_${key}=${verdict.runId}`);
      note(`greenlight[${key}]: GREENLIT by run ${verdict.runId}`);
    } else {
      note(`greenlight[${key}]: no greenlight (${verdict.reason})`);
    }
  }

  if (emit.length > 0) process.stdout.write(`${emit.join('\n')}\n`);
  return 0;
}

module.exports = {
  CLOSURES,
  closureHashOf,
  createCandidateReader,
  createLocalReader,
  evaluateCandidate,
  evaluateGreenlight,
  jobLeafName,
  parseJsonStream,
};

if (require.main === module) {
  // Nothing above may take the process down. A crash here would be a crash in
  // `initialize`, which every job needs, so an engine defect would stop the
  // pipeline rather than merely failing to shrink it.
  let code = 0;
  try {
    code = main(process.argv.slice(2));
  } catch (e) {
    process.stderr.write(`greenlight: unhandled ${errText(e)}, nothing is greenlit\n`);
    code = 0;
  }
  process.exit(code);
}
