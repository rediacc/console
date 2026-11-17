#!/usr/bin/env tsx
/**
 * trace-honest: fail a gate that reads a tracked path its `paths` do not declare (agent/plans/PLAN-ciquick-cpu.md A3).
 *
 * WHY. Carry is sound only while a gate's `paths` name everything it reads. A gate whose glob misses one input keeps a green across a change to that input, and nothing downstream notices: the receipt says carried, the push guard re-hashes the declared inputs and agrees. path-trace.ts writes paths from one trace; this gate keeps them true afterwards, for traced and hand-declared sets alike.
 *
 * TWO INDEPENDENT MODES.
 *   - `trace` re-runs the gate under strace (path-trace.ts `traceCommand`) and fails on any tracked read outside `paths ∪ GLOBAL_INPUTS ∪ leaf closure`, any listed directory no declared glob reaches, a read inside a submodule whose gitlink is undeclared, and any git history or index read (a gate with paths may locate the repository, never read its history). Each finding names the path and the fix.
 *   - `sparse` builds a directory holding ONLY the declared inputs (copied), the dependency trees (hard-link copies, as quick-clone.ts does, so workspace links resolve inside it), the ignored build output (hard-link copies) and the read-only toolchain caches (symlinks), and runs the gate there. A verdict that differs from the same gate's run in the real tree means it needed something undeclared. It shares no code path with the tracer's attribution, so a blind spot in one (a daemon read, io_uring) is not a blind spot in both.
 *
 * WHICH GATES. Every lock entry with `paths` and `gate: true` that is not carry-exempt or ciOnly is a candidate. `--quick` judges the candidates whose lock entry changed, or one of whose leaf-closure files changed, since the last push (quick-select.ts `resolvePushBase`); an unresolvable base is a failure, never an empty pass. `--rotation <i>/<n>` judges bucket i of n, balanced by measured cost; `--rotation auto` takes i from the UTC day of the year over n = 3. Sparse mode takes the `--sparse-top` (default 10) costliest gates of the selection.
 *
 * NEVER GREEN ON NOTHING. Zero candidates in the lock is a failure (the gate is not seeing the estate). A selection of zero is green only in `--quick`, and says how many candidates it saw and against which base. A red gate is a finding: its trace may be partial and its sparse verdict is meaningless.
 *
 * Usage:
 *   tsx scripts/ci-runner/trace-honest.ts [--mode trace|sparse|both] [--quick [--base <ref>]] [--rotation <i>/<n>|auto] [--gate <id> ...] [--origin declared|traced] [--sparse-top N] [--jobs N] [--list]
 *   tsx scripts/ci-runner/trace-honest.ts --selftest
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { isEntryPoint } from '../lib/entry-point.js';
import { CARRY_EXEMPT_REL, exemptIdsOf, GLOBAL_INPUTS, matchGlob } from './input-hash.js';
import {
  attribute,
  type LockEntry,
  LOCK_REL,
  REPO_ROOT,
  type RepoView,
  repoView,
  traceCommand,
  traceRefusal,
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

/** Whether a declared glob reaches a NEW direct child of `dir`, which is what a listing would see. */
export function listingDeclared(dir: string, globs: readonly string[]): boolean {
  const probe = `${dir}/zz-trace-honest-probe`;
  return globs.some((g) => matchGlob(g, probe));
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
  leafFiles: ReadonlySet<string>
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
  for (const e of attr.gitHistory)
    add(
      `reads git history (${e}); a gate whose verdict moves with history cannot declare paths`,
      `drop its paths (it hashes the whole tree then) or add it to ${CARRY_EXEMPT_REL} with the reason`
    );
  for (const e of attr.gitIndex)
    add(
      `enumerates the tracked file list through the git index (${e}), so a new file anywhere can change its verdict`,
      `drop its paths, so it hashes the whole tree`
    );
  for (const c of attr.cacheState)
    add(
      `reads untracked cache state (${c}), so its verdict can move with no tracked input moving`,
      `drop its paths, or add it to ${CARRY_EXEMPT_REL} with the reason`
    );
  if ((entry.needs ?? []).length === 0)
    for (const b of attr.buildOutput)
      add(
        `reads untracked build output (${b}) with no needs edge naming its producer, so no input hash moves when that output does`,
        `add the producer to the needs of ${entry.id} in scripts/ci-runner/manifest.ts`
      );
  const globs = declaredGlobs(entry);
  if (attr.listed.has(''))
    add(
      'lists the repository root, which no paths glob short of ** reaches',
      'drop its paths, so it hashes the whole tree'
    );
  const reads = [...attr.reads].filter((p) => !isDeclared(p, globs, leafFiles)).sort(byteOrder);
  const shown = reads.slice(0, 20);
  for (const p of shown) add(`reads ${p}, outside its paths`);
  if (reads.length > shown.length)
    add(`and ${reads.length - shown.length} more undeclared read(s)`);
  for (const d of [...attr.listed].sort(byteOrder)) {
    if (d !== '' && !listingDeclared(d, globs))
      add(
        `lists ${d}/, so a new file there changes what it sees, and no declared glob reaches ${d}/<new>`
      );
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
  timeoutS: number
): Promise<{ exit: number; tail: string }> {
  return new Promise((resolve) => {
    const chunks: string[] = [];
    const child = spawn('bash', ['-c', cmd], {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: true,
    });
    child.stdout.on('data', (d) => chunks.push(String(d)));
    child.stderr.on('data', (d) => chunks.push(String(d)));
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
      resolve({
        exit: timedOut ? 124 : (code ?? (signal ? 128 : 1)),
        tail: chunks.join('').split('\n').slice(-12).join('\n'),
      });
    });
    child.on('error', () => resolve({ exit: 127, tail: 'spawn failed' }));
  });
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
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'trace-honest-sparse-'));
  const globs = declaredGlobs(entry);
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
    const r = spawnSync('cp', ['-al', path.join(view.root, rel), dst]);
    if (r.status !== 0) throw new Error(`cp -al ${rel} failed: ${r.stderr}`);
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
  return dir;
}

