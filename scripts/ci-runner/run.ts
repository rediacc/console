#!/usr/bin/env tsx
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
/**
 * `npm run ci`, as a parallel worker pool over the gate manifest.
 *
 * WHAT THIS REPLACED AND WHY. package.json `scripts.ci` was a 93-step `&&`
 * string, measured at 1041.6 s serial on a 20-core box. Two properties of that
 * shape were costing real time and real signal:
 *
 *   - `&&` is fail-fast, so one red hid every other red. check:i18n alone
 *     chains 19 leaf gates that way. CI fixed the same defect at lane level by
 *     putting `!cancelled()` on every quality step; the runner defaults to
 *     keep-going for the same reason, and --fail-fast is the opt-in.
 *   - check:ci-quality-gates was 443 s of that total, 43%, as one opaque unit
 *     wrapping the battery. Scheduling it whole caps the speedup at 2.4x no
 *     matter how many cores exist, which is why its 57 tests are individually
 *     scheduled manifest entries.
 *
 * Usage:
 *   tsx scripts/ci-runner/run.ts [--jobs N] [--heavy-limit N] [--sched slots|cores] [--fail-fast]
 *                                [--only <glob,...>] [--skip <glob,...>]
 *                                [--changed] [--json] [--list]
 *                                [--merge-output] [--verbose] [--selftest]
 *                                [--lane <lane> --shard i/N]
 *
 * `--lane <lane> --shard i/N` (PLAN-ci-time-budget T2.10) replays one committed CI leg of
 * a sharded lane locally, from `.ci/config/shards/<lane>.json`. Today this only resolves
 * for a gate-backed lane (`quality-code`); a test lane's manifest names test-runner units,
 * which this pool does not execute (see `resolveLaneShard`'s own refusal).
 *
 * `--quick` is ONE PASS (agent/plans/PLAN-prepush-full-cpu.md part 2): the fast gates plus every slow gate the change set since the last push touches, scheduled together, so the long ones start at t=0. When HEAD has moved since the receipt only through record paths (`.ci/policy/record-paths.json`), it runs only their readers and appends an `advances` step to the receipt instead (`planAdvance`).
 *
 * Every gate is told its width at launch: `CI_RUNNER_CORES` (exec.ts `gateEnv`), sized by the area rule for a gate declaring `cores: {min, max}` (pool.ts `elasticGrant`), and the run draws its cores from the machine-wide lease when core_lease.py offers a broker (lease-client.ts).
 *
 * `--sched cores` (env CI_SCHED), the DEFAULT since 2026-09-30, packs gates against a core budget from their measured CPU instead of one slot each; `slots` is the pool's original rule, kept for A/B and rollback. Five alternating pairs on 24 cores: wall/floor 1.04-1.09 against 1.14-1.16, idle core-seconds median 69 against 89, check:test-shared starting at 13 s against 40 s. See agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.2 and pool.ts admit().
 *
 * See agent/plans/PLAN-npm-ci-parallel-parity.md section 4.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CORES_ENV, execGate, type Grant, gateEnv, LEASE_HELD_ENV } from './exec';
import { findingsSelftest, receiptFindings } from './findings';
import { retiredFieldFindings } from './gate-spec';
import { stepDurationsMs } from './lanes';
import { grantFromEnv, leaseClientSelftest, openLease, type RunnerLease } from './lease-client';
import { GATES, type GateSpec } from './manifest';
import {
  buildGraph,
  type CoreBudget,
  type GateCost,
  type GateResult,
  type PoolLease,
  runPool,
  type Sched,
} from './pool';
import {
  admitTouched,
  type DropKind,
  quickSelectSelftest,
  resolvePushBase,
  type SlowCandidate,
  touchedSlow,
} from './quick-select';
import {
  type CpuTick,
  createReporter,
  criticalPath,
  type GateTiming,
  timelineOf,
  type Utilisation,
  utilisation,
} from './report';
import { type ChangeSet, ChangeSetRefusal, selectChanged } from './select';
import { legIds, parseShardManifest, shardManifestPath } from './shard-manifest';
import { schedulerSelftest } from './sim';
import { unitsFrom } from './unit-enumerators';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
// Per-gate process-tree profiling (agent/plans/PLAN-shell-resource-profiling.md). ON by default: captures land in .ci/cache/profiles (untracked), and the previous run's set is rotated to profiles.prev at start so check:ci-resprofile judges COMPLETE captures,
// never the torn files of gates still running. CI_PROFILE=off disables it; CI_PROFILE_DIR
// redirects it. One run id per process so the E4 cross-gate join can pair captures.
const PROFILE_OPTS = ((): { profileDir?: string; profileRunId?: string } => {
  if (process.env.CI_PROFILE === 'off') return {};
  try {
    // A NESTED RUNNER MUST NOT ROTATE. gate-test:ci-runner runs this very file as a gate, so without this the inner run rotated the pointer and aimed it at its own two selftest captures -- last writer wins, and a full 292-gate run left a profiles.current naming a directory with two files in it. The inner run inherits the outer run's directory and id and simply writes beside it.
    const inherited = process.env.CI_PROFILE_RUN;
    if (inherited !== undefined && inherited !== '') {
      const [id, ...rest] = inherited.split('\u0000');
      return { profileDir: rest.join('\u0000'), profileRunId: id };
    }
    const runId = `ci-${process.pid}-${Date.now()}`;
    let dir = process.env.CI_PROFILE_DIR;
    if (!dir) {
      // Time-based, durable, outside the tree: one folder per day, one per run.
      const slug = REPO_ROOT.replace(/^\/+/, '').replace(/\//g, '-');
      const day = new Date().toISOString().slice(0, 10);
      dir = path.join(os.homedir(), '.claude', 'resprofile', slug, day, runId);
    }
    fs.mkdirSync(dir, { recursive: true });
    const cache = path.join(REPO_ROOT, '.ci', 'cache');
    fs.mkdirSync(cache, { recursive: true });
    const pointer = path.join(cache, 'profiles.current');
    const prev = path.join(cache, 'profiles.prev');
    if (fs.existsSync(pointer)) fs.writeFileSync(prev, fs.readFileSync(pointer));
    fs.writeFileSync(pointer, dir);
    process.env.CI_PROFILE_RUN = `${runId}\u0000${dir}`;
    return { profileDir: dir, profileRunId: runId };
  } catch {
    return {}; // profiling is best-effort by contract
  }
})();
const DEFAULT_CACHE = path.join(REPO_ROOT, '.ci', 'cache', 'gate-durations.json');
const EWMA_ALPHA = 0.3;

interface Options {
  jobs?: number;
  heavyLimit?: number;
  /** `--sched` / CI_SCHED; undefined means the default, `cores`. */
  sched?: Sched;
  failFast: boolean;
  json: boolean;
  list: boolean;
  changed: boolean;
  quick: boolean;
  mergeOutput: boolean;
  selftest: boolean;
  verbose: boolean;
  only?: string[];
  skip?: string[];
  manifest?: string;
  /** T2.10 `--lane <lane> --shard i/N`: replay exactly one committed shard's ids, in place of `--only`. Both or neither. */
  lane?: string;
  shard?: { index: number; of: number };
  /** `--receipt-out`: where to write the push receipt instead of this checkout's own `.ci/cache/`. */
  receiptOut?: string;
}

/** Every flag off. Selftest-only, so a control states the flag it exercises
 *  and nothing else; spelling one out per case invites a typo that silently
 *  changes what is under test. */
const EMPTY_OPTS: Options = {
  failFast: false,
  json: false,
  list: false,
  changed: false,
  quick: false,
  mergeOutput: false,
  selftest: false,
  verbose: false,
};

/** A scheduler name, refused loudly when misspelt: a typo that silently fell back to the default would make an A/B compare slots with slots. */
function schedFrom(raw: string, flag: string): Sched {
  if (raw === 'slots' || raw === 'cores') return raw;
  throw new Error(`ci-runner: ${flag} needs 'slots' or 'cores', got '${raw}'`);
}

function parseArgs(argv: readonly string[]): Options {
  const opts: Options = {
    failFast: false,
    json: false,
    list: false,
    changed: false,
    quick: false,
    mergeOutput: false,
    selftest: false,
    verbose: false,
    manifest: process.env.CI_RUNNER_MANIFEST,
  };
  const value = (i: number, flag: string): string => {
    const v = argv[i + 1];
    if (v === undefined) throw new Error(`ci-runner: ${flag} needs a value`);
    return v;
  };
  const number = (raw: string, flag: string): number => {
    const n = Number(raw);
    if (!Number.isInteger(n) || n < 1)
      throw new Error(`ci-runner: ${flag} needs a positive integer, got '${raw}'`);
    return n;
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case '--jobs':
        opts.jobs = number(value(i, arg), arg);
        i += 1;
        break;
      case '--heavy-limit':
        opts.heavyLimit = number(value(i, arg), arg);
        i += 1;
        break;
      case '--sched':
        opts.sched = schedFrom(value(i, arg), arg);
        i += 1;
        break;
      case '--only':
        // APPENDS, and used to ASSIGN. A repeated flag silently discarded every earlier one, so `--only a --only b` ran ONLY b, printed `ci-runner: 1 gate` and exited green. The operator believes two gates passed; one did, and the other was never scheduled. That is a vacuous green produced by the selector rather than by a gate, which is the worse of the two because nothing in the
        // output names a missing gate. The `1 gate` header line was the only tell and it reads as a count, not as a warning. Found 2026-09-06 by an agent that passed eleven separate --only flags and was told it had run one gate, ok. Comma-separated remains the documented spelling and still works.
        opts.only = [...(opts.only ?? []), ...value(i, arg).split(',').filter(Boolean)];
        i += 1;
        break;
      case '--skip':
        // Appends for the same reason as --only above: a dropped --skip is a gate that RUNS when the operator asked for it not to, which on a machine-mutex gate is worse than a dropped --only.
        opts.skip = [...(opts.skip ?? []), ...value(i, arg).split(',').filter(Boolean)];
        i += 1;
        break;
      case '--manifest':
        opts.manifest = value(i, arg);
        i += 1;
        break;
      case '--lane':
        opts.lane = value(i, arg);
        i += 1;
        break;
      case '--shard': {
        const raw = value(i, arg);
        const m = /^(\d+)\/(\d+)$/.exec(raw);
        if (m === null) {
          throw new Error(`ci-runner: --shard needs "i/N" (1-based), got '${raw}'`);
        }
        const index = Number(m[1]);
        const of = Number(m[2]);
        if (index < 1 || index > of) {
          throw new Error(`ci-runner: --shard ${raw}: index must be between 1 and ${of}`);
        }
        opts.shard = { index, of };
        i += 1;
        break;
      }
      case '--fail-fast':
        opts.failFast = true;
        break;
      case '--json':
        opts.json = true;
        break;
      case '--list':
        opts.list = true;
        break;
      case '--quick':
        opts.quick = true;
        break;
      case '--changed':
        opts.changed = true;
        break;
      case '--merge-output':
        opts.mergeOutput = true;
        break;
      case '--selftest':
        opts.selftest = true;
        break;
      case '--verbose':
        opts.verbose = true;
        break;
      case '--receipt-out': {
        // A CLEAN-SNAPSHOT RECEIPT. The gates judge the worktree they run in, and the push carries HEAD^{tree}. In a tree shared with live writers, their uncommitted edits turn a receipt red for a tree that does not contain them (2026-09-24: 14 writers, python-lint red on two files in nobody's HEAD). Running ci:quick in a clean clone checked out at HEAD
        // and writing the receipt into the pushing checkout's cache judges exactly the pushed tree. Nothing is trusted: the receipt still records the clone's own HEAD^{tree}, and block_unverified_push refuses unless that equals the pushing HEAD^{tree}. ABSOLUTE ONLY, because a relative path would resolve against whichever cwd npm happened to use.
        const out = value(i, arg);
        if (!path.isAbsolute(out))
          throw new Error(`ci-runner: ${arg} needs an absolute path, got '${out}'`);
        opts.receiptOut = out;
        i += 1;
        break;
      }
      default:
        throw new Error(`ci-runner: unknown flag '${arg}'`);
    }
  }
  if (opts.jobs === undefined && process.env.CI_JOBS !== undefined) {
    opts.jobs = number(process.env.CI_JOBS, 'CI_JOBS');
  }
  if (
    opts.sched === undefined &&
    process.env.CI_SCHED !== undefined &&
    process.env.CI_SCHED !== ''
  ) {
    opts.sched = schedFrom(process.env.CI_SCHED, 'CI_SCHED');
  }
  if ((opts.lane === undefined) !== (opts.shard === undefined)) {
    throw new Error('ci-runner: --lane and --shard are both required together, or neither.');
  }
  return opts;
}

async function loadManifest(source: string | undefined): Promise<readonly GateSpec[]> {
  if (source === undefined) return GATES;
  const abs = path.resolve(REPO_ROOT, source);
  if (abs.endsWith('.json')) {
    const parsed: unknown = JSON.parse(fs.readFileSync(abs, 'utf-8'));
    if (!Array.isArray(parsed))
      throw new Error(`ci-runner: ${source} must contain an array of gate specs`);
    return parsed as GateSpec[];
  }
  const mod: unknown = await import(abs);
  const gates = (mod as { GATES?: unknown }).GATES;
  if (!Array.isArray(gates)) throw new Error(`ci-runner: ${source} does not export GATES`);
  return gates as GateSpec[];
}

/**
 * `*`, `**` and `?`; enough for gate ids and repo-relative path globs.
 * One pass, because a two-pass version needs a placeholder byte that cannot
 * occur in the input, and any such byte is invisible in the source.
 *
 * `**\/` MEANS ZERO OR MORE DIRECTORIES, and it used to mean "at least one".
 * `**` alone expanded to `.*`, so `**\/*.sh` compiled to `^.*\/[^/]*\.sh$` --
 * a pattern REQUIRING a literal slash. Measured 2026-08-27: `run.sh` and
 * `rdc.sh` are both tracked, both matched by `git ls-files '*.sh'` (which is
 * how check-shell-size.sh actually enumerates), and neither matched this
 * regex. So a diff touching only `run.sh` silently dropped the gate that
 * would have judged it.
 *
 * That is the narrowing direction, which is the dangerous one: the glob did
 * not fail loudly, it quietly covered less than its author wrote. The
 * `**\/` -> `(?:.*\/)?` form is handled before the bare `**` so the optional
 * separator is part of the token rather than left behind.
 */
export function globToRegExp(glob: string): RegExp {
  const body = glob.replace(/\*\*\/|\*\*|[*?.+^${}()|[\]\\]/g, (token) => {
    if (token === '**/') return '(?:.*/)?';
    if (token === '**') return '.*';
    if (token === '*') return '[^/]*';
    if (token === '?') return '.';
    return `\\${token}`;
  });
  return new RegExp(`^${body}$`);
}

function matchesAny(text: string, globs: readonly string[]): boolean {
  return globs.some((g) => globToRegExp(g).test(text));
}

/**
 * A CHANGED SUBMODULE IS ONE DIFF ENTRY, NOT A LIST OF FILES.
 *
 * `git diff --name-only` reports a gitlink as the submodule PATH -- measured
 * on this branch, `private/account` and nothing beneath it, mode 160000. So a
 * glob like `private/account/**` can never match a real submodule change, and
 * any gate scoped that way is dead by construction rather than by mistake.
 *
 * Widen instead of narrowing: keep the gitlink entry (so a glob naming the
 * submodule path itself still matches) and add a bare wildcard beneath it. A
 * caller that can read the submodule gets the real file list; one that cannot
 * still gets the wildcard, so the failure direction is INCLUSION. That matters
 * more here than precision -- a missed file silently drops a gate, an extra
 * one costs a few seconds.
 */
/** The first submodule path recorded in HEAD, for the selftest's precondition. */
function firstGitlink(): string | undefined {
  try {
    for (const line of execFileSync(
      'git',
      ['ls-tree', '-r', '--format=%(objectmode) %(path)', 'HEAD'],
      {
        cwd: REPO_ROOT,
        encoding: 'utf-8',
        maxBuffer: 64 * 1024 * 1024,
      }
    ).split('\n')) {
      if (line.startsWith('160000 ')) return line.slice('160000 '.length);
    }
  } catch {
    /* reported by the caller as a failed precondition */
  }
  return undefined;
}

/**
 * Every gitlink (submodule) path in HEAD, from ONE `git ls-tree`. Asking per changed file spawned one git process per path: a
 * 60-commit branch paid about 12 s in process start-up alone, and check:ci-changed-selection's all-files change set about 50 s
 * (2026-09-26, profiled: 11.6 s of 12.6 s inside spawnSync). An unreadable tree answers "no gitlinks", the same answer the
 * per-file probe gave on failure.
 */
function headGitlinks(): Set<string> {
  try {
    const out = execFileSync('git', ['ls-tree', '-r', '--format=%(objectmode) %(path)', 'HEAD'], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      maxBuffer: 64 * 1024 * 1024,
    });
    const links = new Set<string>();
    for (const line of out.split('\n')) {
      if (line.startsWith('160000 ')) links.add(line.slice('160000 '.length));
    }
    return links;
  } catch {
    return new Set();
  }
}

function expandGitlinks(named: readonly string[], warn: (text: string) => void): string[] {
  const out = new Set<string>(named);
  const gitlinks = headGitlinks();
  for (const entry of named) {
    if (!gitlinks.has(entry)) continue;
    // The wildcard goes in FIRST, so a submodule we cannot read still selects every gate scoped beneath it rather than none.
    out.add(`${entry}/**`);
    try {
      const inner = execFileSync('git', ['-C', entry, 'diff', '--name-only', 'HEAD'], {
        cwd: REPO_ROOT,
        encoding: 'utf-8',
      })
        .split('\n')
        .filter(Boolean);
      for (const f of inner) out.add(`${entry}/${f}`);
    } catch {
      warn(`ci-runner: could not read inside ${entry}; kept ${entry}/** as a wildcard\n`);
    }
  }
  return [...out];
}

/**
 * The change set, WITH its provenance. It used to return a bare `string[]` and
 * swallow a git failure into `[]` under a warning that said "selecting every gate"
 * -- which was false, because `select()` then dropped every path-declaring gate for
 * want of a match. See scripts/ci-runner/select.ts for the measurement.
 */
