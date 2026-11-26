/**
 * A per-run temp directory that a LATER run removes when this one is killed. The TypeScript twin of
 * .ci/rediacc_ci/runtmp.py: the same stamp (`<prefix><pid>-n<pidns>-<random>`), the same prefix rule and the
 * same DEEP_TMPDIR budget, so either language's sweep removes the other's dead run dirs.
 *
 * WHY NOT `process.on('exit')` ALONE. It runs when the process gets to exit. A run killed by SIGKILL, or by SIGTERM
 * with no handler, unwinds nothing, so its temp stays. The exit hook covers the normal end, `installSignalCleanup`
 * covers SIGINT, SIGTERM and SIGHUP, and `sweepDead` (called by every `runDir`) covers SIGKILL on the next run.
 *
 * THE SWEEP IS CONSERVATIVE: a pid that cannot be parsed is left, a live pid is left (even a reused one), and a
 * directory stamped in a different pid namespace is left, because its pid would look dead from here while its run is live.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

const PREFIX_SHAPE = /^[A-Za-z][A-Za-z0-9_.-]*-$/;

/** Past this many bytes of inherited TMPDIR a new run dir is rooted at /tmp (the tsx socket-path budget in runtmp.py). */
export const DEEP_TMPDIR = 24;

function pidNamespace(): string {
  try {
    return String(fs.statSync('/proc/self/ns/pid', { bigint: true }).ino);
  } catch {
    return '0';
  }
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
  } catch (err) {
    // EPERM: someone else's live process, alive and not ours to sweep. ESRCH: gone.
    return (err as NodeJS.ErrnoException).code === 'EPERM';
  }
  return true;
}

function checkPrefix(prefix: string): void {
  if (!PREFIX_SHAPE.test(prefix))
    throw new Error(
      `runtmp prefix ${JSON.stringify(prefix)} must be non-empty, start with a letter and end with '-'`
    );
}

/** The name prefix a run with `pid` gets: `<prefix><pid>-n<pidns>-`. */
export function stamp(prefix: string, pid: number = process.pid): string {
  checkPrefix(prefix);
  return `${prefix}${pid}-n${pidNamespace()}-`;
}

/** `fs.rmSync` that never throws; a tree it cannot finish is left for the next sweep. */
export function removeTree(target: string): void {
  try {
    fs.rmSync(target, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
  } catch {
    // left for a later sweep
  }
}

/** Removes every `<prefix><pid>-n<ns>-*` directory in `base` whose pid is dead in THIS namespace; returns the removed paths. */
export function sweepDead(prefix: string, base: string = os.tmpdir()): string[] {
  checkPrefix(prefix);
  const shape = new RegExp(`^${prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(\\d+)-n(\\d+)-`);
  const here = pidNamespace();
  const removed: string[] = [];
  let names: string[];
  try {
    names = fs.readdirSync(base);
  } catch (err) {
    // A base that does not exist holds no dead run. Any other read failure is a VACUOUS sweep: it judged nothing, so it
    // says so on stderr rather than passing as "nothing dead", and still never throws (a cleanup must not fail its caller).
    const code = (err as NodeJS.ErrnoException).code;
    if (code !== 'ENOENT')
      process.stderr.write(
        `runtmp: VACUOUS sweep of ${base}: it could not be read (${code ?? String(err)}), so no dead ${prefix} run dir was judged\n`
      );
    return removed;
  }
  for (const name of names) {
    const m = shape.exec(name);
    if (m === null || m[2] !== here) continue;
    const pid = Number(m[1]);
    if (pid === process.pid || alive(pid)) continue;
    const full = path.join(base, name);
    let st: fs.Stats;
    try {
      st = fs.lstatSync(full);
    } catch {
      continue;
    }
    if (st.isSymbolicLink() || !st.isDirectory()) continue;
    removeTree(full);
    if (!fs.existsSync(full)) removed.push(full);
  }
  return removed;
}

const OWNED = new Set<string>();
let exitHooked = false;

function hookExit(): void {
  if (exitHooked) return;
  exitHooked = true;
  process.on('exit', removeOwned);
}

/** Removes every run dir this process made. Idempotent; also what the exit hook runs. */
export function removeOwned(): void {
  for (const dir of OWNED) removeTree(dir);
  OWNED.clear();
  SHARED.clear();
}

function shallowBase(): string | undefined {
  const inherited = os.tmpdir();
  if (inherited.length > DEEP_TMPDIR && fs.existsSync('/tmp')) return '/tmp';
  return undefined;
}

/** Sweeps dead runs of `prefix`, then creates and returns this process's run directory, removed at exit. */
export function runDir(prefix: string, base?: string): string {
  const root = base ?? shallowBase() ?? os.tmpdir();
  sweepDead(prefix, root);
  const dir = fs.mkdtempSync(path.join(root, stamp(prefix)));
  OWNED.add(dir);
  hookExit();
  return dir;
}

const SHARED = new Map<string, string>();

/** `runDir(prefix)`, made once per process and handed back on every later call (made again if something removed it). */
export function shared(prefix: string, base?: string): string {
  const key = `${prefix}\0${base ?? ''}`;
  const hit = SHARED.get(key);
  if (hit !== undefined && fs.existsSync(hit)) return hit;
  const dir = runDir(prefix, base);
  SHARED.set(key, dir);
  return dir;
}

/** A thrown value as text, never throwing itself: `String(Object.create(null))` throws, and the signal exit must still be reached. */
function describeThrown(err: unknown): string {
  try {
    return String(err);
  } catch {
    return '(a value with no string form)';
  }
}

/**
 * Makes SIGINT, SIGTERM and SIGHUP run `extra` (the caller's own cleanup, such as killing child groups), then exit 130,
 * which runs the exit hook that removes the run dirs. Chained, never replacing: a handler the caller already has stays.
 * An `extra` that throws is named on stderr before the exit, so a failed cleanup leaves a trace.
 */
export function installSignalCleanup(extra?: () => void): void {
  hookExit();
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP'] as const) {
    process.on(sig, () => {
      try {
        extra?.();
      } catch (err) {
        process.stderr.write(`runtmp: the ${sig} cleanup callback threw: ${describeThrown(err)}\n`);
      }
      process.exit(130);
    });
  }
}
