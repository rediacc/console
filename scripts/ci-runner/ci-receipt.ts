#!/usr/bin/env tsx
/**
 * SIGNED CI RECEIPTS (agent/plans/PLAN-two-track-merge-dev.md D6, box R3): a container CI lane writes which of its gates PASSED at which inputHash, the workflow attests the file, and a local verb downloads, verifies and stores the verified ones as carry priors. A gate CI already judged green at the exact inputs a local run would hash then carries instead of re-running.
 *
 *   npx tsx scripts/ci-runner/ci-receipt.ts --selftest
 *   npx tsx scripts/ci-runner/ci-receipt.ts write --lane quality-content --out <file>   (in CI, last steps of the lane)
 *   npx tsx scripts/ci-runner/ci-receipt.ts fetch [--branch <b> ...] [--limit <n>]       (local)
 *   npx tsx scripts/ci-runner/ci-receipt.ts verify <file>                                 (local: the verifier on one file)
 *
 * WRITE. Inside the lane's container, after its gates, `computeGateHashes` runs for the lane's lock ids at the checked-out tree with the runner's own options (run.ts `incrementalPlan`), so a hash here equals the hash a local run in the same image computes. A gate is receipted only when its inputHash is non-null AND its step is known to have PASSED. A workflow step without an `id:` has no entry in the `steps` context, so the outcome is read from the job's own record instead: the writer reads `repos/<repo>/actions/jobs/<job.check_run_id>` through `gh api` on github.token (the lane holds `actions: read` for it) and takes each earlier step's conclusion by name. The receipt step runs under the standard guard, never `success()`, so no failed step can skip it, a drift step's included: the drift waiver reads a skipped step as passed, and test_release_nightly_drift_waiver.py holds every step after a drift step to `!cancelled()`. A failed or skipped gate is omitted and the rest of the lane is still receipted. A step whose record is missing, not yet completed, or whose name is not unique reads `unknown` and is omitted. The record is fetched by this job's own `check_run_id` and must name this run and attempt and show the receipt step itself in progress, or the writer exits 1, so a wrong id is refused by those checks (a same-run, same-attempt record of a sibling lane that shows its own receipt step in progress is not told apart by them, only by the id); a record it could not read at all is UNCHECKED and exits 1 too. That over-omits on purpose: a gate absent from a receipt only re-runs locally, while a gate present in error would carry a verdict nothing judged. ciOnly gates are left out too, since the local runner never judges them as ok.
 *
 * FETCH. Recent completed `ci.yml` runs on the named branches (default: the current branch and main) are listed through `gh`, each run's `ci-receipt-*` artifact is downloaded, and every file is verified with `gh attestation verify <file> --repo rediacc/console --signer-workflow rediacc/console/.github/workflows/ci-quality.yml --source-digest <sha>` before anything is written. A verified file is stored content-addressed as `.ci/cache/ci-receipts/<sha256>.json`, byte for byte, and a prior the runner reads is written beside the local archive as `.ci/cache/receipts/ci-<tree>.json`. An unverifiable file is never stored. A run whose download failed for any reason other than "no such artifact" is UNCHECKED, and any unchecked run, refused file, or a fetch that stored nothing exits 1.
 *
 * THE PRIOR, and why it needs no runner change. run.ts `loadPriorReceipts` reads every `*.json` under `.ci/cache/receipts/`, and `planCarry` keys the archive by each receipt's `headTree`. The prior names itself `ci-<tree>` there, so (a) it never collides with a local receipt for the same tree, (b) a gate carried from it records `carriedFrom.headTree: "ci-<tree>"`, which is exactly the file name the push guard reads back (block_unverified_push.py `_carried_refusal`, R4), and (c) the unchanged inputHash rule decides. Its `finishedAt` is empty, so it sorts after every local receipt: a local red at the same inputs outvotes a CI green, and the outcome ledger (`gate_ledger.receipt_rows`) and the scheduler replay (learned-selftest T7) both skip it, since neither a timing nor a local run is in it. The ledger takes the CI side from the stored receipt instead: `gate_ledger fold-ci` reads `.ci/cache/ci-receipts/<sha256>.json`, which still names its run, and keys each receipted gate of that job on its inputHash. Its gates are `ok` with findings `[]`, because only passes are receipted.
 *
 * THE VERIFIER SEAM. `Verifier` takes a file and the source digest it must have been built from and answers ok or the failing field. `ghAttestationVerifier` is the real one; the selftest passes stubs. The push guard runs the same command with the same `ATTESTATION_SPEC` (`CI_ATTESTATION_SPEC` there; its suite pins the two equal) on every carried entry whose origin is a CI prior, so a receipt edited after the fetch, or one signed by another workflow, is refused at the push and not only at the fetch.
 *
 * THREAT MODEL (D6). This protects against self-deception: a stale, edited or misattributed verdict. It does not protect against a malicious workflow on a branch, since a pull_request run executes the branch's own workflow file; this writer lives under scripts/ci-runner/**, which is in every inputHash through GLOBAL_INPUTS.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { WK_GH_REPO } from '@rediacc/shared/config/well-known.generated';
import { isEntryPoint } from '../lib/entry-point.js';
import { REPO_ROOT } from '../lib/repo-root.js';
import {
  computeGateHashes,
  exemptIdsOf,
  type GateHash,
  type LockEntry,
  type PriorGate,
  type PriorReceipt,
  planCarry,
  SCHEMA,
  saltHash,
  scriptsMapOf,
} from './input-hash.js';
import { leafClosure } from './quick-select.js';

export const CI_RECEIPT_SCHEMA = 1;
/** Who may have signed a receipt. The push guard holds the same two strings as `CI_ATTESTATION_SPEC`. */
export const ATTESTATION_SPEC = {
  repo: WK_GH_REPO,
  signerWorkflow: `${WK_GH_REPO}/.github/workflows/ci-quality.yml`,
} as const;
export const QUALITY_WORKFLOW = '.github/workflows/ci-quality.yml';
/** The run list fetch reads: ci-quality.yml is a reusable workflow, so its artifacts belong to the calling ci.yml run. */
export const CALLER_WORKFLOW = 'ci.yml';
export const RECEIPT_STEP = 'Write CI receipt';
export const ARTIFACT_PREFIX = 'ci-receipt-';
/** The one job in QUALITY_WORKFLOW allowed to hold id-token or attestations at write: it checks out nothing, attests the unsigned receipt and uploads it under ARTIFACT_PREFIX. */
export const SIGNER_JOB = 'quality-content-receipt';
/** What quality-content uploads before signing. Deliberately outside ARTIFACT_PREFIX, so fetch never downloads an unattested file. */
export const UNSIGNED_ARTIFACT = 'unsigned-receipt-quality-content';
const SIGNING_PERMISSIONS = new Set(['id-token', 'attestations']);
const byCodeUnit = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);
export const CI_PRIOR_PREFIX = 'ci-';
export const RAW_DIR_REL = path.join('.ci', 'cache', 'ci-receipts');
export const PRIOR_DIR_REL = path.join('.ci', 'cache', 'receipts');
const STANDARD_GUARDS = new Set([
  "${{ !cancelled() && steps.setup.outcome == 'success' }}",
  "!cancelled() && steps.setup.outcome == 'success'",
]);
const SHA_RE = /^[0-9a-f]{40}$/;
const TREE_RE = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/;

export interface CiReceiptGate {
  inputHash: string;
  verdict: 'pass';
}

export interface CiReceipt {
  schema: number;
  repo: string;
  run: { id: string; attempt: string };
  lane: string;
  sha: string;
  tree: string;
  salt: string;
  gates: Record<string, CiReceiptGate>;
  omitted: Record<string, string>;
}

export type VerifyResult = { ok: true } | { ok: false; field: string; detail: string };
/** The seam: `file` must carry an attestation for its exact bytes, built from `sourceDigest` by the signer workflow. */
export type Verifier = (file: string, sourceDigest: string) => VerifyResult;

export type StepOutcome = 'success' | 'skipped' | 'failure' | 'unknown';

interface WorkflowStep {
  name: string | null;
  cond: string | null;
}

/** One step as the jobs API records it while the job runs. */
export interface JobRunStep {
  name: string;
  status: string;
  conclusion: string | null;
}

