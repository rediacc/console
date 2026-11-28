#!/usr/bin/env tsx
/**
 * trace-honest: fail a gate that reads a tracked path its `paths` do not declare (agent/plans/PLAN-ciquick-cpu.md A3).
 *
 * WHY. Carry is sound only while a gate's `paths` name everything it reads. A gate whose glob misses one input keeps a green across a change to that input, and nothing downstream notices: the receipt says carried, the push guard re-hashes the declared inputs and agrees. path-trace.ts writes paths from one trace; this gate keeps them true afterwards, for traced and hand-declared sets alike.
 *
 * TWO INDEPENDENT MODES.
 *   - `trace` re-runs the gate under strace (path-trace.ts `traceCommand`) and fails on any tracked read outside `paths ∪ GLOBAL_INPUTS ∪ leaf closure`, any listed directory (a missed lookup's nearest tracked directory included) that is neither in `lists` nor reached by a declared `paths` or `names` glob, a name-only `git ls-files` scan without the `names` it folds to (`**`, or its pathspec globs), content read through git (a narrowed `ls-files -s`, a `git diff <file>`) outside `paths`, a history read pinned to a ref that `refs` does not declare, a read inside a submodule whose gitlink is undeclared, any other git history or index read (a gate with paths may locate the repository, and read history only at the refs it declares), and any connection to the network. Each finding names the path and the fix.
 *   - `sparse` builds a directory holding ONLY the declared inputs (copied; a `lists` child or a `names` match that is not declared content enters as an EMPTY placeholder, so its name is there and its bytes are not), the dependency trees (hard-link copies, as quick-clone.ts does, so workspace links resolve inside it), the ignored build output (hard-link copies) and the read-only toolchain caches (symlinks), and runs the gate there. A verdict that differs from the same gate's run in the real tree means it needed something undeclared. It shares no code path with the tracer's attribution, so a blind spot in one (a daemon read, io_uring) is not a blind spot in both.
 *
 * WHICH GATES. Every lock entry with `paths`, `lists` or `names` and `gate: true` that is not carry-exempt or ciOnly is a candidate. `--quick` judges the candidates whose lock entry changed, or one of whose leaf-closure files changed, since the last push (quick-select.ts `resolvePushBase`); an unresolvable base is a failure, never an empty pass. `--rotation <i>/<n>` judges bucket i of n, balanced by measured cost; `--rotation auto` takes i from the UTC day of the year over n = 3. Sparse mode takes the `--sparse-top` (default 10) costliest gates of the selection.
 *
 * NEVER GREEN ON NOTHING. Zero candidates in the lock is a failure (the gate is not seeing the estate). A selection of zero is green only in `--quick`, and says how many candidates it saw and against which base. A red gate is a finding: its trace may be partial and its sparse verdict is meaningless.
 *
 * Usage:
 *   tsx scripts/ci-runner/trace-honest.ts [--mode trace|sparse|both] [--quick [--base <ref>]] [--rotation <i>/<n>|auto] [--gate <id> ...] [--origin declared|traced] [--sparse-top N] [--jobs N] [--max-log-mb N] [--list]
 *   tsx scripts/ci-runner/trace-honest.ts --selftest
 */
import { type ChildProcess, spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import { isEntryPoint } from '../lib/entry-point.js';
import { policyPath } from '../lib/policy-paths.js';
import { shared as runRoot } from '../lib/runtmp.js';
import { spawnWatched } from './exec.js';
import { GateCores, gateCoresSelftest } from './gate-cores.js';
import { CARRY_EXEMPT_REL, exemptIdsOf, GLOBAL_INPUTS, matchGlob } from './input-hash.js';
import { openLease, type RunnerLease } from './lease-client.js';
import {
  attribute,
  DEFAULT_MAX_LOG_MB,
  installEntrySignals,
  LOCK_REL,
  type LockEntry,
  liveGroupCount,
  logCapCases,
  needsClosure,
  pidRunning,
  REPO_ROOT,
  type RepoView,
  repoView,
  type TraceRun,
  tempDisposalCases,
  traceCommand,
  traceRefusal,
  trackLiveGroup,
  uncoveredBuildOutput,
  waitPidGone,
  writeStraceStub,
} from './path-trace.js';
import { leafClosure, resolvePushBase } from './quick-select.js';

/** Read-only toolchain caches the sparse directory links rather than copies (quick-clone.ts LINKED_CACHES). */
const LINKED_CACHES = ['.ci/cache/toolchain', '.ci/cache/bin', '.venv'];
const DURATIONS_REL = '.ci/cache/gate-durations.json';
const UNPRICED_MS = 60_000;
/** Code-unit order, spelled out so the sort is not a locale question. */
const byteOrder = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export interface Finding {
  id: string;
  mode: 'trace' | 'sparse';
  what: string;
  fix: string;
}

// ---------------------------------------------------------------------------
// pure judgement
// ---------------------------------------------------------------------------

/** The globs a gate's hash already covers: its paths plus the global inputs. */
export function declaredGlobs(entry: LockEntry): string[] {
  return [...(entry.paths ?? []), ...GLOBAL_INPUTS];
}

/** Whether a tracked path is a declared input: matched by a glob, or a file of the gate's leaf closure. */
export function isDeclared(
  p: string,
  globs: readonly string[],
  leafFiles: ReadonlySet<string>
): boolean {
  return leafFiles.has(p) || globs.some((g) => matchGlob(g, p));
}

/**
 * Whether one declared glob reaches every NEW direct child of `dir` ('' the root) a listing would see: a new file, and a new subdirectory, whose names hash moves only through a file inside it. `D/**` reaches both; `D/*` reaches the file and misses the subdirectory, so it does not declare the listing.
 */
export function listingDeclared(dir: string, globs: readonly string[]): boolean {
  const base = dir === '' ? '' : `${dir}/`;
  const file = `${base}zz-trace-honest-probe`;
  const nested = `${base}zz-trace-honest-probe/zz-trace-honest-probe`;
  return globs.some((g) => matchGlob(g, file) && matchGlob(g, nested));
}

/**
 * Whether a declared glob reaches every path a traced glob `g` reaches: the same glob, `**`, a `D/**` above it, or, for a `g` with no `**`, a declared glob matching `g` read as a literal path (a `*` in `g` stands for any one segment piece, which only a wildcard in the declared glob can match). A `g` holding `**` is never covered by a one-level `*`, which is what the literal reading alone would get wrong.
 */
export function globDeclared(g: string, globs: readonly string[]): boolean {
  return globs.some(
    (d) =>
      d === g ||
      d === '**' ||
      (d.endsWith('/**') && g.startsWith(d.slice(0, -2))) ||
      (!g.includes('**') && matchGlob(d, g))
  );
}

function fixFor(entry: LockEntry): string {
  return entry.pathsOrigin === 'traced'
    ? `re-trace it: npx tsx scripts/ci-runner/path-trace.ts --gate ${entry.id} --write`
    : `widen the declared paths of ${entry.id} in scripts/ci-runner/manifest.ts to cover it (then npm run gen:gates-lock), or replace them with a trace: drop its paths and run npx tsx scripts/ci-runner/path-trace.ts --gate ${entry.id} --write`;
}

/** The honesty findings of one traced run. */
export function traceFindings(
  entry: LockEntry,
  attr: ReturnType<typeof attribute>,
  exit: number,
  leafFiles: ReadonlySet<string>,
  /** Every node the gate reaches through needs (path-trace.ts needsClosure); defaults to its direct needs. */
  closure: ReadonlySet<string> = new Set(entry.needs ?? [])
): Finding[] {
  const out: Finding[] = [];
  const fix = fixFor(entry);
  const add = (what: string, f = fix): void => {
    out.push({ id: entry.id, mode: 'trace', what, fix: f });
  };
  if (exit !== 0) {
    add(
      `exited ${exit} under the trace, so its read set cannot be vouched for`,
      `make it green in this tree first: ${entry.run}`
    );
  }
  // path-trace collects every unpinned history read (F2 B5); the first few name the class, the count says the rest exists.
  const history = attr.gitHistory;
  for (const e of history.slice(0, 5))
    add(
      `reads git history no named ref pins (${e}); a gate whose verdict moves with history cannot declare paths`,
      `drop its paths (it hashes the whole tree then) or add it to ${CARRY_EXEMPT_REL} with the reason`
    );
  if (history.length > 5) add(`and ${history.length - 5} more unpinned history read(s)`);
  // F2 B5: a history read pinned to named refs is honest once `refs` declares each one, since input-hash.ts hashes the sha each resolves to.
  const refs = new Set(entry.refs ?? []);
  for (const r of attr.gitRefs ?? [])
    if (!refs.has(r))
      add(
        `reads git history at ref ${r}, and refs does not declare it, so the ref can move with no input hash moving`,
        `declare refs: [${JSON.stringify(r)}] on ${entry.id} (re-trace it: npx tsx scripts/ci-runner/path-trace.ts --gate ${entry.id} --write)`
      );
  for (const e of attr.gitIndex)
    add(
      `enumerates the tracked file list through the git index (${e}), so a new file anywhere can change its verdict`,
      `drop its paths, so it hashes the whole tree`
    );
  // A name-only ls-files scan is honest once the gate declares the names it folds to: the whole name set, or its pathspec globs (F2 B3). A hand-built attribution with scans and no folded globs reads as the whole set.
  const names = entry.names ?? [];
  const scanned = attr.gitNameGlobs ?? ((attr.gitNames ?? []).length > 0 ? ['**'] : []);
  const missingNames = scanned.filter((g) => !globDeclared(g, names));
  if (missingNames.length > 0)
    for (const e of (attr.gitNames ?? []).length > 0 ? (attr.gitNames ?? []) : ['git ls-files'])
      add(
        `reads the tracked name set through the git index (${e}), and names: [${missingNames.map((g) => `'${g}'`).join(', ')}] is not declared`,
        `declare names: [${missingNames.map((g) => `'${g}'`).join(', ')}] on ${entry.id} (re-trace it: npx tsx scripts/ci-runner/path-trace.ts --gate ${entry.id} --write)`
      );
  // F2 B3/B4: what a narrowed `ls-files -s` or a `git diff <file>` reads through git is content, and the declared paths must reach it.
  for (const g of attr.gitContentGlobs ?? [])
    if (!globDeclared(g, declaredGlobs(entry)))
      add(`reads what ${g} holds through git, outside its paths`);
  for (const peer of attr.network ?? [])
    add(
      `connects to ${peer}, so its verdict can move with nothing in the tree moving`,
      `drop its paths, lists and names, or add it to ${CARRY_EXEMPT_REL} with the reason`
    );
  for (const c of attr.cacheState)
    add(
      `reads untracked cache state (${c}), so its verdict can move with no tracked input moving`,
      `drop its paths, or add it to ${CARRY_EXEMPT_REL} with the reason`
    );
  // Each build-output read needs ITS producer among the gate's needs: an unrelated edge covers nothing.
  for (const b of uncoveredBuildOutput(attr.buildOutput, closure))
    add(
      `reads untracked build output ${b} with no needs edge naming its producer, so no input hash moves when that output does`,
      `add the producer to the needs of ${entry.id} in scripts/ci-runner/manifest.ts`
    );
  const globs = declaredGlobs(entry);
  const reads = [...attr.reads].filter((p) => !isDeclared(p, globs, leafFiles)).sort(byteOrder);
  const shown = reads.slice(0, 20);
  for (const p of shown) add(`reads ${p}, outside its paths`);
  if (reads.length > shown.length)
    add(`and ${reads.length - shown.length} more undeclared read(s)`);
  // A listing is declared by `lists` naming the directory, or by a paths or names glob reaching a new child of it.
  const lists = new Set(entry.lists ?? []);
  for (const d of [...attr.listed].sort(byteOrder)) {
    if (!lists.has(d) && !listingDeclared(d, [...globs, ...names])) {
      const shown = d === '' ? 'the repository root' : `${d}/`;
      add(
        `lists ${shown} (or looks up a name there that does not exist), so a new file there changes what it sees, and neither lists nor a declared glob covers it`,
        `${fixFor(entry)}; or add ${JSON.stringify(d)} to its lists`
      );
    }
  }
  for (const g of [...attr.gitlinkReads].sort(byteOrder)) {
    if (!globs.some((x) => x === g || x === `${g}/**`))
      add(`reads inside submodule ${g}, and neither ${g} nor ${g}/** is declared`);
  }
  return out;
}

/** Bucket `index` (1-based) of `of`: the ids dealt longest first onto the lightest bucket, so every bucket costs about the same. */
export function rotation(
  ids: readonly string[],
  costMs: (id: string) => number,
  index: number,
  of: number
): string[] {
  const buckets = Array.from({ length: of }, () => ({ ms: 0, ids: [] as string[] }));
  const sorted = [...ids].sort((a, b) => costMs(b) - costMs(a) || (a < b ? -1 : a > b ? 1 : 0));
  for (const id of sorted) {
    let best = 0;
    for (let b = 1; b < of; b++) if (buckets[b].ms < buckets[best].ms) best = b;
    buckets[best].ms += costMs(id);
    buckets[best].ids.push(id);
  }
  return buckets[index - 1].ids;
}

/** `auto` is today's bucket: the UTC day of the year modulo `of`, plus one. */
export function rotationIndex(spec: string, now: Date): { index: number; of: number } {
  if (spec === 'auto') {
    const start = Date.UTC(now.getUTCFullYear(), 0, 1);
    const day = Math.floor((now.getTime() - start) / 86_400_000);
    return { index: (day % 3) + 1, of: 3 };
  }
  const m = /^(\d+)\/(\d+)$/.exec(spec);
  if (m === null) throw new Error(`--rotation takes <i>/<n> or auto, got ${spec}`);
  const index = Number(m[1]);
  const of = Number(m[2]);
  if (of < 1 || index < 1 || index > of) throw new Error(`--rotation ${spec}: need 1 <= i <= n`);
  return { index, of };
}

/** Candidates whose lock entry or leaf closure changed between `baseLock` and `lock`, given the changed files. */
export function touchedCandidates(
  candidates: readonly LockEntry[],
  baseLock: ReadonlyMap<string, LockEntry>,
  changed: ReadonlySet<string>,
  leafFilesOf: (e: LockEntry) => ReadonlySet<string>
): Array<{ id: string; why: string }> {
  const out: Array<{ id: string; why: string }> = [];
  for (const e of candidates) {
    const before = baseLock.get(e.id);
    if (before === undefined) {
      out.push({ id: e.id, why: 'new lock entry' });
      continue;
    }
    if (JSON.stringify(before) !== JSON.stringify(e)) {
      out.push({ id: e.id, why: 'lock entry changed' });
      continue;
    }
    const hit = [...leafFilesOf(e)].find((f) => changed.has(f));
    if (hit !== undefined) out.push({ id: e.id, why: `leaf closure file ${hit} changed` });
  }
  return out;
}

// ---------------------------------------------------------------------------
// running
// ---------------------------------------------------------------------------

function git(root: string, args: readonly string[]): string | undefined {
  const r = spawnSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 1 << 28 });
  return r.status === 0 ? r.stdout.trim() : undefined;
}

