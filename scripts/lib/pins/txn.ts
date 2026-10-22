/**
 * The write half of `npm run pins`: one transaction per run, planned in full before the first
 * byte is written (agent/plans/PLAN-pins-command.md Design 3).
 *
 * THE ORDER, and each step is a refusal point that leaves the tree as it was:
 *   1. every file the plans write, or their steps declare, is checked against git: one that
 *      already holds changes this run did not make is another session's work, and the whole
 *      run is refused by naming it;
 *   2. the journal (.ci/cache/pins/<stamp>/journal.json) records each such file's bytes
 *      BEFORE anything is written;
 *   3. the planned contents are written, then each step (driver commands, the registry's
 *      derive steps) runs; a step that changes a file it did not declare fails the run, and
 *      the file is named and left as it is, since nothing proves the step wrote it rather
 *      than a peer session working in the same tree;
 *   4. every package-lock.json the run changed gets the canonical pass under the pinned npm
 *      (`npx -y npm@<NPM_VERSION> install --package-lock-only --ignore-scripts`), and a
 *      changed root lockfile is followed by `npm ci` and `npm run install:natives`;
 *   5. the gates the entries name run as `npm run ci -- --only <ids>`;
 *   6. on any failure, COMPARE-AND-RESTORE: a journaled file whose bytes are still the ones
 *      this run last wrote gets its before-bytes back (or is deleted, when it did not exist);
 *      a file that changed since then is someone else's edit and is left alone, by name.
 *
 * The journal is written before every phase and before every step, so a run killed half-way
 * leaves a record `pins verify` reads and `pins verify --restore <stamp>` replays with the same
 * comparison. A step's declared files are marked in flight before its command starts: a run
 * killed inside the step cannot know which bytes the step wrote, so whatever such a file holds
 * is counted as this run's write, exactly as a step that returns has its declared files
 * counted. Only an unfinished run ('writing') replays; a finished, refused or already
 * restored run is refused by state, since its files may since hold the same bytes again on
 * purpose.
 * The tool never commits: a finished run writes one message draft per repo, submodules
 * first, and prints the exact add and commit lines.
 */
import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { type Fixture, keyOf, type Mutant, type PinPlan, type PlanStep } from './driver.js';
import type { RepoPath } from './registry.js';

// ---- running commands -----------------------------------------------------------------------

export interface CommandRecord {
  cmd: string;
  cwd: string;
  rc: number;
}

/** Runs a shell command line; the fixture stub answers from the fixture instead. */
export type Runner = (cmd: string, cwdAbs: string) => { rc: number; out: string };