/** The jobs API record of the job the writer runs in. */
export interface JobRun {
  runId: string;
  attempt: string;
  steps: JobRunStep[];
}

/** `GET repos/<repo>/actions/jobs/<id>` parsed, or the first field that is wrong. */
export function parseJobRun(text: string): JobRun | { error: string } {
  let v: unknown;
  try {
    v = JSON.parse(text);
  } catch (e) {
    return { error: `the job record is not JSON (${(e as Error).message})` };
  }
  if (typeof v !== 'object' || v === null || Array.isArray(v))
    return { error: 'the job record is not an object' };
  const o = v as Record<string, unknown>;
  if (!Array.isArray(o.steps)) return { error: 'the job record has no steps array' };
  const steps: JobRunStep[] = [];
  for (const s of o.steps as unknown[]) {
    const r = (typeof s === 'object' && s !== null ? s : {}) as Record<string, unknown>;
    if (
      typeof r.name !== 'string' ||
      typeof r.status !== 'string' ||
      !(r.conclusion === null || typeof r.conclusion === 'string')
    )
      return { error: `a recorded step lacks name, status or conclusion: ${JSON.stringify(s)}` };
    steps.push({ name: r.name, status: r.status, conclusion: r.conclusion as string | null });
  }
  return { runId: String(o.run_id ?? ''), attempt: String(o.run_attempt ?? ''), steps };
}

/** A recorded step's outcome: its conclusion once completed, `unknown` while it runs or for a conclusion that is neither a pass, a skip nor a failure. */
function recordedOutcome(s: JobRunStep): StepOutcome {
  if (s.status !== 'completed') return 'unknown';
  return s.conclusion === 'success' || s.conclusion === 'skipped' || s.conclusion === 'failure'
    ? s.conclusion
    : 'unknown';
}

function unquote(v: string): string {
  const t = v.trim();
  if ((t.startsWith("'") && t.endsWith("'")) || (t.startsWith('"') && t.endsWith('"')))
    return t.slice(1, -1);
  return t;
}

/** The steps of one job, in order, with each step's `name:` and `if:` (null when absent; `<block>` for a block scalar, which is never read as a known guard). Null when the job or its `steps:` is absent. */
export function jobSteps(workflow: string, job: string): WorkflowStep[] | null {
  const lines = workflow.split('\n');
  const start = lines.findIndex((l) => l === `  ${job}:`);
  if (start === -1) return null;
  const next = lines.findIndex((l, i) => i > start && /^ {0,2}[A-Za-z0-9_-]+:\s*$/.test(l));
  const end = next === -1 ? lines.length : next;
  const stepsAt = lines.findIndex((l, i) => i > start && i < end && l === '    steps:');
  if (stepsAt === -1) return null;
  const steps: WorkflowStep[] = [];
  let cur: WorkflowStep | null = null;
  for (let i = stepsAt + 1; i < end; i++) {
    const line = lines[i];
    const dash = /^ {6}- (.*)$/.exec(line);
    let body: string | null = null;
    if (dash) {
      cur = { name: null, cond: null };
      steps.push(cur);
      body = dash[1];
    } else if (cur && /^ {8}\S/.test(line)) {
      body = line.slice(8);
    }
    if (cur === null || body === null) continue;
    const kv = /^(name|if):\s*(.*)$/.exec(body);
    if (!kv) continue;
    const value = /^[|>][-+]?\s*$/.test(kv[2]) ? '<block>' : unquote(kv[2]);
    if (kv[1] === 'name') cur.name = value;
    else cur.cond = value;
  }
  return steps;
}

/** The body lines of one top-level job (the lines after `  <job>:` up to the next job or top-level key), or null when absent. */
export function jobBody(workflow: string, job: string): string[] | null {
  const lines = workflow.split('\n');
  const start = lines.findIndex((l) => l === `  ${job}:`);
  if (start === -1) return null;
  const next = lines.findIndex((l, i) => i > start && /^ {0,2}[A-Za-z0-9_-]+:\s*$/.test(l));
  return lines.slice(start + 1, next === -1 ? lines.length : next);
}

/**
 * Every job whose own `permissions:` grants `id-token` or `attestations` at write, `write-all` included, plus `<workflow>` when the top-level block does (a top-level grant reaches every job without one of its own). Block style, flow style (`permissions: {id-token: write}`) and quoted scalars are the same grant. Sorted. A job that inherits silently is not named: QUALITY_WORKFLOW sets `permissions: {}` at the top, and that is checked separately.
 */