function runPlain(
  cmd: string,
  cwd: string,
  timeoutS: number,
  env: NodeJS.ProcessEnv = process.env
): Promise<{ exit: number; tail: string }> {
  return new Promise((resolve) => {
    const chunks: string[] = [];
    // Its own group (the timeout and the signal handler kill it whole), with the runner-death watch: a SIGKILLed trace-honest runs no handler, and the gate would otherwise outlive it.
    const child = spawnWatched('bash', ['-c', cmd], {
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    child.stdout?.on('data', (d) => chunks.push(String(d)));
    child.stderr?.on('data', (d) => chunks.push(String(d)));
    const untrack = trackLiveGroup(child.pid);
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      try {
        if (child.pid !== undefined) process.kill(-child.pid, 'SIGKILL');
      } catch {
        // already gone
      }
    }, timeoutS * 1000);
    child.on('exit', (code, signal) => {
      clearTimeout(timer);
      untrack();
      resolve({
        exit: timedOut ? 124 : (code ?? (signal ? 128 : 1)),
        tail: chunks.join('').split('\n').slice(-12).join('\n'),
      });
    });
    child.on('error', () => {
      // A pid assigned before the error must not stay registered: a later signal would kill -pid, a group that may have been reused.
      clearTimeout(timer);
      untrack();
      resolve({ exit: 127, tail: 'spawn failed' });
    });
  });
}

/** Runs a gate under its core grant: the grant's environment (the width every gate is told) is the one the child sees. */
function runGate(
  cmd: string,
  cwd: string,
  timeoutS: number,
  grant: { env: NodeJS.ProcessEnv }
): Promise<{ exit: number; tail: string }> {
  return runPlain(cmd, cwd, timeoutS, grant.env);
}

/** The options one traced gate runs under: the grant's environment, never the launcher's own. */
export function traceOptionsFor(
  id: string,
  args: { timeoutS: number; maxLogMb: number },
  grant: { env: NodeJS.ProcessEnv }
): { timeoutS: number; label: string; env: NodeJS.ProcessEnv; maxLogMb: number } {
  return { timeoutS: args.timeoutS, label: id, env: grant.env, maxLogMb: args.maxLogMb };
}

/** Removes a sparse tree and then hands the grant back: a removal that throws must not keep the tokens held, since the next take would wait on them with no deadline. */
export async function finishSparse(
  dir: string | undefined,
  remove: (dir: string) => void,
  give: () => Promise<void>
): Promise<void> {
  try {
    if (dir !== undefined) remove(dir);
  } finally {
    await give();
  }
}

/** The finding for a trace the log limit killed: its read set is partial, so it is never a pass and says how to proceed. */
export function capFindings(
  id: string,
  run: Pick<TraceRun, 'capped' | 'logBytes'>,
  maxLogMb: number
): Finding[] {
  if (!run.capped) return [];
  return [
    {
      id,
      mode: 'trace',
      what: `trace-log-cap: strace logs passed ${maxLogMb} MB (${Math.round(run.logBytes / 1048576)} MB written) and the trace was killed, so its read set is partial`,
      fix: `split the gate or raise --max-log-mb (now ${maxLogMb})`,
    },
  ];
}

/** Free bytes on the filesystem holding `dir` (fs.statfsSync). */
function freeBytes(dir: string): number {
  const st = fs.statfsSync(dir);
  return Number(st.bavail) * Number(st.bsize);
}

const GIB = 1024 ** 3;

/** What one trace needs free before it starts: its log limit per parallel job, and 20 GiB beside them (D4). */
export function requiredFreeBytes(jobs: number, maxLogMb: number): number {
  return jobs * maxLogMb * 1024 * 1024 + 20 * GIB;
}

/**
 * Waits until `need` bytes are free on the log filesystem, polling, and gives up after `maxWaitMs` (10 minutes). `statfs` and `pollMs` are seams for the selftest.
 */
export async function waitForFreeSpace(
  dir: string,
  need: number,
  opts: { statfs?: (dir: string) => number; pollMs?: number; maxWaitMs?: number } = {}
): Promise<{ ok: boolean; free: number; waitedMs: number }> {
  const statfs = opts.statfs ?? freeBytes;
  const started = Date.now();
  for (;;) {
    const free = statfs(dir);
    const waitedMs = Date.now() - started;
    if (free >= need) return { ok: true, free, waitedMs };
    if (waitedMs >= (opts.maxWaitMs ?? 600_000)) return { ok: false, free, waitedMs };
    await new Promise((r) => setTimeout(r, opts.pollMs ?? 15_000));
  }
}

/** Every `node_modules` directory of the tree, outside other `node_modules`, to depth 4. */
function nodeModulesDirs(root: string): string[] {
  const out: string[] = [];
  const walk = (rel: string, depth: number): void => {
    let ents: fs.Dirent[];
    try {
      ents = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of ents) {
      if (!e.isDirectory() || e.name === '.git') continue;
      const child = rel === '' ? e.name : `${rel}/${e.name}`;
      if (e.name === 'node_modules') out.push(child);
      else if (depth < 4 && !e.name.startsWith('.')) walk(child, depth + 1);
    }
  };
  walk('', 0);
  return out;
}

/** Ignored, untracked entries outside node_modules and the caches: the build output a gate's `needs` produced. */
function ignoredBuildOutput(root: string): string[] {
  const out =
    git(root, ['ls-files', '-z', '--others', '--ignored', '--exclude-standard', '--directory']) ??
    '';
  return out
    .split('\0')
    .map((p) => p.replace(/\/$/, ''))
    .filter(
      (p) =>
        p !== '' &&
        !p.split('/').includes('node_modules') &&
        !p.startsWith('.ci/cache') &&
        !p.startsWith('.venv') &&
        !holdsCheckout(root, p)
    );
}

