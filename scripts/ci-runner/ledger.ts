/**
 * THE OUTCOME LEDGER'S WRITER (agent/plans/PLAN-gate-scheduling-learned.md section 1, T6): one `run` row, one `g` row per gate as it settles, one `end` row, streamed to a long-lived `python3 -m rediacc_ci.ci.gate_ledger append` child that does the locked append. The ledger is what model.json (and so rank.ts) is learned from; it is state, not cache, because receipts rotate at 50 and history past that cannot be backfilled.
 *
 * THE WIRE (what the child reads on stdin): one JSON object per line, each carrying `"t"` (`run`, `g` or `end`) and `"v": 1`; EOF ends the run. These are gate_ledger.py's v1 rows (its module docstring and `validate`), and the key rule and its bytes are its `input_key`, so a row streamed here and a row `backfill` derives from the same receipt carry the same key:
 *
 *   {"t":"run","v":1,"id","src":"prepush|quick","at","branch","head","tree","salt","clean","whole","base_tree","changed":[...],"changed_n","lock_sha","classes":[...],"narrowed_by":[...],"ci":null}
 *   {"t":"g","v":1,"run","gate","outcome":"pass|fail|timeout|skip|cancel|blocked","wall_ms","t0_ms","key","key_kind":"input|paths|tree|tree+dirty","findings":[...]|null,"attr":"own"}
 *   {"t":"end","v":1,"run","wall_ms","exit","cut"}
 *
 * The directory is passed to the child as REDIACC_GATE_LEDGER_DIR, always, so the writer and this module never disagree about where rows land.
 *
 * DEGRADES, LOUDLY, TO "THIS RUN IS NOT RECORDED", the lease client's pattern (lease-client.ts): no module, a child that will not spawn, dies mid-run or exits non-zero each print ONE warning naming the reason, and the run continues with its verdict untouched. Ledger I/O never changes an exit code. Off when `CI=true` unless REDIACC_GATE_LEDGER_DIR is set, so a CI job writes rows only where a fold step asked it to.
 *
 * NAMES NO GATE: every row is built from the result in hand. The runner's selftest (T9) reads this file and fails on any id the lock declares.
 */