export const realRunner: Runner = (cmd, cwdAbs) => {
  const r = spawnSync('bash', ['-c', cmd], {
    cwd: cwdAbs,
    encoding: 'utf8',
    maxBuffer: 256 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  return { rc: r.status ?? 1, out: `${r.stdout ?? ''}${r.stderr ?? ''}` };
};

/** The selftest's runner: the first fixture command whose regex matches answers, writing its files. */
export function fixtureRunner(root: string, fixture: Fixture): Runner {
  return (cmd) => {
    const hit = fixture.commands.find((c) => new RegExp(c.match).test(cmd));
    if (!hit) return { rc: 127, out: `fixture: no command matches ${JSON.stringify(cmd)}` };
    for (const [rel, text] of Object.entries(hit.writes ?? {})) {
      const abs = path.join(root, rel);
      fs.mkdirSync(path.dirname(abs), { recursive: true });
      fs.writeFileSync(abs, text);
    }
    const events = /--events (\S+)/.exec(cmd)?.[1];
    if (events && hit.events) fs.writeFileSync(events, hit.events.map((l) => `${l}\n`).join(''));
    return { rc: hit.rc, out: hit.out ?? '' };
  };
}

// ---- git and bytes --------------------------------------------------------------------------

const sha = (b: Buffer | null): string =>
  b === null ? 'absent' : crypto.createHash('sha256').update(b).digest('hex');
const readBytes = (abs: string): Buffer | null =>
  fs.existsSync(abs) ? fs.readFileSync(abs) : null;
const absOf = (root: string, p: RepoPath): string => path.join(root, p.repo, p.file);

function git(repoAbs: string, args: string[]): { rc: number; out: string } {
  const r = spawnSync('git', ['-C', repoAbs, ...args], {
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  return { rc: r.status ?? 1, out: r.stdout ?? '' };
}

/** Porcelain paths with changes in one repo; null when git cannot answer (fail closed). */
function dirtyPaths(repoAbs: string, files: string[] = []): Set<string> | null {
  const r = git(repoAbs, [
    'status',
    '--porcelain=v1',
    '--untracked-files=all',
    '-z',
    '--',
    ...files,
  ]);
  if (r.rc !== 0) return null;
  const out = new Set<string>();
  const recs = r.out.split('\0');
  for (let i = 0; i < recs.length; i++) {
    const rec = recs[i];
    if (rec.length < 4) continue;
    out.add(rec.slice(3));
    if (rec[0] === 'R' || rec[0] === 'C') i++;
  }
  return out;
}

// ---- the journal ----------------------------------------------------------------------------

interface JournalFile extends RepoPath {
  /** base64 of the bytes before the run; null when the file did not exist. */
  before: string | null;
  /** sha256 of the bytes this run last wrote; null until it writes the file. */
  wrote: string | null;
  /** True while a step that declares this file runs; cleared when the step returns. */
  inflight?: boolean;
}

interface Journal {
  stamp: string;
  state: 'planned' | 'writing' | 'done' | 'restored' | 'refused';
  pins: string[];
  files: Record<string, JournalFile>;
  /** sha256 of files written after the transaction closed (the regenerated docs), by key; the ledger trusts them like a `wrote`. */
  late?: Record<string, string>;
}

export const journalRoot = (root: string): string => path.join(root, '.ci/cache/pins');

function saveJournal(dir: string, j: Journal): void {
  fs.writeFileSync(path.join(dir, 'journal.json'), `${JSON.stringify(j, null, 2)}\n`);
}

/**
 * The per-tree ledger, read from the journals every finished run already leaves: a file that
 * is dirty only because an earlier run of this tree wrote it is not a peer's change. The
 * ledger holds when some done journal recorded exactly these bytes (`wrote`, or a `late`
 * write) for the key, so any byte a peer adds afterwards changes the hash and the file is
 * refused again. `ledger-off` never holds (the refusal before 2026-10-22); `ledger-by-path`
 * holds for any key a journal names, whatever the bytes.
 */
export function ledgerHolds(
  root: string,
  key: string,
  currentSha: string,
  mutant: Mutant | null = null
): boolean {
  if (mutant === 'ledger-off') return false;
  let names: string[];
  try {
    names = fs.readdirSync(journalRoot(root));
  } catch {
    return false;
  }
  for (const n of names) {
    let j: Journal;
    try {
      j = JSON.parse(fs.readFileSync(path.join(journalRoot(root), n, 'journal.json'), 'utf8'));
    } catch {
      continue;
    }
    if (j.state !== 'done') continue;
    const wrote = j.files?.[key]?.wrote ?? null;
    const late = j.late?.[key] ?? null;
    if (mutant === 'ledger-by-path') {
      if (wrote !== null || late !== null) return true;
      continue;
    }
    if (wrote === currentSha || late === currentSha) return true;
  }
  return false;
}

/** Record files written after a done transaction (the regenerated docs), so a later run trusts their bytes. */
export function recordLateWrites(root: string, stamp: string, paths: RepoPath[]): void {
  const dir = path.join(journalRoot(root), stamp);
  let j: Journal;
  try {
    j = JSON.parse(fs.readFileSync(path.join(dir, 'journal.json'), 'utf8'));
  } catch {
    return;
  }
  if (j.state !== 'done') return;
  j.late = j.late ?? {};
  for (const p of paths) j.late[keyOf(p)] = sha(readBytes(absOf(root, p)));
  saveJournal(dir, j);
}

export interface RestoreOutcome {
  restored: string[];
  leftAlone: string[];
  /** Files a killed step had in flight that no longer hold their before-bytes: the run never recorded what it wrote, so they are named and kept unless the operator names them in `take`. */
  inflight: string[];
}

/**
 * Give every file this run wrote its before-bytes back, but only while it still holds the
 * bytes the run wrote. Anything else is a later edit and is named, not overwritten. A file
 * already holding its before-bytes (a replayed journal's earlier pass) is skipped silently.
 * A file a killed step had in flight is kept and named too unless `take` names it, since the
 * journal never recorded what that step wrote.
 */
export function compareAndRestore(
  root: string,
  j: Journal,
  mutant: Mutant | null,
  take: ReadonlySet<string> = new Set()
): RestoreOutcome {
  const out: RestoreOutcome = { restored: [], leftAlone: [], inflight: [] };
  if (mutant === 'no-restore') return out;
  for (const [k, f] of Object.entries(j.files)) {
    if (f.wrote === null && f.inflight !== true) continue;
    const abs = absOf(root, f);
    const now = sha(readBytes(abs));
    if (f.inflight === true) {
      if (now === (f.before === null ? 'absent' : sha(Buffer.from(f.before, 'base64')))) continue;
      // A killed step never recorded what it wrote, so a partial write and a later edit look the same: the file is named and kept unless the operator names it to take its before-bytes back.
      if (!take.has(k) && !take.has(f.file)) {
        out.inflight.push(k);
        continue;
      }
    } else {
      if (now === (f.before === null ? 'absent' : sha(Buffer.from(f.before, 'base64')))) continue;
      if (mutant !== 'blind-restore' && now !== f.wrote) {
        out.leftAlone.push(k);
        continue;
      }
    }
    if (f.before === null) fs.rmSync(abs, { force: true });
    else fs.writeFileSync(abs, Buffer.from(f.before, 'base64'));
    out.restored.push(k);
  }
  return out;
}

/** Unfinished journals (a run killed between writing and its verdict). */
export function openJournals(root: string): Array<{ stamp: string; files: string[] }> {
  const dir = journalRoot(root);
  if (!fs.existsSync(dir)) return [];
  const out: Array<{ stamp: string; files: string[] }> = [];
  // Only directories are stamps (a symlink to one counts, which Dirent.isDirectory() does not report): a lock file, its tombs or a stray .DS_Store is not a journal layout this code could misread.
  const stamps = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter(
      (e) =>
        !e.name.startsWith('.lock') &&
        (e.isDirectory() ||
          (e.isSymbolicLink() &&
            fs.statSync(path.join(dir, e.name), { throwIfNoEntry: false })?.isDirectory()))
    )
    .map((e) => e.name)
    .sort();
  let readable = 0;
  for (const stamp of stamps) {
    const f = path.join(dir, stamp, 'journal.json');
    if (!fs.existsSync(f)) continue;
    readable++;
    const j = JSON.parse(fs.readFileSync(f, 'utf8')) as Journal;
    if (j.state === 'writing') out.push({ stamp, files: Object.keys(j.files) });
  }
  if (stamps.length > 0 && readable === 0)
    throw new Error(
      `VACUOUS: ${dir} holds ${stamps.length} stamp entries and not one journal.json, so "no unfinished run" would be read off a layout this code no longer knows`
    );
  return out;
}

/** Why `restoreJournal` refused a stamp: unknown, or a run that is not unfinished. */
export class RestoreRefused extends Error {}

/**
 * `pins verify --restore <stamp>`: replay a killed run's compare-and-restore. Only a run left
 * in 'writing' replays: a 'done' run's files are a finished bump, and a 'restored' or
 * 'refused' one has nothing of its own left on disk, so replaying either would undo bytes a
 * later run or edit put there.
 */
export function restoreJournal(
  root: string,
  stamp: string,
  take: ReadonlySet<string> = new Set()
): RestoreOutcome {
  const dir = path.join(journalRoot(root), stamp);
  const file = path.join(dir, 'journal.json');
  if (path.basename(stamp) !== stamp || stamp === '.' || stamp === '..' || !fs.existsSync(file))
    throw new RestoreRefused(`no journal ${stamp} under ${journalRoot(root)}`);
  const holder = liveLockPid(root);
  if (holder !== null)
    throw new RestoreRefused(
      `a live run (pid ${holder}) holds ${path.join(journalRoot(root), '.lock')}; its in-flight step files are not a killed run's to restore`
    );
  const j = JSON.parse(fs.readFileSync(file, 'utf8')) as Journal;
  if (j.state !== 'writing')
    throw new RestoreRefused(
      `journal ${stamp} is '${j.state}', not a run killed mid-write; only 'writing' journals replay`
    );
  const out = compareAndRestore(root, j, null, take);
  // A journal with in-flight files still named stays 'writing', so the operator can replay it with those files taken once they are inspected.
  if (out.inflight.length === 0) {
    j.state = 'restored';
    saveJournal(dir, j);
  }
  return out;
}

// ---- the transaction ------------------------------------------------------------------------

export interface TxnOptions {
  root: string;
  stamp: string;
  runner: Runner;
  mutant: Mutant | null;
  /** The pinned npm version, from .devcontainer/toolchain.env NPM_VERSION. */
  npmVersion: string | null;
  /** Scanned submodule paths, whose gitlink entries are not changes of the console's own. */
  submodules: string[];
  /** Every registry entry's id and gates, so a red gate shared with pins this run did not move can name them. */
  registry?: ReadonlyArray<{ id: string; gates: readonly string[] }>;
  /** The `lockfiles` verb: a dirty package-lock.json is not foreign while its sibling package.json is clean (or ledger-known). */
  lockfilesVerb?: boolean;
}

export interface RepoChange {
  repo: string;
  paths: string[];
  added: string[];
}

export interface TxnResult {
  ok: boolean;
  stamp: string;
  dir: string;
  failure: string | null;
  commands: CommandRecord[];
  /** `failed` holds the gates the runner's event stream reported red; empty when it reported none. */
  gates: { ids: string[]; rc: number; failed: string[] } | null;
  /** The pins of the run whose registry entry names no gate, so no gate judged them; printed and drafted, never silent. */
  ungated: string[];
  restored: string[];
  leftAlone: string[];
  /** Project directories whose installed tree a failed run put back to the restored lockfile (`npm ci`). */
  resynced: string[];
  changes: RepoChange[];
}

type Verdict = 'red' | 'ok' | 'skip' | 'block';

/**
 * The verdict of each gate a `npm run ci -- --only <ids> --events <file>` run judged. RED comes only from the runner's own `{"ev":"gate-red","gate":...}` event rows (scripts/ci-runner/report.ts), never from text a gate printed; `ok`, `SKIP` and `BLOCK` come from the runner's per-gate verdict lines, which carry no event. Pure.
 */
export function gateVerdicts(
  out: string,
  eventsText: string,
  ids: readonly string[]
): Map<string, Verdict> {
  const v = new Map<string, Verdict>();
  for (const line of eventsText.split('\n')) {
    if (line.trim() === '') continue;
    let row: { ev?: unknown; gate?: unknown };
    try {
      row = JSON.parse(line) as { ev?: unknown; gate?: unknown };
    } catch {
      continue;
    }
    if (row.ev === 'gate-red' && typeof row.gate === 'string' && ids.includes(row.gate))
      v.set(row.gate, 'red');
  }
  const word = { ok: 'ok', SKIP: 'skip', BLOCK: 'block' } as const;
  // A gate with a FAIL line is never read as ok from a later line: its own stdout follows that line and may hold anything.
  const failedText = new Set<string>();
  for (const l of out.replace(/\x1b\[[0-9;]*m/g, '').split('\n')) {
    const m = /^\s*(ok|FAIL|SKIP|BLOCK)\s+(\S+)(?:\s|$)/.exec(l);
    if (!m || !ids.includes(m[2]) || v.has(m[2]) || failedText.has(m[2])) continue;
    if (m[1] === 'FAIL') failedText.add(m[2]);
    else v.set(m[2], word[m[1] as keyof typeof word]);
  }
  return v;
}

/** The FAILED line of a red gate run: the gates the runner reported red, never the whole selection, with the rest by verdict. The all-gates mutant names every gate, the line before 2026-10-15. Pure. */
export function gateFailure(
  rc: number,
  ids: readonly string[],
  v: ReadonlyMap<string, Verdict>,
  allGates = false
): string {
  if (allGates) return `gates failed (rc=${rc}): ${ids.join(', ')}`;
  const by = (s: Verdict): string[] => ids.filter((id) => v.get(id) === s);
  const rest = [
    by('ok').length > 0 ? `ok: ${by('ok').join(', ')}` : '',
    by('skip').length > 0 ? `skipped: ${by('skip').join(', ')}` : '',
    by('block').length > 0 ? `blocked: ${by('block').join(', ')}` : '',
    ids.some((id) => !v.has(id)) ? `no verdict: ${ids.filter((id) => !v.has(id)).join(', ')}` : '',
  ].filter((x) => x !== '');
  const tail = rest.length > 0 ? ` (${rest.join('; ')})` : '';
  if (by('red').length === 0)
    return `gates failed (rc=${rc}): no gate reported red; see commands.log${tail}`;
  return `gates failed (rc=${rc}): ${by('red').join(', ')}${tail}`;
}

/** The FAILED message's extra line: the registry pins this run did not move whose gates include a gate that went red, and the command shape that moves the behind ones with this run (an already-current pin named explicitly is refused, so the line does not name them all as arguments). Derived from the registry entries' gates, never from gate output. Empty when no red gate is shared. Pure. */
export function siblingHint(
  red: readonly string[],
  moved: readonly string[],
  registry: ReadonlyArray<{ id: string; gates: readonly string[] }>
): string {
  const others = registry.filter((e) => !moved.includes(e.id));
  const siblings = others.filter((e) => e.gates.some((g) => red.includes(g))).map((e) => e.id);
  if (siblings.length === 0) return '';
  const shared = red.filter((g) => others.some((e) => e.gates.includes(g)));
  return `${shared.join(', ')} also judge${shared.length === 1 ? 's' : ''} ${siblings.join(', ')}, which this run did not move; the gate's output names the ones that are behind, and they move with this run in one transaction: npm run pins -- bump ${moved.join(' ')} <each behind sibling> (with the run's --to, and --major --reason when a move is a major)`;
}

/** NPM_VERSION as .devcontainer/toolchain.env declares it right now; null when the file or the line is absent. */
function pinnedNpmNow(root: string): string | null {
  const f = path.join(root, '.devcontainer/toolchain.env');
  const m = fs.existsSync(f) ? /^NPM_VERSION=(\S+)$/m.exec(fs.readFileSync(f, 'utf8')) : null;
  return m ? m[1] : null;
}

const canonicalCmd = (v: string): string =>
  `npx -y npm@${v} install --package-lock-only --ignore-scripts`;

export function runTransaction(plans: PinPlan[], o: TxnOptions): TxnResult {
  const dir = path.join(journalRoot(o.root), o.stamp);
  fs.mkdirSync(dir, { recursive: true });
  const j: Journal = {
    stamp: o.stamp,
    state: 'planned',
    pins: plans.map((p) => p.entry.id),
    files: {},
  };
  const res: TxnResult = {
    ok: false,
    stamp: o.stamp,
    dir,
    failure: null,
    commands: [],
    gates: null,
    ungated: [],
    restored: [],
    leftAlone: [],
    resynced: [],
    changes: [],
  };
  const steps: PlanStep[] = plans.flatMap((p) => [
    ...p.steps,
    ...p.entry.derive.map((d) => ({
      label: `derive: ${d.run}`,
      run: d.run,
      cwd: d.cwd,
      writes: d.writes,
    })),
  ]);
  const touched = new Map<string, RepoPath>();
  for (const w of plans.flatMap((p) => p.writes))
    touched.set(keyOf(w), { repo: w.repo, file: w.file });
  for (const w of steps.flatMap((s) => s.writes))
    touched.set(keyOf(w), { repo: w.repo, file: w.file });

  // 1. The dirty-site refusal: before any write, by name.
  if (o.mutant !== 'no-dirty-check') {
    const byRepo = new Map<string, string[]>();
    for (const p of touched.values()) byRepo.set(p.repo, [...(byRepo.get(p.repo) ?? []), p.file]);
    const foreign: string[] = [];
    for (const [repo, files] of byRepo) {
      const dirty = dirtyPaths(path.join(o.root, repo), files);
      if (dirty === null) {
        res.failure = `git status failed in ${repo}; refusing rather than guessing which files are clean`;
        j.state = 'refused';
        saveJournal(dir, j);
        return res;
      }
      for (const f of files) {
        if (!dirty.has(f)) continue;
        const p = { repo, file: f };
        const trusted = (q: RepoPath): boolean =>
          ledgerHolds(o.root, keyOf(q), sha(readBytes(absOf(o.root, q))), o.mutant);
        if (trusted(p)) continue;
        if (o.lockfilesVerb && path.posix.basename(f) === 'package-lock.json') {
          const manifest = { repo, file: path.posix.join(path.posix.dirname(f), 'package.json') };
          const md = dirtyPaths(path.join(o.root, repo), [manifest.file]);
          if (md !== null && (!md.has(manifest.file) || trusted(manifest))) continue;
        }
        foreign.push(repo === '.' ? f : `${repo}/${f}`);
      }
    }
    if (foreign.length > 0) {
      res.failure = `refused: ${foreign.join(', ')} already hold(s) changes this run did not make (another session's work); commit or move them first`;
      j.state = 'refused';
      saveJournal(dir, j);
      return res;
    }
  }

  // 2. The journal, before anything is written.
  const journal = (p: RepoPath, before: Buffer | null): void => {
    const k = keyOf(p);
    if (!j.files[k])
      j.files[k] = {
        repo: p.repo,
        file: p.file,
        before: before === null ? null : before.toString('base64'),
        wrote: null,
      };
  };
  for (const p of touched.values()) journal(p, readBytes(absOf(o.root, p)));
  const markWrote = (k: string): void => {
    const f = j.files[k];
    const now = sha(readBytes(absOf(o.root, f)));
    const before = f.before === null ? 'absent' : sha(Buffer.from(f.before, 'base64'));
    if (now !== before || f.wrote !== null) f.wrote = now;
    delete f.inflight;
  };
  j.state = 'writing';
  saveJournal(dir, j);

  const runOut = (cmd: string, cwdRel: string): { rc: number; out: string } => {
    const r = o.runner(cmd, path.join(o.root, cwdRel));
    res.commands.push({ cmd, cwd: cwdRel, rc: r.rc });
    fs.appendFileSync(
      path.join(dir, 'commands.log'),
      `$ (cd ${cwdRel} && ${cmd})  # rc=${r.rc}\n${r.out}\n`
    );
    return r;
  };
  const run = (cmd: string, cwdRel: string): number => runOut(cmd, cwdRel).rc;

  // A file a step changed without declaring it is named and never restored: nothing proves the step wrote it rather than a peer session working in the same tree at that moment.
  const undeclared: string[] = [];
  try {
    // 3. Writes, then steps.
    for (const w of plans.flatMap((p) => p.writes)) {
      const abs = absOf(o.root, w);
      fs.mkdirSync(path.dirname(abs), { recursive: true });
      fs.writeFileSync(abs, w.after);
      markWrote(keyOf(w));
    }
    saveJournal(dir, j);
    const repos = [...new Set(['.', ...[...touched.values()].map((p) => p.repo)])];
    // A step is judged by the BYTES it changed, not by which files are dirty: a file an earlier write or step already made dirty is dirty before and after, and only its hash shows that this step rewrote it. A change is declared only by this step's own writes, never by the journal, which also holds every other plan's files. A deleted file hashes as 'absent', so a step that removes a dirty file is judged the same way.
    const dirtyHashes = (r: string): Map<string, string> => {
      const out = new Map<string, string>();
      for (const f of dirtyPaths(path.join(o.root, r)) ?? new Set<string>()) {
        if (f.endsWith('/') || (r === '.' && o.submodules.includes(f))) continue;
        out.set(f, sha(readBytes(path.join(o.root, r, f))));
      }
      return out;
    };
    for (const s of steps) {
      const pre = new Map(repos.map((r) => [r, dirtyHashes(r)]));
      for (const w of s.writes) j.files[keyOf(w)].inflight = true;
      saveJournal(dir, j);
      const rc = run(s.run, s.cwd);
      const declared = new Set(s.writes.map((w) => keyOf(w)));
      for (const w of s.writes) markWrote(keyOf(w));
      const before = undeclared.length;
      for (const r of repos) {
        const was = pre.get(r) ?? new Map<string, string>();
        const now = dirtyHashes(r);
        for (const f of new Set([...was.keys(), ...now.keys()])) {
          const after = now.get(f) ?? sha(readBytes(path.join(o.root, r, f)));
          if (was.get(f) === after) continue;
          const k = keyOf({ repo: r, file: f });
          if (!declared.has(k) && !undeclared.includes(k)) undeclared.push(k);
        }
      }
      saveJournal(dir, j);
      if (rc !== 0) throw new Error(`step failed (rc=${rc}): ${s.label}`);
      if (undeclared.length > before)
        throw new Error(
          `step changed file(s) it did not declare: ${undeclared.slice(before).join(', ')} (${s.label}); declare them in its writes`
        );
    }

    // 4. The canonical lockfile pass, under the pinned npm only.
    const changedLocks = Object.entries(j.files)
      .filter(([, f]) => path.basename(f.file) === 'package-lock.json' && f.wrote !== null)
      .map(([k, f]) => ({ k, f }));
    if (changedLocks.length > 0 && o.mutant !== 'no-canonical') {
      // The pinned npm AFTER the writes: a run that moves NPM_VERSION itself (toolchain:npm) must canonicalise under the new npm, since the lockfiles its steps wrote were produced by it and check:ci-lockfile compares against the pin the tree now declares.
      const npmVersion = pinnedNpmNow(o.root) ?? o.npmVersion;
      if (!npmVersion)
        throw new Error(
          'NPM_VERSION is missing from .devcontainer/toolchain.env; refusing to run an ambient npm'
        );
      for (const { k, f } of changedLocks) {
        f.inflight = true;
        saveJournal(dir, j);
        const rc = run(canonicalCmd(npmVersion), path.join(f.repo, path.dirname(f.file)));
        markWrote(k);
        if (rc !== 0) throw new Error(`the canonical lockfile pass failed for ${k} (rc=${rc})`);
      }
      if (changedLocks.some(({ f }) => f.repo === '.' && f.file === 'package-lock.json')) {
        if (run(`npx -y npm@${npmVersion} ci`, '.') !== 0)
          throw new Error('npm ci failed after the root lockfile changed');
        if (run(`npx -y npm@${npmVersion} run install:natives`, '.') !== 0)
          throw new Error('npm run install:natives failed after npm ci');
      }
      saveJournal(dir, j);
    }

    // 5. The gates.
    const ids = [...new Set(plans.flatMap((p) => p.entry.gates))];
    // A pin whose entry names no gate is judged by none. On 2026-10-15 `bump --all` moved gemini-cli, agent-browser and wrangler with `gates: []` and printed no gate line and wrote no commands.log, so nothing said that no gate had run; the journal and the output now name them.
    if (o.mutant !== 'silent-ungated') {
      res.ungated = plans.filter((p) => p.entry.gates.length === 0).map((p) => p.entry.id);
      if (res.ungated.length > 0)
        fs.appendFileSync(
          path.join(dir, 'commands.log'),
          `# no gate ran for ${res.ungated.join(', ')}: the registry entry names none (.ci/config/pins.json gates)\n`
        );
    }
    if (ids.length > 0) {
      // The runner's event stream names each red gate; its text output interleaves every gate's own stdout.
      const events = path.join(dir, 'gates.jsonl');
      fs.rmSync(events, { force: true });
      const g = runOut(
        `npm run ci -- --only ${ids.join(',')} --events ${/^[\w@%+=:,./-]+$/.test(events) ? events : `'${events.replace(/'/g, `'\\''`)}'`}`,
        '.'
      );
      const v = gateVerdicts(
        g.out,
        fs.existsSync(events) ? fs.readFileSync(events, 'utf8') : '',
        ids
      );
      res.gates = { ids, rc: g.rc, failed: ids.filter((id) => v.get(id) === 'red') };
      if (g.rc !== 0) {
        const hint = siblingHint(
          res.gates.failed,
          plans.map((p) => p.entry.id),
          o.registry ?? []
        );
        throw new Error(
          `${gateFailure(g.rc, ids, v, o.mutant === 'all-gates')}${hint === '' ? '' : `\n${hint}`}`
        );
      }
    }
  } catch (err) {
    res.failure = (err as Error).message;
    const r = compareAndRestore(o.root, j, o.mutant);
    res.restored = r.restored;
    res.leftAlone = [...new Set([...r.leftAlone, ...undeclared])];
    j.state = 'restored';
    saveJournal(dir, j);
    // 6. THE INSTALLED TREE FOLLOWS THE RESTORED LOCKFILE. The restore puts back package.json and package-lock.json only, while the steps had already moved node_modules; on 2026-10-15 the next plan read the moved versions back from it (`npm outdated` judges what is installed), planned oxc-parser alone, and that run's own `npm ci` reinstalled the two minors it had left out, so check:deps went red on them.
    if (o.mutant !== 'no-resync') {
      const npmVersion = pinnedNpmNow(o.root) ?? o.npmVersion;
      const dirs = [
        ...new Set(
          r.restored
            .filter((k) => path.basename(k) === 'package-lock.json')
            .map((k) => path.dirname(k))
        ),
      ].filter((d) => d === '.' || fs.existsSync(path.join(o.root, d, 'node_modules')));
      for (const d of dirs) {
        const rc = npmVersion === null ? 1 : run(`npx -y npm@${npmVersion} ci`, d);
        const natives =
          rc === 0 && d === '.' ? run(`npx -y npm@${npmVersion} run install:natives`, d) : 0;
        if (rc === 0 && natives === 0) res.resynced.push(d);
        else
          res.failure += `; the installed tree under ${d} still holds what this run installed (${npmVersion === null ? 'NPM_VERSION is missing from .devcontainer/toolchain.env' : `rc=${rc || natives}`}), so put it back before the next plan, which otherwise reads versions the lockfile no longer names: (cd ${d} && npx -y npm@<NPM_VERSION> ci${d === '.' ? ' && npm run install:natives' : ''})`;
      }
    }
    return res;
  }

  j.state = 'done';
  saveJournal(dir, j);
  const byRepo = new Map<string, RepoChange>();
  for (const f of Object.values(j.files)) {
    const before = f.before === null ? 'absent' : sha(Buffer.from(f.before, 'base64'));
    if (f.wrote === null || f.wrote === before) continue;
    const c = byRepo.get(f.repo) ?? { repo: f.repo, paths: [], added: [] };
    c.paths.push(f.file);
    if (f.before === null) c.added.push(f.file);
    byRepo.set(f.repo, c);
  }
  res.changes = [...byRepo.values()].sort((a, b) =>
    a.repo === '.' ? 1 : b.repo === '.' ? -1 : a.repo.localeCompare(b.repo)
  );
  res.ok = true;
  return res;
}

/** The start time of a running process in clock ticks since boot (/proc/<pid>/stat field 22), or null where /proc does not answer. */
function processStart(pid: number): string | null {
  try {
    const stat = fs.readFileSync(`/proc/${pid}/stat`, 'utf8');
    return stat.slice(stat.lastIndexOf(')') + 2).split(' ')[19] ?? null;
  } catch {
    return null;
  }
}

/** The pid a lock file's text names when that process is alive (a pid that exists but is not ours to signal counts as alive); null for debris or a dead pid. */
function livePid(text: string): number | null {
  const pid = /^\d+$/.test(text) ? Number(text) : 0;
  if (!Number.isSafeInteger(pid) || pid <= 0) return null;
  try {
    process.kill(pid, 0);
    return pid;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === 'EPERM' ? pid : null;
  }
}

/** An identity line, `<pid> <start ticks or -> <nonce>`, names a live holder when its pid is alive and, where both start times are known, that process is the one that wrote the line rather than a later one that reused the pid. No age enters the verdict: a slow live holder stays live however old its files are. */
function identityLive(line: string | null): number | null {
  const m = /^(\d+) (\d+|-) ([0-9a-f]+)$/.exec(line ?? '');
  if (!m) return null;
  const pid = livePid(m[1]);
  if (pid === null) return null;
  const now = m[2] === '-' ? null : processStart(pid);
  return now !== null && now !== m[2] ? null : pid;
}

/** The trimmed text of a file, or null when it does not exist. */
function readText(file: string): string | null {
  try {
    return fs.readFileSync(file, 'utf8').trim();
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === 'ENOENT') return null;
    throw e;
  }
}

/** The lock file holds only `<pid>\n`; `.lock.owner` beside it holds the holder's identity line. The pid decides; the owner line, when it names the same pid, adds the start-time check that catches a reused pid. */
function lockHolder(lockText: string | null, ownerText: string | null): number | null {
  const pid = livePid(lockText ?? '');
  if (pid === null) return null;
  const m = /^(\d+) /.exec(ownerText ?? '');
  return m && Number(m[1]) === pid ? identityLive(ownerText) : pid;
}

/** The live pid holding the one-run-at-a-time lock, or null when nobody does. */
export function liveLockPid(root: string): number | null {
  const lock = path.join(journalRoot(root), '.lock');
  try {
    return lockHolder(readText(lock), readText(`${lock}.owner`));
  } catch {
    return null;
  }
}

/** Test seams for the lock's race windows. */
export interface LockSeams {
  /** Runs between judging the lock file stale and moving it aside. */
  afterStaleVerdict?: () => void;
  /** Runs between moving the judged lock file aside and checking it is the one judged. */
  afterMove?: () => void;
  /** Runs between judging the claim's owner dead and moving the claim aside. */
  afterClaimVerdict?: () => void;
  /** Runs while this taker holds the claim, before it reads the lock slot. */
  whileClaimed?: () => void;
  /** How long a claim held by a live taker is waited on before giving up; 2000 ms by default. */
  claimWaitMs?: number;
  /** How long a live taker may hold the claim before a waiter refuses by name instead of reporting a held lock; 60000 ms by default. */
  claimCeilingMs?: number;
}

/** rename(2) refuses to replace a non-empty directory with ENOTEMPTY or EEXIST. */
const occupied = (e: unknown): boolean => {
  const code = (e as NodeJS.ErrnoException).code;
  return code === 'ENOTEMPTY' || code === 'EEXIST';
};

const pause = (ms: number): void => {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
};

/** A taker's private claim directory, `.lock.claim.<pid>.<16-hex nonce>`; it exists from the taker's start until its claim is installed, and again while the claim is dropped. */
const STAGE_NAME = /^\.lock\.claim\.(\d+)\.[0-9a-f]{16}$/;
/** A cleared claim, `.lock.claim.dead.<16 hex>`. */
const TOMB_NAME = /^\.lock\.claim\.dead\.[0-9a-f]{16}$/;

/**
 * Take the one-run-at-a-time lock; null when a live run holds it.
 *
 * ONE PRIMITIVE: rename(2) of a directory onto a non-empty directory fails. Every change to the lock slot happens under the claim `.lock.claim`, a directory that appears only by renaming a private directory that already holds its `owner` identity line, so a claim is never visible empty or half-written, two takers can never both install one, and none of it needs hard links. An empty `.lock.claim` is debris no taker could be holding and is replaced by that same rename.
 *
 * A claim whose owner is dead (pid gone, or the pid now belongs to a process with another start time) is cleared by renaming it to `.lock.claim.dead.<hash of its owner line>`. The owner line carries a random nonce, so that name is unique to the claim judged, and the tomb is kept while any other taker is in progress: a second taker that judged the same dead claim and moves late finds the tomb occupied, its rename fails, and the live claim installed since stays where it is. A plain remove, or a tomb name of its own, would let that late taker move the live claim away. A claim with no owner file, which no taker writes, is cleared the same way under a name derived from its inode, which stays unique while the tomb holds that inode.
 *
 * Tombs are swept by a claim holder that finds no other live taker's private claim directory: every taker keeps one from its start until it installs its claim, so a taker that judged a cleared claim and has not yet acted is always visible by it, and with none present no late move can reach a swept name. A tomb whose owner is alive is never swept.
 *
 * A claim held by a live owner is never taken from it, however old: the owner can resume at any time, and a stolen claim would let two takers fill the slot. A claim held longer than `claimCeilingMs` (a taker holds it for a directory listing and a few renames) is refused by name with the owner's pid, so a stopped or wedged owner is reported rather than read as a held lock.
 *
 * Under the claim, the lock file `.lock` (`<pid>\n`) and its owner line `.lock.owner` are written to private names and renamed into place, so the lock also appears whole; a stale lock is moved to `.lock.stale.<pid>.<fresh 16-hex nonce>` and checked to be the one judged, and anything else it turns out to be goes back into the slot when the slot is still empty, or stays named in its tomb.
 *
 * A claim moved aside by mistake (only when a judged claim left the slot without its tomb, as by a hand removal) goes back once the slot is free; if it cannot within the wait, the mover refuses by naming the tomb, and the claim's holder, finding its claim in a tomb at release, removes it and refuses, since another taker may have held the claim meanwhile.
 */
export function takeLock(root: string, seams: LockSeams = {}): (() => void) | null {
  const dir = journalRoot(root);
  fs.mkdirSync(dir, { recursive: true });
  const lock = path.join(dir, '.lock');
  const owner = `${lock}.owner`;
  const claim = `${lock}.claim`;
  const nonce = crypto.randomBytes(8).toString('hex');
  const self = `${process.pid} ${processStart(process.pid) ?? '-'} ${nonce}`;
  const stage = `${claim}.${process.pid}.${nonce}`;
  const tmp = `${lock}.${process.pid}.${nonce}`;
  const ownerTmp = `${owner}.${process.pid}.${nonce}`;
  const waitMs = seams.claimWaitMs ?? 2000;
  const ceilingMs = seams.claimCeilingMs ?? 60_000;

  /** Puts a claim moved aside by mistake back once the slot is free; a holder that already took it back leaves nothing to do. */
  const putBack = (tomb: string, text: string | null): void => {
    const deadline = Date.now() + waitMs;
    for (;;) {
      try {
        fs.renameSync(tomb, claim);
        return;
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code === 'ENOENT') return;
        if (!occupied(e)) throw e;
      }
      if (Date.now() >= deadline)
        throw new Error(
          `${tomb} holds a claim moved aside by mistake (owner ${text ?? 'none'}) and ${claim} has not been free to take it back; once ${claim} is gone, run: mv ${tomb} ${claim}`
        );
      pause(10);
    }
  };

  /** Moves the claim to `tomb` and keeps it there only when `judged` says the moved directory is the one judged; anything else goes back. */
  const clear = (tomb: string, judged: (moved: string) => boolean): void => {
    try {
      fs.renameSync(claim, tomb);
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === 'ENOENT' || occupied(e)) return;
      throw e;
    }
    // The tomb did not exist, so nobody had moved the judged claim yet and the slot still held it; the check below is the compare half of the swap.
    if (judged(tomb)) return;
    const movedText = readText(path.join(tomb, 'owner'));
    // A different claim whose owner is dead is as harmless in this tomb as the judged one would be: the sweep clears it, and no live taker is waiting on it.
    if (movedText !== null && identityLive(movedText) === null) return;
    putBack(tomb, movedText);
  };

  const inode = (p: string): string | null => {
    const st = fs.statSync(p, { throwIfNoEntry: false });
    return st ? `${st.dev} ${st.ino}` : null;
  };

  const takeClaim = (): boolean => {
    const deadline = Date.now() + waitMs;
    let ownerless = 0;
    for (let i = 0; i < 10_000; i++) {
      let installed = true;
      try {
        fs.renameSync(stage, claim);
      } catch (e) {
        if (!occupied(e)) throw e;
        installed = false;
      }
      if (installed) {
        // The owner line was written before any wait for the slot; its time is the install time from here on. A failure here comes after the install, so the claim is dropped before it propagates.
        try {
          const now = new Date();
          fs.utimesSync(path.join(claim, 'owner'), now, now);
        } catch (e) {
          dropClaim();
          throw e;
        }
        return true;
      }
      const ownerFile = path.join(claim, 'owner');
      const text = readText(ownerFile);
      if (text === null) {
        // Read between one claim's release and the next one's install; a claim that stays ownerless is debris no taker wrote.
        if (++ownerless <= 100) {
          pause(1);
          continue;
        }
        ownerless = 0;
        const ino = inode(claim);
        if (ino === null || readText(ownerFile) !== null) continue;
        clear(
          `${claim}.dead.${sha(Buffer.from(`inode ${ino}`)).slice(0, 16)}`,
          (moved) => readText(path.join(moved, 'owner')) === null && inode(moved) === ino
        );
        continue;
      }
      ownerless = 0;
      const pid = identityLive(text);
      if (pid !== null) {
        const mtime = fs.statSync(ownerFile, { throwIfNoEntry: false })?.mtimeMs;
        const heldMs = mtime === undefined ? 0 : Date.now() - mtime;
        if (heldMs > ceilingMs && readText(ownerFile) === text)
          throw new Error(
            `${claim} has been held for ${Math.round(heldMs / 1000)}s by live pid ${pid}, and a pins run holds it for milliseconds; it is never taken from a live holder. Resume or end that process (kill -CONT ${pid}, or kill ${pid}), then run again`
          );
        if (Date.now() >= deadline) return false;
        pause(10);
        continue;
      }
      seams.afterClaimVerdict?.();
      clear(
        `${claim}.dead.${sha(Buffer.from(text)).slice(0, 16)}`,
        (moved) => readText(path.join(moved, 'owner')) === text
      );
    }
    throw new Error(`${claim}: no verdict after 10000 attempts`);
  };

  const dropClaim = (): void => {
    if (readText(path.join(claim, 'owner')) !== self) {
      // Moved aside by a taker acting on a mistaken verdict: take it back out of its tomb, and refuse, since the slot was open to another taker meanwhile.
      for (const n of fs.readdirSync(dir)) {
        if (!TOMB_NAME.test(n) || readText(path.join(dir, n, 'owner')) !== self) continue;
        try {
          fs.renameSync(path.join(dir, n), stage);
        } catch (e) {
          if ((e as NodeJS.ErrnoException).code === 'ENOENT') return dropClaim();
          throw e;
        }
        fs.rmSync(stage, { recursive: true, force: true });
        throw new Error(
          `${claim} was moved to ${n} while this taker held it, so another taker may have held the claim too; this run's lock is released and nothing it read under the claim is trusted`
        );
      }
      throw new Error(`${claim} is not the claim this taker installed; it is left in place`);
    }
    // Renamed away whole before removal: removing the directory in place would leave it empty for a moment, and an empty claim is one any taker may replace.
    fs.renameSync(claim, stage);
    if (readText(path.join(stage, 'owner')) !== self) {
      fs.renameSync(stage, claim);
      throw new Error(`${claim} is not the claim this taker installed; it is left in place`);
    }
    fs.rmSync(stage, { recursive: true, force: true });
  };

  const release = (): void => {
    if (readText(lock) === String(process.pid)) fs.rmSync(lock, { force: true });
    if (readText(owner) === self) fs.rmSync(owner, { force: true });
  };

  const fillSlot = (): (() => void) | null => {
    for (let attempt = 0; attempt < 3; attempt++) {
      const text = readText(lock);
      if (text === null) {
        fs.writeFileSync(ownerTmp, `${self}\n`);
        fs.renameSync(ownerTmp, owner);
        fs.writeFileSync(tmp, `${process.pid}\n`);
        fs.renameSync(tmp, lock);
        return release;
      }
      if (lockHolder(text, readText(owner)) !== null) return null;
      seams.afterStaleVerdict?.();
      const tomb = `${lock}.stale.${process.pid}.${crypto.randomBytes(8).toString('hex')}`;
      try {
        fs.renameSync(lock, tomb);
      } catch (e) {
        if ((e as NodeJS.ErrnoException).code === 'ENOENT') continue;
        throw e;
      }
      seams.afterMove?.();
      if ((readText(tomb) ?? '') !== text) {
        // Not the lock judged: back into the slot while the slot is empty (only a claim holder fills it, and the claim is this taker's), otherwise kept in its tomb so it stays named.
        if (readText(lock) === null) fs.renameSync(tomb, lock);
        return null;
      }
      fs.rmSync(tomb, { force: true });
    }
    return null;
  };

  /** Under the claim: a killed taker's private names (each carries its creator's pid, and no live taker uses one whose creator is dead), then, with no other taker in progress, the tombs of dead claims. Stale locks' tombs stay. */
  const sweep = (): void => {
    let others = false;
    for (const n of fs.readdirSync(dir)) {
      const m = /^\.lock(?:\.claim|\.owner)?\.(\d+)\.[0-9a-f]{16}$/.exec(n);
      if (!m) continue;
      if (livePid(m[1]) === null) fs.rmSync(path.join(dir, n), { recursive: true, force: true });
      else if (STAGE_NAME.test(n)) others = true;
    }
    if (others) return;
    for (const n of fs.readdirSync(dir))
      if (TOMB_NAME.test(n) && identityLive(readText(path.join(dir, n, 'owner'))) === null)
        fs.rmSync(path.join(dir, n), { recursive: true, force: true });
  };

  try {
    fs.mkdirSync(stage);
    fs.writeFileSync(path.join(stage, 'owner'), `${self}\n`);
    if (!takeClaim()) return null;
    let got: (() => void) | null = null;
    try {
      seams.whileClaimed?.();
      sweep();
      got = fillSlot();
    } catch (e) {
      dropClaim();
      throw e;
    }
    try {
      dropClaim();
    } catch (e) {
      // A claim that cannot be dropped as installed outranks the slot's verdict, so the lock this run took is given back.
      got?.();
      throw e;
    }
    return got;
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
    fs.rmSync(tmp, { force: true });
    fs.rmSync(ownerTmp, { force: true });
  }
}