export function signingJobs(workflow: string): string[] {
  const lines = workflow.split('\n');
  const found = new Set<string>();
  // One `key: value` pair, either scalar single- or double-quoted, trailing comment dropped.
  const pair = (text: string): [string, string] | null => {
    const kv = /^\s*(['"]?)([A-Za-z-]+)\1\s*:\s*(['"]?)([A-Za-z-]+)\3\s*(?:#.*)?$/.exec(text);
    return kv ? [kv[2], kv[4]] : null;
  };
  const signs = (kv: [string, string] | null): boolean =>
    kv !== null && SIGNING_PERMISSIONS.has(kv[0]) && kv[1] === 'write';
  const grants = (block: string[], indent: number, inline: string): boolean => {
    const value = inline.replace(/\s+#.*$/, '').trim();
    if (unquote(value) === 'write-all') return true;
    if (unquote(value) === 'read-all') return false;
    // Flow style, `permissions: {id-token: write, contents: read}`: the same grant on one line. A part that does not parse as `key: value` is read as a grant, like any other shape below.
    const flow = /^\{(.*)\}$/.exec(value);
    if (flow)
      return flow[1]
        .split(',')
        .filter((part) => part.trim() !== '')
        .some((part) => pair(part) === null || signs(pair(part)));
    // Any other inline value (an expression, a flow map spread over lines) cannot be read here, so it is named: a false name fails the signer check loudly, while a missed grant would let a job that runs code sign.
    if (value !== '') return true;
    const pad = ' '.repeat(indent);
    // A line the block does not read as `key: value` (a `write-all` scalar on the line after `permissions:`) is named, like any other shape this parser cannot read (review e7ce4979.1).
    return block.some(
      (l) => l.startsWith(pad) && !l.startsWith(`${pad} `) && (pair(l) === null || signs(pair(l)))
    );
  };
  const blockAfter = (from: number, indent: number): string[] => {
    const out: string[] = [];
    for (let i = from + 1; i < lines.length; i++) {
      const l = lines[i];
      if (l.trim() === '' || l.trim().startsWith('#')) continue;
      if (!l.startsWith(' '.repeat(indent))) break;
      out.push(l);
    }
    return out;
  };
  lines.forEach((l, i) => {
    const top = /^permissions:\s*(.*)$/.exec(l);
    if (top && grants(blockAfter(i, 2), 2, top[1])) found.add('<workflow>');
  });
  const jobsAt = lines.indexOf('jobs:');
  if (jobsAt === -1) return [...found].sort(byCodeUnit);
  let job: string | null = null;
  for (let i = jobsAt + 1; i < lines.length; i++) {
    const l = lines[i];
    if (/^\S/.test(l)) break;
    const head = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(l);
    if (head) {
      job = head[1];
      continue;
    }
    const perm = /^ {4}permissions:\s*(.*)$/.exec(l);
    if (job !== null && perm && grants(blockAfter(i, 6), 6, perm[1])) found.add(job);
  }
  return [...found].sort(byCodeUnit);
}

/**
 * What the receipt step knows about each earlier workflow step, by name: the conclusion the job's own record (`run`) gives it, or `unknown` when the record has no completed entry of that name, more than one, or the workflow names two steps alike. An error when the job has no single receipt step, when that step is not under the standard guard (under `success()` any failed step, a drift step's included, skips it, and the drift waiver reads the skip as a pass), or when the record does not show that receipt step in progress, since then the record is not this job's, read while it runs.
 */
export function laneOutcomes(
  steps: readonly WorkflowStep[],
  run: JobRun
): { outcomes: Map<string, StepOutcome> } | { error: string } {
  const at = steps.flatMap((s, i) => (s.name === RECEIPT_STEP ? [i] : []));
  if (at.length !== 1)
    return {
      error: `the job has ${at.length} step(s) named "${RECEIPT_STEP}", expected exactly one`,
    };
  const cond = steps[at[0]].cond;
  if (cond === null || !STANDARD_GUARDS.has(cond))
    return {
      error: `"${RECEIPT_STEP}" must run under the standard guard ${JSON.stringify([...STANDARD_GUARDS][0])}, got ${JSON.stringify(cond)}: under success() a failed step, a drift step's included, skips it, and the drift waiver reads that skip as a pass`,
    };
  const self = run.steps.filter((s) => s.name === RECEIPT_STEP);
  if (self.length !== 1 || self[0].status !== 'in_progress')
    return {
      error: `the job record shows ${self.length} "${RECEIPT_STEP}" step(s) (${self.map((s) => s.status).join(', ') || 'none'}), expected exactly one in_progress: a record that is not this job's, read while it runs, says nothing about this lane`,
    };
  const recorded = new Map<string, JobRunStep[]>();
  for (const s of run.steps) recorded.set(s.name, [...(recorded.get(s.name) ?? []), s]);
  const outcomes = new Map<string, StepOutcome>();
  const seen = new Set<string>();
  for (const s of steps.slice(0, at[0])) {
    if (s.name === null) continue;
    const r = recorded.get(s.name) ?? [];
    outcomes.set(s.name, seen.has(s.name) || r.length !== 1 ? 'unknown' : recordedOutcome(r[0]));
    seen.add(s.name);
  }
  return { outcomes };
}

interface CiStep {
  kind?: string;
  workflow?: string;
  job?: string;
  step?: string;
}

/** Lock ids whose CI step is in `lane` of the quality workflow, `gate: true`, not ciOnly. */
export function laneIds(lock: Record<string, LockEntry>, lane: string): string[] {
  return Object.values(lock)
    .filter((e) => {
      const ci = e.ci as CiStep | undefined;
      return (
        e.gate === true &&
        e.ciOnly === undefined &&
        ci?.kind === 'step' &&
        ci.workflow === QUALITY_WORKFLOW &&
        ci.job === lane &&
        typeof ci.step === 'string'
      );
    })
    .map((e) => e.id)
    .sort();
}

/** The receipt, pure. Only a gate whose step passed and whose inputHash is non-null is written; every other lane gate is named in `omitted` with why. */
export function buildCiReceipt(input: {
  repo: string;
  run: { id: string; attempt: string };
  lane: string;
  sha: string;
  tree: string;
  salt: string;
  lock: Record<string, LockEntry>;
  outcomes: ReadonlyMap<string, StepOutcome>;
  hashes: ReadonlyMap<string, GateHash>;
}): CiReceipt {
  const gates: Record<string, CiReceiptGate> = {};
  const omitted: Record<string, string> = {};
  for (const id of laneIds(input.lock, input.lane)) {
    const step = (input.lock[id].ci as CiStep).step as string;
    const outcome = input.outcomes.get(step);
    if (outcome !== 'success') {
      omitted[id] =
        outcome === undefined ? 'step not found before the receipt step' : `step ${outcome}`;
      continue;
    }
    const h = input.hashes.get(id);
    if (h === undefined || h.inputHash === null) {
      omitted[id] = `no inputHash (${h?.reason ?? 'not hashed'})`;
      continue;
    }
    gates[id] = { inputHash: h.inputHash, verdict: 'pass' };
  }
  return {
    schema: CI_RECEIPT_SCHEMA,
    repo: input.repo,
    run: input.run,
    lane: input.lane,
    sha: input.sha,
    tree: input.tree,
    salt: input.salt,
    gates,
    omitted,
  };
}

/** The receipt's shape, or the first field that is wrong. Run on bytes BEFORE they are verified or stored. */
export function parseCiReceipt(
  bytes: Buffer
): { receipt: CiReceipt } | { field: string; detail: string } {
  let doc: unknown;
  try {
    doc = JSON.parse(bytes.toString('utf8'));
  } catch (e) {
    return { field: 'json', detail: (e as Error).message };
  }
  const r = doc as Partial<CiReceipt> | null;
  if (r === null || typeof r !== 'object' || Array.isArray(r))
    return { field: 'json', detail: 'not an object' };
  if (r.schema !== CI_RECEIPT_SCHEMA)
    return {
      field: 'schema',
      detail: `expected ${CI_RECEIPT_SCHEMA}, got ${JSON.stringify(r.schema)}`,
    };
  if (r.repo !== ATTESTATION_SPEC.repo)
    return {
      field: 'repo',
      detail: `expected ${ATTESTATION_SPEC.repo}, got ${JSON.stringify(r.repo)}`,
    };
  if (typeof r.sha !== 'string' || !SHA_RE.test(r.sha))
    return { field: 'sha', detail: 'not a 40-hex commit' };
  if (typeof r.tree !== 'string' || !TREE_RE.test(r.tree))
    return { field: 'tree', detail: 'not a tree hash' };
  if (typeof r.salt !== 'string' || r.salt === '') return { field: 'salt', detail: 'empty' };
  if (typeof r.lane !== 'string' || r.lane === '') return { field: 'lane', detail: 'empty' };
  if (r.gates === null || typeof r.gates !== 'object' || Array.isArray(r.gates))
    return { field: 'gates', detail: 'not a map' };
  for (const [id, g] of Object.entries(r.gates)) {
    if (g?.verdict !== 'pass' || typeof g.inputHash !== 'string' || g.inputHash === '')
      return { field: 'gates', detail: `${id} is not {inputHash, verdict: "pass"}` };
  }
  return { receipt: r as CiReceipt };
}

const sha256 = (b: Buffer): string => createHash('sha256').update(b).digest('hex');

export const priorNameOf = (tree: string): string => `${CI_PRIOR_PREFIX}${tree}`;

interface CiPrior extends PriorReceipt {
  origin: 'ci';
  tree: string;
  repo: string;
  ciReceipts: Array<{
    lane: string;
    run: { id: string; attempt: string };
    path: string;
    sha256: string;
  }>;
  gates: Record<string, PriorGate & { lane: string }>;
}

/** The runner-readable prior for `receipts` (one per lane, all at one tree), pure. */
export function priorOf(
  entries: ReadonlyArray<{ receipt: CiReceipt; path: string; sha256: string }>
): CiPrior {
  const first = entries[0].receipt;
  const gates: CiPrior['gates'] = {};
  for (const { receipt } of entries) {
    for (const [id, g] of Object.entries(receipt.gates)) {
      gates[id] = {
        inputHash: g.inputHash,
        verdict: 'ok',
        exitCode: 0,
        findings: [],
        judgedTree: receipt.tree,
        carriedFrom: null,
        lane: receipt.lane,
      };
    }
  }
  return {
    schema: SCHEMA,
    whole: true,
    origin: 'ci',
    headTree: priorNameOf(first.tree),
    tree: first.tree,
    head: first.sha,
    finishedAt: '',
    repo: first.repo,
    saltHash: first.salt,
    ciReceipts: entries.map((e) => ({
      lane: e.receipt.lane,
      run: e.receipt.run,
      path: e.path,
      sha256: e.sha256,
    })),
    gates,
  };
}

/**
 * Verifies the file's bytes and, only on success, stores them content-addressed under `<root>/.ci/cache/ci-receipts/` and merges the receipt into `<root>/.ci/cache/receipts/ci-<tree>.json` (the same lane is replaced, other lanes at the same tree and salt are kept). The bytes are copied to a private file first and THAT file is verified, so what is stored is exactly what was verified.
 */
export function storeVerified(
  root: string,
  file: string,
  verify: Verifier
):
  | { stored: true; prior: string; receipt: CiReceipt }
  | { stored: false; field: string; detail: string } {
  const bytes = fs.readFileSync(file);
  const parsed = parseCiReceipt(bytes);
  if (!('receipt' in parsed)) return { stored: false, ...parsed };
  const receipt = parsed.receipt;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-receipt-verify-'));
  let verdict: VerifyResult;
  try {
    const copy = path.join(tmp, path.basename(file));
    fs.writeFileSync(copy, bytes);
    verdict = verify(copy, receipt.sha);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  if (!verdict.ok) return { stored: false, field: verdict.field, detail: verdict.detail };
  const digest = sha256(bytes);
  const rawRel = path.join(RAW_DIR_REL, `${digest}.json`);
  fs.mkdirSync(path.join(root, RAW_DIR_REL), { recursive: true });
  fs.writeFileSync(path.join(root, rawRel), bytes);
  const priorPath = path.join(root, PRIOR_DIR_REL, `${priorNameOf(receipt.tree)}.json`);
  const kept: Array<{ receipt: CiReceipt; path: string; sha256: string }> = [];
  try {
    const old = JSON.parse(fs.readFileSync(priorPath, 'utf8')) as CiPrior;
    if (old.saltHash === receipt.salt) {
      for (const e of Array.isArray(old.ciReceipts) ? old.ciReceipts : []) {
        if (e.lane === receipt.lane) continue;
        const b = fs.readFileSync(path.join(root, e.path));
        const p = parseCiReceipt(b);
        if ('receipt' in p && sha256(b) === e.sha256)
          kept.push({ receipt: p.receipt, path: e.path, sha256: e.sha256 });
      }
    }
  } catch {
    // no prior yet, or an unreadable one: this receipt starts it
  }
  kept.push({ receipt, path: rawRel, sha256: digest });
  fs.mkdirSync(path.dirname(priorPath), { recursive: true });
  fs.writeFileSync(priorPath, `${JSON.stringify(priorOf(kept), null, 2)}\n`);
  return { stored: true, prior: priorPath, receipt };
}

/** The real verifier: `gh attestation verify` with D6's flags. A missing gh is a refusal with the install line, never a pass. */
export const ghAttestationVerifier: Verifier = (file, sourceDigest) => {
  if (!SHA_RE.test(sourceDigest)) return { ok: false, field: 'sha', detail: 'not a 40-hex commit' };
  const r = spawnSync(
    'gh',
    [
      'attestation',
      'verify',
      file,
      '--repo',
      ATTESTATION_SPEC.repo,
      '--signer-workflow',
      ATTESTATION_SPEC.signerWorkflow,
      '--source-digest',
      sourceDigest,
      '--format',
      'json',
    ],
    { encoding: 'utf8', timeout: 120_000 }
  );
  if (r.error) {
    const missing = (r.error as NodeJS.ErrnoException).code === 'ENOENT';
    return {
      ok: false,
      field: 'attestation',
      detail: missing
        ? 'gh is not installed (https://cli.github.com, then gh auth login)'
        : r.error.message,
    };
  }
  if (r.status !== 0) {
    const tail = `${r.stderr ?? ''}`.trim().split('\n').slice(-3).join(' | ');
    return {
      ok: false,
      field: 'attestation',
      detail: `gh attestation verify exited ${r.status}: ${tail}`,
    };
  }
  return { ok: true };
};

function git(root: string, args: string[]): string {
  return execFileSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 1 << 28 }).trim();
}

function argValue(args: string[], flag: string): string | undefined {
  const i = args.indexOf(flag);
  return i === -1 ? undefined : args[i + 1];
}

/** The runner's own hash options (run.ts `incrementalPlan`), so a hash here is the hash a local run computes. */
function laneHashes(
  root: string,
  tree: string,
  lock: Record<string, LockEntry>
): Map<string, GateHash> {
  const pkg = JSON.parse(git(root, ['show', `${tree}:package.json`])) as {
    scripts?: Record<string, string>;
  };
  const scripts = pkg.scripts ?? {};
  let exemptText: string | null = null;
  try {
    exemptText = git(root, ['show', `${tree}:${path.join('.ci', 'policy', 'carry-exempt.json')}`]);
  } catch {
    exemptText = null;
  }
  return computeGateHashes(root, tree, lock, {
    exempt: exemptIdsOf(exemptText),
    scriptsOf: (id) => scriptsMapOf(String(lock[id]?.run ?? ''), scripts),
    leafFilesOf: (id) => {
      const leaves = lock[id]?.leaves;
      const closure = leafClosure(root, Array.isArray(leaves) ? (leaves as string[]) : []);
      return { files: [...closure.files], capped: closure.capped };
    },
  });
}

/** Why a job record is not this run's and attempt's, or null. Only judged in Actions, where the run and attempt are known (review 60625cca.2). */
export function jobRecordMismatch(
  jobRun: JobRun,
  run: { id: string; attempt: string },
  inActions: boolean
): string | null {
  if (!inActions || (jobRun.runId === run.id && jobRun.attempt === run.attempt)) return null;
  return `the job record names run ${jobRun.runId} attempt ${jobRun.attempt}, but this is run ${run.id} attempt ${run.attempt}; another job's outcomes are not this lane's`;
}

/**
 * The job record the writer judges outcomes from. In Actions it is always read live, `gh api repos/<GITHUB_REPOSITORY>/actions/jobs/<RECEIPT_JOB_ID>` with the token in GH_TOKEN (env, never argv); `--steps <file>` (a saved record) serves a local dry run only and is refused in Actions, where it would let a receipt name outcomes nothing observed.
 */
function readJobRun(args: string[]): JobRun | { error: string } {
  if (args.includes('--steps')) {
    const file = argValue(args, '--steps');
    if (process.env.GITHUB_ACTIONS === 'true')
      return { error: '--steps is refused in Actions; the record is read live from the jobs API' };
    if (file === undefined || !fs.existsSync(file))
      return { error: `--steps ${file ?? '(no value)'} does not name a file` };
    return parseJobRun(fs.readFileSync(file, 'utf8'));
  }
  const repo = process.env.GITHUB_REPOSITORY ?? '';
  const id = process.env.RECEIPT_JOB_ID ?? '';
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo) || !/^\d+$/.test(id))
    return {
      error: `GITHUB_REPOSITORY=${JSON.stringify(repo)} and RECEIPT_JOB_ID=${JSON.stringify(id)} must name this job (the step sets RECEIPT_JOB_ID from job.check_run_id); outside Actions pass --steps <saved job record>`,
    };
  const r = gh(['api', `repos/${repo}/actions/jobs/${id}`]);
  if (r.status !== 0)
    return {
      error: `gh api repos/${repo}/actions/jobs/${id} exited ${r.status}: ${r.stderr.trim().slice(0, 300) || 'no stderr'}${r.status === 127 ? ' (gh is missing from the image)' : ''}`,
    };
  return parseJobRun(r.stdout);
}