/** A nested checkout (an ignored directory holding a `.git`, or whose children do) is another tree, never build output. */
function holdsCheckout(root: string, rel: string): boolean {
  const abs = path.join(root, rel);
  if (fs.existsSync(path.join(abs, '.git'))) return true;
  try {
    return fs.readdirSync(abs).some((c) => fs.existsSync(path.join(abs, c, '.git')));
  } catch {
    return false;
  }
}

/** A directory holding only `entry`'s declared inputs, plus dependencies, build output and toolchain. Returns its path. */
export function buildSparse(
  view: RepoView,
  entry: LockEntry,
  leafFiles: ReadonlySet<string>
): string {
  const dir = fs.mkdtempSync(path.join(runRoot('trace-honest-'), 'sparse-'));
  try {
    return fillSparse(dir, view, entry, leafFiles);
  } catch (err) {
    // A build that throws after mkdtemp would otherwise leave the directory and its links behind: the caller never receives the path.
    guards.delete(dir);
    removeSparse(dir);
    throw err;
  }
}

function fillSparse(
  dir: string,
  view: RepoView,
  entry: LockEntry,
  leafFiles: ReadonlySet<string>
): string {
  const globs = declaredGlobs(entry);
  const hardLinked: string[] = [];
  const copyReal = (rel: string): void => {
    const dst = path.join(dir, rel);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    const r = spawnSync('cp', ['-a', '--reflink=auto', path.join(view.root, rel), dst]);
    if (r.status !== 0) throw new Error(`cp ${rel} failed: ${r.stderr}`);
  };
  const linkCopy = (rel: string): void => {
    const dst = path.join(dir, rel);
    if (fs.existsSync(dst)) return;
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    const src = path.join(view.root, rel);
    // A reflink copy is its own inode: a gate rewriting a file in place cannot reach the real one. Tried first, and only where the filesystem has reflinks.
    if (reflinkWorks !== false) {
      const r = spawnSync('cp', ['-a', '--reflink=always', src, dst]);
      if (r.status === 0) {
        reflinkWorks = true;
        return;
      }
      fs.rmSync(dst, { recursive: true, force: true });
      if (reflinkWorks === true) throw new Error(`cp --reflink ${rel} failed: ${r.stderr}`);
      reflinkWorks = false;
      console.error(
        `trace-honest: WARNING reflink copy of ${rel} failed (${String(r.stderr).trim()}); every sparse build in this process falls back to hard links, guarded by verifyLinked`
      );
    }
    // No reflinks (ext4): a hard link keeps the sparse tree fast, but shares the inode, so the run is guarded (see verifyLinked).
    const r = spawnSync('cp', ['-al', src, dst]);
    if (r.status !== 0) throw new Error(`cp -al ${rel} failed: ${r.stderr}`);
    hardLinked.push(rel);
  };
  let copied = 0;
  for (const f of view.files) {
    if (isDeclared(f, globs, leafFiles)) {
      copyReal(f);
      copied++;
    }
  }
  for (const g of view.gitlinks) {
    if (globs.some((x) => x === g || x === `${g}/**`) && fs.existsSync(path.join(view.root, g)))
      copyReal(g);
  }
  copied += placeNames(dir, view, entry, (f) => isDeclared(f, globs, leafFiles));
  for (const nm of nodeModulesDirs(view.root)) linkCopy(nm);
  for (const b of ignoredBuildOutput(view.root))
    if (fs.existsSync(path.join(view.root, b))) linkCopy(b);
  for (const c of LINKED_CACHES) {
    const src = path.join(view.root, c);
    if (!fs.existsSync(src)) continue;
    const dst = path.join(dir, c);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.rmSync(dst, { recursive: true, force: true });
    fs.symlinkSync(fs.realpathSync(src), dst);
  }
  // A repository, so a gate may locate its root; it holds only the declared inputs, so it hides nothing undeclared either.
  const env = {
    ...process.env,
    GIT_AUTHOR_NAME: 'trace-honest',
    GIT_AUTHOR_EMAIL: 'trace-honest@localhost',
    GIT_COMMITTER_NAME: 'trace-honest',
    GIT_COMMITTER_EMAIL: 'trace-honest@localhost',
  };
  for (const args of [
    ['init', '-q'],
    ['add', '-A', '--', '.'],
    ['commit', '-q', '--no-verify', '-m', 'sparse inputs'],
  ]) {
    // No background gc or maintenance: git may detach one after a commit, and it would still be writing here when the directory is removed.
    const r = spawnSync('git', ['-c', 'gc.auto=0', '-c', 'maintenance.auto=false', ...args], {
      cwd: dir,
      env,
      encoding: 'utf8',
    });
    if (r.status !== 0)
      throw new Error(`git ${args[0]} in the sparse directory failed: ${r.stderr}`);
  }
  if (copied === 0)
    throw new Error(
      `${entry.id}: the sparse directory holds ZERO declared files; its paths match nothing tracked`
    );
  const bounded = new Set<string>();
  guards.set(dir, {
    root: view.root,
    rels: hardLinked,
    before: statLinked(view.root, hardLinked, bounded),
    bounded,
  });
  return dir;
}

/**
 * The names a gate declares without their content: each tracked child of a `lists` directory and each tracked file a `names` glob matches, when not already copied as content, enters the sparse directory EMPTY (a subdirectory child as an empty directory). The gate sees every name it declared and none of the bytes it did not, so a verdict that needed those bytes differs. Returns the count placed.
 */
export function placeNames(
  dir: string,
  view: RepoView,
  entry: LockEntry,
  isContent: (f: string) => boolean
): number {
  const lists = entry.lists ?? [];
  const names = entry.names ?? [];
  if (lists.length === 0 && names.length === 0) return 0;
  let n = 0;
  const place = (rel: string, asDir: boolean): void => {
    const dst = path.join(dir, rel);
    if (fs.existsSync(dst)) return;
    if (asDir) fs.mkdirSync(dst, { recursive: true });
    else {
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.writeFileSync(dst, '');
    }
    n++;
  };
  for (const f of view.files) {
    if (isContent(f)) continue;
    if (names.some((g) => matchGlob(g, f))) place(f, false);
  }
  for (const d of lists) {
    const prefix = d === '' ? '' : `${d}/`;
    const seen = new Set<string>();
    for (const f of [...view.files, ...view.gitlinks]) {
      if (!f.startsWith(prefix)) continue;
      const rest = f.slice(prefix.length);
      const child = rest.split('/')[0];
      if (seen.has(child)) continue;
      seen.add(child);
      const rel = `${prefix}${child}`;
      const isDir = rest.includes('/') || view.gitlinks.includes(f);
      if (!isDir && isContent(rel)) continue;
      place(rel, isDir);
    }
  }
  return n;
}

/** Whether `cp --reflink=always` has worked on this filesystem: unknown until the first link, then settled for the process. */
let reflinkWorks: boolean | undefined;

/** The real files a sparse directory shares by hard link, as they stood when it was built. */
const guards = new Map<
  string,
  { root: string; rels: string[]; before: Map<string, string>; bounded: Set<string> }
>();

/** The most entries one `snapshotTree` call records and the deepest directory it descends: a symlink in the sparse tree pointing at a cache, a home directory or `/` must cost a bounded walk, twice per guarded run. */
export const SNAPSHOT_MAX_ENTRIES = 100_000;
export const SNAPSHOT_MAX_DEPTH = 32;

/** `inode:size:mtime:mode` of every regular file under an absolute directory, keyed by its path below it. A symlink inside is followed once per real directory (a visited set of real paths, so a cycle cannot loop and a write through a nested link still moves the snapshot); the walk stops at `SNAPSHOT_MAX_ENTRIES` entries or `SNAPSHOT_MAX_DEPTH` levels, says so on stderr and names the directory to `onBound`, which is how a guarded run reports that part of its tree went unwatched. */
export function snapshotTree(
  absDir: string,
  maxEntries: number = SNAPSHOT_MAX_ENTRIES,
  maxDepth: number = SNAPSHOT_MAX_DEPTH,
  onBound?: (dir: string) => void
): Map<string, string> {
  const out = new Map<string, string>();
  const seen = new Set<string>();
  let bounded = false;
  const walk = (dir: string, rel: string, depth: number): void => {
    if (out.size >= maxEntries || depth > maxDepth) {
      // Only a directory that holds something skips an entry: an empty one at the bound is not a gap.
      try {
        if (fs.readdirSync(dir).length > 0) bounded = true;
      } catch {
        // an unreadable directory records nothing either way
      }
      return;
    }
    let real: string;
    try {
      real = fs.realpathSync(dir);
    } catch {
      return;
    }
    if (seen.has(real)) return;
    seen.add(real);
    let ents: fs.Dirent[];
    try {
      ents = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of ents) {
      const abs = path.join(dir, e.name);
      const childRel = rel === '' ? e.name : `${rel}/${e.name}`;
      let isDir = e.isDirectory();
      let isFile = e.isFile();
      if (e.isSymbolicLink()) {
        try {
          const t = fs.statSync(abs);
          isDir = t.isDirectory();
          isFile = t.isFile();
        } catch {
          continue;
        }
      }
      if (isDir) walk(abs, childRel, depth + 1);
      else if (isFile) {
        if (out.size >= maxEntries) {
          bounded = true;
          break;
        }
        const st = fs.statSync(abs, { bigint: true });
        out.set(childRel, `${st.ino}:${st.size}:${st.mtimeNs}:${st.mode}`);
      }
    }
  };
  walk(absDir, '', 0);
  if (bounded) {
    onBound?.(absDir);
    console.error(
      `trace-honest: WARNING snapshot of ${absDir} stopped at ${maxEntries} entries or depth ${maxDepth}; a write beyond the bound is not guarded`
    );
  }
  return out;
}