/** Removes a sparse directory, retrying while a straggling child of the gate finishes writing; a directory that survives is named, never leaked silently. */
function removeSparse(dir: string): void {
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
  selftest: boolean;
  /** Print the selection, one `<id>\t<why>` per line, and exit without running anything. */
  list: boolean;
  /** Judge only candidates whose pathsOrigin is this (`declared` or `traced`). */
  origin?: string;
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
    else if (t === '--sparse-top') a.sparseTop = Number(val());
    else if (t === '--jobs') a.jobs = Number(val());
    else if (t === '--root') a.root = path.resolve(val());
    else if (t === '--timeout-s') a.timeoutS = Number(val());
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
      (e.paths ?? []).length > 0 &&
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
  if (args.mode !== 'sparse') {
    await pool(selected, args.jobs, async ({ id, why }) => {
      const e = byId.get(id) as LockEntry;
      const run = await traceCommand(e.run, view.root, { timeoutS: args.timeoutS, label: id });
      const f = traceFindings(e, attribute(run.access, view), run.exit, leafFilesOf(e));
      traced++;
      findings.push(...f);
      console.error(
        `  trace  ${f.length === 0 ? 'PASS' : 'FAIL'}  ${id} (${why}; ${run.seconds}s, ${e.paths?.length} glob(s))`
      );
      if (run.exit !== 0) console.error(run.outputTail.replace(/^/gm, '      | '));
    });
  }
  if (args.mode !== 'trace') {
    const cost = costOf(args.root);
    const top = [...selected].sort((a, b) => cost(b.id) - cost(a.id)).slice(0, args.sparseTop);
    for (const { id } of top) {
      const e = byId.get(id) as LockEntry;
      const real = await runPlain(e.run, view.root, args.timeoutS);
      let dir: string | undefined;
      try {
        dir = buildSparse(view, e, leafFilesOf(e));
        const sparse = await runPlain(e.run, dir, args.timeoutS);
        sparsed++;
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
        if (dir !== undefined) removeSparse(dir);
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
    `trace-honest: OK, ${traced} traced and ${sparsed} sparse-run of ${selected.length} selected (${candidates.length} candidates, ${scope}); every read is declared`
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
    traceFindings(entry, attr(['a/x.ts', 'b.txt', 'packages/p/package-lock.json']), 0, new Set())
      .length === 0,
    'CONTROL: declared reads, a global input and nothing else pass'
  );
  // input-hash.ts matches `**/package-lock.json` as `.*/package-lock.json`, so the ROOT lockfile is not a global input; the honesty check follows the hasher, not the glob's apparent intent.
  check(
    traceFindings(entry, attr(['package-lock.json']), 0, new Set()).length === 1,
    'the root lockfile is outside GLOBAL_INPUTS as the hasher matches them, so it must be declared'
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
    'CONTROL: the same read with a needs edge passes'
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
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'trace-honest-self-'));
  try {
    const files: Record<string, string> = { 'a.txt': 'a', 'b.txt': 'b', 'tool.sh': '#!/bin/sh\n' };
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
    ];
    files[LOCK_REL] = `${JSON.stringify(lockRows, null, 2)}\n`;
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
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  console.log(`trace-honest selftest: ${n - bad}/${n} passed`);
  return bad === 0 ? 0 : 1;
}

if (isEntryPoint(import.meta.filename)) {
  main(process.argv.slice(2)).then(
    (code) => {
      process.exitCode = code;
    },
    (err: unknown) => {
      console.error(`trace-honest: ${(err as Error).stack ?? String(err)}`);
      process.exitCode = 1;
    }
  );
}