function write(args: string[]): number {
  const lane = argValue(args, '--lane');
  const out = argValue(args, '--out');
  if (!lane || !out) {
    process.stderr.write('ci-receipt write: --lane <job> and --out <file> are required\n');
    return 2;
  }
  const root = REPO_ROOT;
  const sha = git(root, ['rev-parse', 'HEAD']);
  const tree = git(root, ['rev-parse', 'HEAD^{tree}']);
  const ghSha = process.env.GITHUB_SHA ?? '';
  if (process.env.GITHUB_ACTIONS === 'true' && ghSha !== sha) {
    process.stderr.write(
      `ci-receipt write: HEAD is ${sha} but GITHUB_SHA is ${ghSha}; the attestation's source digest would not describe the tree hashed here\n`
    );
    return 1;
  }
  const lock: Record<string, LockEntry> = {};
  for (const e of JSON.parse(
    git(root, ['show', `${tree}:scripts/ci-runner/gates.lock.json`])
  ) as LockEntry[])
    lock[e.id] = e;
  const steps = jobSteps(git(root, ['show', `${tree}:${QUALITY_WORKFLOW}`]), lane);
  if (steps === null) {
    process.stderr.write(`ci-receipt write: ${QUALITY_WORKFLOW} has no job ${lane} with steps\n`);
    return 1;
  }
  const run = {
    id: process.env.GITHUB_RUN_ID ?? '',
    attempt: process.env.GITHUB_RUN_ATTEMPT ?? '',
  };
  const jobRun = readJobRun(args);
  if ('error' in jobRun) {
    process.stderr.write(
      `ci-receipt write: ${lane}: the job's own step record is UNCHECKED (${jobRun.error}); without it no step is known to have passed, so no receipt is written\n`
    );
    return 1;
  }
  const mismatch = jobRecordMismatch(jobRun, run, process.env.GITHUB_ACTIONS === 'true');
  if (mismatch !== null) {
    process.stderr.write(`ci-receipt write: ${lane}: ${mismatch}\n`);
    return 1;
  }
  const lo = laneOutcomes(steps, jobRun);
  if ('error' in lo) {
    process.stderr.write(`ci-receipt write: ${lane}: ${lo.error}\n`);
    return 1;
  }
  const receipt = buildCiReceipt({
    repo: process.env.GITHUB_REPOSITORY ?? '',
    run,
    lane,
    sha,
    tree,
    salt: saltHash(root, tree),
    lock,
    outcomes: lo.outcomes,
    hashes: laneHashes(root, tree, lock),
  });
  const total = laneIds(lock, lane).length;
  const passed = Object.keys(receipt.gates).length;
  if (passed === 0) {
    process.stderr.write(
      `ci-receipt write: ${lane}: 0 of ${total} lane gate(s) receipted; the writer is not seeing the lane, so an empty receipt would mean nothing. Omitted: ${JSON.stringify(receipt.omitted)}\n`
    );
    return 1;
  }
  fs.writeFileSync(out, `${JSON.stringify(receipt, null, 2)}\n`);
  const why = new Map<string, number>();
  for (const w of Object.values(receipt.omitted)) {
    const k = w.replace(/\(.*\)/, '').trim();
    why.set(k, (why.get(k) ?? 0) + 1);
  }
  process.stdout.write(
    `ci-receipt write: ${lane}: ${passed} of ${total} lane gate(s) receipted as pass, ${total - passed} omitted (${[...why].map(([k, n]) => `${n} ${k}`).join(', ') || 'none'}); tree ${tree}, sha ${sha}, salt ${receipt.salt.slice(0, 12)} -> ${out}\n`
  );
  return 0;
}