function changedFiles(): ChangeSet {
  const base = process.env.CI_RUNNER_BASE ?? 'origin/main';
  try {
    const mergeBase = execFileSync('git', ['merge-base', 'HEAD', base], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
    const named = execFileSync('git', ['diff', '--name-only', mergeBase], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    })
      .split('\n')
      .filter(Boolean);
    // expandGitlinks warns through stderr directly; a submodule it cannot read widens to a wildcard rather than narrowing, so the set stays inclusive.
    return {
      files: expandGitlinks(named, (t) => process.stderr.write(t)),
      origin: 'resolved',
      base,
    };
  } catch (err) {
    return {
      files: [],
      origin: 'unresolved',
      base,
      reason: err instanceof Error ? err.message.split('\n')[0] : String(err),
    };
  }
}

interface Selection {
  ids: Set<string>;
  /** Human description when the run is partial; undefined for a full run. */
  description?: string;
  /** Slow gates the `--quick` diff admitted into this pass, for the receipt's `slowAdmitted`; empty when none or not quick. */
  slowAdmitted?: string[];
  /** Slow gates the diff touched and the lane still dropped, for the receipt; undefined when not quick. */
  droppedTouched?: DroppedTouched[];
  /** The base the `--quick` diff was taken against, for the receipt; undefined when not quick. */
  pushBase?: PushBaseRecord;
  /** Tree-writing slow gates admitted because this is a clean, disposable clone; named by the stable-tree warning. */
  treeWritersAdmitted?: string[];
}

/**
 * A slow gate the change set touched that the quick lane did not run. It is recorded in the receipt so the push guard can refuse until a `--only` run of it passes (`droppedVerified`): on 2026-10-03 a dropped `check:ci-plan-record` was printed, then lost, and CI run 37129843955 went red on exactly that gate.
 */
interface DroppedTouched {
  id: string;
  /** How the change set reached the gate (quick-select.ts `touchedSlow`). */
  why: string;
  /** Why the lane dropped it. */
  reason: string;
  kind: DropKind;
  /** The exact command that runs it and records the result in this receipt. */
  run: string;
}

/** One passing or failing `--only` run of a dropped gate, merged into the whole receipt of the same tree. */
interface DroppedVerification {
  exitCode: number;
  headTree: string;
  finishedAt: string;
  judgedRoot: string;
  stable: boolean;
}

interface PushBaseRecord {
  ref: string | null;
  via: string | null;
  mergeBase: string | null;
  warnings: string[];
}

const LANE_DURATIONS = path.join(REPO_ROOT, '.ci', 'config', 'lane-durations.json');

function gitTry(args: readonly string[]): string | undefined {
  try {
    return execFileSync('git', [...args], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
      maxBuffer: 64 * 1024 * 1024,
    }).trim();
  } catch {
    return undefined;
  }
}

interface PushDiff {
  /** Undefined when no base resolved; `tried` then names every ref attempted. */
  files?: string[];
  label: string;
  scriptsBase?: Record<string, string>;
  /** Tracking refs skipped because they name another branch (quick-select.ts `resolvePushBase`). */
  warnings?: string[];
  pushBase?: PushBaseRecord;
}

/**
 * Files changed since the last push: the merge-base with the first resolvable ref of quick-select.ts `resolvePushBase`, against the WORKTREE, plus untracked files and widened gitlinks. The quick lane judges the worktree, so committed, staged, unstaged and new files all count.
 */
function changedSinceLastPush(): PushDiff {
  const branch = gitTry(['branch', '--show-current']);
  const base = resolvePushBase(gitTry, branch);
  const warned = base.warnings.length > 0 ? `; ${base.warnings.join('; ')}` : '';
  const pushBase: PushBaseRecord = {
    ref: base.ref ?? null,
    via: base.via ?? null,
    mergeBase: base.mergeBase ?? null,
    warnings: [...base.warnings],
  };
  if (base.mergeBase === undefined) {
    return {
      label: `UNRESOLVED (tried ${base.tried.join(', ')}${warned})`,
      warnings: [...base.warnings],
      pushBase,
    };
  }
  const named = (gitTry(['diff', '--name-only', base.mergeBase]) ?? '').split('\n').filter(Boolean);
  const untracked = (gitTry(['ls-files', '--others', '--exclude-standard']) ?? '')
    .split('\n')
    .filter(Boolean);
  const files = expandGitlinks([...new Set([...named, ...untracked])], (t) =>
    process.stderr.write(t)
  );
  let scriptsBase: Record<string, string> | undefined;
  try {
    const raw = gitTry(['show', `${base.mergeBase}:package.json`]);
    if (raw !== undefined)
      scriptsBase = (JSON.parse(raw) as { scripts?: Record<string, string> }).scripts;
  } catch {
    scriptsBase = undefined;
  }
  return {
    files,
    label: `${base.ref} via ${base.via}, merge-base ${base.mergeBase.slice(0, 9)}${warned}`,
    scriptsBase,
    warnings: [...base.warnings],
    pushBase,
  };
}

/** `{gate id: CI step p90 ms}` from lane-durations.json, the committed CI timing; empty when unreadable. The scheduler's wall estimate for a gate this machine has never timed, so a long gate seen only in CI still starts in the first wave. */
function ciStepP90(): Map<string, number> {
  try {
    return new Map(
      Object.entries(stepDurationsMs(JSON.parse(fs.readFileSync(LANE_DURATIONS, 'utf-8'))))
    );
  } catch {
    /* priced from the local cache alone */
    return new Map();
  }
}

/** The tree write a gate declares (`writesTree`, else its `tree:` mutex claim), or undefined. */
function treeWriteOf(spec: GateSpec | undefined): string | undefined {
  if (spec === undefined) return undefined;
  return spec.writesTree ?? (spec.mutex ?? []).find((m) => m.startsWith('tree:'));
}

/** Why the quick lane will not admit a gate at any price, or undefined. Only tree writers today, and only outside a clean, disposable clone; see quick-select.ts THE TREE. */
function treeWriteRefusal(spec: GateSpec | undefined, disposable = false): string | undefined {
  const write = treeWriteOf(spec);
  if (write === undefined || disposable) return undefined;
  return `it writes the shared tree (${write}), which the quick lane does not do`;
}

/**
 * A clean, disposable clone: the receipt goes OUTSIDE this checkout (`--receipt-out`, the push clone's shape) and `git status --porcelain` is empty, so no other session reads this tree and a tree writer may run in it.
 */
function isDisposableClone(opts: Options): boolean {
  if (opts.receiptOut === undefined) return false;
  const rel = path.relative(REPO_ROOT, path.resolve(opts.receiptOut));
  if (!(rel.startsWith('..') || path.isAbsolute(rel))) return false;
  const porcelain = gitTry(['status', '--porcelain']);
  return porcelain === '';
}

function select(
  specs: readonly GateSpec[],
  opts: Options,
  warn: (text: string) => void,
  quickDeps?: QuickDiffDeps
): Selection {
  const notes: string[] = [];
  let selectedSlow: string[] = [];
  let droppedTouched: DroppedTouched[] | undefined;
  let pushBase: PushBaseRecord | undefined;
  let treeWritersAdmitted: string[] | undefined;
  // gate:false nodes are prerequisites, never selected on their own. They enter the run only through the needs-closure in buildGraph.
  let chosen = specs.filter((spec) => spec.gate);

  if (opts.changed) {
    // BOTH HALVES LIVE IN select.ts. Fail OPEN on scope -- an entry with no declared `paths` is selected for every non-empty change set, because the overwhelming majority of gates declare none and a half-populated path table would drop them silently. REFUSE an unusable change set -- an empty file list is the one input
    // for which fail-open inverts into fail-closed, and "nothing changed" and "the
    // differ broke" arrive in exactly that shape.
    //
    // THE RATIO IS NOT WRITTEN DOWN HERE ON PURPOSE. It moved twice in one session (474/46 to 475/46) while this box was being written, and a number quoted in a comment is a number nobody recomputes. `check:ci-changed-selection` derives it
    // from the lock and PRINTS it on every run, and asserts both halves against the
    // real invocation.
    const result = selectChanged(chosen, changedFiles(), matchesAny);
    chosen = [...result.chosen];
    notes.push(result.note);
  }
  if (opts.quick) {
    // THE LANE IS A FIXPOINT, not a filter. A cheap gate whose `needs` closure reaches a slow prerequisite costs that prerequisite's time, so it is not cheap -- buildGraph pulls prereqs in transitively and would have made the "10 second" lane silently cost minutes. Demote until nothing moves.
    const byId = new Map(specs.map((spec) => [spec.id, spec]));
    const slow = new Set(specs.filter((spec) => spec.slow === true).map((spec) => spec.id));
    for (;;) {
      const before = slow.size;
      for (const spec of specs) {
        if (slow.has(spec.id)) continue;
        if ((spec.needs ?? []).some((n) => slow.has(n))) slow.add(spec.id);
      }
      if (slow.size === before) break;
    }
    // NAME THE DEMOTIONS. A gate that silently left the lane is coverage lost without a record, which is the vacuity this whole design is against.
    const demoted = specs
      .filter((spec) => spec.gate && spec.slow !== true && slow.has(spec.id))
      .map((spec) => {
        const via = (spec.needs ?? []).filter((n) => slow.has(n));
        return `${spec.id} (needs ${via.join(', ')})`;
      });
    // DIFF-SELECTED SLOW GATES (quick-select.ts). Every slow gate the change set since the last push touches joins this one pass; every other slow gate stays deferred and is named as such.
    const slowCandidates = chosen.filter((spec) => slow.has(spec.id));
    const verdict = quickDiffAdmit(slowCandidates, specs, opts, warn, quickDeps);
    const admitted = verdict.admitted;
    selectedSlow = admitted;
    droppedTouched = verdict.droppedTouched;
    pushBase = verdict.pushBase;
    treeWritersAdmitted = verdict.treeWritersAdmitted;
    const admittedSet = new Set(admitted);
    chosen = chosen.filter((spec) => !slow.has(spec.id) || admittedSet.has(spec.id));
    notes.push(
      `--quick (${chosen.length - admitted.length} fast gate(s) + ${admitted.length} diff-selected slow; ${slow.size - admitted.length} deferred)`
    );
    if (demoted.length > 0) {
      warn(
        `ci-runner: --quick DEFERRED ${demoted.length} otherwise-fast gate(s) whose prerequisites are slow:\n` +
          demoted.map((d) => `  - ${d}\n`).join('')
      );
    }
    if (byId.size === 0) warn('ci-runner: --quick saw an empty manifest\n');
  }
  if (opts.only !== undefined) {
    chosen = chosen.filter((spec) => matchesAny(spec.id, opts.only ?? []));
    notes.push(`--only ${opts.only.join(',')}`);
  }
  if (opts.skip !== undefined) {
    chosen = chosen.filter((spec) => !matchesAny(spec.id, opts.skip ?? []));
    notes.push(`--skip ${opts.skip.join(',')}`);
  }

  const ids = new Set(chosen.map((spec) => spec.id));
  return {
    ids,
    description: notes.length > 0 ? notes.join(' ') : undefined,
    slowAdmitted: selectedSlow.filter((id) => ids.has(id)),
    droppedTouched,
    pushBase,
    treeWritersAdmitted: treeWritersAdmitted?.filter((id) => ids.has(id)),
  };
}

/** Injected seams for the selftest; the real run reads git and package.json. */
interface QuickDiffDeps {
  diff: () => PushDiff;
  scriptsNow: () => Record<string, string>;
  /** A clean, disposable clone, where tree writers are admitted (`isDisposableClone`). */
  disposable: () => boolean;
}

function realQuickDiffDeps(opts: Options): QuickDiffDeps {
  return {
    diff: changedSinceLastPush,
    scriptsNow: () =>
      (
        JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'package.json'), 'utf-8')) as {
          scripts?: Record<string, string>;
        }
      ).scripts ?? {},
    disposable: () => isDisposableClone(opts),
  };
}

/**
 * The slow candidates the change set since the last push touches, every one admitted into this pass except a tree writer outside a disposable clone. Prints the whole shape: the base, the file count, every admitted gate with why, every dropped gate with why and how to run it, and the untouched deferred set by name.
 */
function quickDiffAdmit(
  candidates: readonly GateSpec[],
  specs: readonly GateSpec[],
  opts: Options,
  warn: (text: string) => void,
  injected?: QuickDiffDeps
): {
  admitted: string[];
  droppedTouched: DroppedTouched[];
  pushBase?: PushBaseRecord;
  treeWritersAdmitted: string[];
} {
  const deps = injected ?? realQuickDiffDeps(opts);
  const diff = deps.diff();
  const deferredLine = (ids: readonly string[]): string =>
    ids.length === 0 ? '' : `  deferred, untouched (${ids.length}): ${ids.join(', ')}\n`;
  const warningLines = (diff.warnings ?? [])
    .map((w) => `  WARNING: the push base skipped a tracking ref: ${w}\n`)
    .join('');
  if (diff.files === undefined) {
    warn(
      `ci-runner: --quick could not find the last push: ${diff.label}. NO slow gate was diff-selected, so all ${candidates.length} stay deferred; push the branch, or fetch origin/main so the fallback resolves.\n` +
        warningLines +
        deferredLine(candidates.map((c) => c.id))
    );
    return { admitted: [], droppedTouched: [], pushBase: diff.pushBase, treeWritersAdmitted: [] };
  }
  const disposable = deps.disposable();
  const touches = touchedSlow(candidates as readonly SlowCandidate[], {
    root: REPO_ROOT,
    changed: diff.files,
    matches: matchesAny,
    scriptsNow: deps.scriptsNow(),
    scriptsBase: diff.scriptsBase,
  });
  const byId = new Map(specs.map((s) => [s.id, s]));
  const verdict = admitTouched(
    touches.map((t) => t.id),
    (id) => treeWriteRefusal(byId.get(id), disposable)
  );
  const why = new Map(touches.map((t) => [t.id, t.why]));
  const touchedSet = new Set(touches.map((t) => t.id));
  const receiptDest = receiptPathFor(opts);
  const droppedTouched: DroppedTouched[] = verdict.dropped.map((d) => ({
    id: d.id,
    why: why.get(d.id) ?? '',
    reason: d.reason,
    kind: d.kind,
    run: dropRerunCommand(d.id, opts.receiptOut),
  }));
  const treeWritersAdmitted = verdict.admitted.filter(
    (id) => treeWriteOf(byId.get(id)) !== undefined
  );
  const lines = [
    `ci-runner: --quick diff since the last push (${diff.label}): ${diff.files.length} file(s); slow gates ${candidates.length}: ${touches.length} touched, ${verdict.admitted.length} selected into this pass, ${verdict.dropped.length} dropped, ${candidates.length - touches.length} untouched\n`,
    warningLines,
    ...verdict.admitted.map((id) =>
      treeWriteOf(byId.get(id)) !== undefined
        ? `  + SELECTED ${id} (tree writer; disposable clone, receipt -> ${receiptDest}): ${why.get(id)}\n`
        : `  + SELECTED ${id}: ${why.get(id)}\n`
    ),
    ...droppedTouched.map(
      (d) =>
        `  - DROPPED ${d.id} (touched: ${d.why}): ${d.reason}. CI runs it, and the push guard refuses until it passes here: \`${d.run}\`\n`
    ),
    deferredLine(candidates.filter((c) => !touchedSet.has(c.id)).map((c) => c.id)),
  ];
  warn(lines.join(''));
  return {
    admitted: [...verdict.admitted],
    droppedTouched,
    pushBase: diff.pushBase,
    treeWritersAdmitted,
  };
}

/** The command that runs one dropped gate and merges its result into the receipt this run writes: the same `--receipt-out` when this run had one. */
function dropRerunCommand(id: string, receiptOut: string | undefined): string {
  return `npx tsx scripts/ci-runner/run.ts --only ${id}${receiptOut === undefined ? '' : ` --receipt-out ${receiptOut}`}`;
}

/**
 * One cache entry per gate. `ewma` is the scheduling estimate. `recent` is
 * the last RECENT_KEEP raw measurements, oldest first, and exists for
 * check-gate-manifest's tier oracle: it judges the FLOOR of those, because
 * load only ever adds time. One full run overlapping two other sessions on
 * 2026-09-02 pushed a 4.5s gate's ewma to 21s and the oracle then demanded it
 * be marked slow; five measurements cannot all be poisoned by one bad run.
 * A bare number is the pre-2026-09-02 shape and is still read.
 */
export interface DurationRecord {
  ewma: number;
  recent: number[];
  /** CPU ms of the last RECENT_KEEP passing runs that reported one (PLAN-ci-quick-cpu-scheduling 2.1), oldest first. Absent until a wrapped run measures the gate. */
  cpu?: number[];
  /** Peak RSS MB of the last RECENT_KEEP passing runs with a sampler capture, oldest first. */
  rssMb?: number[];
  /** An elastic gate's cpu / wall / grant of the last RECENT_KEEP passing runs, oldest first: the share of each granted core it kept busy. Stored per core so a run at 20 workers does not teach the scheduler the gate is 20 wide (agent/plans/PLAN-prepush-full-cpu.md part 1). */
  perCore?: number[];
}
const RECENT_KEEP = 5;

/** A finite, non-negative number list from an untrusted cache field; undefined when nothing usable is there. */
function numberList(raw: unknown): number[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const kept = raw.filter(
    (n): n is number => typeof n === 'number' && Number.isFinite(n) && n >= 0
  );
  return kept.length > 0 ? kept.slice(-RECENT_KEEP) : undefined;
}