/** `inode:size:mtime:mode` of every file under the given real directories. A rewrite in place keeps the inode but moves size or mtime; an unlink-and-recreate in the sparse tree leaves the real file untouched. */
function statLinked(
  root: string,
  rels: readonly string[],
  bounded?: Set<string>
): Map<string, string> {
  const out = new Map<string, string>();
  const walk = (rel: string): void => {
    let ents: fs.Dirent[];
    try {
      ents = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of ents) {
      const child = `${rel}/${e.name}`;
      if (e.isDirectory()) walk(child);
      else if (e.isFile()) {
        const st = fs.lstatSync(path.join(root, child), { bigint: true });
        out.set(child, `${st.ino}:${st.size}:${st.mtimeNs}:${st.mode}`);
      } else if (e.isSymbolicLink()) {
        // `cp -a` copies a symlink as a symlink, so a gate writing through an absolute one reaches the real target: snapshot the target too.
        const abs = path.join(root, child);
        const target = fs.readlinkSync(abs);
        let tgt = 'dangling';
        try {
          const t = fs.statSync(abs, { bigint: true });
          // A directory's own ino/size/mtime does not move when a file inside it is written, so a link to a directory snapshots every file under the target instead.
          tgt = t.isDirectory()
            ? `dir:${[...snapshotTree(fs.realpathSync(abs), SNAPSHOT_MAX_ENTRIES, SNAPSHOT_MAX_DEPTH, (d) => bounded?.add(d)).entries()].join(',')}`
            : `${t.ino}:${t.size}:${t.mtimeNs}:${t.mode}`;
        } catch {
          // a dangling link has no target to guard
        }
        out.set(child, `link:${target}:${tgt}`);
      }
    }
  };
  for (const rel of rels) {
    const st = fs.lstatSync(path.join(root, rel));
    if (st.isDirectory()) walk(rel);
    else if (st.isFile()) {
      const b = fs.lstatSync(path.join(root, rel), { bigint: true });
      out.set(rel, `${b.ino}:${b.size}:${b.mtimeNs}:${b.mode}`);
    }
  }
  return out;
}

/** The directories under a sparse tree's links whose snapshot hit a bound, so a write beyond it went unwatched; empty when the guard saw every file. Read after `verifyLinked`. */
export function unguardedLinked(dir: string): string[] {
  return [...(guards.get(dir)?.bounded ?? [])];
}

/** The real files a gate changed through the hard links of its sparse directory; empty when none did (or none were linked). The tree cannot be restored, so a hit fails the trace loudly with the file named. */
export function verifyLinked(dir: string): string[] {
  const g = guards.get(dir);
  if (g === undefined) return [];
  const now = statLinked(g.root, g.rels, g.bounded);
  const changed: string[] = [];
  for (const [rel, was] of g.before) if (now.get(rel) !== was) changed.push(rel);
  return changed;
}

/** Removes a sparse directory, retrying while a straggling child of the gate finishes writing; a directory that survives is named, never leaked silently. */
function removeSparse(dir: string): void {
  guards.delete(dir);
  try {
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  } catch (err) {
    console.error(`trace-honest: WARNING could not remove ${dir}: ${(err as Error).message}`);
  }
  if (fs.existsSync(dir))
    console.error(
      `trace-honest: WARNING ${dir} survived its removal (a process of the gate still writing there?); remove it by hand`
    );
}

interface Args {
  mode: 'trace' | 'sparse' | 'both';
  quick: boolean;
  base?: string;
  rotation?: string;
  gates: string[];
  sparseTop: number;
  jobs: number;
  root: string;
  timeoutS: number;
  /** `--max-log-mb`: the size limit on one trace's strace logs, MB (D4). */
  maxLogMb: number;
  selftest: boolean;
  /** Print the selection, one `<id>\t<why>` per line, and exit without running anything. */
  list: boolean;
  /** Judge only candidates whose pathsOrigin is this (`declared` or `traced`). */
  origin?: string;
}

/** A whole number of at least `min`: a NaN would make slice or the worker pool run nothing and print OK on nothing. */
function count(flag: string, text: string, min: number): number {
  const n = Number(text);
  if (!Number.isInteger(n) || n < min)
    throw new Error(`${flag} takes a whole number >= ${min}, got ${text}`);
  return n;
}

/** A finite number of at least `min`, fractions allowed: a NaN or an infinity would arm no timer or one that never fires. */
function seconds(flag: string, text: string, min: number, unit = 'seconds'): number {
  const n = Number(text);
  if (text.trim() === '' || !Number.isFinite(n) || n < min)
    throw new Error(`${flag} takes a number of ${unit} >= ${min}, got ${text}`);
  return n;
}

function parseArgs(argv: string[]): Args {
  const a: Args = {
    mode: 'trace',
    quick: false,
    gates: [],
    sparseTop: 10,
    jobs: Math.max(1, Math.floor(os.cpus().length / 4)),
    root: REPO_ROOT,
    timeoutS: 1800,
    maxLogMb: DEFAULT_MAX_LOG_MB,
    selftest: false,
    list: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    const val = (): string => {
      const v = argv[++i];
      if (v === undefined) throw new Error(`${t} needs a value`);
      return v;
    };
    if (t === '--mode') {
      const m = val();
      if (m !== 'trace' && m !== 'sparse' && m !== 'both')
        throw new Error(`--mode takes trace, sparse or both, got ${m}`);
      a.mode = m;
    } else if (t === '--quick') a.quick = true;
    else if (t === '--base') a.base = val();
    else if (t === '--rotation') a.rotation = val();
    else if (t === '--gate') a.gates.push(val());
    else if (t === '--sparse-top') a.sparseTop = count(t, val(), 0);
    else if (t === '--jobs') a.jobs = count(t, val(), 1);
    else if (t === '--root') a.root = path.resolve(val());
    else if (t === '--timeout-s') a.timeoutS = seconds(t, val(), 1);
    else if (t === '--max-log-mb') a.maxLogMb = seconds(t, val(), 1, 'MB');
    else if (t === '--selftest') a.selftest = true;
    else if (t === '--list') a.list = true;
    else if (t === '--origin') a.origin = val();
    else throw new Error(`unknown argument ${t}`);
  }
  return a;
}

function costOf(root: string): (id: string) => number {
  let d: Record<string, { ewma?: number }> = {};
  try {
    d = JSON.parse(fs.readFileSync(path.join(root, DURATIONS_REL), 'utf8')) as typeof d;
  } catch {
    d = {};
  }
  return (id) => d[id]?.ewma ?? UNPRICED_MS;
}

async function pool<T>(
  items: readonly T[],
  jobs: number,
  fn: (t: T) => Promise<void>
): Promise<void> {
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.max(1, jobs) }, async () => {
      while (next < items.length) await fn(items[next++]);
    })
  );
}

/** The broker main opened, closed by the entry point so a live broker never holds the event loop (or its tokens) past the run. */
let openedLease: RunnerLease | undefined;