function gh(args: string[]): { status: number; stdout: string; stderr: string } {
  const r = spawnSync('gh', args, { encoding: 'utf8', timeout: 180_000, maxBuffer: 1 << 26 });
  if (r.error) return { status: 127, stdout: '', stderr: r.error.message };
  return { status: r.status ?? 1, stdout: r.stdout ?? '', stderr: r.stderr ?? '' };
}

function fetchVerb(args: string[]): number {
  const probe = gh(['--version']);
  if (probe.status !== 0) {
    process.stderr.write(
      `ci-receipt fetch: gh is not usable (${probe.stderr.trim()}). Install https://cli.github.com and run gh auth login; without it no receipt can be verified.\n`
    );
    return 1;
  }
  const limit = Number(argValue(args, '--limit') ?? '5');
  const branches: string[] = [];
  args.forEach((a, i) => {
    if (a === '--branch' && args[i + 1]) branches.push(args[i + 1]);
  });
  if (branches.length === 0) {
    const cur = git(REPO_ROOT, ['rev-parse', '--abbrev-ref', 'HEAD']);
    if (cur !== 'HEAD') branches.push(cur);
    branches.push('main');
  }
  let listed = 0;
  let stored = 0;
  let noArtifact = 0;
  const refused: string[] = [];
  const unchecked: string[] = [];
  for (const branch of [...new Set(branches)]) {
    const list = gh([
      'run',
      'list',
      '--repo',
      ATTESTATION_SPEC.repo,
      '--workflow',
      CALLER_WORKFLOW,
      '--branch',
      branch,
      '--status',
      'completed',
      '--limit',
      String(limit),
      '--json',
      'databaseId,headSha',
    ]);
    if (list.status !== 0) {
      unchecked.push(`branch ${branch}: gh run list exited ${list.status}: ${list.stderr.trim()}`);
      continue;
    }
    const runs = JSON.parse(list.stdout) as Array<{ databaseId: number; headSha: string }>;
    for (const run of runs) {
      listed++;
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-receipt-dl-'));
      try {
        const dl = gh([
          'run',
          'download',
          String(run.databaseId),
          '--repo',
          ATTESTATION_SPEC.repo,
          '--pattern',
          `${ARTIFACT_PREFIX}*`,
          '--dir',
          dir,
        ]);
        if (dl.status !== 0) {
          if (/no (valid )?artifacts? (found|matches)/i.test(dl.stderr)) noArtifact++;
          else
            unchecked.push(
              `run ${run.databaseId}: gh run download exited ${dl.status}: ${dl.stderr.trim()}`
            );
          continue;
        }
        const files = fs
          .readdirSync(dir, { recursive: true, withFileTypes: true })
          .filter((d) => d.isFile() && d.name.endsWith('.json'))
          .map((d) => path.join(d.parentPath, d.name));
        if (files.length === 0) {
          unchecked.push(`run ${run.databaseId}: the download held no .json file`);
          continue;
        }
        for (const f of files) {
          const r = storeVerified(REPO_ROOT, f, ghAttestationVerifier);
          if (r.stored) {
            stored++;
            process.stdout.write(
              `  run ${run.databaseId} ${r.receipt.lane}: ${Object.keys(r.receipt.gates).length} gate(s) at tree ${r.receipt.tree} -> ${path.relative(REPO_ROOT, r.prior)}\n`
            );
          } else
            refused.push(
              `run ${run.databaseId} ${path.basename(f)}: NOT STORED (field ${r.field}): ${r.detail}`
            );
        }
      } finally {
        fs.rmSync(dir, { recursive: true, force: true });
      }
    }
  }
  for (const r of refused) process.stderr.write(`ci-receipt fetch: ${r}\n`);
  for (const u of unchecked) process.stderr.write(`ci-receipt fetch: UNCHECKED ${u}\n`);
  process.stdout.write(
    `ci-receipt fetch: ${listed} run(s) listed on ${new Set(branches).size} branch(es), ${stored} receipt(s) verified and stored, ${noArtifact} run(s) without a receipt artifact, ${refused.length} refused, ${unchecked.length} unchecked\n`
  );
  if (refused.length > 0 || unchecked.length > 0) return 1;
  if (stored === 0) {
    process.stderr.write(
      'ci-receipt fetch: VACUOUS: no CI receipt was verified and stored, so nothing can carry from CI\n'
    );
    return 1;
  }
  return 0;
}

function verifyVerb(args: string[]): number {
  const file = args[0];
  if (!file) {
    process.stderr.write('ci-receipt verify: <file> is required\n');
    return 2;
  }
  const parsed = parseCiReceipt(fs.readFileSync(file));
  if (!('receipt' in parsed)) {
    process.stderr.write(`ci-receipt verify: ${file}: field ${parsed.field}: ${parsed.detail}\n`);
    return 1;
  }
  const v = ghAttestationVerifier(file, parsed.receipt.sha);
  if (!v.ok) {
    process.stderr.write(`ci-receipt verify: ${file}: REFUSED (field ${v.field}): ${v.detail}\n`);
    return 1;
  }
  process.stdout.write(
    `ci-receipt verify: ${file}: verified (signer ${ATTESTATION_SPEC.signerWorkflow}, source ${parsed.receipt.sha}, ${Object.keys(parsed.receipt.gates).length} gate(s))\n`
  );
  return 0;
}

// ---------------------------------------------------------------------------------------- selftest

/** The one line a mutant neutralizes: storing must depend on the verifier's answer. */
export const STORE_GUARD_LINE =
  '  if (!verdict.ok) return { stored: false, field: verdict.field, detail: verdict.detail };';

function fixtureHash(id: string, inputHash: string | null, reason: string | null = null): GateHash {
  return {
    id,
    inputHash,
    defHash: 'd',
    filesHash: 'f',
    inputs: { globs: [], files: [], scripts: [] },
    reason,
    artifactHash: null,
    exemptKind: null,
  };
}