function loadDurationRecords(cachePath: string | undefined): Map<string, DurationRecord> {
  const records = new Map<string, DurationRecord>();
  if (cachePath === undefined) return records;
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(cachePath, 'utf-8'));
    if (parsed === null || typeof parsed !== 'object') return records;
    for (const [id, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === 'number' && Number.isFinite(v) && v > 0) {
        records.set(id, { ewma: v, recent: [v] });
      } else if (v !== null && typeof v === 'object') {
        const { ewma, recent, cpu, rssMb, perCore } = v as {
          ewma?: unknown;
          recent?: unknown;
          cpu?: unknown;
          rssMb?: unknown;
          perCore?: unknown;
        };
        if (typeof ewma !== 'number' || !Number.isFinite(ewma) || ewma <= 0) continue;
        const kept = Array.isArray(recent)
          ? recent.filter((n): n is number => typeof n === 'number' && Number.isFinite(n) && n > 0)
          : [];
        // cpu and rssMb MUST be carried here: saveDurations rebuilds the whole file from this map, so a field this loader drops is erased from every gate on the next run, including gates that run did not touch.
        const rec: DurationRecord = { ewma, recent: kept.length > 0 ? kept : [ewma] };
        const cpuKept = numberList(cpu);
        const rssKept = numberList(rssMb);
        const perCoreKept = numberList(perCore);
        if (cpuKept !== undefined) rec.cpu = cpuKept;
        if (rssKept !== undefined) rec.rssMb = rssKept;
        if (perCoreKept !== undefined) rec.perCore = perCoreKept;
        records.set(id, rec);
      }
    }
  } catch {
    // A missing or corrupt cache is a scheduling hint at worst. It must never fail the run.
  }
  return records;
}

function loadDurations(cachePath: string | undefined): Map<string, number> {
  const durations = new Map<string, number>();
  for (const [id, rec] of loadDurationRecords(cachePath)) durations.set(id, rec.ewma);
  return durations;
}

function median(xs: readonly number[]): number {
  const sorted = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * The cores rule's per-gate costs (PLAN-ci-quick-cpu-scheduling 2.2): the median of the recent cpu samples, the FLOOR of recent wall (the least-contended run, the same rule the tier oracle uses, since load only adds wall and would shrink d), the largest recent peak RSS, and an elastic gate's median per-core share. A gate the wrapper never measured has no cpu and is budgeted at one core.
 */
function costsFrom(
  records: ReadonlyMap<string, DurationRecord>,
  failed: ReadonlyMap<string, FailCost> = new Map()
): Map<string, GateCost> {
  const costs = new Map<string, GateCost>();
  for (const [id, rec] of records) {
    const cost: GateCost = { wallMs: Math.min(...rec.recent) };
    if (rec.cpu !== undefined && rec.cpu.length > 0) cost.cpuMs = median(rec.cpu);
    if (rec.rssMb !== undefined && rec.rssMb.length > 0) cost.rssMb = Math.max(...rec.rssMb);
    if (rec.perCore !== undefined && rec.perCore.length > 0) cost.perCore = median(rec.perCore);
    costs.set(id, cost);
  }
  // A FAILED RUN'S COST FILLS ONLY WHAT NO PASSING RUN MEASURED. The largest failed cpu is a floor on the gate's real cost: a run that failed early did less work, never more. Without it a gate that has only ever failed in this checkout is planned as an unmeasured 5 s gate at its `min` width, which is how check:ci-pytest, the critical path, was granted 10 of 23 cores in the push clone on 2026-10-05 (pre-push wall 1096 s against a cpu floor of 675 s).
  for (const [id, f] of failed) {
    const cost: GateCost = costs.get(id) ?? {};
    if (cost.cpuMs === undefined && f.cpu.length > 0) cost.cpuMs = Math.max(...f.cpu);
    if (cost.wallMs === undefined && f.wallMs.length > 0) cost.wallMs = Math.max(...f.wallMs);
    if (cost.perCore === undefined && f.perCore !== undefined && f.perCore.length > 0)
      cost.perCore = median(f.perCore);
    costs.set(id, cost);
  }
  return costs;
}

/**
 * The measured cost of FAILED runs, kept in a sibling of gate-durations.json and never in it: that file's `ewma` and `recent` are the tier oracle's wall, and saveDurations keeps failures out of them on purpose (a fail-fast run is cheap in wall and teaches the oracle nothing). The cores rule needs the other half: what a gate costs when nothing has passed yet. `costsFrom` uses these samples only where no passing sample exists.
 */
export interface FailCost {
  /** CPU ms of the last RECENT_KEEP failed runs that reported one, oldest first. */
  cpu: number[];
  /** Their wall ms, same order. */
  wallMs: number[];
  /** An elastic gate's cpu / wall / grant over the same runs. */
  perCore?: number[];
}

function failCostPath(cachePath: string): string {
  return path.join(path.dirname(cachePath), 'gate-fail-costs.json');
}

function loadFailCosts(cachePath: string | undefined): Map<string, FailCost> {
  const out = new Map<string, FailCost>();
  if (cachePath === undefined) return out;
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(failCostPath(cachePath), 'utf-8'));
    if (parsed === null || typeof parsed !== 'object') return out;
    for (const [id, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (v === null || typeof v !== 'object') continue;
      const { cpu, wallMs, perCore } = v as { cpu?: unknown; wallMs?: unknown; perCore?: unknown };
      const cpuKept = numberList(cpu);
      const wallKept = numberList(wallMs);
      if (cpuKept === undefined || wallKept === undefined) continue;
      const rec: FailCost = { cpu: cpuKept, wallMs: wallKept };
      const perCoreKept = numberList(perCore);
      if (perCoreKept !== undefined) rec.perCore = perCoreKept;
      out.set(id, rec);
    }
  } catch {
    // Same reasoning as loadDurationRecords: a cost hint is never load-bearing.
  }
  return out;
}

function saveFailCosts(cachePath: string | undefined, results: readonly GateResult[]): void {
  if (cachePath === undefined) return;
  try {
    const next: Record<string, FailCost> = Object.fromEntries(loadFailCosts(cachePath));
    for (const r of results) {
      if (r.status !== 'fail' || r.cpuMs === undefined || r.ms <= 0) continue;
      const had = next[r.id];
      const rec: FailCost = {
        cpu: [...(had?.cpu ?? []), r.cpuMs].slice(-RECENT_KEEP),
        wallMs: [...(had?.wallMs ?? []), r.ms].slice(-RECENT_KEEP),
      };
      const share =
        r.elastic === true && r.grantedCores !== undefined
          ? r.cpuMs / (r.ms * r.grantedCores)
          : undefined;
      const perCore = share !== undefined ? [...(had?.perCore ?? []), share] : had?.perCore;
      if (perCore !== undefined) rec.perCore = perCore.slice(-RECENT_KEEP);
      next[r.id] = rec;
    }
    fs.mkdirSync(path.dirname(cachePath), { recursive: true });
    fs.writeFileSync(failCostPath(cachePath), `${JSON.stringify(next, null, 2)}\n`);
  } catch {
    // A cache write is never load-bearing.
  }
}

/** MB the kernel says can be allocated without swapping (MemAvailable), else os.freemem() off Linux. */
function memAvailableMb(): number {
  try {
    const m = /^MemAvailable:\s+(\d+) kB/m.exec(fs.readFileSync('/proc/meminfo', 'utf-8'));
    if (m !== null) return Number(m[1]) / 1024;
  } catch {
    /* not Linux */
  }
  return os.freemem() / (1024 * 1024);
}

/**
 * C = --jobs when given, else the grant this run was itself launched with (CI_RUNNER_CORES, a runner nested inside a gate), else the broker lease's token total, else availableParallelism() - 1; epsilon 10%, K = 2C, M = 0.75 x MemAvailable now. The lease total wins over the core count less one because the lease, not a reserved core, is what keeps the machine responsive now: B11 measured a lone run using 23 of 24 tokens.
 */
function coreBudget(jobs: number | undefined, leaseTotal: number | undefined): CoreBudget {
  const cores = jobs ?? grantFromEnv() ?? leaseTotal ?? Math.max(1, os.availableParallelism() - 1);
  return {
    cores,
    epsilon: 0.1,
    maxProcs: 2 * cores,
    memMb: Math.floor(0.75 * memAvailableMb()),
  };
}

function saveDurations(
  cachePath: string | undefined,
  prior: Map<string, number>,
  results: readonly GateResult[]
): void {
  // An elastic gate's samples carry their grant's share (`perCore`); a fixed-width gate's never do.
  if (cachePath === undefined) return;
  try {
    const next: Record<string, DurationRecord> = Object.fromEntries(loadDurationRecords(cachePath));
    for (const r of results) {
      // ONLY a passing run. A gate that fails fast is cheap in wall-clock and expensive in nothing -- but the tier oracle judges the FLOOR of `recent`, so one 1.1s failure of a 21s gate makes it look like a pre-push-lane candidate forever. That is how check:ci-shape-duplication (21.4s), check:ci-renet-types (10.7s) and gate-test:trap-registry (46.4s) were all demanded into the
      // fast lane on 2026-09-02, during a session that had just triaged ten red gates. A failure's duration is not the gate's cost; it is the cost of the part that ran.
      if (r.status !== 'ok' || r.ms <= 0) continue;
      const old = prior.get(r.id);
      const ewma =
        old === undefined ? r.ms : Math.round(old * (1 - EWMA_ALPHA) + r.ms * EWMA_ALPHA);
      const had = next[r.id];
      const recent = [...(had?.recent ?? []), r.ms].slice(-RECENT_KEEP);
      const rec: DurationRecord = { ewma, recent };
      const cpu = r.cpuMs !== undefined ? [...(had?.cpu ?? []), r.cpuMs] : had?.cpu;
      const rssMb = r.rssMb !== undefined ? [...(had?.rssMb ?? []), r.rssMb] : had?.rssMb;
      const share =
        r.elastic === true && r.cpuMs !== undefined && r.grantedCores !== undefined
          ? r.cpuMs / (r.ms * r.grantedCores)
          : undefined;
      const perCore = share !== undefined ? [...(had?.perCore ?? []), share] : had?.perCore;
      if (cpu !== undefined) rec.cpu = cpu.slice(-RECENT_KEEP);
      if (rssMb !== undefined) rec.rssMb = rssMb.slice(-RECENT_KEEP);
      if (perCore !== undefined) rec.perCore = perCore.slice(-RECENT_KEEP);
      next[r.id] = rec;
    }
    fs.mkdirSync(path.dirname(cachePath), { recursive: true });
    fs.writeFileSync(cachePath, `${JSON.stringify(next, null, 2)}\n`);
  } catch {
    // Same reasoning as loadDurations: a cache write is never load-bearing.
  }
}

/**
 * One reading of the machine's aggregate CPU counters: /proc/stat on Linux (the only source with iowait), os.cpus() elsewhere. Undefined when neither answers.
 */
function readCpuTick(): { tick: CpuTick; cores: number } | undefined {
  const t = Date.now();
  try {
    const stat = fs.readFileSync('/proc/stat', 'utf-8');
    const lines = stat.split('\n');
    const agg = lines.find((l) => l.startsWith('cpu '));
    if (agg !== undefined) {
      // user nice system idle iowait irq softirq steal; guest time is already inside user.
      const [user, nice, system, idle, iowait, irq, softirq, steal] = agg
        .trim()
        .split(/\s+/)
        .slice(1, 9)
        .map((n) => Number(n) || 0);
      const busy = user + nice + system + irq + softirq + steal;
      return {
        tick: { t, busy, idle, iowait, total: busy + idle + iowait },
        cores: lines.filter((l) => /^cpu\d+ /.test(l)).length,
      };
    }
  } catch {
    /* not Linux: fall through to os.cpus() */
  }
  const cpus = os.cpus();
  if (cpus.length === 0) return undefined;
  let busy = 0;
  let idle = 0;
  for (const c of cpus) {
    busy += c.times.user + c.times.nice + c.times.sys + c.times.irq;
    idle += c.times.idle;
  }
  return { tick: { t, busy, idle, iowait: 0, total: busy + idle }, cores: cpus.length };
}

/** Machine CPU every 500 ms for the life of the pool (PLAN-ci-quick-cpu-scheduling 2.3). Unreferenced, so it can never keep the runner alive. */
function startCpuSampler(): { stop: () => { ticks: CpuTick[]; cores: number } } {
  const ticks: CpuTick[] = [];
  let cores = 0;
  const take = (): void => {
    const r = readCpuTick();
    if (r === undefined) return;
    ticks.push(r.tick);
    cores = r.cores;
  };
  take();
  const timer = setInterval(take, 500);
  timer.unref();
  return {
    stop: () => {
      clearInterval(timer);
      take();
      return { ticks, cores };
    },
  };
}

/** What a gate's /proc sampler capture says: peak summed RSS and the largest summed CPU any one tick saw. */
function readCapture(file: string, runId: string | undefined): { rssMb?: number; cpuMs?: number } {
  let text: string;
  try {
    text = fs.readFileSync(file, 'utf-8');
  } catch {
    return {};
  }
  let peakKb = 0;
  let peakTicks = 0;
  let clkTck = 100;
  let sampled = false;
  for (const line of text.split('\n')) {
    if (line === '') continue;
    let rec: {
      k?: string;
      run?: string;
      clk_tck?: number;
      p?: { rss_kb?: number; utime?: number; stime?: number; cutime?: number; cstime?: number }[];
    };
    try {
      rec = JSON.parse(line) as typeof rec;
    } catch {
      continue; // a torn last line from a sampler still writing
    }
    // A nested runner writes beside the outer one in the same directory, so only this run's lines count.
    if (runId !== undefined && rec.run !== runId) continue;
    if (rec.k === 'RUN' && typeof rec.clk_tck === 'number' && rec.clk_tck > 0) clkTck = rec.clk_tck;
    if (rec.k !== 'S' || !Array.isArray(rec.p)) continue;
    sampled = true;
    let kb = 0;
    let ticks = 0;
    // Summing cutime over the LIVE processes of one tick counts each reaped descendant once: it sits in its reaper's cutime and is no longer live itself. RSS double-counts shared pages, which errs conservative.
    for (const p of rec.p) {
      kb += p.rss_kb ?? 0;
      ticks += (p.utime ?? 0) + (p.stime ?? 0) + (p.cutime ?? 0) + (p.cstime ?? 0);
    }
    peakKb = Math.max(peakKb, kb);
    peakTicks = Math.max(peakTicks, ticks);
  }
  if (!sampled) return {};
  return {
    rssMb: peakKb > 0 ? Math.round(peakKb / 1024) : undefined,
    cpuMs: Math.round((peakTicks * 1000) / clkTck),
  };
}

/** The sampler's file name for a gate id; mirrors exec.ts. */
function captureFile(profileDir: string, id: string): string {
  return path.join(profileDir, `${id.replace(/[^A-Za-z0-9_.-]/g, '_')}.jsonl`);
}

/**
 * Fold each gate's sampler capture into its result: peak RSS, and the undercount cross-check of PLAN-ci-quick-cpu-scheduling 2.1. `times` sees only descendants the gate's shell reaped; the sampler sees whatever was alive under the gate at each tick, so a sampler total more than 20% above `times` means something escaped the reap, and the larger value stands.
 */
function applyCaptures(
  results: readonly GateResult[],
  profileDir: string | undefined,
  runId: string | undefined
): GateResult[] {
  if (profileDir === undefined) return [...results];
  return results.map((r) => {
    if (r.status === 'skipped') return r;
    const cap = readCapture(captureFile(profileDir, r.id), runId);
    const next: GateResult = { ...r };
    if (cap.rssMb !== undefined) next.rssMb = cap.rssMb;
    if (cap.cpuMs !== undefined) {
      if (r.cpuMs === undefined) next.cpuMs = cap.cpuMs;
      else if (cap.cpuMs > r.cpuMs * 1.2) {
        next.cpuMs = cap.cpuMs;
        next.undercount = true;
      }
    }
    return next;
  });
}

const SELFTEST_OUT = 'ci-runner-selftest-stdout-marker';
const SELFTEST_ERR = 'ci-runner-selftest-stderr-marker';

function syntheticSpec(id: string, run: string, needs?: string[]): GateSpec {
  return {
    id,
    run,
    gate: true,
    needs,
    leaves: [],
    ci: {
      kind: 'local-only',
      blocker: 'BLOCKER: synthetic --selftest fixture, never part of the real gate set',
    },
  };
}

/**
 * The runner's anti-vacuity control, wired into the `ci` npm key itself so it
 * cannot sit behind a flag nothing invokes -- the exact failure
 * check-gate-reachability recorded for check-i18n-cross-locale, which shipped
 * broken behind a flag no caller passed.
 *
 * A planted failing gate must produce: exit 1, BOTH captured streams printed
 * verbatim, the gate named in the summary, and its dependent reported skipped
 * rather than passed. If any leg does not fire, the runner's green means
 * nothing, so this refuses to proceed.
 */