async function main(argv: string[]): Promise<number> {
  const args = parseArgs(argv);
  if (args.selftest) return selftest();
  const refusal = traceRefusal();
  if (refusal !== undefined && args.mode !== 'sparse') {
    console.error(`trace-honest: REFUSED. ${refusal}`);
    return 1;
  }
  const lock = JSON.parse(fs.readFileSync(path.join(args.root, LOCK_REL), 'utf8')) as LockEntry[];
  const exemptPath = path.join(args.root, CARRY_EXEMPT_REL);
  const exempt = exemptIdsOf(
    fs.existsSync(exemptPath) ? fs.readFileSync(exemptPath, 'utf8') : null
  );
  const candidates = lock.filter(
    (e) =>
      e.gate &&
      ((e.paths ?? []).length > 0 || (e.lists ?? []).length > 0 || (e.names ?? []).length > 0) &&
      !exempt.has(e.id) &&
      e.ciOnly === undefined &&
      (args.origin === undefined || e.pathsOrigin === args.origin)
  );
  if (candidates.length === 0) {
    console.error(
      `trace-honest: ${LOCK_REL} holds ZERO paths-bearing gates; this gate is not seeing the estate, and its green would mean nothing.`
    );
    return 1;
  }
  const byId = new Map(candidates.map((e) => [e.id, e]));
  const lockById = new Map(lock.map((e) => [e.id, e]));
  const leafCache = new Map<string, Set<string>>();
  const leafFilesOf = (e: LockEntry): Set<string> => {
    let s = leafCache.get(e.id);
    if (s === undefined) {
      s = leafClosure(args.root, e.leaves ?? []).files;
      leafCache.set(e.id, s);
    }
    return s;
  };
  let selected: Array<{ id: string; why: string }> = [];
  let scope = '';
  if (args.gates.length > 0) {
    for (const id of args.gates) {
      if (!byId.has(id)) {
        console.error(`trace-honest: ${id} is not a paths-bearing, carryable gate in ${LOCK_REL}`);
        return 2;
      }
      selected.push({ id, why: 'named by --gate' });
    }
    scope = `${selected.length} named`;
  } else if (args.quick) {
    let mergeBase =
      args.base === undefined ? undefined : git(args.root, ['merge-base', 'HEAD', args.base]);
    let via = args.base ?? '';
    if (args.base === undefined) {
      const branch = git(args.root, ['symbolic-ref', '--short', '-q', 'HEAD']);
      const res = resolvePushBase((a) => git(args.root, a), branch);
      for (const w of res.warnings) console.error(`trace-honest: WARNING ${w}`);
      mergeBase = res.mergeBase;
      via = res.ref ?? '';
      if (mergeBase === undefined) {
        console.error(
          `trace-honest: no push base resolves (tried ${res.tried.join(', ')}), so the change set is UNKNOWN; refusing rather than judging nothing. Name one with --base <ref>.`
        );
        return 1;
      }
    }
    if (mergeBase === undefined) {
      console.error(`trace-honest: --base ${args.base} has no merge-base with HEAD`);
      return 1;
    }
    const changed = new Set(
      (git(args.root, ['diff', '--name-only', mergeBase]) ?? '').split('\n').filter(Boolean)
    );
    const baseLockText = git(args.root, ['show', `${mergeBase}:${LOCK_REL}`]);
    const baseLock = new Map<string, LockEntry>(
      (baseLockText === undefined ? [] : (JSON.parse(baseLockText) as LockEntry[])).map((e) => [
        e.id,
        e,
      ])
    );
    selected = touchedCandidates(candidates, baseLock, changed, leafFilesOf);
    scope = `quick: ${changed.size} changed file(s) since ${via} (${mergeBase.slice(0, 10)})`;
  } else if (args.rotation !== undefined) {
    const { index, of } = rotationIndex(args.rotation, new Date());
    selected = rotation([...byId.keys()], costOf(args.root), index, of).map((id) => ({
      id,
      why: `rotation ${index}/${of}`,
    }));
    scope = `rotation ${index}/${of}`;
  } else {
    selected = [...byId.keys()].map((id) => ({ id, why: 'every candidate' }));
    scope = 'every candidate';
  }
  console.error(
    `trace-honest: ${candidates.length} paths-bearing gate(s) in the lock; ${selected.length} selected (${scope}); mode ${args.mode}`
  );
  if (args.list) {
    for (const { id, why } of selected) console.log(`${id}\t${why}`);
    return 0;
  }
  if (selected.length === 0 && !args.quick) {
    console.error(
      `trace-honest: FAIL, 0 of ${candidates.length} candidates selected (${scope}); a zero selection is green only in --quick (a rotation bucket larger than the candidate count, or a filter that matches nothing, judged nothing)`
    );
    return 1;
  }
  if (selected.length === 0) {
    console.log(
      `trace-honest: OK, 0 of ${candidates.length} candidates touched (${scope}); nothing to re-trace`
    );
    return 0;
  }
  const view = repoView(args.root);
  const findings: Finding[] = [];
  let traced = 0;
  let sparsed = 0;
  // Every gate draws its width from the machine-wide core lease (gate-cores.ts): without it six traced vitest gates each took all 24 cores at load 134 (PR-TASK 79b7e92e).
  const warn = (text: string): void => {
    process.stderr.write(text);
  };
  openedLease = await openLease({ root: REPO_ROOT, warn });
  console.error(`trace-honest: ${openedLease.note}`);
  const cores = new GateCores(openedLease, args.jobs, { warn });
  if (args.mode !== 'sparse') {
    await pool(selected, args.jobs, async ({ id, why }) => {
      const e = byId.get(id) as LockEntry;
      // Wait for room for every parallel trace's logs before each one starts; refuse rather than fill the disk.
      const space = await waitForFreeSpace(
        runRoot('path-trace-'),
        requiredFreeBytes(args.jobs, args.maxLogMb)
      );
      if (!space.ok) {
        traced++;
        findings.push({
          id,
          mode: 'trace',
          what: `not traced: free space on the log filesystem stayed at ${Math.round(space.free / GIB)} GiB for ${Math.round(space.waitedMs / 60_000)} min, below the ${Math.round(requiredFreeBytes(args.jobs, args.maxLogMb) / GIB)} GiB (jobs x --max-log-mb + 20 GiB) a trace needs`,
          fix: 'free disk space (the host-temp sweep, or remove old path-trace-* run dirs) or lower --jobs or --max-log-mb, then re-run',
        });
        console.error(`  trace  FAIL  ${id} (refused: free space)`);
        return;
      }
      const grant = await cores.take(id);
      const run = await traceCommand(e.run, view.root, traceOptionsFor(id, args, grant)).finally(
        () => cores.give(grant)
      );
      const f = run.capped
        ? capFindings(id, run, args.maxLogMb)
        : traceFindings(
            e,
            attribute(run.access, view),
            run.exit,
            leafFilesOf(e),
            needsClosure(e.id, lockById)
          );
      traced++;
      findings.push(...f);
      console.error(
        `  trace  ${f.length === 0 ? 'PASS' : 'FAIL'}  ${id} (${why}; ${run.seconds}s, ${e.paths?.length ?? 0} glob(s), ${e.lists?.length ?? 0} list(s), ${e.names?.length ?? 0} names glob(s))`
      );
      if (run.exit !== 0) console.error(run.outputTail.replace(/^/gm, '      | '));
    });
  }
  if (args.mode !== 'trace') {
    const cost = costOf(args.root);
    const top = [...selected].sort((a, b) => cost(b.id) - cost(a.id)).slice(0, args.sparseTop);
    const serialCores = new GateCores(openedLease, 1, { warn });
    for (const { id } of top) {
      const e = byId.get(id) as LockEntry;
      const grant = await serialCores.take(id);
      const real = await runGate(e.run, view.root, args.timeoutS, grant);
      let dir: string | undefined;
      try {
        dir = buildSparse(view, e, leafFilesOf(e));
        const sparse = await runGate(e.run, dir, args.timeoutS, grant);
        sparsed++;
        const mutated = verifyLinked(dir);
        if (mutated.length > 0) {
          findings.push({
            id,
            mode: 'sparse',
            what: `rewrote ${mutated.length} REAL file(s) in place through its hard-linked sparse tree (first: ${mutated.slice(0, 5).join(', ')}); the real checkout is now changed`,
            fix: 'make the gate write build output to a fresh file (write then rename), not over an installed or built one; restore the named files (npm ci, or rebuild)',
          });
        }
        const unguarded = unguardedLinked(dir);
        if (unguarded.length > 0) {
          findings.push({
            id,
            mode: 'sparse',
            what: `links to ${unguarded.length} tree(s) too large for the write guard (first: ${unguarded.slice(0, 3).join(', ')}); a write beyond the bound would pass unseen`,
            fix: 'declare fewer inputs for the gate, or stop linking the large tree into its sparse directory',
          });
        }
        const same = (real.exit === 0) === (sparse.exit === 0);
        if (real.exit !== 0) {
          findings.push({
            id,
            mode: 'sparse',
            what: `is red in the real tree (exit ${real.exit}), so the sparse comparison means nothing`,
            fix: `make it green first: ${e.run}`,
          });
        } else if (!same) {
          findings.push({
            id,
            mode: 'sparse',
            what: `passes in the tree but exits ${sparse.exit} holding only its declared inputs; it needs something undeclared. Its sparse output:\n${sparse.tail.replace(/^/gm, '        | ')}`,
            fix: fixFor(e),
          });
        }
        console.error(
          `  sparse ${real.exit === 0 && same ? 'PASS' : 'FAIL'}  ${id} (tree exit ${real.exit}, sparse exit ${sparse.exit})`
        );
      } catch (err) {
        findings.push({
          id,
          mode: 'sparse',
          what: `the sparse directory could not be built: ${(err as Error).message}`,
          fix: 'fix the declared paths or the build output the gate needs',
        });
      } finally {
        await finishSparse(dir, removeSparse, () => serialCores.give(grant));
      }
    }
  }
  if (findings.length > 0) {
    console.error(
      `trace-honest: ${findings.length} finding(s) across ${new Set(findings.map((f) => f.id)).size} gate(s):`
    );
    for (const f of findings) console.error(`  ${f.id} [${f.mode}] ${f.what}\n      fix: ${f.fix}`);
    return 1;
  }
  console.log(
    `trace-honest: OK, ${traced} traced and ${sparsed} sparse-run of ${selected.length} selected (${candidates.length} candidates, ${scope}); ${args.mode === 'sparse' ? 'sparse runs agreed with the tree (reads not traced in this mode)' : 'every read is declared'}`
  );
  return 0;
}

// ---------------------------------------------------------------------------
// selftest: the pure helpers in both directions, then both modes against a fixture repository
// ---------------------------------------------------------------------------