/** The cases that need nothing but this module: run by `--selftest`, and by the mutant copy under `--selftest-core`. Returns the failure messages. */
function coreCases(): { failures: string[]; count: number } {
  const failures: string[] = [];
  let count = 0;
  const check = (ok: boolean, msg: string): void => {
    count++;
    if (!ok) failures.push(msg);
  };
  const wf = [
    'jobs:',
    '  lane:',
    '    runs-on: x',
    '    steps:',
    '      - id: setup',
    '        uses: ./.github/actions/setup-workspace',
    '      - name: Plain gate',
    "        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}",
    '        run: npm run check:a',
    '      - name: Held gate',
    "        if: ${{ !cancelled() && steps.setup.outcome == 'success' && (inputs.media_quality != 'skip') }}",
    '        run: npm run check:b',
    '      - name: Bare gate',
    '        run: npm run check:c',
    `      - name: ${RECEIPT_STEP}`,
    "        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}",
    '        run: x',
    '      - name: After gate',
    '        run: npm run check:d',
    '  other:',
    '    steps:',
    '      - name: Plain gate',
    '        run: y',
  ].join('\n');
  const steps = jobSteps(wf, 'lane');
  check(
    steps !== null && steps.length === 6,
    `jobSteps reads the lane's 6 steps and stops at the next job, got ${JSON.stringify(steps)}`
  );
  // The job record as the jobs API returns it while the receipt step runs. The Held gate has no entry, so it reads unknown.
  const done = (name: string, conclusion: string): JobRunStep => ({
    name,
    status: 'completed',
    conclusion,
  });
  const self: JobRunStep = { name: RECEIPT_STEP, status: 'in_progress', conclusion: null };
  const record = (...extra: JobRunStep[]): JobRun => ({
    runId: '1',
    attempt: '1',
    steps: [
      done('Set up job', 'success'),
      ...extra,
      self,
      { name: 'After gate', status: 'pending', conclusion: null },
    ],
  });
  const runRecord = record(done('Plain gate', 'success'), done('Bare gate', 'success'));
  const lo = steps ? laneOutcomes(steps, runRecord) : { error: 'no steps' };
  const oc = 'outcomes' in lo ? lo.outcomes : new Map<string, StepOutcome>();
  check(
    oc.get('Plain gate') === 'success',
    `a step the job record shows completed with success reads as passed, got ${JSON.stringify('error' in lo ? lo.error : oc.get('Plain gate'))}`
  );
  check(
    oc.get('Bare gate') === 'success',
    'CONTROL: a step with no condition reads its record too'
  );
  check(
    oc.get('Held gate') === 'unknown',
    'a step the job record does not name reads unknown, never passed'
  );
  check(!oc.has('After gate'), 'a step after the receipt step has not run and is not read');
  const judged = (...extra: JobRunStep[]): Map<string, StepOutcome> => {
    const r = steps ? laneOutcomes(steps, record(...extra)) : { error: 'no steps' };
    return 'outcomes' in r ? r.outcomes : new Map<string, StepOutcome>();
  };
  check(
    judged(done('Held gate', 'success')).get('Held gate') === 'success',
    'a step with an extra conjunct that the record shows passed reads as passed'
  );
  check(
    judged(done('Plain gate', 'failure')).get('Plain gate') === 'failure' &&
      judged(done('Plain gate', 'skipped')).get('Plain gate') === 'skipped',
    'a failed or skipped step reads as recorded, so a drift failure before the receipt omits only its own gate'
  );
  check(
    judged({ name: 'Plain gate', status: 'in_progress', conclusion: null }).get('Plain gate') ===
      'unknown' && judged(done('Plain gate', 'cancelled')).get('Plain gate') === 'unknown',
    'a step not yet completed, or concluded neither pass, skip nor failure, reads unknown'
  );
  check(
    judged(done('Plain gate', 'success'), done('Plain gate', 'success')).get('Plain gate') ===
      'unknown',
    'a name the record carries twice reads unknown, since it cannot say which step passed'
  );
  const receiptGuard =
    "        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}\n        run: x";
  const underSuccess = laneOutcomes(
    jobSteps(wf.replace(receiptGuard, '        if: success()\n        run: x'), 'lane') ?? [],
    runRecord
  );
  check(
    'error' in underSuccess && underSuccess.error.includes('standard guard'),
    'a receipt step under `if: success()` is refused, since a drift failure would skip it into a pass the waiver reads'
  );
  const noGuard = laneOutcomes(
    jobSteps(wf.replace(receiptGuard, '        run: x'), 'lane') ?? [],
    runRecord
  );
  check('error' in noGuard, 'a receipt step with no condition is refused');
  const notThisJob = laneOutcomes(steps ?? [], {
    ...runRecord,
    steps: runRecord.steps.filter((s) => s !== self),
  });
  check(
    'error' in notThisJob,
    'a record without the receipt step in progress is refused: it is not this job, read while it runs'
  );
  const twice = laneOutcomes(
    jobSteps(wf.replace('      - name: After gate', `      - name: ${RECEIPT_STEP}`), 'lane') ?? [],
    runRecord
  );
  check('error' in twice, 'two receipt steps in one job are refused');
  const parsed = parseJobRun(
    JSON.stringify({
      run_id: 7,
      run_attempt: 2,
      steps: [{ name: 'a', status: 'completed', conclusion: 'success' }],
    })
  );
  check(
    !('error' in parsed) &&
      parsed.runId === '7' &&
      parsed.attempt === '2' &&
      parsed.steps.length === 1,
    'parseJobRun reads the run, the attempt and each step'
  );
  check(
    'error' in parseJobRun('{"run_id": 7}') &&
      'error' in parseJobRun('not json') &&
      'error' in parseJobRun('{"steps": [{"name": "a"}]}'),
    'CONTROL: a record with no steps array, no JSON, or a step lacking its status is refused'
  );
  const rec = { runId: '7', attempt: '2', steps: [] };
  check(
    jobRecordMismatch(rec, { id: '7', attempt: '2' }, true) === null &&
      jobRecordMismatch(rec, { id: '8', attempt: '2' }, true) !== null &&
      jobRecordMismatch(rec, { id: '7', attempt: '3' }, true) !== null &&
      jobRecordMismatch(rec, { id: '8', attempt: '3' }, false) === null,
    'CONTROL: in Actions a record of another run or attempt is refused; a matching one and a local dry run pass (review 60625cca.2)'
  );
  const savedActions = process.env.GITHUB_ACTIONS;
  process.env.GITHUB_ACTIONS = 'true';
  const stepsRead = readJobRun(['--steps', '/nonexistent']);
  if (savedActions === undefined) delete process.env.GITHUB_ACTIONS;
  else process.env.GITHUB_ACTIONS = savedActions;
  check(
    'error' in stepsRead && stepsRead.error.includes('refused in Actions'),
    'CONTROL: --steps is refused in Actions (review 60625cca.2)'
  );
  check(
    jobSteps(wf, 'absent') === null,
    'an absent job reads as null, never as a job with no steps'
  );

  const ci = (job: string, step: string): Record<string, unknown> => ({
    ci: { kind: 'step', workflow: QUALITY_WORKFLOW, job, step },
  });
  const lock: Record<string, LockEntry> = {
    'check:a': { id: 'check:a', run: 'npm run check:a', gate: true, ...ci('lane', 'Plain gate') },
    'check:b': { id: 'check:b', run: 'npm run check:b', gate: true, ...ci('lane', 'Held gate') },
    'check:c': { id: 'check:c', run: 'npm run check:c', gate: true, ...ci('lane', 'Bare gate') },
    'check:nohash': { id: 'check:nohash', run: 'x', gate: true, ...ci('lane', 'Plain gate') },
    'check:skip': { id: 'check:skip', run: 'x', gate: true, ...ci('lane', 'Skipped gate') },
    'check:fail': { id: 'check:fail', run: 'x', gate: true, ...ci('lane', 'Failed gate') },
    'check:cionly': {
      id: 'check:cionly',
      run: 'x',
      gate: true,
      ciOnly: 'r',
      ...ci('lane', 'Plain gate'),
    },
    'check:elsewhere': {
      id: 'check:elsewhere',
      run: 'x',
      gate: true,
      ...ci('other', 'Plain gate'),
    },
    'build:x': { id: 'build:x', run: 'x', gate: false, ...ci('lane', 'Plain gate') },
  };
  const outcomes = new Map<string, StepOutcome>([
    ...oc,
    ['Skipped gate', 'skipped'],
    ['Failed gate', 'failure'],
  ]);
  const hashes = new Map<string, GateHash>(
    [
      'check:a',
      'check:b',
      'check:c',
      'check:skip',
      'check:fail',
      'check:cionly',
      'check:elsewhere',
      'build:x',
    ].map((id) => [id, fixtureHash(id, `h-${id}`)])
  );
  hashes.set('check:nohash', fixtureHash('check:nohash', null, 'env'));
  const tree = 'a'.repeat(40);
  const sha = 'b'.repeat(40);
  const receipt = buildCiReceipt({
    repo: ATTESTATION_SPEC.repo,
    run: { id: '1', attempt: '1' },
    lane: 'lane',
    sha,
    tree,
    salt: 'salt-1',
    lock,
    outcomes,
    hashes,
  });
  const ids = Object.keys(receipt.gates).sort((a, b) => Number(a > b) - Number(a < b));
  check(
    JSON.stringify(ids) === JSON.stringify(['check:a', 'check:c']),
    `only passed gates with a non-null inputHash are written, got ${ids.join(',')}`
  );
  check(
    Object.values(receipt.gates).every((g) => g.verdict === 'pass'),
    'every written verdict is pass'
  );
  check(
    'check:a' in receipt.gates && receipt.gates['check:a'].inputHash === 'h-check:a',
    'CONTROL: a passed gate carries its own inputHash'
  );
  check(
    receipt.omitted['check:skip'] === 'step skipped',
    'a gate whose step was skipped is absent, and named in omitted'
  );
  check(receipt.omitted['check:fail'] === 'step failure', 'a gate whose step failed is absent');
  check(
    receipt.omitted['check:b'] === 'step unknown',
    'a gate behind a conditional step is absent'
  );
  check(
    String(receipt.omitted['check:nohash']).startsWith('no inputHash'),
    'a gate with a null inputHash is absent'
  );
  check(
    !('check:cionly' in receipt.gates) && !('check:cionly' in receipt.omitted),
    'a ciOnly gate is not a lane gate here'
  );
  check(
    !('check:elsewhere' in receipt.gates) && !('build:x' in receipt.gates),
    "another job's gate and a gate: false entry are never written"
  );

  // Storage: a stub verifier that knows which digests carry an attestation, and from which workflow.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-receipt-st-'));
  try {
    const bytes = Buffer.from(`${JSON.stringify(receipt, null, 2)}\n`);
    const file = path.join(root, 'in.json');
    fs.writeFileSync(file, bytes);
    const attested = new Map<string, string>([[sha256(bytes), ATTESTATION_SPEC.signerWorkflow]]);
    const stub: Verifier = (f, digest) => {
      const signer = attested.get(sha256(fs.readFileSync(f)));
      if (signer === undefined)
        return { ok: false, field: 'attestation', detail: 'no attestation for these bytes' };
      if (signer !== ATTESTATION_SPEC.signerWorkflow)
        return { ok: false, field: 'attestation', detail: `signed by ${signer}` };
      return digest === sha
        ? { ok: true }
        : { ok: false, field: 'attestation', detail: 'source digest differs' };
    };
    const listing = (): string[] =>
      [RAW_DIR_REL, PRIOR_DIR_REL].flatMap((d) => {
        try {
          return fs.readdirSync(path.join(root, d)).map((n) => path.join(d, n));
        } catch {
          return [];
        }
      });
    const failing: Verifier = () => ({
      ok: false,
      field: 'attestation',
      detail: 'stub: always fails',
    });
    const r0 = storeVerified(root, file, failing);
    check(
      !r0.stored && r0.field === 'attestation',
      'an unverifiable file is refused with the field named'
    );
    check(
      listing().length === 0,
      `an unverifiable file is never stored, found ${listing().join(',')}`
    );
    const altered = path.join(root, 'altered.json');
    fs.writeFileSync(
      altered,
      Buffer.from(bytes.toString('utf8').replace('h-check:a', 'h-check:A'))
    );
    check(
      !storeVerified(root, altered, stub).stored && listing().length === 0,
      'a byte-altered receipt is not verified and not stored'
    );
    const r1 = storeVerified(root, file, stub);
    check(r1.stored, `CONTROL: an attested receipt is stored, got ${JSON.stringify(r1)}`);
    const priorFile = path.join(root, PRIOR_DIR_REL, `${CI_PRIOR_PREFIX}${tree}.json`);
    const raw = path.join(root, RAW_DIR_REL, `${sha256(bytes)}.json`);
    check(
      fs.existsSync(raw) && fs.readFileSync(raw).equals(bytes),
      'the stored raw file is byte-identical and named by its sha256'
    );
    const prior = JSON.parse(fs.readFileSync(priorFile, 'utf8')) as CiPrior;
    check(
      prior.headTree === `ci-${tree}` && prior.origin === 'ci' && prior.finishedAt === '',
      'the prior names itself ci-<tree>, says origin ci and carries an empty finishedAt'
    );
    // The runner's rule, unchanged: the prior carries a gate at the same inputHash and salt, and only then.
    const current = new Map<string, GateHash>([
      ['check:a', fixtureHash('check:a', 'h-check:a')],
      ['check:c', fixtureHash('check:c', 'h-other')],
    ]);
    const plan = planCarry([prior], current, ['check:a', 'check:c'], 'salt-1');
    check(
      plan.carry.get('check:a')?.carriedFrom?.headTree === `ci-${tree}`,
      'planCarry carries a gate from the CI prior, origin ci-<tree>'
    );
    check(plan.run.includes('check:c'), 'CONTROL: a gate whose inputHash moved re-runs');
    check(
      planCarry([prior], current, ['check:a'], 'salt-2').carry.size === 0,
      'CONTROL: another salt (another image) carries nothing'
    );
    const local: PriorReceipt = {
      schema: SCHEMA,
      whole: true,
      headTree: tree,
      head: sha,
      finishedAt: '2026-11-22T00:00:00Z',
      saltHash: 'salt-1',
      gates: {
        'check:a': {
          inputHash: 'h-check:a',
          verdict: 'fail',
          exitCode: 1,
          findings: ['x'],
          judgedTree: tree,
          carriedFrom: null,
        },
      },
    };
    check(
      planCarry([local, prior], current, ['check:a'], 'salt-1').rejudged.includes('check:a'),
      'a local red at the same inputs outvotes the CI green, which sorts last'
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
  // The signer split: only SIGNER_JOB may mint an OIDC token or sign. Both directions.
  const permWf = (jobPerms: string): string =>
    [
      'permissions: {}',
      'jobs:',
      '  gates:',
      '    permissions:',
      '      contents: read',
      jobPerms,
      '    steps:',
      '      - run: x',
      '  sign:',
      '    permissions:',
      '      id-token: write',
      '      attestations: write',
      '    steps:',
      '      - uses: a',
    ].join('\n');
  check(
    JSON.stringify(signingJobs(permWf('      packages: read'))) === '["sign"]',
    'signingJobs names only the job granting id-token/attestations write'
  );
  check(
    JSON.stringify(signingJobs(permWf('      id-token: write'))) === '["gates","sign"]',
    'signingJobs fires on a gate job that also grants id-token: write'
  );
  check(
    JSON.stringify(signingJobs(permWf('      attestations: write'))) === '["gates","sign"]',
    'signingJobs fires on a gate job that also grants attestations: write'
  );
  check(
    JSON.stringify(signingJobs(permWf('      attestations: read'))) === '["sign"]',
    'signingJobs does not fire on attestations: read'
  );
  check(
    JSON.stringify(
      signingJobs(
        permWf('').replace(
          '    permissions:\n      contents: read\n',
          '    permissions: write-all\n'
        )
      )
    ) === '["gates","sign"]',
    'signingJobs fires on permissions: write-all'
  );
  // Review f1c7c026.2: a job's permissions in flow style, or with quoted scalars, are the same grant as the block form.
  const inlinePerms = (inline: string): string[] =>
    signingJobs(
      permWf('').replace('    permissions:\n      contents: read\n', `    permissions: ${inline}\n`)
    );
  for (const [inline, want] of [
    ['{id-token: write}', '["gates","sign"]'],
    ['{ contents: read, attestations: write }', '["gates","sign"]'],
    ['{"id-token": "write"}', '["gates","sign"]'],
    ["{'attestations': 'write'}  # signer", '["gates","sign"]'],
    ["'write-all'", '["gates","sign"]'],
    ['write-all # every scope', '["gates","sign"]'],
    ['{id-token: read, contents: write}', '["sign"]'],
    ['{}', '["sign"]'],
    ['read-all', '["sign"]'],
    ['{id-token: write', '["gates","sign"]'],
    ['${{ fromJSON(vars.PERMS) }}', '["gates","sign"]'],
    ['{contents: read, nested: {a: b}}', '["gates","sign"]'],
  ] as const) {
    const got = JSON.stringify(inlinePerms(inline));
    check(got === want, `signingJobs on job permissions: ${inline} -> ${got}, want ${want}`);
  }
  check(
    JSON.stringify(
      signingJobs(
        permWf('').replace(
          '    permissions:\n      contents: read\n',
          '    permissions:\n      write-all\n'
        )
      )
    ) === '["gates","sign"]',
    'CONTROL: a write-all scalar on the line after permissions: names the job (review e7ce4979.1)'
  );
  check(
    JSON.stringify(
      signingJobs(
        permWf('      packages: read').replace('permissions: {}', 'permissions: {id-token: write}')
      )
    ) === '["<workflow>","sign"]',
    'signingJobs fires on a top-level flow-style id-token: write'
  );
  check(
    JSON.stringify(signingJobs(permWf('      \'id-token\': "write"'))) === '["gates","sign"]',
    'signingJobs fires on a block-style grant with quoted key and value'
  );
  check(
    JSON.stringify(
      signingJobs(
        permWf('      packages: read').replace('permissions: {}', 'permissions:\n  id-token: write')
      )
    ) === '["<workflow>","sign"]',
    'signingJobs fires on a top-level id-token: write'
  );
  check(
    !UNSIGNED_ARTIFACT.startsWith(ARTIFACT_PREFIX),
    `UNSIGNED_ARTIFACT ${UNSIGNED_ARTIFACT} must stay outside the fetch pattern ${ARTIFACT_PREFIX}*`
  );
  return { failures, count };
}

/** Runs a copy of this file with STORE_GUARD_LINE neutralized; its core cases must fail. */
function mutantRed(): { ok: boolean; detail: string } {
  const self = import.meta.filename;
  const src = fs.readFileSync(self, 'utf8');
  const occurrences = src.split(STORE_GUARD_LINE).length - 1;
  // Twice: once in the code, once in the constant naming it.
  if (occurrences !== 2)
    return {
      ok: false,
      detail: `the store guard line occurs ${occurrences} time(s), expected 2 (code and constant)`,
    };
  const at = src.indexOf(STORE_GUARD_LINE);
  const dir = path.dirname(self);
  const mutated = (
    src.slice(0, at) +
    '  if (false) return { stored: false, field: verdict.field, detail: verdict.detail };' +
    src.slice(at + STORE_GUARD_LINE.length)
  ).replace(/from '(\.{1,2}\/[^']+)'/g, (_m, rel: string) => `from '${path.resolve(dir, rel)}'`);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-receipt-mutant-'));
  try {
    const copy = path.join(tmp, 'ci-receipt.ts');
    fs.writeFileSync(copy, mutated);
    const tsx = path.join(REPO_ROOT, 'node_modules', '.bin', 'tsx');
    const r = spawnSync(tsx, [copy, '--selftest-core'], { encoding: 'utf8', timeout: 120_000 });
    const out = `${r.stdout ?? ''}${r.stderr ?? ''}`;
    if (r.error) return { ok: false, detail: `the mutant could not start: ${r.error.message}` };
    const red = r.status === 1 && out.includes('never stored');
    return { ok: red, detail: `exit ${r.status}: ${out.trim().split('\n').slice(-2).join(' | ')}` };
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function selftest(core: boolean): number {
  const { failures, count } = coreCases();
  let total = count;
  if (!core) {
    // The loader pin: run.ts reads every *.json under receipts/ beside the destination, which is where the prior is written.
    const runSrc = fs.readFileSync(path.join(REPO_ROOT, 'scripts', 'ci-runner', 'run.ts'), 'utf8');
    total++;
    if (
      !/const dir = path\.join\(path\.dirname\(dest\), 'receipts'\);[\s\S]{0,200}\.filter\(\(n\) => n\.endsWith\('\.json'\)\)/.test(
        runSrc
      )
    )
      failures.push(
        'run.ts loadPriorReceipts no longer reads every *.json under receipts/, so a ci-<tree>.json prior would not be loaded'
      );
    // The real workflow: the lane's steps parse, so the writer is not blind on the tree it will run against.
    const real = jobSteps(
      fs.readFileSync(path.join(REPO_ROOT, QUALITY_WORKFLOW), 'utf8'),
      'quality-content'
    );
    total++;
    if (real === null || real.filter((s) => s.name !== null).length < 10)
      failures.push(
        `the real quality-content job parses to ${real?.length ?? 0} step(s); the writer would be reading nothing`
      );
    // The real receipt step: under the standard guard, so the writer accepts it, and wired to read its own job record.
    total++;
    const realLo = laneOutcomes(real ?? [], {
      runId: '1',
      attempt: '1',
      steps: [{ name: RECEIPT_STEP, status: 'in_progress', conclusion: null }],
    });
    const contentBody = (
      jobBody(fs.readFileSync(path.join(REPO_ROOT, QUALITY_WORKFLOW), 'utf8'), 'quality-content') ??
      []
    ).map((l) => l.trim());
    const wired = [
      'actions: read',
      'RECEIPT_JOB_ID: ${{ job.check_run_id }}',
      'GH_TOKEN: ${{ github.token }}',
    ].filter((l) => !contentBody.includes(l));
    if ('error' in realLo || wired.length > 0)
      failures.push(
        `the real quality-content receipt step: ${'error' in realLo ? realLo.error : 'accepted'}; missing from the job: ${wired.join(' | ') || 'none'}`
      );
    // The real signer split: the gate lane holds no signing permission; one job signs, runs no repo code, and is the only producer of ARTIFACT_PREFIX.
    const wfText = fs.readFileSync(path.join(REPO_ROOT, QUALITY_WORKFLOW), 'utf8');
    total++;
    const signers = signingJobs(wfText);
    if (JSON.stringify(signers) !== JSON.stringify([SIGNER_JOB]))
      failures.push(
        `${QUALITY_WORKFLOW}: jobs granting id-token/attestations write are [${signers.join(', ')}], expected exactly [${SIGNER_JOB}]. A gate job holding either can mint an OIDC token or sign provenance from checked-out repo code; move the signing step into ${SIGNER_JOB}.`
      );
    total++;
    const body = jobBody(wfText, SIGNER_JOB) ?? [];
    const repoCode = body.filter((l) => /^\s+(- )?(run:|uses: (actions\/checkout|\.\/))/.test(l));
    if (body.length < 5 || repoCode.length > 0)
      failures.push(
        `${SIGNER_JOB} must exist and run no repo code (no run:, no checkout, no local action); found ${body.length} line(s), offending: ${repoCode.map((l) => l.trim()).join(' | ') || 'none'}`
      );
    total++;
    const producers = (wfText.match(new RegExp(`^\\s+name: ${ARTIFACT_PREFIX}`, 'gm')) ?? [])
      .length;
    const signerProduces = body.some((l) => l.trim().startsWith(`name: ${ARTIFACT_PREFIX}`));
    const unsignedUp = (jobBody(wfText, 'quality-content') ?? []).some(
      (l) => l.trim() === `name: ${UNSIGNED_ARTIFACT}`
    );
    if (producers !== 1 || !signerProduces || !unsignedUp)
      failures.push(
        `artifact wiring: ${producers} upload(s) named ${ARTIFACT_PREFIX}* (expected 1, in ${SIGNER_JOB}: ${signerProduces}); quality-content uploads ${UNSIGNED_ARTIFACT}: ${unsignedUp}`
      );
    const m = mutantRed();
    total++;
    if (!m.ok)
      failures.push(
        `MUTANT CONTROL: storing without the verifier's answer must turn the core cases red, got ${m.detail}`
      );
  }
  for (const f of failures) process.stderr.write(`  FAIL ${f}\n`);
  if (failures.length > 0) {
    process.stderr.write(`ci-receipt selftest: ${failures.length} of ${total} case(s) failed\n`);
    return 1;
  }
  process.stdout.write(
    `ci-receipt selftest: ${total} case(s) passed${core ? ' (core)' : ', mutant control red as required'}\n`
  );
  return 0;
}

export function main(argv: string[]): number {
  const [verb, ...rest] = argv;
  if (verb === '--selftest') return selftest(false);
  if (verb === '--selftest-core') return selftest(true);
  if (verb === 'write') return write(rest);
  if (verb === 'fetch') return fetchVerb(rest);
  if (verb === 'verify') return verifyVerb(rest);
  process.stderr.write(
    'usage: ci-receipt.ts --selftest | write --lane <job> --out <file> | fetch [--branch <b>] [--limit <n>] | verify <file>\n'
  );
  return 2;
}

if (isEntryPoint(import.meta.filename)) process.exit(main(process.argv.slice(2)));