import { type ChildProcessWithoutNullStreams, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

/** Where an explicit ledger lives; also what the child is told. */
const DIR_ENV = 'REDIACC_GATE_LEDGER_DIR';

/** gate_ledger.py CHANGED_PATHS_MAX: a change wider than this is a sweep, and its classes, not its full path list, are what associations learn from; `changed_n` keeps the true count. */
const CHANGED_CAP = 400;

/** How long close() waits for the child to drain and exit: a locked append of a few hundred rows is milliseconds, and a run must not hang on its ledger. */
const CLOSE_WAIT_MS = 5000;

/** gate_ledger.py `origin_slug`, byte for byte, so the runner reads model.json from the directory `gate_model refresh` writes: `<owner>-<repo>` of origin (a trailing `/` and `.git` dropped, split on `/` and `:`, the last two parts), anything outside `[A-Za-z0-9_.-]` as `_`; no origin, `local-<sha256(resolved root)[:12]>`. */
export function originSlug(url: string | undefined, root: string): string {
  const raw = (url ?? '').trim();
  if (raw === '')
    return `local-${createHash('sha256').update(path.resolve(root), 'utf8').digest('hex').slice(0, 12)}`;
  const tail = raw.replace(/\/+$/, '').replace(/\.git$/, '');
  const parts = tail.split(/[/:]/).filter((x) => x !== '');
  const slug = parts.length >= 2 ? parts.slice(-2).join('-') : (parts[parts.length - 1] ?? '');
  return slug.replace(/[^A-Za-z0-9_.-]/g, '_');
}

/** `$REDIACC_GATE_LEDGER_DIR`, else `${XDG_STATE_HOME:-~/.local/state}/rediacc-gate-ledger/<origin-slug>/`. Per machine, shared by every worktree and the push clone. */
export function ledgerDir(
  env: NodeJS.ProcessEnv,
  originUrl: string | undefined,
  root: string
): string {
  const explicit = env[DIR_ENV];
  if (explicit !== undefined && explicit !== '') return explicit;
  const state =
    env.XDG_STATE_HOME !== undefined && env.XDG_STATE_HOME !== ''
      ? env.XDG_STATE_HOME
      : path.join(os.homedir(), '.local', 'state');
  return path.join(state, 'rediacc-gate-ledger', originSlug(originUrl, root));
}

/** Whether this run writes the ledger. A synthetic manifest (the runner's own selftests) writes only to an explicit directory, never the real one. */
export function ledgerWanted(
  env: NodeJS.ProcessEnv,
  synthetic: boolean
): { on: true } | { on: false; why: string } {
  const explicit = (env[DIR_ENV] ?? '') !== '';
  if (explicit) return { on: true };
  if (env.CI === 'true') return { on: false, why: `CI=true and ${DIR_ENV} is unset` };
  if (synthetic) return { on: false, why: `a synthetic manifest and ${DIR_ENV} is unset` };
  return { on: true };
}

/** One ledger row, as written on the wire. */
type Row = Record<string, unknown> & { t: 'run' | 'g' | 'end' };

export interface GateLedger {
  /** True while rows still reach the child. */
  readonly on: boolean;
  /** One line for the run header. */
  readonly note: string;
  write(row: Row): void;
  /** End stdin and wait (at most CLOSE_WAIT_MS) for the child to exit; warns once on a non-zero exit. Never throws. */
  close(): Promise<void>;
}

/** A ledger that records nothing, with the reason. */
function offLedger(note: string): GateLedger {
  return { on: false, note, write: () => {}, close: async () => {} };
}

interface OpenLedgerOptions {
  root: string;
  dir: string;
  env?: NodeJS.ProcessEnv;
  /** Override the child argv, for the selftest's fake writers. */
  command?: readonly string[];
  warn: (text: string) => void;
  closeWaitMs?: number;
}

/** Open the ledger writer. Never throws: every way the child can be missing or wrong ends in a ledger that records nothing, with ONE warning. */
export function openLedger(opts: OpenLedgerOptions): GateLedger {
  const env = opts.env ?? process.env;
  const module = path.join(opts.root, '.ci', 'rediacc_ci', 'ci', 'gate_ledger.py');
  if (opts.command === undefined && !fs.existsSync(module)) {
    const note = `gate ledger: NONE, ${path.relative(opts.root, module)} is absent; this run is not recorded`;
    opts.warn(`ci-runner: WARNING: ${note}\n`);
    return offLedger(note);
  }
  const argv = opts.command ?? ['python3', '-m', 'rediacc_ci.ci.gate_ledger', 'append'];
  let child: ChildProcessWithoutNullStreams;
  try {
    child = spawn(argv[0], argv.slice(1), {
      cwd: opts.root,
      env: {
        ...env,
        [DIR_ENV]: opts.dir,
        PYTHONPATH: [path.join(opts.root, '.ci'), env.PYTHONPATH]
          .filter(Boolean)
          .join(path.delimiter),
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    const note = `gate ledger: NONE, the writer did not spawn (${(e as Error).message})`;
    opts.warn(`ci-runner: WARNING: ${note}\n`);
    return offLedger(note);
  }
  let dead: string | undefined;
  let closing = false;
  let warned = false;
  let stderrTail = '';
  let exited: { code: number | null; signal: string | null } | undefined;
  const exitWaiters: (() => void)[] = [];
  const warnOnce = (why: string): void => {
    if (warned) return;
    warned = true;
    const tail = stderrTail.trim().split('\n').slice(-3).join(' | ');
    opts.warn(
      `ci-runner: WARNING: the gate ledger writer ${why}${tail === '' ? '' : ` (stderr: ${tail})`}; the rest of this run is not recorded, and its verdict is unchanged\n`
    );
  };
  child.stdout.resume();
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (c: string) => {
    stderrTail = (stderrTail + c).slice(-2000);
  });
  child.on('error', (e) => {
    dead ??= `could not start: ${e.message}`;
    warnOnce(dead);
  });
  child.stdin.on('error', (e) => {
    dead ??= `stopped reading: ${e.message}`;
    warnOnce(dead);
  });
  child.on('close', (code, signal) => {
    exited = { code, signal };
    if (!closing || code !== 0) {
      dead ??= `exited ${signal ?? `code ${code}`}${closing ? ' at close' : ' mid-run'}`;
      warnOnce(dead);
    }
    for (const w of exitWaiters.splice(0)) w();
  });
  return {
    get on(): boolean {
      return dead === undefined && !closing;
    },
    note: `gate ledger: ${opts.dir}`,
    write(row: Row): void {
      if (dead !== undefined || closing) return;
      try {
        child.stdin.write(`${JSON.stringify({ ...row, v: 1 })}\n`);
      } catch (e) {
        dead ??= `stopped reading: ${(e as Error).message}`;
        warnOnce(dead);
      }
    },
    async close(): Promise<void> {
      if (closing) return;
      closing = true;
      try {
        child.stdin.end();
      } catch {
        /* already closed: the close handler has warned */
      }
      if (exited !== undefined) return;
      await new Promise<void>((resolve) => {
        const t = setTimeout(() => {
          warnOnce(`did not exit within ${opts.closeWaitMs ?? CLOSE_WAIT_MS} ms of end of input`);
          child.kill('SIGKILL');
          resolve();
        }, opts.closeWaitMs ?? CLOSE_WAIT_MS);
        exitWaiters.push(() => {
          clearTimeout(t);
          resolve();
        });
      });
    },
  };
}

// ---------------------------------------------------------------- rows

/** The ledger's outcome for one settled gate. A skip whose reason names a failed prerequisite is `skip`; any other skip (fail-fast, a stage stop) is `cancel`. */
export function outcomeOf(r: {
  status: string;
  timedOutMs?: number;
  reason?: string;
}): 'pass' | 'fail' | 'timeout' | 'skip' | 'cancel' | 'blocked' {
  if (r.status === 'ok') return 'pass';
  if (r.status === 'blocked') return 'blocked';
  if (r.status === 'skipped') return (r.reason ?? '').startsWith('needs ') ? 'skip' : 'cancel';
  return r.timedOutMs !== undefined ? 'timeout' : 'fail';
}

/** What the input key is built from for one gate (input-hash.ts GateHash, reduced). */
export interface KeyParts {
  inputHash: string | null;
  defHash: string;
  filesHash: string;
  /** The gate declares `paths`. */
  hasPaths: boolean;
}

/** gate_ledger.py `sha(*parts)`: sha256 of the parts joined by newlines. */
const sha = (...parts: string[]): string =>
  createHash('sha256').update(parts.join('\n'), 'utf8').digest('hex');

/** sha256 of no bytes: gate_ledger.py `clean_digest` reads a dirty digest that is a prefix of it as a clean checkout. */
const EMPTY_SHA = sha();

/**
 * THE INPUT KEY, gate_ledger.py `input_key` exactly: the gate's inputHash when non-null (`input`); else sha("paths", defHash, filesHash, salt) for a gate with declared paths (`paths`); else the head tree in a clean checkout (`tree`), or sha("tree+dirty", tree, dirty) outside one (`tree+dirty`). A path-less gate's inputs are the whole tree: on 2026-10-08 the workspace-versions gate went green, red, green under one filesHash because its fix was in package.json.
 */
export function inputKey(input: {
  parts: KeyParts | undefined;
  tree: string;
  dirty: string;
  salt: string;
}): { key: string; kind: 'input' | 'paths' | 'tree' | 'tree+dirty' } {
  const p = input.parts;
  if (p?.inputHash !== null && p?.inputHash !== undefined && p.inputHash !== '')
    return { key: p.inputHash, kind: 'input' };
  if (p?.hasPaths === true && p.defHash !== '' && p.filesHash !== '')
    return { key: sha('paths', p.defHash, p.filesHash, input.salt), kind: 'paths' };
  if (input.dirty !== '' && EMPTY_SHA.startsWith(input.dirty))
    return { key: input.tree, kind: 'tree' };
  return { key: sha('tree+dirty', input.tree, input.dirty), kind: 'tree+dirty' };
}

/** The `changed` field capped at gate_ledger.py's CHANGED_PATHS_MAX, and `changed_n`, the true count. */
export function cappedChanged(files: readonly string[]): { changed: string[]; changed_n: number } {
  return { changed: files.slice(0, CHANGED_CAP), changed_n: files.length };
}

// ---------------------------------------------------------------- selftest

/**
 * The writer's controls against fake children written to a temp dir: rows arrive in order with `v: 1`, a child that dies mid-run warns once and the writes after it are dropped, a missing module warns by name, a non-zero exit at close warns; and the pure halves (slug, directory, CI switch, outcome, key).
 */
export async function ledgerSelftest(
  tmpRoot: string
): Promise<{ failures: string[]; assertions: number }> {
  const failures: string[] = [];
  let assertions = 0;
  const check = (ok: boolean, message: string): void => {
    assertions += 1;
    if (!ok) failures.push(message);
  };
  check(
    originSlug('git@github.com:Org/Repo.git', '/r') === 'Org-Repo',
    `ssh origin slug, got ${originSlug('git@github.com:Org/Repo.git', '/r')}`
  );
  check(
    originSlug('https://github.com/Org/Repo/', '/r') === 'Org-Repo',
    'an https origin must slug the same as ssh'
  );
  check(
    /^local-[0-9a-f]{12}$/.test(originSlug(undefined, '/r')) &&
      originSlug(undefined, '/r') !== originSlug(undefined, '/s'),
    'no origin slugs as local-<12 hex> of the checkout, so two origin-less checkouts never share a ledger'
  );
  check(
    ledgerDir({ XDG_STATE_HOME: '/s' }, 'git@h:o/r.git', '/r') === '/s/rediacc-gate-ledger/o-r',
    `XDG_STATE_HOME must root the default directory, got ${ledgerDir({ XDG_STATE_HOME: '/s' }, 'git@h:o/r.git', '/r')}`
  );
  check(
    ledgerDir({ [DIR_ENV]: '/x', XDG_STATE_HOME: '/s' }, 'o', '/r') === '/x',
    'an explicit directory wins'
  );
  check(!ledgerWanted({ CI: 'true' }, false).on, 'CI=true turns the ledger off');
  check(
    ledgerWanted({ CI: 'true', [DIR_ENV]: '/x' }, false).on,
    'CONTROL: CI=true with an explicit directory writes'
  );
  check(!ledgerWanted({}, true).on, 'a synthetic manifest never writes the real ledger');
  check(ledgerWanted({}, false).on, 'CONTROL: a real local run writes');
  check(outcomeOf({ status: 'skipped', reason: 'needs build' }) === 'skip', 'a needs-skip is skip');
  check(
    outcomeOf({ status: 'skipped', reason: 'not run (--fail-fast)' }) === 'cancel',
    'a fail-fast skip is cancel'
  );
  check(
    outcomeOf({ status: 'fail', timedOutMs: 1 }) === 'timeout',
    'a killed-at-limit fail is timeout'
  );
  const parts = { inputHash: null, defHash: 'd', filesHash: 'f', hasPaths: true };
  const cleanDigest = EMPTY_SHA.slice(0, 16);
  // The bytes, pinned to gate_ledger.py: sha("paths", "d", "f", "s") there is sha256 of "paths\nd\nf\ns".
  check(
    inputKey({ parts, tree: 'T', dirty: 'abc', salt: 's' }).key ===
      createHash('sha256').update('paths\nd\nf\ns').digest('hex'),
    'a path-declaring gate without inputHash keys on sha("paths", def, files, salt), dirty or not'
  );
  check(
    inputKey({ parts: { ...parts, hasPaths: false }, tree: 'T', dirty: cleanDigest, salt: 's' })
      .key === 'T',
    'a path-less gate in a clean checkout keys on the head tree'
  );
  check(
    inputKey({ parts: { ...parts, hasPaths: false }, tree: 'T', dirty: 'abc', salt: 's' }).kind ===
      'tree+dirty',
    'CONTROL: the same gate outside a clean checkout keys on tree+dirty'
  );
  check(
    inputKey({ parts: { ...parts, inputHash: 'H' }, tree: 'T', dirty: 'abc', salt: 's' }).key ===
      'H',
    'a non-null inputHash is the key'
  );
  const wide = cappedChanged(Array.from({ length: CHANGED_CAP + 1 }, (_, i) => `f${i}`));
  check(
    wide.changed.length === CHANGED_CAP && wide.changed_n === CHANGED_CAP + 1,
    'changed paths are capped and changed_n keeps the true count'
  );

  // tree-write: safe the only caller passes os.tmpdir(), so the fake writers and their output live outside the repository
  const dir = fs.mkdtempSync(path.join(tmpRoot, 'ci-runner-ledger-'));
  try {
    const out = path.join(dir, 'rows.jsonl');
    const good = path.join(dir, 'good.py');
    fs.writeFileSync(
      good,
      `import os, sys\nwith open(${JSON.stringify(out)}, "a") as f:\n    f.write("dir=" + os.environ.get("${DIR_ENV}", "") + "\\n")\n    for line in sys.stdin:\n        f.write(line)\n`
    );
    const warned: string[] = [];
    const ok = openLedger({
      root: dir,
      dir: '/ledger/here',
      command: ['python3', good],
      warn: (t) => warned.push(t),
    });
    ok.write({ t: 'run', id: 'r1' });
    ok.write({ t: 'g', run: 'r1', gate: 'fx:a', outcome: 'pass' });
    ok.write({ t: 'end', run: 'r1', exit: 0 });
    await ok.close();
    const lines = fs.existsSync(out) ? fs.readFileSync(out, 'utf8').trim().split('\n') : [];
    check(lines[0] === 'dir=/ledger/here', `the child must be told the directory, got ${lines[0]}`);
    const rows = lines.slice(1).map((l) => JSON.parse(l) as { t: string; v: number });
    check(
      rows.map((r) => r.t).join() === 'run,g,end' && rows.every((r) => r.v === 1),
      `rows must arrive in order with v 1, got ${lines.slice(1).join(' | ')}`
    );
    check(warned.length === 0, `a healthy writer must not warn, got ${warned.join('')}`);

    const dying = path.join(dir, 'dying.py');
    fs.writeFileSync(
      dying,
      'import sys\nsys.stdin.readline()\nsys.stderr.write("boom\\n")\nsys.exit(3)\n'
    );
    const dyingWarn: string[] = [];
    const d = openLedger({
      root: dir,
      dir,
      command: ['python3', dying],
      warn: (t) => dyingWarn.push(t),
    });
    d.write({ t: 'run', id: 'r2' });
    await new Promise((r) => setTimeout(r, 1500));
    for (let i = 0; i < 50; i += 1) d.write({ t: 'g', run: 'r2', gate: `fx:${i}` });
    await d.close();
    check(
      dyingWarn.length === 1 && /mid-run/.test(dyingWarn[0]) && /boom/.test(dyingWarn[0]) && !d.on,
      `a writer that dies mid-run must warn ONCE, naming it and its stderr, and stop taking rows; got ${JSON.stringify(dyingWarn)}`
    );

    const absentWarn: string[] = [];
    const absent = openLedger({ root: dir, dir, warn: (t) => absentWarn.push(t) });
    check(
      !absent.on && absentWarn.length === 1 && /gate_ledger\.py is absent/.test(absentWarn[0]),
      `a missing gate_ledger.py must warn once by name, got ${JSON.stringify(absentWarn)}`
    );

    const sour = path.join(dir, 'sour.py');
    fs.writeFileSync(sour, 'import sys\nsys.stdin.read()\nsys.exit(2)\n');
    const sourWarn: string[] = [];
    const s = openLedger({
      root: dir,
      dir,
      command: ['python3', sour],
      warn: (t) => sourWarn.push(t),
    });
    s.write({ t: 'run', id: 'r3' });
    await s.close();
    check(
      sourWarn.length === 1 && /code 2 at close/.test(sourWarn[0]),
      `a writer that exits non-zero at close must warn once, got ${JSON.stringify(sourWarn)}`
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  return { failures, assertions };
}