async function selftest(): Promise<number> {
  let bad = 0;
  let n = 0;
  const check = (ok: boolean, label: string): void => {
    n++;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
    if (!ok) bad++;
  };
  const entry: LockEntry = {
    id: 'g',
    run: 'x',
    gate: true,
    paths: ['a/**', 'b.txt'],
    pathsOrigin: 'traced',
    leaves: [],
  };
  const attr = (
    reads: string[],
    listed: string[] = [],
    extra: Partial<ReturnType<typeof attribute>> = {}
  ): ReturnType<typeof attribute> => ({
    reads: new Set(reads),
    gitlinkReads: new Set(),
    listed: new Set(listed),
    gitHistory: [],
    gitIndex: [],
    ignored: new Map(),
    buildOutput: [],
    cacheState: [],
    ...extra,
  });
  check(
    traceFindings(entry, attr(['a/x.ts', 'b.txt', 'a/p/package-lock.json']), 0, new Set())
      .length === 0,
    'CONTROL: declared reads, a global input and nothing else pass'
  );
  // input-hash.ts lists the root `package-lock.json` beside `**/package-lock.json`, so the root lockfile is a global input too.
  check(
    traceFindings(entry, attr(['package-lock.json']), 0, new Set()).length === 0,
    'the root lockfile is a global input, so reading it needs no declaration'
  );
  const f1 = traceFindings(entry, attr(['a/x.ts', 'c.txt']), 0, new Set());
  check(
    f1.length === 1 &&
      f1[0].what.includes('c.txt') &&
      f1[0].fix.includes('path-trace.ts --gate g --write'),
    'an undeclared read fails, naming the path and the re-trace'
  );
  check(
    traceFindings(entry, attr(['tool.ts']), 0, new Set(['tool.ts'])).length === 0,
    'CONTROL: a leaf-closure file is declared by construction'
  );
  check(
    traceFindings(entry, attr([], ['a/sub']), 0, new Set()).length === 0,
    'CONTROL: a listing under a declared dir/** passes'
  );
  check(
    traceFindings(entry, attr([], ['c']), 0, new Set()).length === 1,
    'a listing no glob reaches fails'
  );
  check(
    traceFindings(entry, attr([], ['']), 0, new Set()).some((f) => f.what.includes('root')),
    'a root listing fails'
  );
  check(
    traceFindings(entry, attr([], [], { gitHistory: ['git log'] }), 0, new Set()).some((f) =>
      f.what.includes('history')
    ),
    'a git history read fails'
  );
  check(
    traceFindings(entry, attr([], [], { gitIndex: ['git ls-files'] }), 0, new Set()).some((f) =>
      f.what.includes('index')
    ),
    'a git index read fails'
  );
  check(
    traceFindings(entry, attr([], [], { buildOutput: ['packages/www/dist/x.html'] }), 0, new Set())
      .length === 1,
    'build output read with no needs edge fails'
  );
  check(
    traceFindings(
      { ...entry, needs: ['build:www'] },
      attr([], [], { buildOutput: ['packages/www/dist/x.html'] }),
      0,
      new Set()
    ).length === 0,
    'CONTROL: the same read with its producer among the needs passes'
  );
  check(
    traceFindings(
      { ...entry, needs: ['build:other'] },
      attr([], [], { buildOutput: ['packages/www/dist/x.html'] }),
      0,
      new Set()
    ).length === 1,
    'an unrelated needs entry does not cover build output another node produces'
  );
  check(
    traceFindings(entry, attr([], [], { cacheState: ['.ci/cache/x.json'] }), 0, new Set())
      .length === 1,
    'cache state read fails'
  );
  check(
    traceFindings(entry, attr(['a/x.ts']), 3, new Set()).some((f) => f.what.includes('exited 3')),
    'a red run is a finding, not a pass'
  );
  check(
    traceFindings(
      { ...entry, pathsOrigin: 'declared' },
      attr(['c.txt']),
      0,
      new Set()
    )[0]?.fix.includes('widen the declared paths') === true,
    'a declared set gets the widen fix, not a re-trace'
  );
  check(
    traceFindings(entry, attr([], [], { gitlinkReads: new Set(['private/x']) }), 0, new Set())
      .length === 1,
    'a read inside an undeclared submodule fails'
  );
  // W2.5: lists and names declare listings and name scans; an undeclared one, and the network, fail.
  check(
    traceFindings({ ...entry, lists: [''] }, attr([], ['']), 0, new Set()).length === 0,
    "CONTROL: a root listing passes once lists declares ''"
  );
  check(
    traceFindings({ ...entry, lists: ['c'] }, attr([], ['c']), 0, new Set()).length === 0 &&
      traceFindings({ ...entry, names: ['c/**'] }, attr([], ['c']), 0, new Set()).length === 0 &&
      traceFindings({ ...entry, names: ['**'] }, attr([], ['']), 0, new Set()).length === 0,
    'CONTROL: a listing passes when lists names it, or when a names glob reaches a new child (the root included)'
  );
  check(
    traceFindings({ ...entry, names: ['c/*'] }, attr([], ['c']), 0, new Set()).length === 1 &&
      traceFindings({ ...entry, names: ['*'] }, attr([], ['']), 0, new Set()).length === 1,
    'a one-level glob (c/*, or * at the root) misses a new subdirectory, so it does not declare the listing'
  );
  check(
    traceFindings({ ...entry, lists: ['c'] }, attr([], ['c/sub']), 0, new Set()).length === 1,
    'lists covers the directory it names, not one beneath it'
  );
  check(
    traceFindings(entry, attr([], [], { gitNames: ['git ls-files -z'] }), 0, new Set()).some((f) =>
      f.what.includes("names: ['**'] is not declared")
    ),
    "a name-only ls-files scan without names: ['**'] fails"
  );
  check(
    traceFindings(
      { ...entry, names: ['**'] },
      attr([], [], { gitNames: ['git ls-files -z'] }),
      0,
      new Set()
    ).length === 0,
    "CONTROL: the same scan with names: ['**'] passes"
  );
  // F2 (PLAN-push-decoupling): refs, pathspec-folded names and content read through git are accepted when declared, and fail when not.
  const pinned = attr(['a/x.ts'], [], { gitRefs: ['HEAD', 'origin/main'] });
  check(
    traceFindings({ ...entry, refs: ['HEAD', 'origin/main'] }, pinned, 0, new Set()).length === 0,
    'F2 B5: a history read pinned to HEAD and origin/main passes once refs declares both'
  );
  const missingRef = traceFindings({ ...entry, refs: ['HEAD'] }, pinned, 0, new Set());
  check(
    missingRef.length === 1 && missingRef[0].what.includes('ref origin/main'),
    'F2 B5 CONTROL: the same read with origin/main undeclared fails, naming the ref'
  );
  const many = attr([], [], {
    gitHistory: Array.from({ length: 8 }, (_, i) => `git describe ${i}`),
  });
  const manyF = traceFindings(entry, many, 0, new Set());
  check(
    manyF.length === 6 && manyF[5].what.includes('and 3 more'),
    `F2 B5: eight unpinned history reads print five and count the rest (got ${manyF.length})`
  );
  const tsNames = attr([], [''], { gitNames: ['git ls-files -- *.ts'], gitNameGlobs: ['**/*.ts'] });
  check(
    traceFindings({ ...entry, names: ['**/*.ts'], lists: [''] }, tsNames, 0, new Set()).length ===
      0 &&
      traceFindings({ ...entry, names: ['**'], lists: [''] }, tsNames, 0, new Set()).length === 0,
    "F2 B3: a pathspec scan folded to names ['**/*.ts'] passes when names declares it or the whole set"
  );
  check(
    traceFindings({ ...entry, names: ['src/**'], lists: [''] }, tsNames, 0, new Set()).some((f) =>
      f.what.includes("names: ['**/*.ts'] is not declared")
    ),
    "F2 B3 CONTROL: names ['src/**'] does not declare a scan of **/*.ts"
  );
  const gitContent = attr([], [], { gitContentGlobs: ['a/y.ts', 'c/*.sh'] });
  check(
    traceFindings({ ...entry, paths: ['a/**', 'c/*.sh'] }, gitContent, 0, new Set()).length === 0,
    'F2 B3/B4: content read through git (a/y.ts, c/*.sh) passes when paths reach it'
  );
  const contentMiss = traceFindings(entry, gitContent, 0, new Set());
  check(
    contentMiss.length === 1 && contentMiss[0].what.includes('c/*.sh'),
    'F2 B3/B4 CONTROL: c/*.sh read through git and outside paths fails'
  );
  check(
    globDeclared('a/**/*.ts', ['a/**']) &&
      globDeclared('a/x*.ts', ['a/*.ts']) &&
      !globDeclared('a/**', ['a/*']) &&
      !globDeclared('**/*.ts', ['*.ts']),
    'globDeclared: D/** covers anything under D and a wider one-level glob covers a narrower one; CONTROL: a one-level * never covers a ** glob'
  );
  check(
    traceFindings(entry, attr([], [], { network: ['1.1.1.1:443'] }), 0, new Set()).some((f) =>
      f.what.includes('connects to 1.1.1.1:443')
    ),
    'a network connection is a finding'
  );
  {
    const pdir = fs.mkdtempSync(path.join(runRoot('trace-honest-'), 'place-'));
    try {
      const pview: RepoView = {
        root: '/nowhere',
        files: ['src/a.ts', 'src/deep/b.ts', 'src/real.ts', 'n/x.md', 'other.txt'],
        gitlinks: ['src/mod'],
        gitDirs: [],
      };
      fs.mkdirSync(path.join(pdir, 'src'), { recursive: true });
      fs.writeFileSync(path.join(pdir, 'src/real.ts'), 'REAL');
      const placed = placeNames(
        pdir,
        pview,
        { ...entry, lists: ['src'], names: ['n/**'] },
        (f) => f === 'src/real.ts'
      );
      const size = (rel: string): number => fs.statSync(path.join(pdir, rel)).size;
      check(
        placed === 4 &&
          size('src/a.ts') === 0 &&
          size('n/x.md') === 0 &&
          fs.statSync(path.join(pdir, 'src/deep')).isDirectory() &&
          fs.statSync(path.join(pdir, 'src/mod')).isDirectory() &&
          fs.readFileSync(path.join(pdir, 'src/real.ts'), 'utf8') === 'REAL' &&
          !fs.existsSync(path.join(pdir, 'src/deep/b.ts')) &&
          !fs.existsSync(path.join(pdir, 'other.txt')),
        `sparse placeholders: a listed child or names match enters empty, a subdirectory or gitlink as an empty dir, declared content stays real (placed ${placed})`
      );
    } finally {
      fs.rmSync(pdir, { recursive: true, force: true });
    }
  }
  const cost = (id: string): number => ({ a: 10, b: 9, c: 2, d: 1 })[id] ?? 0;
  const r1 = rotation(['a', 'b', 'c', 'd'], cost, 1, 2);
  const r2 = rotation(['a', 'b', 'c', 'd'], cost, 2, 2);
  check(
    r1.join() === 'a,d' && r2.join() === 'b,c',
    'rotation deals longest first onto the lightest bucket, and the buckets partition the set'
  );
  check(
    rotationIndex('auto', new Date(Date.UTC(2026, 0, 1))).index === 1 &&
      rotationIndex('auto', new Date(Date.UTC(2026, 0, 2))).index === 2,
    'auto rotation advances one bucket per UTC day'
  );
  const base = new Map<string, LockEntry>([
    ['g', entry],
    ['h', { ...entry, id: 'h' }],
  ]);
  const t = touchedCandidates(
    [
      { ...entry, paths: ['a/**'] },
      { ...entry, id: 'h' },
      { ...entry, id: 'k' },
    ],
    base,
    new Set(['tool.ts']),
    (e) => new Set(e.id === 'h' ? ['tool.ts'] : [])
  );
  check(
    t.map((x) => `${x.id}:${x.why}`).join('|') ===
      'g:lock entry changed|h:leaf closure file tool.ts changed|k:new lock entry',
    'quick selects a changed entry, a changed leaf closure and a new entry'
  );
  check(
    touchedCandidates([entry], new Map([['g', entry]]), new Set(['zzz']), () => new Set())
      .length === 0,
    'CONTROL: an untouched entry is not selected'
  );

  // Both modes against a fixture repository with one honest and one lying gate.
  const refusal = traceRefusal();
  if (refusal !== undefined) {
    console.log(`  FAIL  this host cannot trace, so the fixture half cannot run: ${refusal}`);
    return 1;
  }
  const dir = fs.mkdtempSync(path.join(runRoot('trace-honest-'), 'self-'));
  try {
    const files: Record<string, string> = {
      'a.txt': 'a',
      'b.txt': 'b',
      'tool.sh': '#!/bin/sh\n',
      '.ci/tool.py': "open('conf/x.txt').read()\n",
      '.ci/other.py': 'pass\n',
      'conf/x.txt': 'x',
      'src/keep.txt': 'keep',
    };
    for (let i = 0; i < 20; i++) files[`filler/f${i}.txt`] = 'x';
    const lockRows: LockEntry[] = [
      {
        id: 'g:honest',
        run: 'cat a.txt >/dev/null',
        gate: true,
        paths: ['a.txt'],
        pathsOrigin: 'traced',
        leaves: ['tool.sh'],
      },
      {
        id: 'g:liar',
        run: 'cat a.txt b.txt >/dev/null',
        gate: true,
        paths: ['a.txt'],
        pathsOrigin: 'traced',
        leaves: ['tool.sh'],
      },
      // The W2.5 accept fixture: `python3 -m` from the root reading two files, declared with and without its listings.
      {
        id: 'g:py',
        run: 'PYTHONPATH=.ci python3 -m tool',
        gate: true,
        paths: ['.ci/tool.py', 'conf/x.txt'],
        lists: ['', '.ci'],
        pathsOrigin: 'traced',
        leaves: ['tool.sh'],
      },
      {
        id: 'g:py-nolists',
        run: 'PYTHONPATH=.ci python3 -m tool',
        gate: true,
        paths: ['.ci/tool.py', 'conf/x.txt'],
        pathsOrigin: 'traced',
        leaves: ['tool.sh'],
      },
      // Need only the names they declare: sparse mode must place them, or the gate cannot find them.
      {
        id: 'g:names-only',
        run: 'test -e src/keep.txt',
        gate: true,
        names: ['src/**'],
        pathsOrigin: 'traced',
        leaves: ['tool.sh'],
      },
      {
        id: 'g:lists-only',
        run: 'ls src | grep -qx keep.txt',
        gate: true,
        lists: ['src'],
        pathsOrigin: 'traced',
        leaves: ['tool.sh'],
      },
      // Declares only the NAMES under src, yet needs a file's bytes: the sparse placeholder is empty, so sparse mode catches it.
      {
        id: 'g:names-bytes',
        run: 'grep -q keep src/keep.txt',
        gate: true,
        names: ['src/**'],
        pathsOrigin: 'traced',
        leaves: ['tool.sh'],
      },
    ];
    files[LOCK_REL] = `${JSON.stringify(lockRows, null, 2)}\n`;
    // repoView refuses a root with no record set (path-trace.ts readRecordGlobs, review 502ce0ee.2); without one every CLI control below died on that refusal instead of judging its fixture.
    files[policyPath('record-paths.json', '.')] = `${JSON.stringify({ records: [] })}\n`;
    for (const [rel, text] of Object.entries(files)) {
      fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
      fs.writeFileSync(path.join(dir, rel), text);
    }
    const env = {
      ...process.env,
      GIT_AUTHOR_NAME: 't',
      GIT_AUTHOR_EMAIL: 't@t',
      GIT_COMMITTER_NAME: 't',
      GIT_COMMITTER_EMAIL: 't@t',
    };
    for (const a of [
      ['init', '-q'],
      ['add', '-A'],
      ['commit', '-qm', 'fixture'],
    ])
      spawnSync('git', a, { cwd: dir, env });
    const self = import.meta.filename;
    const tsx = path.join(REPO_ROOT, 'node_modules', '.bin', 'tsx');
    const run = (...a: string[]): { status: number | null; err: string } => {
      const r = spawnSync(tsx, [self, '--root', dir, ...a], { encoding: 'utf8' });
      return { status: r.status, err: r.stderr };
    };
    for (const mode of ['trace', 'sparse']) {
      const honest = run('--mode', mode, '--gate', 'g:honest');
      check(
        honest.status === 0,
        `CONTROL: ${mode} mode passes the declared fixture (rc=${honest.status})`
      );
      const liar = run('--mode', mode, '--gate', 'g:liar');
      check(
        liar.status === 1 &&
          (mode === 'sparse' || liar.err.includes('reads b.txt, outside its paths')),
        `${mode} mode fails the undeclared-read fixture (rc=${liar.status})`
      );
    }
    const py = run('--mode', 'trace', '--gate', 'g:py');
    check(
      py.status === 0,
      `python3 -m reading 2 files passes with paths of those 2 plus lists ['', '.ci'] (rc=${py.status}) ${py.status === 0 ? '' : py.err.slice(-600)}`
    );
    const pyNo = run('--mode', 'trace', '--gate', 'g:py-nolists');
    check(
      pyNo.status === 1 &&
        pyNo.err.includes('lists the repository root') &&
        pyNo.err.includes('lists .ci/'),
      `the same fixture without lists fails, naming the root and .ci listings (rc=${pyNo.status})`
    );
    const pySparse = run('--mode', 'sparse', '--gate', 'g:py');
    check(
      pySparse.status === 0,
      `CONTROL: sparse mode passes g:py, its listed names placed empty (rc=${pySparse.status}) ${pySparse.status === 0 ? '' : pySparse.err.slice(-600)}`
    );
    for (const g of ['g:names-only', 'g:lists-only']) {
      const r = run('--mode', 'sparse', '--gate', g);
      check(
        r.status === 0,
        `CONTROL: sparse mode places the names ${g} declares, so it passes there too (rc=${r.status}) ${r.status === 0 ? '' : r.err.slice(-400)}`
      );
    }
    const nb = run('--mode', 'sparse', '--gate', 'g:names-bytes');
    check(
      nb.status === 1 && nb.err.includes('holding only its declared inputs'),
      `sparse mode fails a gate that declares names but needs their bytes (rc=${nb.status})`
    );
    for (const flag of ['--sparse-top', '--jobs']) {
      const bad = run(flag, 'abc', '--mode', 'sparse', '--gate', 'g:honest');
      check(
        bad.status === 1 && bad.err.includes('takes a whole number'),
        `a non-numeric ${flag} is refused, not read as NaN and a green on nothing (rc=${bad.status})`
      );
    }
    const empty = run('--mode', 'trace', '--rotation', '8/8');
    check(
      empty.status === 1 && empty.err.includes('a zero selection is green only in --quick'),
      `an empty rotation bucket (8/8 of 7 candidates) fails outside --quick (rc=${empty.status})`
    );
    const full = run('--rotation', '1/7', '--list');
    check(
      full.status === 0 && full.err.includes('selected (rotation 1/7)'),
      `CONTROL: a non-empty rotation bucket still lists and exits 0 (rc=${full.status})`
    );
    const tmpSparse = (): number => fs.readdirSync(runRoot('trace-honest-')).length;
    const sparseBefore = tmpSparse();
    let threw = false;
    try {
      buildSparse(
        // A listed file that is absent on disk: its copy fails after the directory exists.
        { ...repoView(dir), files: ['ghost.txt'] },
        {
          id: 'g:ghost',
          run: 'true',
          gate: true,
          paths: ['ghost.txt'],
          pathsOrigin: 'traced',
          leaves: [],
        },
        new Set<string>()
      );
    } catch {
      threw = true;
    }
    check(
      threw && tmpSparse() === sparseBefore,
      `a sparse build that throws after mkdtemp removes its directory (threw ${threw}, leaked ${tmpSparse() - sparseBefore})`
    );
    const sdir = fs.mkdtempSync(path.join(runRoot('trace-honest-'), 'sym-'));
    try {
      const real = path.join(sdir, 'real.txt');
      fs.writeFileSync(real, 'one');
      fs.mkdirSync(path.join(sdir, 'd'));
      fs.symlinkSync(real, path.join(sdir, 'd', 'link'));
      const before = statLinked(sdir, ['d']);
      check(
        [...statLinked(sdir, ['d']).entries()].join() === [...before.entries()].join() &&
          before.has('d/link'),
        'CONTROL: an untouched directory with a symlink snapshots the same twice, the link included'
      );
      fs.writeFileSync(real, 'two-longer');
      check(
        statLinked(sdir, ['d']).get('d/link') !== before.get('d/link'),
        "a write through a symlink in a linked directory moves that link's snapshot"
      );
      // A link to a DIRECTORY: a write to a file inside it moves the link's snapshot (a8593634.1).
      fs.mkdirSync(path.join(sdir, 'target'));
      fs.writeFileSync(path.join(sdir, 'target', 'inner.txt'), 'one');
      fs.symlinkSync(path.join(sdir, 'target'), path.join(sdir, 'd', 'dirlink'));
      const dirBefore = statLinked(sdir, ['d']);
      check(
        [...statLinked(sdir, ['d']).entries()].join() === [...dirBefore.entries()].join(),
        'CONTROL: an untouched link to a directory snapshots the same twice'
      );
      fs.writeFileSync(path.join(sdir, 'target', 'inner.txt'), 'two-longer');
      check(
        statLinked(sdir, ['d']).get('d/dirlink') !== dirBefore.get('d/dirlink'),
        "a write to a file inside a symlinked directory moves that link's snapshot"
      );
      // A symlink NESTED inside the linked directory: the write lands outside it, through the inner link (25e08a96.1).
      fs.mkdirSync(path.join(sdir, 'outer'));
      fs.mkdirSync(path.join(sdir, 'outer', 'sub'));
      fs.writeFileSync(path.join(sdir, 'outer', 'sub', 'file.txt'), 'one');
      fs.symlinkSync(path.join(sdir, 'outer', 'sub'), path.join(sdir, 'outer', 'sub', 'cycle'));
      fs.symlinkSync(path.join(sdir, 'outside.txt'), path.join(sdir, 'outer', 'nested'));
      fs.writeFileSync(path.join(sdir, 'outside.txt'), 'one');
      const treeBefore = [...snapshotTree(path.join(sdir, 'outer')).entries()].join();
      check(
        treeBefore === [...snapshotTree(path.join(sdir, 'outer')).entries()].join() &&
          snapshotTree(path.join(sdir, 'outer')).has('nested'),
        'CONTROL: a tree with a nested file link and a directory cycle snapshots the same twice, the nested link included'
      );
      fs.writeFileSync(path.join(sdir, 'outside.txt'), 'two-longer');
      check(
        [...snapshotTree(path.join(sdir, 'outer')).entries()].join() !== treeBefore,
        'a write through a symlink nested inside a snapshotted tree moves the snapshot'
      );
      // The walk is bounded by entries and by depth (25e08a96.2).
      for (let i = 0; i < 5; i += 1) fs.writeFileSync(path.join(sdir, 'target', `f${i}.txt`), 'x');
      check(
        snapshotTree(path.join(sdir, 'target'), 3).size === 3,
        'a snapshot stops at the entry bound'
      );
      check(
        snapshotTree(path.join(sdir, 'target')).size === 6,
        'CONTROL: the same directory under the default bound is recorded whole'
      );
      let deep = path.join(sdir, 'deep');
      fs.mkdirSync(deep);
      for (let i = 0; i < 4; i += 1) {
        deep = path.join(deep, `l${i}`);
        fs.mkdirSync(deep);
        fs.writeFileSync(path.join(deep, 'x.txt'), 'x');
      }
      check(
        snapshotTree(path.join(sdir, 'deep'), SNAPSHOT_MAX_ENTRIES, 2).size === 2,
        'a snapshot stops at the depth bound'
      );
      // A bound that skips something is reported to the caller (b229b8fc.1); one that skips nothing is not (b229b8fc.2).
      const hit: string[] = [];
      snapshotTree(path.join(sdir, 'target'), 3, SNAPSHOT_MAX_DEPTH, (d) => hit.push(d));
      check(hit.length === 1, 'a bound that skips files names its directory to the caller');
      fs.mkdirSync(path.join(sdir, 'exact'));
      for (let i = 0; i < 2; i += 1) fs.writeFileSync(path.join(sdir, 'exact', `f${i}`), 'x');
      fs.mkdirSync(path.join(sdir, 'exact', 'zempty'));
      const quiet: string[] = [];
      snapshotTree(path.join(sdir, 'exact'), 2, SNAPSHOT_MAX_DEPTH, (d) => quiet.push(d));
      check(
        quiet.length === 0,
        'CONTROL: exactly the bound in files plus an empty subdirectory skips nothing'
      );
    } finally {
      fs.rmSync(sdir, { recursive: true, force: true });
    }
    const frac = run('--timeout-s', '2.5', '--mode', 'trace', '--list');
    check(
      frac.status === 0,
      `a fractional --timeout-s is accepted (a8593634.2; rc=${frac.status}) ${frac.err.slice(-200)}`
    );
    for (const text of ['abc', '0.5', '']) {
      const bad = run('--timeout-s', text, '--mode', 'trace', '--list');
      check(
        bad.status === 1 && bad.err.includes('takes a number of seconds'),
        `CONTROL: --timeout-s ${JSON.stringify(text)} is refused (rc=${bad.status})`
      );
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  // Temp disposal: real children, a signal mid-build and a SIGKILL.
  await tempDisposalCases(import.meta.filename, 'trace-honest-', check, false);
  await plainGroupCases(check);
  await grantCases(check);
  await capCases(check);
  const coreFailures = await gateCoresSelftest();
  check(
    coreFailures.length === 0,
    `gate-cores: per-gate grants out of the machine-wide lease (4 tokens, third take waits until a give; an unleased run still names each width)${coreFailures.length === 0 ? '' : `: ${coreFailures.join('; ')}`}`
  );
  console.log(`trace-honest selftest: ${n - bad}/${n} passed`);
  return bad === 0 ? 0 : 1;
}

/**
 * D5 and review a7298eaa.1: `runPlain` registers its group with the signal handler, and carries the runner-death watch. A child runs a fixture gate that forks a sleeper (inside the gate's own detached group, not the child's), reports how many groups are registered, and is SIGKILLed; the sleeper must be gone 3 s later.
 */
async function plainGroupCases(check: (ok: boolean, label: string) => void): Promise<void> {
  const aux = fs.mkdtempSync(path.join(fs.existsSync('/tmp') ? '/tmp' : os.tmpdir(), 'th-plain-'));
  try {
    const pidFile = path.join(aux, 'sleeper.pid');
    const script = path.join(aux, 'child.mts');
    fs.writeFileSync(
      script,
      `import { tempProbeChild } from ${JSON.stringify(pathToFileURL(import.meta.filename).href)};\ntempProbeChild('plain');\n`
    );
    const child: ChildProcess = spawn(process.execPath, [...process.execArgv, script], {
      env: { ...process.env, TH_SLEEPER_PIDFILE: pidFile },
      stdio: ['ignore', 'pipe', 'inherit'],
    });
    let seen = '';
    await new Promise<void>((resolve, reject) => {
      child.stdout?.on('data', (d: Buffer) => {
        seen += String(d);
        if (seen.includes('ready')) resolve();
      });
      child.on('exit', () => reject(new Error('plain probe child exited before it was ready')));
    });
    const live = /live=(\d+)/.exec(seen);
    let sleeper = 0;
    for (let i = 0; i < 60 && sleeper === 0; i++) {
      if (fs.existsSync(pidFile)) sleeper = Number(fs.readFileSync(pidFile, 'utf8').trim()) || 0;
      else await new Promise((r) => setTimeout(r, 50));
    }
    check(
      live !== null && Number(live[1]) === 1,
      `runPlain registers its group with the signal handler (registered groups ${live?.[1] ?? 'unread'}, expected 1)`
    );
    const aliveBefore = sleeper !== 0 && pidRunning(sleeper);
    child.kill('SIGKILL');
    await new Promise<void>((resolve) => child.on('exit', () => resolve()));
    const gone = sleeper !== 0 && (await waitPidGone(sleeper, 3000));
    check(
      aliveBefore && gone,
      `death watch: a SIGKILLed trace-honest leaves no process of its fixture gate (sleeper pid ${sleeper} alive before ${aliveBefore}, gone within 3 s ${gone})`
    );
  } finally {
    fs.rmSync(aux, { recursive: true, force: true });
  }
}

/** 2cefaa4d.1/.2, a7298eaa.3, b1bcc098.2: the grant reaches each gate, a failing removal still gives the tokens back, a spawn error unregisters its group, and a bad `--max-log-mb` names MB. */
async function grantCases(check: (ok: boolean, label: string) => void): Promise<void> {
  const grant = { cores: 3, env: { ...process.env, TH_GRANT_PROBE: 'width-3' } };
  const plain = await runGate('printf %s "$TH_GRANT_PROBE"', process.cwd(), 30, grant);
  const bare = await runPlain('printf %s "${TH_GRANT_PROBE:-none}"', process.cwd(), 30);
  check(
    plain.exit === 0 && plain.tail === 'width-3' && bare.tail === 'none',
    `runGate passes the grant's environment to the gate (saw ${JSON.stringify(plain.tail)}); CONTROL: a run with no grant sees ${JSON.stringify(bare.tail)}`
  );
  const opts = traceOptionsFor('g:x', { timeoutS: 5, maxLogMb: 7 }, grant);
  check(
    opts.env.TH_GRANT_PROBE === 'width-3' && opts.label === 'g:x' && opts.maxLogMb === 7,
    `the traced run's options carry the grant's environment, label and log limit (env ${opts.env.TH_GRANT_PROBE})`
  );
  let given = 0;
  let threw = false;
  try {
    await finishSparse(
      '/x',
      () => {
        throw new Error('rm failed');
      },
      async () => {
        given++;
      }
    );
  } catch {
    threw = true;
  }
  check(
    threw && given === 1,
    `a sparse removal that throws still gives the grant back (threw ${threw}, given ${given})`
  );
  let removed = 0;
  let given2 = 0;
  await finishSparse(
    '/x',
    () => {
      removed++;
    },
    async () => {
      given2++;
    }
  );
  check(removed === 1 && given2 === 1, 'CONTROL: a clean removal removes once and gives once');
  const failed = await runPlain('true', '/nonexistent-cwd-for-th-selftest', 30);
  check(
    failed.exit === 127 && liveGroupCount() === 0,
    `a spawn error resolves 127 and leaves no registered group (exit ${failed.exit}, registered ${liveGroupCount()})`
  );
  let msg = '';
  try {
    parseArgs(['--max-log-mb', '0']);
  } catch (err) {
    msg = (err as Error).message;
  }
  let msgS = '';
  try {
    parseArgs(['--timeout-s', '0']);
  } catch (err) {
    msgS = (err as Error).message;
  }
  check(
    msg.includes('MB') && !msg.includes('seconds') && msgS.includes('seconds'),
    `a bad --max-log-mb names MB, not seconds (${msg}); CONTROL: --timeout-s still says seconds`
  );
}

/** D4: a trace the stub pushed past the limit is a `trace-log-cap` finding and never a pass; the free-space wait waits, then refuses. */
async function capCases(check: (ok: boolean, label: string) => void): Promise<void> {
  await logCapCases(check);
  const aux = fs.mkdtempSync(path.join(fs.existsSync('/tmp') ? '/tmp' : os.tmpdir(), 'th-cap-'));
  try {
    const stub = writeStraceStub(path.join(aux, 'strace-stub.sh'));
    const run = await traceCommand('true', process.cwd(), {
      straceBin: stub,
      env: { ...process.env, STUB_BYTES: '2000000', STUB_SLEEP: '15' },
      maxLogMb: 1,
      capPollMs: 100,
    });
    const f = capFindings('g:cap', run, 1);
    check(
      f.length === 1 && f[0].what.startsWith('trace-log-cap:') && f[0].fix.includes('--max-log-mb'),
      `a capped trace is the trace-log-cap finding naming the gate and the way out (${f.map((x) => x.what.slice(0, 40)).join('|')})`
    );
    check(
      capFindings('g:ok', { capped: false, logBytes: 10 }, 1).length === 0,
      'CONTROL: an uncapped trace gives no trace-log-cap finding'
    );
  } finally {
    fs.rmSync(aux, { recursive: true, force: true });
  }
  const need = requiredFreeBytes(2, 100);
  check(
    need === 2 * 100 * 1048576 + 20 * 1024 ** 3,
    `the free-space need is jobs x max-log-mb + 20 GiB (${need})`
  );
  const refused = await waitForFreeSpace('/x', need, {
    statfs: () => 1024,
    pollMs: 10,
    maxWaitMs: 60,
  });
  check(
    !refused.ok && refused.waitedMs >= 60,
    `free space below the need refuses after the wait (ok ${refused.ok}, waited ${refused.waitedMs} ms)`
  );
  const reads = [1024, 1024, need];
  let at = 0;
  const waited = await waitForFreeSpace('/x', need, {
    statfs: () => reads[Math.min(at++, reads.length - 1)],
    pollMs: 10,
    maxWaitMs: 5000,
  });
  check(
    waited.ok && at === 3,
    `CONTROL: free space that appears after two polls ends the wait ok (ok ${waited.ok}, polls ${at})`
  );
  const enough = await waitForFreeSpace('/x', need, { statfs: () => need, pollMs: 10 });
  check(enough.ok && enough.waitedMs < 50, 'CONTROL: enough free space starts at once');
}

/** The child side of `tempDisposalCases`: builds one real sparse tree in the run dir, installs the entry hook, then idles (mode `noop` only touches the run dir and exits; mode `plain` runs a fixture gate through `runPlain`). */
export function tempProbeChild(mode: string): void {
  installEntrySignals();
  if (mode === 'noop') {
    runRoot('trace-honest-');
    return;
  }
  if (mode === 'plain') {
    // The fixture gate backgrounds a sleeper inside the gate's own group and records its pid.
    void runPlain(
      'sleep 15 & echo $! > "$TH_SLEEPER_PIDFILE"; wait',
      process.cwd(),
      600,
      process.env
    );
    console.log(`live=${liveGroupCount()}`);
    console.log('ready');
    setInterval(() => undefined, 1000);
    return;
  }
  const empty = fs.mkdtempSync(path.join(runRoot('trace-honest-'), 'probe-root-'));
  fs.writeFileSync(path.join(empty, 'a.txt'), 'x');
  buildSparse(
    { ...repoView(REPO_ROOT), root: empty, files: ['a.txt'] },
    { id: 'g:probe', run: 'true', gate: true, paths: ['a.txt'], pathsOrigin: 'traced', leaves: [] },
    new Set<string>()
  );
  console.log('ready');
  setInterval(() => undefined, 1000);
}

if (isEntryPoint(import.meta.filename)) {
  // A SIGTERM or SIGINT kills the traced groups and exits 130, which removes the run dir with every sparse tree and trace log under it.
  installEntrySignals();
  main(process.argv.slice(2))
    .then(
      (code) => {
        process.exitCode = code;
      },
      (err: unknown) => {
        console.error(`trace-honest: ${(err as Error).stack ?? String(err)}`);
        process.exitCode = 1;
      }
    )
    .finally(() => openedLease?.close());
}
