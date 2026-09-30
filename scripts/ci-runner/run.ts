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
 * `--sched cores` (env CI_SCHED) packs gates against a core budget from their measured CPU instead of one slot each; `slots`, the default, is the pool's original rule. See agent/plans/PLAN-ci-quick-cpu-scheduling.md 2.2 and pool.ts admit().
 *
 * See agent/plans/PLAN-npm-ci-parallel-parity.md section 4.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execGate } from './exec';
import { findingsSelftest, receiptFindings } from './findings';
import { GATES, type GateSpec } from './manifest';
import {
  buildGraph,
  type CoreBudget,
  type GateCost,
  type GateResult,
  runPool,
  type Sched,
} from './pool';
import {
  type CpuTick,
  createReporter,
  criticalPath,
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
  /** `--sched` / CI_SCHED; undefined means the default, `slots`. */
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
}

function select(
  specs: readonly GateSpec[],
  opts: Options,
  warn: (text: string) => void
): Selection {
  const notes: string[] = [];
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
    chosen = chosen.filter((spec) => !slow.has(spec.id));
    notes.push(`--quick (${chosen.length} fast gate(s); ${slow.size} deferred)`);
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

  return {
    ids: new Set(chosen.map((spec) => spec.id)),
    description: notes.length > 0 ? notes.join(' ') : undefined,
  };
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
        const { ewma, recent, cpu, rssMb } = v as {
          ewma?: unknown;
          recent?: unknown;
          cpu?: unknown;
          rssMb?: unknown;
        };
        if (typeof ewma !== 'number' || !Number.isFinite(ewma) || ewma <= 0) continue;
        const kept = Array.isArray(recent)
          ? recent.filter((n): n is number => typeof n === 'number' && Number.isFinite(n) && n > 0)
          : [];
        // cpu and rssMb MUST be carried here: saveDurations rebuilds the whole file from this map, so a field this loader drops is erased from every gate on the next run, including gates that run did not touch.
        const rec: DurationRecord = { ewma, recent: kept.length > 0 ? kept : [ewma] };
        const cpuKept = numberList(cpu);
        const rssKept = numberList(rssMb);
        if (cpuKept !== undefined) rec.cpu = cpuKept;
        if (rssKept !== undefined) rec.rssMb = rssKept;
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
 * The cores rule's per-gate costs (PLAN-ci-quick-cpu-scheduling 2.2): the median of the recent cpu samples, the FLOOR of recent wall (the least-contended run, the same rule the tier oracle uses, since load only adds wall and would shrink d), and the largest recent peak RSS. A gate the wrapper never measured has no cpu and is scheduled on its hand-written weight.
 */
function costsFrom(records: ReadonlyMap<string, DurationRecord>): Map<string, GateCost> {
  const costs = new Map<string, GateCost>();
  for (const [id, rec] of records) {
    const cost: GateCost = { wallMs: Math.min(...rec.recent) };
    if (rec.cpu !== undefined && rec.cpu.length > 0) cost.cpuMs = median(rec.cpu);
    if (rec.rssMb !== undefined && rec.rssMb.length > 0) cost.rssMb = Math.max(...rec.rssMb);
    costs.set(id, cost);
  }
  return costs;
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

/** C = availableParallelism() - 1 (or --jobs), epsilon 10%, K = 2C, M = 0.75 x MemAvailable now. */
function coreBudget(jobs: number | undefined): CoreBudget {
  const cores = jobs ?? Math.max(1, os.availableParallelism() - 1);
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
      if (cpu !== undefined) rec.cpu = cpu.slice(-RECENT_KEEP);
      if (rssMb !== undefined) rec.rssMb = rssMb.slice(-RECENT_KEEP);
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
      syntheticSpec('selftest:cpu-busy', 'e=$((SECONDS+2)); while (( SECONDS < e )); do :; done'),
      wrapOpts
    );
    require_(
      (busy.cpuMs ?? 0) > 500,
      `a busy gate must report cpuMs > 500, got ${busy.cpuMs} over ${busy.ms} ms wall`
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

  if (failures.length > 0) {
    process.stderr.write('CONTROL FAILED: ci-runner --selftest did not fire\n');
    for (const f of failures) process.stderr.write(`  - ${f}\n`);
    process.stderr.write('--- selftest transcript ---\n');
    process.stderr.write(text);
    return 1;
  }
  process.stdout.write(
    `ci-runner: selftest ok (${9 + 1 + keyed.assertions + 7 + 3 + 2 + 3 + 4 + 12 + (process.platform !== 'win32' ? 4 : 0) + 6 + sim.assertions + 2} assertions)\n`
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

/** `git rev-parse HEAD^{tree}`, or '' when git cannot answer. */
function headTreeNow(): string {
  try {
    return gitOut(['rev-parse', 'HEAD^{tree}']);
  } catch {
    return '';
  }
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
    return 1;
  }

  const jobs = opts.jobs ?? Math.max(1, os.availableParallelism() - 2);
  const heavyLimit = opts.heavyLimit ?? Math.max(2, Math.floor(jobs / 4));
  // A synthetic manifest must not pollute (or be scheduled by) the real duration cache, so caching is off unless the caller names a path.
  const cachePath =
    process.env.CI_RUNNER_CACHE ?? (opts.manifest === undefined ? DEFAULT_CACHE : undefined);
  const durations = loadDurations(cachePath);
  const sched: Sched = opts.sched ?? 'slots';
  // Under `cores`, --jobs names C, the core budget, rather than a slot count.
  const budget = sched === 'cores' ? coreBudget(opts.jobs) : undefined;

  const reporter = createReporter({
    idWidth: Math.min(46, Math.max(...graph.map((spec) => spec.id.length))),
    out: humanOut,
    jsonOut: opts.json ? (text: string) => process.stdout.write(text) : undefined,
  });

  // BEFORE runPool, not after: manifest.ts:2817 records a gate that writes a temp .ts into packages/cli and breaks check:format, and check-python-lint plants an untracked probe. A digest taken afterwards would record the gates' own leavings and drift from the tree the session actually has.
  const dirtyAtStart = dirtyDigest();
  const headTreeAtStart = headTreeNow();
  const started = Date.now();
  const meta = {
    jobs,
    failFast: opts.failFast,
    selection: selection.description,
    wallMs: 0,
    sched:
      budget === undefined
        ? undefined
        : `sched cores: C ${budget.cores} +${Math.round(budget.epsilon * 100)}%, K ${budget.maxProcs}, M ${(budget.memMb / 1024).toFixed(1)} GB`,
  };
  reporter.header(graph.length, meta);
  const cpuSampler = startCpuSampler();
  const pooled = await runPool(graph, {
    jobs,
    heavyLimit,
    failFast: opts.failFast,
    durations,
    sched,
    budget,
    costs: sched === 'cores' ? costsFrom(loadDurationRecords(cachePath)) : undefined,
    exec: (spec) =>
      execGate(spec, { cwd: REPO_ROOT, mergeOutput: opts.mergeOutput, ...PROFILE_OPTS }),
    onStart: opts.verbose
      ? (spec) => {
          reporter.start(spec.id);
        }
      : undefined,
    onFinish: (result) => {
      reporter.finish(result);
    },
  });
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
  const exitCode = reporter.footer(results, { ...meta, util });

  // THE RECEIPT IS MINTED ONLY BY A RUNNER THAT PROVED IT CAN FAIL.
  //
  // `--quick` runs selftest() first (see the npm key), and selftest() refuses to return 0 unless a planted failing gate produced exit 1, both captured streams, and a skipped dependent. A runner that cannot fail authorising a push would be strictly worse than no lane at all: it would replace "nobody checked" with "something green says it checked".
  //
  // Minted on RED as well as green, carrying the failing ids. The guard decides what a red receipt is worth; the runner's job is to record what happened, not to editorialise. A receipt that appeared only on success would make "gates failed" and "gates never ran" the same observation at the guard -- the exact conflation this repo keeps paying for. SAMPLE THE TREE AGAIN, and
  // compare. dirtyAtStart alone answers "was the tree dirty when we began"; it cannot answer "did it hold still", and those are different questions once anything else is running in this worktree. Two whole-lane runs were spent on 2026-08-27 discovering that four gates failed only in the lane and passed standalone every time, because a peer session was editing files mid-run. The
  // lane read a moving tree and said nothing.
  const dirtyAtEnd = dirtyDigest();
  if (dirtyAtEnd !== dirtyAtStart) {
    humanOut(
      'WARNING: the working tree CHANGED while these gates ran, so they did not all judge\n' +
        '  the same tree and a failure here may belong to the churn rather than to the code.\n' +
        '  Re-run on a still tree before believing a red. This worktree may be shared.'
    );
  }

  if (opts.quick && !opts.manifest) {
    const narrowedBy = narrowingFlags(opts);
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
        wallMs: meta.wallMs,
        finishedAt: new Date().toISOString(),
        judgedRoot: REPO_ROOT,
        utilisation: util ?? null,
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