async function selftest(): Promise<number> {
  const specs = [
    syntheticSpec('selftest:pass', 'echo selftest-pass'),
    syntheticSpec('selftest:fail', `echo ${SELFTEST_OUT}; echo ${SELFTEST_ERR} >&2; exit 3`),
    syntheticSpec('selftest:dependent', 'echo selftest-dependent-ran', ['selftest:fail']),
  ];

  const captured: string[] = [];
  const reporter = createReporter({ idWidth: 20, out: (text) => captured.push(text) });
  const meta = { jobs: 2, failFast: false, wallMs: 0 };
  reporter.header(specs.length, meta);
  const results = await runPool(buildGraph(specs, new Set(specs.map((s) => s.id))), {
    jobs: 2,
    heavyLimit: 1,
    failFast: false,
    durations: new Map(),
    exec: (spec) => execGate(spec, { cwd: REPO_ROOT, mergeOutput: false, ...PROFILE_OPTS }),
    onFinish: (result) => {
      reporter.finish(result);
    },
  });
  const exitCode = reporter.footer(results, meta);
  const text = captured.join('');

  const failures: string[] = [];
  const require_ = (cond: boolean, message: string): void => {
    if (!cond) failures.push(message);
  };
  require_(exitCode === 1, `a failing gate must make the run exit 1, got ${exitCode}`);
  require_(text.includes(SELFTEST_OUT), "the failing gate's captured stdout was not printed");
  require_(text.includes(SELFTEST_ERR), "the failing gate's captured stderr was not printed");
  require_(/FAIL {2}selftest:fail/.test(text), 'the failing gate was not named as FAIL');
  require_(text.includes('exit 3'), "the failing gate's exit code was not reported");
  require_(
    results.find((r) => r.id === 'selftest:dependent')?.status === 'skipped',
    'a dependent of a failed gate must be skipped, not passed'
  );
  require_(
    !text.includes('selftest-dependent-ran'),
    'a dependent of a failed gate must not execute'
  );
  require_(
    results.find((r) => r.id === 'selftest:pass')?.status === 'ok',
    'the passing control gate did not pass'
  );
  require_(!text.includes('selftest-pass'), "a passing gate's output must stay quiet");
  // FINDING KEYS (PLAN-carried-red-finding-keys test 9). The planted failing gate above printed two markers and no `::finding::` line, so its receipt entry must be null -- "nothing parsable", never "no findings" -- and the passing gate must have no entry at all. The parser's own plants and controls follow in findingsSelftest().
  require_(
    JSON.stringify(receiptFindings(results, () => {})) === '{"selftest:fail":null}',
    `a failed gate with no ::finding:: line must record null, got ${JSON.stringify(receiptFindings(results, () => {}))}`
  );
  const keyed = findingsSelftest();
  for (const f of keyed.failures) require_(false, f);

  // THE TIMELINE (report.ts timelineOf): every launched gate has a start and an end relative to the run's start, a skipped one has none, and the footer prints the tail with them. The footer above had no startedAt, which is the control: it must print no timeline.
  {
    const t0 = Math.min(...results.flatMap((r) => (r.readyAt === undefined ? [] : [r.readyAt])));
    const tl = timelineOf(results, t0);
    const pass = tl['selftest:pass'];
    require_(
      pass !== undefined &&
        pass.start >= 0 &&
        pass.end >= pass.start &&
        pass.ready !== undefined &&
        tl['selftest:fail'] !== undefined &&
        tl['selftest:dependent'] === undefined,
      `the timeline must time every launched gate from the run's start and omit a skipped one, got ${JSON.stringify(tl)}`
    );
    const timed: string[] = [];
    createReporter({ idWidth: 20, out: (t) => timed.push(t) }).footer(results, {
      ...meta,
      startedAt: t0,
    });
    const tail = timed.join('');
    require_(
      /last to finish/.test(tail) && /-> +\d+\.\d+s +1 {2}selftest:pass/.test(tail),
      `the footer must print the tail with start, end and cores, got:\n${tail}`
    );
    require_(
      !text.includes('last to finish'),
      'CONTROL: a footer with no startedAt must print no timeline'
    );
  }

  // A GATE'S DECLARED ENV REACHES ITS PROCESS, as its CI step's `env:` does. execGate spawned without it, so tutorial-player's PUBLIC_VIDEO_CDN_BASE_URL never applied locally and the gate failed in every clean clone while passing in CI (2026-09-26). The control spec fails unless the variable arrives.
  const envSpec = {
    ...syntheticSpec('selftest:env', '[ "$CI_RUNNER_SELFTEST_ENV" = arrived ]'),
    env: { CI_RUNNER_SELFTEST_ENV: 'arrived' },
  };
  const envRun = await execGate(envSpec, { cwd: REPO_ROOT, mergeOutput: false });
  require_(envRun.code === 0, "a gate's declared env did not reach its process");
  const bare = await execGate(
    syntheticSpec('selftest:env-control', '[ "$CI_RUNNER_SELFTEST_ENV" = arrived ]'),
    {
      cwd: REPO_ROOT,
      mergeOutput: false,
    }
  );
  require_(bare.code !== 0, 'CONTROL: without a declared env the variable must be absent');
  // A GitHub expression is the workflow's to evaluate, never a literal to inject.
  const exprRun = await execGate(
    {
      ...syntheticSpec('selftest:env-expr', '[ -z "$CI_RUNNER_SELFTEST_EXPR" ]'),
      env: { CI_RUNNER_SELFTEST_EXPR: '${{ github.ref_name }}' },
    },
    { cwd: REPO_ROOT, mergeOutput: false }
  );
  require_(exprRun.code === 0, 'a ${{ }} env value was injected locally as a literal');

  // GLOB SEMANTICS, both directions. These three were all FALSE before the `**\/` fix, and the first one is a live defect: manifest.ts declares `paths: ['**\/*.sh']` for check:ci-shell-size under a comment saying "deliberately not path-narrowed", while the gate itself enumerates with the git pathspec `*.sh`, which DOES match at the root.
  require_(globToRegExp('**/*.sh').test('run.sh'), '**/*.sh must match a root-level run.sh');
  require_(
    globToRegExp('**/*.sh').test('.ci/scripts/quality/check-npmrc.sh'),
    '**/*.sh must still match a nested .sh'
  );
  require_(
    !globToRegExp('**/*.sh').test('packages/cli/src/index.ts'),
    'CONTROL: **/*.sh must NOT match a .ts, or the pattern matches everything'
  );
  // The two paths below are ASSEMBLED rather than written out. They name files that do not exist -- that is the point of a glob fixture -- and test_gate_paths_exist.py scans this source for path literals and requires every one to exist. Writing them plainly made that gate red, correctly.
  const dirA = ['private', 'account'].join('/');
  const dirB = ['private', 'renet'].join('/');
  require_(
    globToRegExp(`${dirA}/**`).test(`${dirA}/src/nope.ts`),
    'a trailing ** must match beneath the directory'
  );
  require_(
    !globToRegExp(`${dirA}/**`).test(`${dirB}/src/nope.ts`),
    'CONTROL: a directory glob must not match a sibling directory'
  );

  // A GITLINK MUST WIDEN, NOT PASS THROUGH. `git diff --name-only` names a changed submodule as ONE entry (mode 160000), so a `private/x/**` glob can never match it. Both directions against the real repo, with a precondition so the case cannot pass because the fixture stopped being a submodule.
  const gitlink = firstGitlink();
  if (gitlink === undefined) {
    require_(false, 'CONTROL: no gitlink found in HEAD, so the expansion case proves nothing');
  } else {
    const expanded = expandGitlinks([gitlink, 'package.json'], () => {});
    require_(
      expanded.includes(`${gitlink}/**`),
      `a changed ${gitlink} must widen to ${gitlink}/**`
    );
    require_(expanded.includes(gitlink), 'the gitlink entry itself must survive');
    require_(
      expanded.includes('package.json') && !expanded.includes('package.json/**'),
      'CONTROL: an ordinary file must pass through unwidened'
    );
  }

  // ORDERING, END TO END, THROUGH main() ITSELF. The two select() controls below exercise the FUNCTION; neither would notice `--list` moving back above the `select()` call, which is exactly the regression that shipped: `--list` returned before selection ran, so `--list --changed` printed all 314 specs whatever the scoping did, and a measurement taken from it was reported to the
  // operator by an instrument that could not have shown otherwise.
  //
  // A unit test on select() cannot see that; only the real argv path can. The first draft of this spawned `process.execPath run.ts`, which fails because node cannot execute TypeScript -- so it drives main() in-process with argv set and stdout captured. Same path, no interpreter, no subprocess.
  const listGateLines = async (argv: string[]): Promise<number> => {
    const realArgv = process.argv;
    const realWrite = process.stdout.write.bind(process.stdout);
    let captured = '';
    process.argv = [realArgv[0], realArgv[1], ...argv];
    (process.stdout as { write: unknown }).write = (chunk: unknown): boolean => {
      captured += String(chunk);
      return true;
    };
    try {
      await main();
    } finally {
      process.argv = realArgv;
      (process.stdout as { write: unknown }).write = realWrite;
    }
    return captured.split('\n').filter((l) => l.startsWith('gate ')).length;
  };
  const onlyOne = await listGateLines(['--list', '--only', 'check:ci-npmrc']);
  require_(
    onlyOne === 1,
    `--list must print the SELECTION: --only one id printed ${onlyOne} gate lines`
  );
  // CONTROL: a bare --list must print many. Without this the assertion above also passes on a --list that prints nothing at all.
  const allGates = await listGateLines(['--list']);
  require_(
    allGates > 50,
    `CONTROL: a bare --list must print the whole set, got ${allGates} -- the --only case proves nothing without this`
  );

  // `--list` MUST REFLECT THE SELECTION. Before this it returned before select() ran, so a scoped list was indistinguishable from a full one -- and no oracle could assert on a selection it could not read.
  const listSpecs = [
    syntheticSpec('selftest:list-a', 'true'),
    syntheticSpec('selftest:list-b', 'true'),
  ];
  const listSel = select(listSpecs, { ...EMPTY_OPTS, only: ['selftest:list-a'] }, () => {});
  require_(
    listSel.ids.has('selftest:list-a') && !listSel.ids.has('selftest:list-b'),
    'select() must honour --only'
  );
  require_(
    select(listSpecs, EMPTY_OPTS, () => {}).ids.size === 2,
    'CONTROL: with no flags select() must keep every gate, or --only proves nothing'
  );

  // THE DURATION CACHE MUST NOT LEARN FROM FAILURES. It feeds the tier oracle in check-gate-manifest, which judges the FLOOR of `recent` -- so a single fast failure of a slow gate is indistinguishable from the gate becoming cheap, and demands it be moved into the pre-push lane forever. Both directions, because "records nothing" would pass the first assertion alone.
  const durDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-runner-dur-'));
  const durCache = path.join(durDir, 'gate-durations.json');
  const durResult = (id: string, status: GateResult['status'], ms: number): GateResult => ({
    id,
    gate: true,
    status,
    ms,
    exitCode: status === 'ok' ? 0 : 1,
    stdout: '',
    stderr: '',
    rerun: 'true',
  });
  saveDurations(durCache, new Map(), [
    durResult('selftest:dur-ok', 'ok', 4321),
    durResult('selftest:dur-fail', 'fail', 11),
    durResult('selftest:dur-blocked', 'blocked', 12),
  ]);
  const durWritten = JSON.parse(fs.readFileSync(durCache, 'utf-8')) as Record<string, unknown>;
  fs.rmSync(durDir, { recursive: true, force: true });
  require_(
    durWritten['selftest:dur-fail'] === undefined,
    'a FAILED run must not enter the duration cache -- it poisons the tier oracle floor'
  );
  require_(
    durWritten['selftest:dur-blocked'] === undefined,
    'a BLOCKED run must not enter the duration cache either'
  );
  require_(
    (durWritten['selftest:dur-ok'] as { recent?: number[] } | undefined)?.recent?.[0] === 4321,
    'CONTROL: a PASSING run must still be recorded, or the two assertions above prove nothing'
  );

  // THE RECEIPT MUST NOT CLAIM A WHOLE LANE IT DID NOT RUN. `--changed` was missing from this condition until 2026-09-06: `select()` drops every gate whose declared `paths` the diff does not touch, and the run still wrote `whole: true` -- the field the pre-push guard reads to authorise a push. Measured on this tree the same day: a `--changed` receipt claimed `whole`
  // while its own selection prose said "30 gate(s) path-scoped".
  require_(
    narrowingFlags({ ...EMPTY_OPTS, changed: true }).includes('--changed'),
    '--changed must narrow the receipt: it drops every path-declaring gate'
  );
  require_(
    narrowingFlags({ ...EMPTY_OPTS, only: ['x'] }).includes('--only'),
    '--only must narrow the receipt'
  );
  require_(
    narrowingFlags({ ...EMPTY_OPTS, skip: ['x'] }).includes('--skip'),
    '--skip must narrow the receipt'
  );
  require_(
    narrowingFlags(EMPTY_OPTS).length === 0,
    'CONTROL: an unnarrowed quick run must still report the whole lane, or the three above prove nothing'
  );

  // THE RECEIPT NAMES THE TREE JUDGED FROM THE START, OR NONE.
  require_(receiptTree('aaa', 'aaa') === 'aaa', 'an unmoved HEAD must be vouched for');
  require_(
    receiptTree('aaa', 'bbb') === '',
    'a HEAD that moved mid-run must vouch for NO tree -- the end tree was never judged'
  );
  require_(receiptTree('', '') === '', 'CONTROL: an unreadable HEAD vouches for nothing either');
  require_(
    parseStaleSubmodules(' 1844b07 s (heads/main)\n+a1f430b private/account (a1f430b)').join() ===
      'private/account',
    'a submodule checked out off its gitlink (a + line) must void the receipt (#a423d9ab)'
  );
  require_(
    parseStaleSubmodules(' 1844b07 s (heads/main)\n-5c82fec private/elite').length === 0,
    'CONTROL: an in-step or uninitialised submodule is not reported as off its gitlink'
  );

  // --receipt-out: a snapshot clone's run lands where the pushing checkout's guard reads, and nowhere else.
  require_(
    receiptPathFor(parseArgs(['--quick', '--receipt-out', '/snap/receipt.json'])) ===
      '/snap/receipt.json',
    '--receipt-out must redirect the receipt to the given path'
  );
  require_(
    receiptPathFor(parseArgs(['--quick'])) === RECEIPT_PATH,
    "CONTROL: without --receipt-out the receipt stays in this checkout's own cache"
  );
  let relRefused = false;
  try {
    parseArgs(['--receipt-out', 'relative/receipt.json']);
  } catch {
    relRefused = true;
  }
  require_(
    relRefused,
    '--receipt-out must refuse a relative path, which would resolve against an arbitrary cwd'
  );
  require_(
    narrowingFlags(parseArgs(['--quick', '--receipt-out', '/snap/r.json'])).length === 0,
    '--receipt-out must not narrow the lane: it changes where the verdict is written, not which gates run'
  );
  // A narrowed run keeps an existing whole receipt; a whole run replaces anything.
  {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-runner-receipt-'));
    const dest = path.join(dir, 'receipt.json');
    try {
      require_(
        !narrowedWouldReplaceWhole(dest, false),
        'CONTROL: a narrowed run with no receipt on disk writes one'
      );
      fs.writeFileSync(dest, JSON.stringify({ whole: true }));
      require_(
        narrowedWouldReplaceWhole(dest, false),
        'a narrowed run must not replace a whole receipt'
      );
      require_(
        !narrowedWouldReplaceWhole(dest, true),
        'CONTROL: a whole run replaces a whole receipt'
      );
      fs.writeFileSync(dest, JSON.stringify({ whole: false }));
      require_(
        !narrowedWouldReplaceWhole(dest, false),
        'CONTROL: a narrowed run replaces a narrowed receipt'
      );
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }

  // T2.10: --lane/--shard PARSING. Both required together, or neither -- a lone --lane silently running the WHOLE manifest (because opts.only stayed undefined) would look exactly like a successful, narrower replay.
  const laneShardParseCases: [string[], boolean][] = [
    [['--lane', 'quality-code'], true],
    [['--shard', '1/4'], true],
    [['--lane', 'quality-code', '--shard', '1/4'], false],
    [[], false],
    [['--shard', 'abc'], true],
    [['--shard', '0/4'], true],
    [['--shard', '5/4'], true],
  ];
  for (const [argv, wantThrow] of laneShardParseCases) {
    let threw = false;
    try {
      parseArgs(argv);
    } catch {
      threw = true;
    }
    require_(
      threw === wantThrow,
      `parseArgs(${JSON.stringify(argv)}) should ${wantThrow ? '' : 'NOT '}throw`
    );
  }

  // T2.10: resolveLaneShard, against a synthetic manifest so this control never depends on what any real lane happens to hold today.
  const laneDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-runner-lane-'));
  const shardsDir = path.join(laneDir, '.ci', 'config', 'shards');
  fs.mkdirSync(shardsDir, { recursive: true });
  const gateSpecs: GateSpec[] = [
    syntheticSpec('selftest:lane-a', 'true'),
    syntheticSpec('selftest:lane-b', 'true'),
  ];
  fs.writeFileSync(
    path.join(shardsDir, 'fixture-lane.json'),
    JSON.stringify({
      lane: 'fixture-lane',
      of: 2,
      generatedAt: '2026-09-26T00:00:00.000Z',
      legs: [
        { index: 1, ids: ['selftest:lane-a'] },
        { index: 2, ids: ['selftest:lane-b'] },
      ],
    })
  );
  fs.writeFileSync(
    path.join(shardsDir, 'fixture-test-lane.json'),
    JSON.stringify({
      lane: 'fixture-test-lane',
      of: 1,
      generatedAt: '2026-09-26T00:00:00.000Z',
      legs: [{ index: 1, ids: ['playwright:some-spec.test.ts'] }],
    })
  );
  fs.writeFileSync(
    path.join(shardsDir, 'fixture-mixed.json'),
    JSON.stringify({
      lane: 'fixture-mixed',
      of: 1,
      generatedAt: '2026-09-26T00:00:00.000Z',
      legs: [{ index: 1, ids: ['selftest:lane-a', 'playwright:some-spec.test.ts'] }],
    })
  );
  require_(
    resolveLaneShard('fixture-lane', { index: 1, of: 2 }, gateSpecs, laneDir).join(',') ===
      'selftest:lane-a',
    'resolveLaneShard must return exactly leg 1 of a gate-backed lane'
  );
  let missingRefused = false;
  try {
    resolveLaneShard('no-such-lane', { index: 1, of: 1 }, gateSpecs, laneDir);
  } catch {
    missingRefused = true;
  }
  require_(missingRefused, 'resolveLaneShard must refuse a lane with no committed manifest');
  let testLaneRefused = false;
  try {
    resolveLaneShard('fixture-test-lane', { index: 1, of: 1 }, gateSpecs, laneDir);
  } catch (err) {
    testLaneRefused = /are check gates/.test((err as Error).message);
  }
  require_(
    testLaneRefused,
    'resolveLaneShard must refuse (by name) a leg whose units are not check gates'
  );
  let mixedRefused = false;
  try {
    resolveLaneShard('fixture-mixed', { index: 1, of: 1 }, gateSpecs, laneDir);
  } catch (err) {
    mixedRefused = /mixed leg cannot be replayed/.test((err as Error).message);
  }
  require_(mixedRefused, 'resolveLaneShard must refuse a leg mixing gate and non-gate units');
  fs.rmSync(laneDir, { recursive: true, force: true });

  // T2.10 END TO END, against the REAL committed manifest, through main() itself -- the same `listGateLines` harness the --list/--only control above uses. Skips only while no lane has ever been sharded to disk yet, which this box's own acceptance requires this session to have already fixed by the time selftest runs.
  const realManifest = path.join(REPO_ROOT, '.ci', 'config', 'shards', 'quality-code.json');
  if (fs.existsSync(realManifest)) {
    const file = parseShardManifest(fs.readFileSync(realManifest, 'utf-8'), 'quality-code');
    const leg1 = legIds(file, 1, file.of);
    // Some of leg 1's ids are `gate: false` prerequisite steps (`check:lint` is the shared step several `check:lint:*` gates ride, per shardPlan's own step-sharing merge), and `select()` never selects those on their own -- they run only through a real gate's `needs` closure. `--list` therefore prints one "gate " line per real gate in the leg, not one per id in the manifest.
    const gateFlagById = new Map(GATES.map((g) => [g.id, g.gate]));
    const wantGateLines = leg1.filter((id) => gateFlagById.get(id) === true).length;
    const printed = await listGateLines([
      '--list',
      '--lane',
      'quality-code',
      '--shard',
      `1/${file.of}`,
    ]);
    require_(
      printed === wantGateLines,
      `--lane quality-code --shard 1/${file.of} must print exactly leg 1's ${wantGateLines} gate(s) (of ${leg1.length} unit id(s)), printed ${printed}`
    );
  } else {
    require_(
      false,
      'CONTROL: .ci/config/shards/quality-code.json must exist for the end-to-end check to mean anything'
    );
  }

  // THE RUSAGE WRAPPER (PLAN-ci-quick-cpu-scheduling 2.1), both directions: a busy gate must read as CPU and a sleeping one must not, or cpuMs is a wall clock under another name. Then the two exit paths the wrapper sits in front of: a signal must still read as a signal, and CANNOT_RUN must still reach the pool as blocked.
  const wrapOpts = { cwd: REPO_ROOT, mergeOutput: false };
  if (process.platform !== 'win32') {
    const busy = await execGate(
      // A FIXED AMOUNT OF WORK, not a wall-clock window: `while (( SECONDS < e ))` burned whatever CPU the host left it in about 1-2 s, and on a loaded host (2026-10-01: a VM fleet and two writers) that was 466 ms against a 500 ms floor. 400k iterations cost about 0.3-0.9 s of CPU whatever the load; the floor sits well above the sleeping control's 100 ms.
      syntheticSpec('selftest:cpu-busy', 'i=0; while (( i < 400000 )); do ((i++)); done'),
      wrapOpts
    );
    require_(
      (busy.cpuMs ?? 0) > 200,
      `a busy gate must report cpuMs > 200, got ${busy.cpuMs} over ${busy.ms} ms wall`
    );
    const idle = await execGate(syntheticSpec('selftest:cpu-sleep', 'sleep 1'), wrapOpts);
    require_(
      idle.cpuMs !== undefined && idle.cpuMs < 100,
      `CONTROL: a sleeping gate must report cpuMs < 100, got ${idle.cpuMs} -- or cpuMs is wall time`
    );
    const killed = await execGate(syntheticSpec('selftest:kill9', 'kill -9 $$'), wrapOpts);
    require_(
      killed.code === null && killed.stderr.includes('terminated by signal'),
      `kill -9 $$ must still report a signal, got code ${killed.code}`
    );
    const termed = await execGate(syntheticSpec('selftest:term', 'kill -TERM $BASHPID'), wrapOpts);
    require_(
      termed.code === null && termed.stderr.includes('signal SIGTERM'),
      `a gate killed by SIGTERM (outer status 143) must report the signal, got code ${termed.code}`
    );
  }
  const cannot = await runPool([syntheticSpec('selftest:cannot-run', 'exit 77')], {
    jobs: 1,
    heavyLimit: 1,
    failFast: false,
    durations: new Map(),
    exec: (spec) => execGate(spec, wrapOpts),
  });
  require_(cannot[0]?.status === 'blocked', `exit 77 must stay blocked, got ${cannot[0]?.status}`);
  require_(
    cannot[0]?.startAt !== undefined &&
      cannot[0]?.endAt !== undefined &&
      cannot[0].endAt >= cannot[0].startAt,
    'the pool must stamp startAt/endAt on a result'
  );

  // THE DURATION CACHE MUST KEEP cpu AND rssMb ACROSS A RUN THAT DID NOT TOUCH THE GATE. saveDurations rebuilds the file from loadDurationRecords, so a field the loader drops vanishes from every gate on the next write; the second save below names only another gate for exactly that reason.
  const cpuDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-runner-cpu-'));
  const cpuCache = path.join(cpuDir, 'gate-durations.json');
  saveDurations(cpuCache, new Map(), [
    { ...durResult('selftest:cpu-a', 'ok', 2000), cpuMs: 1500, rssMb: 120 },
    durResult('selftest:cpu-none', 'ok', 900),
  ]);
  saveDurations(cpuCache, loadDurations(cpuCache), [durResult('selftest:cpu-b', 'ok', 700)]);
  const cpuRecords = loadDurationRecords(cpuCache);
  fs.rmSync(cpuDir, { recursive: true, force: true });
  const kept = cpuRecords.get('selftest:cpu-a');
  require_(
    kept?.cpu?.[0] === 1500 && kept?.rssMb?.[0] === 120,
    `cpu/rssMb must survive a cache round trip, got ${JSON.stringify(kept)}`
  );
  require_(
    cpuRecords.get('selftest:cpu-none')?.cpu === undefined,
    'CONTROL: a gate that reported no cpuMs must not gain a cpu field'
  );

  // A FAILED RUN'S COST IS KEPT APART AND FILLS ONLY WHAT NO PASS MEASURED (costsFrom). The wall oracle's file must not gain the failure; the cores rule must see it.
  const failDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-runner-fail-'));
  const failCache = path.join(failDir, 'gate-durations.json');
  const failed = (id: string, ms: number, cpuMs: number): GateResult => ({
    ...durResult(id, 'fail', ms),
    cpuMs,
    elastic: true,
    grantedCores: 10,
  });
  saveDurations(failCache, new Map(), [
    failed('selftest:only-failed', 1_000_000, 9_000_000),
    { ...durResult('selftest:passed-too', 'ok', 4000), cpuMs: 3000 },
  ]);
  saveFailCosts(failCache, [
    failed('selftest:only-failed', 1_000_000, 9_000_000),
    failed('selftest:passed-too', 500, 100),
    durResult('selftest:fail-no-cpu', 'fail', 700),
  ]);
  const failCosts = costsFrom(loadDurationRecords(failCache), loadFailCosts(failCache));
  const failRecords = loadDurationRecords(failCache);
  const failFile = loadFailCosts(failCache);
  fs.rmSync(failDir, { recursive: true, force: true });
  const only = failCosts.get('selftest:only-failed');
  require_(
    only?.cpuMs === 9_000_000 && only?.wallMs === 1_000_000 && only?.perCore === 0.9,
    `a gate that has only failed must be costed from its failed run, got ${JSON.stringify(only)}`
  );
  require_(
    !failRecords.has('selftest:only-failed'),
    "CONTROL: a failed run must not enter gate-durations.json, the tier oracle's wall"
  );
  require_(
    failCosts.get('selftest:passed-too')?.cpuMs === 3000,
    `CONTROL: a passing sample must win over a failed one, got ${JSON.stringify(failCosts.get('selftest:passed-too'))}`
  );
  require_(
    !failFile.has('selftest:fail-no-cpu'),
    'CONTROL: a failed run that reported no cpu must not be recorded'
  );

  // THE SAMPLER CROSS-CHECK: a capture that saw far more CPU than `times` flags undercount and wins; one within 20% leaves `times` alone. Only this run's lines count.
  const capDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ci-runner-cap-'));
  const tick = (run: string, rss: number, cpuTicks: number): string =>
    `${JSON.stringify({ v: 1, k: 'S', run, p: [{ rss_kb: rss, utime: cpuTicks, stime: 0, cutime: 0, cstime: 0 }] })}\n`;
  fs.writeFileSync(
    captureFile(capDir, 'selftest:cap'),
    tick('r1', 102400, 50) +
      tick('r1', 204800, 300) +
      tick('other-run', 9999999, 99999) +
      `${JSON.stringify({ v: 1, k: 'RUN', run: 'r1', clk_tck: 100 })}\n`
  );
  const [under, fine] = applyCaptures(
    [
      { ...durResult('selftest:cap', 'ok', 4000), cpuMs: 1000 },
      { ...durResult('selftest:cap', 'ok', 4000), cpuMs: 2900 },
    ],
    capDir,
    'r1'
  );
  fs.rmSync(capDir, { recursive: true, force: true });
  require_(
    under.undercount === true && under.cpuMs === 3000 && under.rssMb === 200,
    `a sampler total 3x times must flag undercount and win, got ${JSON.stringify(under)}`
  );
  require_(
    fine.undercount === undefined && fine.cpuMs === 2900,
    `CONTROL: a sampler within 20% of times must leave it alone, got ${JSON.stringify(fine)}`
  );

  // THE SCHEDULER (PLAN-ci-quick-cpu-scheduling section 3), through sim.ts, which drives the same admit() runPool does: the synthetic mix under both rules, and a control per claim (epsilon infinite trips the cap check, all-one-core matches slots within 1%, no reservation starves a d-8 gate, d > C runs alone on an idle pool, two 20 GB gates never overlap under M 32 GB).
  const sim = schedulerSelftest();
  for (const f of sim.failures) require_(false, `scheduler: ${f}`);
  // --sched is refused when misspelt rather than quietly falling back, or an A/B would compare slots with slots.
  require_(parseArgs(['--sched', 'cores']).sched === 'cores', '--sched cores must parse');
  let badSched = false;
  try {
    parseArgs(['--sched', 'core']);
  } catch {
    badSched = true;
  }
  require_(badSched, "CONTROL: --sched core (a typo) must be refused, not read as 'slots'");

  // --quick DIFF SELECTION (quick-select.ts). The pure half: touch, import closure, npm script change, the mutant matcher, the budget, the base fallback.
  const qs = quickSelectSelftest(os.tmpdir(), matchesAny);
  for (const f of qs.failures) require_(false, `quick-select: ${f}`);
  // END TO END THROUGH select() ITSELF, so the lane wiring is under test and not only the helper: a touched slow gate is selected, an untouched one deferred, the fast gate kept. The leaves are real files with no relative imports, so neither can reach the other's closure.
  {
    // Each fixture DECLARES paths that match nothing in the diff: a slow gate without paths is selected by any change (quick-select rule 4), which would hide whether the leaf rule selected it.
    const slowSpec = (id: string, leaf: string): GateSpec => ({
      ...syntheticSpec(id, 'true'),
      slow: true,
      leaves: [leaf],
      paths: ['selftest-no-such-dir/**'],
      pathsOrigin: 'declared',
    });
    const qSpecs = [
      syntheticSpec('selftest:q-fast', 'true'),
      slowSpec('selftest:q-touched', 'scripts/ci-runner/quick-select.ts'),
      slowSpec('selftest:q-untouched', 'scripts/ci-runner/gate-spec.ts'),
    ];
    const deps = (files: string[] | undefined, disposable = false): QuickDiffDeps => ({
      diff: () => ({ files, label: 'selftest-base' }),
      scriptsNow: () => ({}),
      disposable: () => disposable,
    });
    let said = '';
    const capture = (t: string): void => {
      said += t;
    };
    const quick = { ...EMPTY_OPTS, quick: true };
    const sel = select(qSpecs, quick, capture, deps(['scripts/ci-runner/quick-select.ts']));
    require_(
      sel.ids.has('selftest:q-touched'),
      '--quick must SELECT a slow gate whose leaf is in the diff'
    );
    require_(
      !sel.ids.has('selftest:q-untouched'),
      '--quick must DEFER a slow gate the diff does not touch'
    );
    require_(sel.ids.has('selftest:q-fast'), 'CONTROL: the fast gate must stay in the quick lane');
    require_(
      /deferred, untouched \(1\): selftest:q-untouched/.test(said),
      `the untouched slow gate must be LISTED as deferred, said: ${said}`
    );
    require_(
      select(qSpecs, quick, () => {}, deps(['scripts/ci-runner/gate-spec.ts'])).ids.has(
        'selftest:q-untouched'
      ),
      'CONTROL: the deferred gate must be selectable when ITS leaf changes, or its deferral above says nothing about the diff'
    );
    require_(
      !select(qSpecs, quick, () => {}, deps([])).ids.has('selftest:q-touched'),
      'CONTROL: an empty diff must select no slow gate, or selection ignores the diff'
    );
    // ONE PASS (PLAN-prepush-full-cpu part 2): the touched slow gate is in this run and named in slowAdmitted, and nothing is dropped. A budget restored anywhere in the selection would drop it here, or name a budget.
    require_(
      (sel.slowAdmitted ?? []).join() === 'selftest:q-touched' &&
        (sel.droppedTouched ?? ['unset']).length === 0 &&
        !/DROPPED|budget/.test(said),
      `a touched slow gate must run in this one pass, in slowAdmitted, with nothing dropped; got slowAdmitted ${JSON.stringify(sel.slowAdmitted)}, droppedTouched ${JSON.stringify(sel.droppedTouched)}, said: ${said}`
    );
    said = '';
    const lost = select(qSpecs, quick, capture, deps(undefined));
    require_(
      !lost.ids.has('selftest:q-touched') && /could not find the last push/.test(said),
      'an unresolvable push base must select no slow gate and SAY so'
    );
    require_(
      select(qSpecs, EMPTY_OPTS, () => {}, deps([])).ids.size === 3,
      'CONTROL: without --quick every gate stays selected'
    );
    // A TOUCHED TREE WRITER IS REFUSED BY NAME, whatever it costs; the identical spec without the claim is admitted, so the refusal is about the claim.
    said = '';
    const writer = {
      ...qSpecs[1],
      mutex: ['tree:repo'],
      writesTree: 'appends a fixture row',
    };
    const wSel = select(
      [qSpecs[0], writer],
      quick,
      capture,
      deps(['scripts/ci-runner/quick-select.ts'])
    );
    require_(
      !wSel.ids.has('selftest:q-touched') &&
        /DROPPED selftest:q-touched.*writes the shared tree/.test(said),
      `a touched slow gate that writes the tree must be dropped BY NAME, said: ${said}`
    );
    // THE DROP REACHES THE SELECTION, so the receipt can name it: kind tree, and the command that runs it.
    const wDrop = wSel.droppedTouched ?? [];
    require_(
      wDrop.length === 1 &&
        wDrop[0].id === 'selftest:q-touched' &&
        wDrop[0].kind === 'tree' &&
        wDrop[0].run.includes('--only selftest:q-touched') &&
        wDrop[0].why.includes('quick-select.ts'),
      `a dropped touched gate must reach sel.droppedTouched with kind tree and its --only command, got ${JSON.stringify(wDrop)}`
    );
    require_(
      (
        select([qSpecs[0], writer], quick, () => {}, deps(['scripts/ci-runner/gate-spec.ts']))
          .droppedTouched ?? ['unset']
      ).length === 0,
      'CONTROL: the same writer with its leaf outside the diff must leave droppedTouched empty'
    );
    require_(
      (select(
        [qSpecs[0], writer],
        { ...quick, receiptOut: '/snap/r.json' },
        () => {},
        deps(['scripts/ci-runner/quick-select.ts'])
      ).droppedTouched ?? [])[0]?.run.endsWith('--receipt-out /snap/r.json') === true,
      "a dropped gate's command must carry this run's --receipt-out, so its re-run lands in the same receipt"
    );
    // A CLEAN, DISPOSABLE CLONE admits the writer; the shared checkout does not.
    said = '';
    const dSel = select(
      [qSpecs[0], writer],
      quick,
      capture,
      deps(['scripts/ci-runner/quick-select.ts'], true)
    );
    require_(
      dSel.ids.has('selftest:q-touched') &&
        /SELECTED selftest:q-touched \(tree writer; disposable clone/.test(said) &&
        (dSel.treeWritersAdmitted ?? []).includes('selftest:q-touched'),
      `in a disposable clone a touched tree writer must be SELECTED and named as one, said: ${said}`
    );
    require_(
      (dSel.droppedTouched ?? ['unset']).length === 0,
      'CONTROL: a disposable clone that admitted the writer drops nothing'
    );
  }

  // A `--only` RUN OF A DROPPED GATE MERGES INTO THE WHOLE RECEIPT OF THE SAME TREE, and nothing else does.
  {
    const whole = {
      headTree: 't',
      whole: true,
      exitCode: 0,
      failed: [] as string[],
      findings: {},
      droppedTouched: [{ id: 'x', why: 'w', reason: 'r', kind: 'tree', run: 'c' }],
      droppedVerified: {},
    };
    const onlyRun = (tree: string, ids: string[], status: string): OnlyRun => ({
      tree,
      ids,
      results: ids.map((id) => ({ id, status })),
      findings: status === 'fail' ? Object.fromEntries(ids.map((id) => [id, ['k1']])) : {},
      finishedAt: 'now',
      judgedRoot: '/r',
      stable: true,
    });
    const green = mergeDroppedVerified(whole, onlyRun('t', ['x'], 'ok')).merged;
    require_(
      green !== undefined &&
        green.whole === true &&
        green.droppedVerified.x?.exitCode === 0 &&
        green.droppedVerified.x?.headTree === 't' &&
        green.exitCode === 0 &&
        green.failed.length === 0,
      `a passing --only x at the receipt's tree must land in droppedVerified and keep whole, got ${JSON.stringify(green)}`
    );
    require_(
      mergeDroppedVerified(whole, onlyRun('u', ['x'], 'ok')).merged === undefined,
      'CONTROL: an --only run at another tree must not merge'
    );
    require_(
      mergeDroppedVerified(whole, onlyRun('', ['x'], 'ok')).merged === undefined,
      'CONTROL: an --only run whose HEAD moved (no tree) must not merge'
    );
    require_(
      mergeDroppedVerified(whole, onlyRun('t', ['y'], 'ok')).merged === undefined,
      'CONTROL: an --only run of a gate the receipt did not drop must not merge (it stays "kept")'
    );
    require_(
      mergeDroppedVerified({ ...whole, whole: false }, onlyRun('t', ['x'], 'ok')).merged ===
        undefined,
      'CONTROL: a narrowed receipt is never merged into'
    );
    const red = mergeDroppedVerified(whole, onlyRun('t', ['x'], 'fail')).merged;
    require_(
      red?.failed.includes('x') === true &&
        red.exitCode === 1 &&
        red.droppedVerified.x?.exitCode === 1 &&
        JSON.stringify(red.findings.x) === '["k1"]',
      `a red --only x must land in failed with exitCode 1 and its findings, got ${JSON.stringify(red)}`
    );
    const healed = mergeDroppedVerified(red, onlyRun('t', ['x'], 'ok')).merged;
    require_(
      healed !== undefined &&
        healed.failed.length === 0 &&
        healed.exitCode === 0 &&
        !('x' in healed.findings),
      `a later passing --only x must clear the red an earlier merge recorded, got ${JSON.stringify(healed)}`
    );
    const wholeRed = mergeDroppedVerified(
      { ...red, failed: ['check:a', 'x'], exitCode: 1 },
      onlyRun('t', ['x'], 'ok')
    ).merged;
    require_(
      wholeRed !== undefined && wholeRed.failed.join() === 'check:a' && wholeRed.exitCode === 1,
      `CONTROL: a pass of x must keep the whole lane's own failures and exit code, got ${JSON.stringify(wholeRed)}`
    );
  }

  // THE GRANT REACHES THE GATE (PLAN-prepush-full-cpu part 1): CI_RUNNER_CORES always, CI_CORE_LEASE_HELD only when the lease backs it, and an inherited held flag is dropped when this run does not hold one. 11 assertions.
  {
    const probe = syntheticSpec(
      'selftest:grant',
      `echo "granted=[$${CORES_ENV}] held=[$${LEASE_HELD_ENV}]"`
    );
    const held = await execGate(probe, { ...wrapOpts, grant: { cores: 7, leaseHeld: true } });
    require_(
      held.stdout.trim() === 'granted=[7] held=[1]',
      `a granted gate must see CI_RUNNER_CORES=7 and CI_CORE_LEASE_HELD=1, saw ${held.stdout.trim()}`
    );
    const unheld = gateEnv(probe, { cores: 3, leaseHeld: false }, { [LEASE_HELD_ENV]: '1' });
    require_(
      unheld[CORES_ENV] === '3' && unheld[LEASE_HELD_ENV] === undefined,
      `a grant the lease does not back must drop an inherited CI_CORE_LEASE_HELD, got ${JSON.stringify(unheld)}`
    );
    const declared = gateEnv({ env: { [CORES_ENV]: '99' } }, { cores: 4, leaseHeld: false }, {});
    require_(
      declared[CORES_ENV] === '4',
      `the grant must win over a declared env value, got ${declared[CORES_ENV]}`
    );
    const none = gateEnv(probe, undefined, { [CORES_ENV]: '5' });
    require_(
      none[CORES_ENV] === '5',
      'CONTROL: with no grant (a direct execGate call) the inherited env passes through untouched'
    );
    // THROUGH runPool: an elastic gate beside four one-core gates is told the area rule's grant; every gate is told a grant. C 8, the elastic gate measured at 40 cpu-s, the others 1 s each: other = 4 s, k = floor(8 / (1 + 4/40)) = 7.
    const seen = new Map<string, number>();
    const elasticSpecs: GateSpec[] = [
      { ...syntheticSpec('selftest:elastic', 'true'), cores: { min: 2, max: 'all' } },
      ...[1, 2, 3, 4].map((n) => syntheticSpec(`selftest:one-${n}`, 'true')),
    ];
    const pooled = await runPool(elasticSpecs, {
      jobs: 8,
      heavyLimit: 1,
      failFast: false,
      durations: new Map(),
      sched: 'cores',
      budget: { cores: 8, epsilon: 0, maxProcs: 16, memMb: 64 * 1024 },
      costs: new Map([
        ['selftest:elastic', { cpuMs: 40_000, wallMs: 5_000, perCore: 1 }],
        ...[1, 2, 3, 4].map((n): [string, GateCost] => [
          `selftest:one-${n}`,
          { cpuMs: 1_000, wallMs: 1_000 },
        ]),
      ]),
      exec: async (spec, grant) => {
        seen.set(spec.id, grant.cores);
        return { code: 0, stdout: '', stderr: '', ms: 1 };
      },
    });
    require_(
      seen.get('selftest:elastic') === 7,
      `the elastic gate must be granted the area rule's 7 of C 8, got ${seen.get('selftest:elastic')}`
    );
    require_(
      [1, 2, 3, 4].every((n) => seen.get(`selftest:one-${n}`) === 1),
      `every one-core gate must be told a grant of 1, got ${JSON.stringify([...seen])}`
    );
    require_(
      pooled.find((r) => r.id === 'selftest:elastic')?.grantedCores === 7 &&
        pooled.find((r) => r.id === 'selftest:elastic')?.elastic === true,
      'the grant and the elastic flag must land on the GateResult'
    );
    require_(
      grantsOf(pooled)['selftest:one-1'] === 1 && grantsOf(pooled)['selftest:elastic'] === 7,
      `the receipt's grantedCores must carry every launched gate, got ${JSON.stringify(grantsOf(pooled))}`
    );
    // A LEASE SHORT OF `min` HOLDS THE ELASTIC GATE while something runs, and the gate still runs once the lease frees: a fake lease with 1 free core and a running one-core gate.
    const order: string[] = [];
    let held1 = 0;
    const fakeLease: PoolLease = {
      held: true,
      available: async (inUse) => ({ free: Math.max(0, 2 - inUse), share: 2, total: 2 }),
      reconcile: async (c) => {
        held1 = Math.min(2, Math.ceil(c - 1e-9));
        return held1;
      },
    };
    const leased = await runPool(
      [
        { ...syntheticSpec('selftest:lease-wide', 'true'), cores: { min: 2, max: 'all' } },
        syntheticSpec('selftest:lease-one', 'true'),
      ],
      {
        jobs: 8,
        heavyLimit: 1,
        failFast: false,
        durations: new Map([
          ['selftest:lease-one', 9_000_000],
          ['selftest:lease-wide', 1_000],
        ]),
        sched: 'cores',
        budget: { cores: 8, epsilon: 0, maxProcs: 16, memMb: 64 * 1024 },
        lease: fakeLease,
        exec: async (spec, grant) => {
          order.push(`${spec.id}@${grant.cores}${grant.leaseHeld ? '+held' : ''}`);
          await new Promise((r) => setTimeout(r, spec.id === 'selftest:lease-one' ? 50 : 1));
          return { code: 0, stdout: '', stderr: '', ms: 1 };
        },
      }
    );
    require_(
      order.join() === 'selftest:lease-one@1+held,selftest:lease-wide@2+held' &&
        leased.find((r) => r.id === 'selftest:lease-wide')?.blockedBy === 'lease',
      `a lease with fewer free cores than min must hold the elastic gate with 'lease' until it frees, got ${order.join()} blockedBy ${leased.find((r) => r.id === 'selftest:lease-wide')?.blockedBy}`
    );
    require_(held1 === 0, `every token must be released when the pool drains, ${held1} still held`);

    // B11: ONE FREE TOKEN AND NOTHING RUNNING HOLDS, never launches at `min` on one token. The fake lease has 4 tokens, 3 held by another run until 150 ms; the gate's fair wall (60 cpu-s over a share of 4) is 15 s, far past the release, so it must wait for it and then start on tokens it holds.
    const t0 = Date.now();
    let mine = 0;
    const othersHold = (): number => (Date.now() - t0 < 150 ? 3 : 0);
    const lone: { at: number; cores: number }[] = [];
    const loneLease: PoolLease = {
      held: true,
      available: async (inUse) => ({
        free: Math.max(0, 4 - othersHold() - mine) + Math.max(0, mine - inUse),
        share: 4,
        total: 4,
      }),
      reconcile: async (c) => {
        mine = Math.min(Math.ceil(c - 1e-9), 4 - othersHold());
        return mine;
      },
    };
    const alone = await runPool(
      [{ ...syntheticSpec('selftest:lease-alone', 'true'), cores: { min: 2, max: 'all' } }],
      {
        jobs: 8,
        heavyLimit: 1,
        failFast: false,
        durations: new Map(),
        sched: 'cores',
        budget: { cores: 8, epsilon: 0, maxProcs: 16, memMb: 64 * 1024 },
        costs: new Map([['selftest:lease-alone', { cpuMs: 60_000, wallMs: 30_000, perCore: 1 }]]),
        lease: loneLease,
        leasePollMs: 20,
        exec: async (_spec, grant) => {
          lone.push({ at: Date.now() - t0, cores: grant.cores });
          return { code: 0, stdout: '', stderr: '', ms: 1 };
        },
      }
    );
    const aloneResult = alone.find((r) => r.id === 'selftest:lease-alone');
    require_(
      lone.length === 1 &&
        lone[0].at >= 150 &&
        lone[0].cores === 4 &&
        aloneResult?.blockedBy === 'lease' &&
        aloneResult.overLease === undefined,
      `a lease with 1 free token and nothing running must hold the elastic gate until the tokens free, then run on 4 it holds, got ${JSON.stringify(lone)} blockedBy ${aloneResult?.blockedBy} overLease ${JSON.stringify(aloneResult?.overLease)}`
    );
    require_(
      mine === 0,
      `the lone gate's tokens must be released when the pool drains, ${mine} held`
    );
  }

  // A RETIRED FIELD IS REFUSED BY NAME; a well-formed range is not. 4 assertions.
  {
    const weighted = retiredFieldFindings([{ id: 'g', weight: 2 }]);
    require_(
      weighted.length === 1 && /g: `weight` is retired/.test(weighted[0]),
      `a spec carrying weight must be refused by name, got ${JSON.stringify(weighted)}`
    );
    require_(
      retiredFieldFindings([{ id: 'g', cores: { min: 0, max: 'all' } }]).length === 1 &&
        retiredFieldFindings([{ id: 'g', cores: { min: 4, max: 2 } }]).length === 1,
      'a cores range with min < 1 or max < min must be refused'
    );
    require_(
      retiredFieldFindings([
        { id: 'g', cores: { min: 2, max: 'all' } },
        { id: 'h', cores: { min: 1, max: 8 } },
        { id: 'i' },
      ]).length === 0,
      'CONTROL: well-formed cores ranges and a spec with none must pass'
    );
    require_(
      retiredFieldFindings(GATES as unknown[]).every((f) => !f.includes('`cores`')),
      'the real manifest must carry no malformed cores range'
    );
  }

  // THE LEASE CLIENT against fake brokers (lease-client.ts).
  const leaseCheck = await leaseClientSelftest(os.tmpdir());
  for (const f of leaseCheck.failures) require_(false, `lease-client: ${f}`);

  // THE ADVANCE (PLAN-prepush-full-cpu part 5): every refusal and the chain. 11 assertions.
  {
    const policy = parseRecordPolicy(
      JSON.stringify({
        records: [
          { glob: 'agent/reviews/**', readers: [{ id: 'g:plan', evidence: 'x' }] },
          {
            glob: 'agent/worklist/*.jsonl',
            except: ['agent/worklist/epics.jsonl'],
            readers: [{ id: 'g:tree', evidence: 'y' }],
          },
          { glob: 'agent/quiet/**', readers: [] },
        ],
      })
    );
    const known = new Set(['g:plan', 'g:tree']);
    const whole = { whole: true, headTree: 'T0', advances: [] as Advance[] };
    const at =
      (paths: string[]) =>
      (from: string, to: string): string[] | undefined =>
        from === 'T0' && to === 'T1' ? paths : undefined;
    const plan = (receipt: unknown, paths: string[]) =>
      planAdvance({ receipt, headTree: 'T1', policy, diff: at(paths), known });
    const ok = plan(whole, ['agent/reviews/1004-2/clean.jsonl', 'agent/worklist/d.jsonl']);
    require_(
      ok.kind === 'advance' && ok.from === 'T0' && ok.readers.join() === 'g:plan,g:tree',
      `a record-only diff must advance with the union of its readers, got ${JSON.stringify(ok)}`
    );
    const quiet = plan(whole, ['agent/quiet/a']);
    require_(
      quiet.kind === 'advance' && quiet.readers.length === 0,
      'a record glob with no reader must advance with no gate to run'
    );
    require_(
      plan(whole, ['agent/reviews/x.md', 'scripts/ci-runner/run.ts']).kind === 'full',
      'a diff holding one code path must run the whole lane'
    );
    require_(
      plan(whole, ['agent/worklist/epics.jsonl']).kind === 'full',
      'an `except` path must count as outside the record set'
    );
    require_(
      planAdvance({
        receipt: whole,
        headTree: 'T1',
        policy: undefined,
        diff: at(['agent/reviews/x.md']),
        known,
      }).kind === 'full',
      'no policy at HEAD must run the whole lane'
    );
    require_(
      plan({ ...whole, whole: false }, ['agent/reviews/x.md']).kind === 'full' &&
        plan({ ...whole, headTree: '' }, ['agent/reviews/x.md']).kind === 'full' &&
        plan(undefined, ['agent/reviews/x.md']).kind === 'full',
      'a narrowed receipt, a receipt naming no tree, and no receipt must each run the whole lane'
    );
    require_(
      planAdvance({ receipt: whole, headTree: 'T0', policy, diff: at([]), known }).kind === 'full',
      'CONTROL: a receipt already naming HEAD is not advanced'
    );
    require_(
      planAdvance({
        receipt: whole,
        headTree: 'T1',
        policy,
        diff: at(['agent/reviews/x.md']),
        known: new Set(['g:tree']),
      }).kind === 'full',
      'a policy naming a reader that is no manifest gate must run the whole lane'
    );
    const chained = planAdvance({
      receipt: {
        ...whole,
        advances: [{ from: 'T0', to: 'T1', paths: [], gates: {}, finishedAt: '' }],
      },
      headTree: 'T2',
      policy,
      diff: (from, to) => (from === 'T1' && to === 'T2' ? ['agent/reviews/y.md'] : undefined),
      known,
    });
    require_(
      chained.kind === 'advance' && chained.from === 'T1' && chained.to === 'T2',
      `a second advance must start where the chain ends, got ${JSON.stringify(chained)}`
    );
    require_(
      typeof parseRecordPolicy('{"records":[{"glob":"a/**","readers":["bare-string"]}]}') ===
        'string' && typeof parseRecordPolicy('not json') === 'string',
      'a malformed policy must be refused with a reason, never half-read'
    );
    require_(
      Array.isArray(policy) && policy.length === 3,
      'CONTROL: the well-formed fixture policy must parse, or every refusal above is about the parser'
    );
  }

  if (failures.length > 0) {
    process.stderr.write('CONTROL FAILED: ci-runner --selftest did not fire\n');
    for (const f of failures) process.stderr.write(`  - ${f}\n`);
    process.stderr.write('--- selftest transcript ---\n');
    process.stderr.write(text);
    return 1;
  }
  process.stdout.write(
    `ci-runner: selftest ok (${9 + 1 + keyed.assertions + 3 + 7 + 3 + 2 + 3 + 4 + 12 + (process.platform !== 'win32' ? 4 : 0) + 6 + sim.assertions + 2 + qs.assertions + 10 + 5 + 9 + 10 + 4 + leaseCheck.assertions + 11} assertions)\n`
  );
  return 0;
}

/**
 * THE RECEIPT EXISTS SO A PUSH CAN BE CHECKED IN MICROSECONDS.
 *
 * The pre-push guard runs in the PreToolUse chain, which fires on every single
 * Bash call, so it cannot afford to run a gate -- but it can afford one
 * `git rev-parse` and one file read. The expensive half happens here, once,
 * and leaves an artifact naming exactly what it proved.
 *
 * KEYED ON `HEAD^{tree}`, NOT ON THE WORKTREE, and that choice is load-bearing
 * twice over. CI checks out the pushed commit, so the tree object is precisely
 * what CI will judge. And this repo's tree normally holds dozens of dirty paths
 * from OTHER live sessions -- keying on the worktree would invalidate the
 * receipt on someone else's keystroke and make it unobtainable.
 *
 * The honest residual: the gates ran against the WORKTREE, not against
 * `HEAD^{tree}`. So the digest of the dirty set is recorded too, and the guard
 * warns (naming files) when it has moved while the tree object has not.
 */
interface Receipt {
  headTree: string;
  head: string;
  branch: string;
  dirtyDigest: string;
  /**
   * Did the working tree hold still for the whole run?
   *
   * false means at least one file changed between the first and last sample, so
   * the gates did not all judge the same tree and a red may belong to the churn
   * rather than to the code. Not a guarantee of the converse: an edit made and
   * reverted inside the window leaves both samples equal, and two samples cannot
   * see that.
   */
  stable: boolean;
  selection: string | null;
  /**
   * The lane ran WHOLE. `--only`, `--skip` and `--changed` all narrow it, and a
   * receipt from a one-gate run would otherwise read exactly like a receipt
   * from all 254 -- the guard would then honour a push proven by nothing.
   * Recorded as a flag rather than left for the guard to infer from the
   * selection prose, because a guard parsing English is a guard that fails open
   * on a rewording.
   *
   * `--changed` was MISSING from this condition until 2026-09-06. It is the
   * narrowing that matters most, because `select()` drops every gate declaring
   * `paths` that the diff does not touch -- so a `--changed` run can execute a
   * small fraction of the lane and still write `whole: true`, and
   * `.claude/hooks/pre-bash/block-unverified-push.sh` reads exactly this field
   * to authorise the push. Unlike `--only`, which a human types deliberately
   * about one gate, `--changed` is the flag a session reaches for BECAUSE it
   * believes it is running the relevant lane, which is what made the hole quiet.
   */
  whole: boolean;
  /**
   * Which flags narrowed the lane; empty exactly when `whole` is true.
   *
   * Diagnostic, not load-bearing: the guard reads `whole`. It exists because
   * that guard's refusal text names `--only/--skip` only, so a run refused for
   * `--changed` would otherwise leave the reader nothing to go on.
   */
  narrowedBy: string[];
  /**
   * Gates that COULD NOT RUN here. Recorded separately from `failed` because
   * the guard treats them differently -- it warns, it does not refuse. A
   * missing toolchain is not evidence about the code, and a lane that refuses
   * on it is a lane that gets bypassed.
   */
  blocked: string[];
  exitCode: number;
  failed: string[];
  /**
   * The finding keys each FAILED gate printed as `::finding::<key>` lines (scripts/ci-runner/findings.ts), one entry per failed gate, inserted in gate-id order so this block is byte-stable for identical gate output. `null` means the gate printed no valid line, or more than the cap: never read as zero findings. The push guard compares these with the keys `.ci/config/carried-reds.json` carries, so a carried gate cannot hide a new finding.
   */
  findings: Record<string, string[] | null>;
  wallMs: number;
  finishedAt: string;
  /** The checkout the gates actually ran in. Differs from the pushing checkout when `--receipt-out` wrote this from a snapshot clone. */
  judgedRoot: string;
  /** Where the run's CPU went (report.ts Utilisation). Diagnostic; the push guard does not read it. */
  utilisation: Utilisation | null;
  /**
   * Slow gates the change set touched that this lane DROPPED (a tree writer, over budget, or unpriced), each with the command that runs it. Always written, `[]` when nothing dropped. The push guard refuses while any of them has no passing `droppedVerified` entry at this tree, and refuses a receipt with no such field at all.
   */
  droppedTouched: DroppedTouched[];
  /** `--only` runs of dropped gates merged into this receipt (`mergeDroppedVerified`), by gate id. Starts `{}`. */
  droppedVerified: Record<string, DroppedVerification>;
  /** The base the quick diff was taken against, with any tracking ref it skipped. Diagnostic; the guard does not read it. */
  pushBase: PushBaseRecord | null;
  /** The touched slow gates this one pass ran, in touch order (agent/plans/PLAN-prepush-full-cpu.md part 2). Diagnostic; the guard does not read it. Always written, `[]` when none. */
  slowAdmitted: string[];
  /** `{gate id: cores}` the pool granted each gate it launched, the CI_RUNNER_CORES its process saw. Diagnostic. Always written. */
  grantedCores: Record<string, number>;
  /** `{gate id: {ready, start, end, cores}}` in ms from the run's start, every launched gate (report.ts timelineOf). Diagnostic; the guard does not read it. Always written on a fresh run; absent on a receipt written before 2026-10-06. */
  timeline?: Record<string, GateTiming>;
  /**
   * Record-only steps this receipt was carried across, oldest first, each starting where the previous one (or `headTree`) ended (`runAdvance`). `[]` on a fresh whole run. The push guard accepts a pushed tree other than `headTree` only through this chain, recomputing every step's diff itself.
   */
  advances: Advance[];
}

function gitOut(args: readonly string[]): string {
  return execFileSync('git', [...args], { cwd: REPO_ROOT, encoding: 'utf-8' }).trim();
}

function dirtyDigest(): string {
  try {
    const porcelain = execFileSync('git', ['status', '--porcelain=v1', '-z'], {
      cwd: REPO_ROOT,
      encoding: 'utf-8',
      maxBuffer: 64 * 1024 * 1024,
    });
    return createHash('sha256').update(porcelain).digest('hex').slice(0, 16);
  } catch {
    return 'unreadable';
  }
}

const RECEIPT_PATH = path.join(REPO_ROOT, '.ci', 'cache', 'prepush-receipt.json');

/**
 * Every flag that makes this run LESS than the whole lane.
 *
 * `--quick` is deliberately not one of them: the receipt is only written for
 * quick runs, the lane IS quick by definition, and the push guard's own message
 * says so ("a PARTIAL run ... slower gates are deferred to CI").
 *
 * Extracted from the receipt literal so the selftest can assert it. The bug it
 * exists to keep out was one missing term in an inline boolean, which nothing
 * could reach.
 */
function narrowingFlags(opts: Options): string[] {
  const flags: string[] = [];
  if (opts.only !== undefined) flags.push('--only');
  if (opts.skip !== undefined) flags.push('--skip');
  if (opts.changed) flags.push('--changed');
  return flags;
}

/**
 * The tree a receipt may vouch for. A run judges the tree HEAD named when it STARTED; if HEAD moved before the receipt was written (a commit landed mid-run), no single tree was judged, so the receipt vouches for none and the push guard, which demands tree equality, refuses it. Found 2026-09-24: the tree used to be read at write time, so a mid-run commit bound a verdict to a tree nothing had judged.
 */
function receiptTree(atStart: string, atEnd: string): string {
  return atStart !== '' && atStart === atEnd ? atStart : '';
}

/**
 * `git rev-parse HEAD^{tree}`, or '' when git cannot answer or a submodule checkout disagrees with its gitlink.
 *
 * HEAD^{tree} names each submodule by its gitlink, so a checkout left at another commit (a `+` line in `git submodule status`) means the gates judged code the tree does not contain. Found 2026-10-05 (#a423d9ab): a push clone reset with `git reset --hard` kept private/account at c5cc76f against gitlink 050e15c, and check:deps and every account gate passed judgement on the old account. Such a run vouches for no tree, the same rule as a mid-run HEAD move.
 */
function headTreeNow(): string {
  let tree: string;
  try {
    tree = gitOut(['rev-parse', 'HEAD^{tree}']);
  } catch {
    return '';
  }
  const stale = staleSubmodules();
  if (stale.length > 0) {
    process.stderr.write(
      `ci-runner: the receipt vouches for no tree: submodule checkout(s) disagree with their gitlinks (${stale.join(', ')}). Run \`git submodule update --init\` and re-run.\n`
    );
    return '';
  }
  return tree;
}

/** Submodule paths whose checkout is at another commit than the gitlink (`git submodule status` `+` lines); [] when git cannot answer. */
function staleSubmodules(): string[] {
  let out: string;
  try {
    out = gitOut(['submodule', 'status']);
  } catch {
    return [];
  }
  return parseStaleSubmodules(out);
}

/** The paths on `git submodule status` lines that start with `+` (checked out off the gitlink). */
function parseStaleSubmodules(status: string): string[] {
  return status
    .split('\n')
    .filter((line) => line.startsWith('+'))
    .map((line) => line.slice(1).trim().split(/\s+/)[1] ?? line);
}

/** The receipt's destination: `--receipt-out` when given, else this checkout's own cache. */
function receiptPathFor(opts: Options): string {
  return opts.receiptOut ?? RECEIPT_PATH;
}

/**
 * A narrowed run (`--only`, `--skip`, `--changed`) never replaces a WHOLE receipt. Found 2026-09-30: a one-gate `--quick --only` re-check after a push-clone receipt overwrote `.ci/cache/prepush-receipt.json` with `whole: false`, so the push that the whole lane had just authorised was refused. The whole receipt still names its own tree, so the guard's tree check keeps it honest when HEAD has moved since.
 */
function narrowedWouldReplaceWhole(dest: string, whole: boolean): boolean {
  if (whole) return false;
  try {
    return (JSON.parse(fs.readFileSync(dest, 'utf8')) as Partial<Receipt>).whole === true;
  } catch {
    return false;
  }
}

/** What one `--only` run hands `mergeDroppedVerified`. */
interface OnlyRun {
  tree: string;
  ids: readonly string[];
  results: ReadonlyArray<{ id: string; status: string }>;
  findings: Record<string, string[] | null>;
  finishedAt: string;
  judgedRoot: string;
  stable: boolean;
}

/**
 * A `--only` run of DROPPED gates merges into the whole receipt of the same tree, and nothing else does. `existing` must be `whole: true`, name `run.tree` (non-empty), and list every one of `run.ids` in its `droppedTouched`; anything else returns `merged: undefined` with the reason, and the caller keeps today's behaviour. Each id lands in `droppedVerified`; a failure joins `failed` and its findings, a pass leaves both, and `exitCode` is the worst of the whole lane and the dropped runs.
 */
function mergeDroppedVerified(existing: unknown, run: OnlyRun): { merged?: Receipt; why: string } {
  if (existing === null || typeof existing !== 'object') return { why: 'no receipt to merge into' };
  const prior = existing as Partial<Receipt>;
  if (prior.whole !== true) return { why: 'the receipt on disk is not a whole-lane receipt' };
  if (run.tree === '' || prior.headTree !== run.tree)
    return {
      why: `the receipt judged tree ${prior.headTree || '(none)'}, this run ${run.tree || '(none)'}`,
    };
  const dropped = new Set(
    (Array.isArray(prior.droppedTouched) ? prior.droppedTouched : []).map((d) => d.id)
  );
  const outside = run.ids.filter((id) => !dropped.has(id));
  if (run.ids.length === 0 || outside.length > 0)
    return {
      why: `not every selected gate was dropped by that receipt (${outside.join(', ') || 'none selected'})`,
    };
  const verified: Record<string, DroppedVerification> = { ...(prior.droppedVerified ?? {}) };
  const priorFailedDrop = Object.values(verified).some((v) => v.exitCode !== 0);
  // A dropped gate never ran in the whole lane, so any id of it in `failed` came from an earlier merge.
  const wholeFailed = (prior.failed ?? []).filter(
    (id) => !(id in verified) && !run.ids.includes(id)
  );
  const findings: Record<string, string[] | null> = { ...(prior.findings ?? {}) };
  for (const id of run.ids) {
    const status = run.results.find((r) => r.id === id)?.status;
    verified[id] = {
      exitCode: status === 'ok' ? 0 : 1,
      headTree: run.tree,
      finishedAt: run.finishedAt,
      judgedRoot: run.judgedRoot,
      stable: run.stable,
    };
    delete findings[id];
    if (status === 'fail' && id in run.findings) findings[id] = run.findings[id];
  }
  const droppedFailed = Object.keys(verified).filter((id) => verified[id].exitCode !== 0);
  const failed = [...wholeFailed, ...droppedFailed.filter((id) => !wholeFailed.includes(id))];
  const priorExit = typeof prior.exitCode === 'number' ? prior.exitCode : 1;
  const wholeExit = priorFailedDrop ? (wholeFailed.length > 0 ? priorExit : 0) : priorExit;
  return {
    merged: {
      ...(prior as Receipt),
      droppedVerified: verified,
      failed,
      findings,
      exitCode: Math.max(wholeExit, droppedFailed.length > 0 ? 1 : 0),
    },
    why: 'merged',
  };
}

function writeReceipt(receipt: Receipt, dest: string, warn: (text: string) => void): void {
  if (narrowedWouldReplaceWhole(dest, receipt.whole)) {
    warn(
      `ci-runner: a narrowed run does not replace the whole-lane receipt at ${dest}; that receipt is kept\n`
    );
    return;
  }
  try {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, `${JSON.stringify(receipt, null, 2)}\n`);
  } catch (err) {
    // LOUD, unlike the duration cache. That cache is an optimisation and is deliberately non-load-bearing; this authorises a push, so a silent failure to write it would present as "you never ran the gates".
    warn(`ci-runner: could not write the push receipt: ${(err as Error).message}\n`);
  }
}

/**
 * T2.10 local reproduction: `npm run ci -- --lane <lane> --shard i/N` replays exactly one
 * committed leg, read from `.ci/config/shards/<lane>.json` -- the SAME file a CI leg's
 * `--shard-manifest` would read, never a live `shardPlan` re-run, so a local replay can
 * never disagree with what was reviewed and committed.
 *
 * ONLY WORKS TODAY FOR A GATE-BACKED LANE (`quality-code`): its shard ids are gate ids
 * already in `specs`, so translating them into `--only` reuses the whole pool unchanged.
 * A TEST lane's shard holds test-runner unit ids (a spec file, a Go package, ...), which
 * this pool does not know how to execute -- refusing by name here is the honest answer,
 * not a silent zero-gate run.
 */
function resolveLaneShard(
  lane: string,
  shard: { index: number; of: number },
  specs: readonly GateSpec[],
  root: string = REPO_ROOT
): string[] {
  const rel = shardManifestPath(lane);
  const abs = path.join(root, rel);
  if (!fs.existsSync(abs)) {
    throw new Error(
      `ci-runner: --lane ${lane}: no shard manifest at ${rel}. It is generated alongside ` +
        "the workflow's shard-strategy region; run gate-bind's writer, or ask the lane's owner."
    );
  }
  const file = parseShardManifest(fs.readFileSync(abs, 'utf-8'), lane);
  const ids = legIds(file, shard.index, shard.of);
  const specIds = new Set(specs.map((s) => s.id));
  const known = ids.filter((id) => specIds.has(id));
  if (known.length === 0) {
    throw new Error(
      `ci-runner: --lane ${lane}: none of this leg's ${ids.length} unit(s) are check gates ` +
        '(this is a test lane, not a quality lane). Local replay for a test lane is not ' +
        "implemented here yet; run the lane's own test command with this leg's manifest " +
        `directly: ${rel}.`
    );
  }
  if (known.length !== ids.length) {
    const missing = ids.filter((id) => !specIds.has(id));
    throw new Error(
      `ci-runner: --lane ${lane}: ${missing.length} of this leg's ${ids.length} unit(s) are ` +
        `not check gates (${missing.slice(0, 3).join(', ')}${missing.length > 3 ? ', ...' : ''}). ` +
        'A mixed leg cannot be replayed through this pool.'
    );
  }
  return known;
}

async function listUnits(lane: string | undefined): Promise<number> {
  try {
    for (const unit of await unitsFrom(lane ?? '', REPO_ROOT)) {
      process.stdout.write(`${JSON.stringify(unit)}\n`);
    }
    return 0;
  } catch (error) {
    process.stderr.write(`ci-runner: ${(error as Error).message}\n`);
    return 2;
  }
}

/** `{gate id: cores granted}` for every gate that launched; the receipt's `grantedCores`. */
function grantsOf(results: readonly GateResult[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of results) if (r.grantedCores !== undefined) out[r.id] = r.grantedCores;
  return out;
}

/**
 * Schedule one graph through the pool and print it: the budget, the lease, the per-gate lines and the footer. Shared by the lane and by an advance's readers, so both draw from the same lease and report the same shape.
 */
async function runGraph(
  graph: readonly GateSpec[],
  opts: Options,
  description: string | undefined,
  humanOut: (text: string) => void
): Promise<{
  results: GateResult[];
  exitCode: number;
  wallMs: number;
  util?: Utilisation;
  startedAt: number;
}> {
  // A runner nested inside a gate sizes itself from the grant it was launched with, never from the whole machine.
  const jobs = opts.jobs ?? grantFromEnv() ?? Math.max(1, os.availableParallelism() - 2);
  const heavyLimit = opts.heavyLimit ?? Math.max(2, Math.floor(jobs / 4));
  // A synthetic manifest must not pollute (or be scheduled by) the real duration cache, so caching is off unless the caller names a path.
  const cachePath =
    process.env.CI_RUNNER_CACHE ?? (opts.manifest === undefined ? DEFAULT_CACHE : undefined);
  const durations = loadDurations(cachePath);
  // Scheduling estimates: this machine's timings, else the committed CI step p90, so a long gate never timed here (a fresh clone's pytest) still starts in the first wave. The cache keeps learning from `durations` alone.
  const estimates =
    opts.manifest === undefined ? new Map([...ciStepP90(), ...durations]) : durations;
  const sched: Sched = opts.sched ?? 'cores';
  // Under `cores`, --jobs names C, the core budget, rather than a slot count.
  const lease: RunnerLease | undefined =
    sched === 'cores' ? await openLease({ root: REPO_ROOT, warn: humanOut }) : undefined;
  const budget = sched === 'cores' ? coreBudget(opts.jobs, lease?.total) : undefined;

  const reporter = createReporter({
    idWidth: Math.min(46, Math.max(...graph.map((spec) => spec.id.length))),
    out: humanOut,
    jsonOut: opts.json ? (text: string) => process.stdout.write(text) : undefined,
  });
  const started = Date.now();
  const meta = {
    jobs,
    failFast: opts.failFast,
    selection: description,
    wallMs: 0,
    sched:
      budget === undefined
        ? undefined
        : `sched cores: C ${budget.cores} +${Math.round(budget.epsilon * 100)}%, K ${budget.maxProcs}, M ${(budget.memMb / 1024).toFixed(1)} GB`,
  };
  reporter.header(graph.length, meta);
  if (lease !== undefined) humanOut(`ci-runner: ${lease.note}\n`);
  const cpuSampler = startCpuSampler();
  let pooled: GateResult[];
  try {
    pooled = await runPool(graph, {
      jobs,
      heavyLimit,
      failFast: opts.failFast,
      durations: estimates,
      sched,
      budget,
      costs:
        sched === 'cores'
          ? costsFrom(loadDurationRecords(cachePath), loadFailCosts(cachePath))
          : undefined,
      lease,
      exec: (spec, grant: Grant) =>
        execGate(spec, { cwd: REPO_ROOT, mergeOutput: opts.mergeOutput, ...PROFILE_OPTS, grant }),
      onStart: opts.verbose
        ? (spec) => {
            reporter.start(spec.id);
          }
        : undefined,
      onFinish: (result) => {
        reporter.finish(result);
      },
    });
  } finally {
    lease?.close();
  }
  meta.wallMs = Date.now() - started;
  const cpu = cpuSampler.stop();
  const results = applyCaptures(pooled, PROFILE_OPTS.profileDir, PROFILE_OPTS.profileRunId);
  const util: Utilisation | undefined = utilisation(
    cpu.ticks,
    cpu.cores,
    results,
    criticalPath(graph, results),
    meta.wallMs
  );
  saveDurations(cachePath, durations, results);
  saveFailCosts(cachePath, results);
  const exitCode = reporter.footer(results, { ...meta, util, startedAt: started });
  // A grant above the tokens held is the bounded lease hold expiring, never routine; each one is named so a run that oversubscribed the machine says so.
  for (const r of results)
    if (r.overLease !== undefined)
      humanOut(
        `ci-runner: ${r.id} ran on ${r.overLease.granted} core(s) holding ${r.overLease.held} lease token(s): its lease hold reached its bound\n`
      );
  return { results, exitCode, wallMs: meta.wallMs, util, startedAt: started };
}

/**
 * THE RECORD SET (agent/plans/PLAN-prepush-full-cpu.md part 5): globs a commit may touch without voiding a receipt, each with the gates that read them. `.ci/policy/record-paths.json` at HEAD, owned by check:ci-record-paths, which derives the readers from every gate's leaves and reds when this list differs. The runner reads only `glob`, `except` and each reader's `id`:
 *
 *   { "records": [ { "glob": "agent/reviews/**", "except": [], "readers": [ { "id": "check:ci-plan-implementation", "evidence": "..." } ] } ] }
 */
interface RecordGlob {
  glob: string;
  except: string[];
  readers: string[];
}

/** The record set from the policy's text, or a sentence saying why it cannot be used. */
function parseRecordPolicy(raw: string): RecordGlob[] | string {
  let doc: unknown;
  try {
    doc = JSON.parse(raw);
  } catch (e) {
    return `record-paths.json is not JSON (${(e as Error).message})`;
  }
  const records = (doc as { records?: unknown } | null)?.records;
  if (!Array.isArray(records) || records.length === 0)
    return 'record-paths.json has no non-empty `records` array';
  const out: RecordGlob[] = [];
  for (const [i, r] of records.entries()) {
    const rec = r as { glob?: unknown; except?: unknown; readers?: unknown } | null;
    const except = rec?.except ?? [];
    if (
      typeof rec?.glob !== 'string' ||
      rec.glob === '' ||
      !Array.isArray(except) ||
      !except.every((e) => typeof e === 'string') ||
      !Array.isArray(rec.readers) ||
      !rec.readers.every((x) => typeof (x as { id?: unknown } | null)?.id === 'string')
    )
      return `record-paths.json records[${i}] is not { glob: string, except?: string[], readers: [{ id: string }] }`;
    out.push({
      glob: rec.glob,
      except: except as string[],
      readers: (rec.readers as { id: string }[]).map((x) => x.id),
    });
  }
  return out;
}

/** One record-only step a receipt was carried across without re-running the lane. */
interface Advance {
  /** The tree the step starts at: the receipt's headTree, or the previous step's `to`. */
  from: string;
  /** HEAD^{tree} when the readers ran, unchanged from start to end. */
  to: string;
  /** `git diff --name-only <from> <to>` as the runner saw it. The guard recomputes it rather than trusting this. */
  paths: string[];
  /** Every reader of every touched glob, with its exit code: 0 passed, 77 could not run, anything else failed. `{}` when the touched globs have no reader. */
  gates: Record<string, number>;
  finishedAt: string;
}

type AdvancePlan =
  | { kind: 'advance'; from: string; to: string; paths: string[]; readers: string[] }
  | { kind: 'full'; why: string };

/**
 * Whether a `--quick` run may ADVANCE the receipt instead of running the lane: the receipt on disk is whole and names a tree, HEAD has moved from the end of its chain, and every path that moved lies inside the record set. Pure, so the selftest drives every refusal; the caller supplies the diff and the policy.
 */
function planAdvance(input: {
  receipt: unknown;
  headTree: string;
  policy: RecordGlob[] | string | undefined;
  diff: (from: string, to: string) => string[] | undefined;
  known: ReadonlySet<string>;
}): AdvancePlan {
  const r = input.receipt as Partial<Receipt> | null | undefined;
  if (r === null || typeof r !== 'object' || r.whole !== true)
    return { kind: 'full', why: 'no whole-lane receipt to advance' };
  if (typeof r.headTree !== 'string' || r.headTree === '')
    return { kind: 'full', why: 'the receipt vouches for no tree' };
  const chain = Array.isArray(r.advances) ? r.advances : [];
  const from = chain.length > 0 ? chain[chain.length - 1].to : r.headTree;
  if (input.headTree === '') return { kind: 'full', why: 'HEAD^{tree} is unreadable' };
  if (from === input.headTree) return { kind: 'full', why: 'the receipt already names this tree' };
  if (input.policy === undefined)
    return { kind: 'full', why: 'HEAD carries no .ci/policy/record-paths.json' };
  if (typeof input.policy === 'string') return { kind: 'full', why: input.policy };
  const paths = input.diff(from, input.headTree);
  if (paths === undefined || paths.length === 0)
    return {
      kind: 'full',
      why: `git could not list what changed between ${from.slice(0, 9)} and ${input.headTree.slice(0, 9)}`,
    };
  const policy = input.policy;
  const matching = (p: string): RecordGlob[] =>
    policy.filter(
      (g) => globToRegExp(g.glob).test(p) && !g.except.some((e) => globToRegExp(e).test(p))
    );
  const outside = paths.filter((p) => matching(p).length === 0);
  if (outside.length > 0)
    return {
      kind: 'full',
      why: `${outside.length} changed path(s) lie outside the record set, e.g. ${outside.slice(0, 3).join(', ')}`,
    };
  const readers = [...new Set(paths.flatMap((p) => matching(p).flatMap((g) => g.readers)))].sort();
  const unknown = readers.filter((id) => !input.known.has(id));
  if (unknown.length > 0)
    return {
      kind: 'full',
      why: `record-paths.json names reader(s) that are not manifest gates: ${unknown.join(', ')}`,
    };
  return { kind: 'advance', from, to: input.headTree, paths, readers };
}

/** The record-set policy as HEAD carries it (the guard reads the same copy), parsed; undefined when HEAD has none. */
function recordPolicyAtHead(): RecordGlob[] | string | undefined {
  const raw = gitTry(['show', 'HEAD:.ci/policy/record-paths.json']);
  return raw === undefined ? undefined : parseRecordPolicy(raw);
}

/**
 * Run an advance: the readers of the touched globs (none when they have no reader), then append the step to the receipt. The step is written only when HEAD held still, for the same reason a receipt vouches for no tree after a mid-run commit.
 */
async function runAdvance(
  specs: readonly GateSpec[],
  plan: Extract<AdvancePlan, { kind: 'advance' }>,
  receipt: Receipt,
  dest: string,
  opts: Options,
  humanOut: (text: string) => void
): Promise<number> {
  const shown = plan.paths.slice(0, 5).join(', ') + (plan.paths.length > 5 ? ', ...' : '');
  humanOut(
    `ci-runner: --quick ADVANCE ${plan.from.slice(0, 9)} -> ${plan.to.slice(0, 9)}: ${plan.paths.length} record path(s) changed (${shown}); ` +
      (plan.readers.length > 0
        ? `running their ${plan.readers.length} reader(s) instead of the lane: ${plan.readers.join(', ')}\n`
        : 'no gate reads them, so nothing runs\n')
  );
  const gates: Record<string, number> = {};
  let exitCode = 0;
  if (plan.readers.length > 0) {
    const ran = await runGraph(
      buildGraph(specs, new Set(plan.readers)),
      opts,
      `--quick advance (readers of ${plan.paths.length} record path(s))`,
      humanOut
    );
    exitCode = ran.exitCode;
    for (const id of plan.readers) {
      const r = ran.results.find((x) => x.id === id);
      gates[id] = r === undefined ? 1 : r.status === 'ok' ? 0 : (r.exitCode ?? 1) || 1;
    }
  }
  if (receiptTree(plan.to, headTreeNow()) === '') {
    humanOut(
      'WARNING: HEAD moved while the readers ran, so this advance names no tree and is NOT recorded. Re-run on a HEAD that stays put.\n'
    );
    return 1;
  }
  const step: Advance = {
    from: plan.from,
    to: plan.to,
    paths: plan.paths,
    gates,
    finishedAt: new Date().toISOString(),
  };
  try {
    fs.writeFileSync(
      dest,
      `${JSON.stringify({ ...receipt, advances: [...(receipt.advances ?? []), step] }, null, 2)}\n`
    );
    humanOut(
      `ci-runner: receipt at ${dest} advanced to tree ${plan.to.slice(0, 9)} (advances[${(receipt.advances ?? []).length}])\n`
    );
  } catch (err) {
    humanOut(`ci-runner: could not write the push receipt: ${(err as Error).message}\n`);
    return 1;
  }
  return exitCode;
}

async function main(): Promise<number> {
  // `--list-units <lane>` prints the lane's test units, one JSON object per line (PLAN-ci-time-budget T2.8): the input to a shard manifest and to the per-unit durations T1.6/T3.2 measure. Handled before parseArgs, which knows only gate flags.
  const listUnitsAt = process.argv.indexOf('--list-units');
  if (listUnitsAt >= 0) return listUnits(process.argv[listUnitsAt + 1]);
  const opts = parseArgs(process.argv.slice(2));
  if (opts.selftest) return selftest();

  const specs = await loadManifest(opts.manifest);
  if (specs.length === 0) {
    process.stderr.write('ci-runner: Refusing to run: the manifest declares zero gates.\n');
    return 1;
  }
  // A RETIRED FIELD IS REFUSED, NOT IGNORED: `weight` left in a manifest would be scheduled on a number nothing reads (gate-spec.ts retiredFieldFindings).
  const retired = retiredFieldFindings(specs);
  if (retired.length > 0) {
    process.stderr.write(
      `ci-runner: Refusing to run: the manifest carries ${retired.length} retired or malformed field(s):\n${retired.map((f) => `  - ${f}\n`).join('')}`
    );
    return 1;
  }

  if (opts.lane !== undefined && opts.shard !== undefined) {
    try {
      opts.only = [...(opts.only ?? []), ...resolveLaneShard(opts.lane, opts.shard, specs)];
    } catch (err) {
      process.stderr.write(`${(err as Error).message}\n`);
      return 1;
    }
  }

  const humanOut = opts.json
    ? (text: string) => process.stderr.write(text)
    : (text: string) => process.stdout.write(text);

  // THE ADVANCE (agent/plans/PLAN-prepush-full-cpu.md part 5): a whole `--quick` run whose receipt is only a record-only commit behind runs those records' readers and appends a step, rather than the whole lane again. Every refusal is printed, so a whole run says why it was not an advance.
  if (opts.quick && !opts.list && narrowingFlags(opts).length === 0 && opts.lane === undefined) {
    const dest = receiptPathFor(opts);
    let existing: unknown;
    try {
      existing = JSON.parse(fs.readFileSync(dest, 'utf8'));
    } catch {
      existing = undefined;
    }
    const plan = planAdvance({
      receipt: existing,
      headTree: headTreeNow(),
      policy: recordPolicyAtHead(),
      // `--no-renames`: a rename lists only its NEW path, so `code.ts` moved to `agent/reviews/x.md` read as record-only and advanced, where block_unverified_push (which diffs with --no-renames) then refused the push. Both sides must list the old path too.
      diff: (from, to) =>
        gitTry(['diff', '--name-only', '--no-renames', from, to])?.split('\n').filter(Boolean),
      known: new Set(specs.map((spec) => spec.id)),
    });
    if (plan.kind === 'advance')
      return runAdvance(specs, plan, existing as Receipt, dest, opts, humanOut);
    humanOut(`ci-runner: --quick runs the whole lane, not an advance: ${plan.why}\n`);
  }

  // `--list` USED TO RETURN BEFORE `select()` RAN, so `--list --changed` printed all 314 specs whatever the scoping did. That is worse than unhelpful: it is an instrument that answers a question it never asked, and it is how --changed stayed inert without anyone noticing. Measured 2026-08-27 -- a reader (me) concluded from it that --changed scoped nothing, on evidence that could
  // not have shown otherwise.
  let selection: Selection;
  try {
    selection = select(specs, opts, humanOut);
  } catch (err) {
    // A REFUSAL IS NOT A CRASH, and it must not read as one. `--changed` with a change set it cannot trust exits 1 with the reason and the fix on stderr, rather than selecting the 418 gates that happen to declare no `paths` and reporting a green over the 46 it dropped.
    if (err instanceof ChangeSetRefusal) {
      process.stderr.write(`ci-runner: ${err.message}\n`);
      return 1;
    }
    throw err;
  }
  if (opts.list) {
    for (const spec of specs) {
      if (spec.gate && !selection.ids.has(spec.id)) continue;
      process.stdout.write(`${spec.gate ? 'gate ' : 'prereq'} ${spec.id.padEnd(48)} ${spec.run}\n`);
    }
    return 0;
  }

  const graph = buildGraph(specs, selection.ids);
  if (graph.length === 0) {
    process.stderr.write('ci-runner: Refusing to run: the selection matched zero gates.\n');
    // `--quick` narrows first and `--only` narrows what is left, so `npm run ci:quick -- --only <slow gate>` matches nothing: the quick lane already deferred it (#1434d694).
    const only = opts.only?.join(',') ?? '';
    if (opts.quick && only !== '') {
      process.stderr.write(
        `ci-runner: --only narrows the --quick lane, which defers slow gates. To run ${only} on its own: npx tsx scripts/ci-runner/run.ts --only ${only}\n`
      );
    }
    return 1;
  }

  // BEFORE runPool, not after: manifest.ts:2817 records a gate that writes a temp .ts into packages/cli and breaks check:format, and check-python-lint plants an untracked probe. A digest taken afterwards would record the gates' own leavings and drift from the tree the session actually has.
  const dirtyAtStart = dirtyDigest();
  const headTreeAtStart = headTreeNow();
  const { results, exitCode, wallMs, util, startedAt } = await runGraph(
    graph,
    opts,
    selection.description,
    humanOut
  );

  // THE RECEIPT IS MINTED ONLY BY A RUNNER THAT PROVED IT CAN FAIL.
  //
  // `--quick` runs selftest() first (see the npm key), and selftest() refuses to return 0 unless a planted failing gate produced exit 1, both captured streams, and a skipped dependent. A runner that cannot fail authorising a push would be strictly worse than no lane at all: it would replace "nobody checked" with "something green says it checked".
  //
  // Minted on RED as well as green, carrying the failing ids. The guard decides what a red receipt is worth; the runner's job is to record what happened, not to editorialise. A receipt that appeared only on success would make "gates failed" and "gates never ran" the same observation at the guard -- the exact conflation this repo keeps paying for. SAMPLE THE TREE AGAIN, and
  // compare. dirtyAtStart alone answers "was the tree dirty when we began"; it cannot answer "did it hold still", and those are different questions once anything else is running in this worktree. Two whole-lane runs were spent on 2026-08-27 discovering that four gates failed only in the lane and passed standalone every time, because a peer session was editing files mid-run. The
  // lane read a moving tree and said nothing.
  const dirtyAtEnd = dirtyDigest();
  if (dirtyAtEnd !== dirtyAtStart) {
    const writers = selection.treeWritersAdmitted ?? [];
    humanOut(
      'WARNING: the working tree CHANGED while these gates ran, so they did not all judge\n' +
        '  the same tree and a failure here may belong to the churn rather than to the code.\n' +
        '  Re-run on a still tree before believing a red. This worktree may be shared.' +
        (writers.length > 0
          ? `\n  This disposable clone admitted tree-writing gate(s) that may account for it: ${writers.join(', ')}.`
          : '') +
        '\n'
    );
  }

  // A `--only` RUN OF DROPPED GATES MERGES into the whole receipt of the same tree, quick or not: the command a DROPPED line prints is exactly this, and before 2026-10-04 it wrote no receipt at all, so a dropped gate could not be proven run. Every other narrowed run keeps the "kept" behaviour below.
  const narrowedBy = narrowingFlags(opts);
  let merged = false;
  if (!opts.manifest && narrowedBy.length === 1 && narrowedBy[0] === '--only') {
    const dest = receiptPathFor(opts);
    let existing: unknown;
    try {
      existing = JSON.parse(fs.readFileSync(dest, 'utf8'));
    } catch {
      existing = undefined;
    }
    const verdict = mergeDroppedVerified(existing, {
      tree: receiptTree(headTreeAtStart, headTreeNow()),
      ids: [...selection.ids],
      results,
      findings: receiptFindings(results, humanOut),
      finishedAt: new Date().toISOString(),
      judgedRoot: REPO_ROOT,
      stable: dirtyAtEnd === dirtyAtStart,
    });
    if (verdict.merged !== undefined) {
      try {
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.writeFileSync(dest, `${JSON.stringify(verdict.merged, null, 2)}\n`);
        humanOut(
          `ci-runner: merged ${[...selection.ids].join(', ')} into the whole-lane receipt at ${dest} (droppedVerified)\n`
        );
        merged = true;
      } catch (err) {
        humanOut(`ci-runner: could not write the push receipt: ${(err as Error).message}\n`);
      }
    } else if (existing !== undefined && (existing as Partial<Receipt>).whole === true) {
      humanOut(`ci-runner: this --only run did not merge into ${dest}: ${verdict.why}\n`);
    }
  }

  if (opts.quick && !opts.manifest && !merged) {
    writeReceipt(
      {
        headTree: (() => {
          const tree = receiptTree(headTreeAtStart, headTreeNow());
          if (tree === '' && headTreeAtStart !== '') {
            humanOut(
              'WARNING: HEAD moved while these gates ran, so this receipt vouches for no tree and\n' +
                '  cannot authorise a push. Re-run on a HEAD that stays put.'
            );
          }
          return tree;
        })(),
        head: (() => {
          try {
            return gitOut(['rev-parse', 'HEAD']);
          } catch {
            return '';
          }
        })(),
        branch: (() => {
          try {
            return gitOut(['branch', '--show-current']);
          } catch {
            return '';
          }
        })(),
        dirtyDigest: dirtyAtStart,
        stable: dirtyAtEnd === dirtyAtStart,
        selection: selection.description ?? null,
        whole: narrowedBy.length === 0,
        narrowedBy,
        exitCode,
        failed: results.filter((r) => r.status === 'fail').map((r) => r.id),
        findings: receiptFindings(results, humanOut),
        blocked: results.filter((r) => r.status === 'blocked').map((r) => r.id),
        wallMs,
        finishedAt: new Date().toISOString(),
        judgedRoot: REPO_ROOT,
        utilisation: util ?? null,
        droppedTouched: selection.droppedTouched ?? [],
        droppedVerified: {},
        pushBase: selection.pushBase ?? null,
        slowAdmitted: selection.slowAdmitted ?? [],
        grantedCores: grantsOf(results),
        timeline: timelineOf(results, startedAt),
        advances: [],
      },
      receiptPathFor(opts),
      humanOut
    );
  }
  return exitCode;
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error: unknown) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
