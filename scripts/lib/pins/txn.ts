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
    return { rc: hit.rc, out: '' };
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
}

export const journalRoot = (root: string): string => path.join(root, '.ci/cache/pins');

function saveJournal(dir: string, j: Journal): void {
  fs.writeFileSync(path.join(dir, 'journal.json'), `${JSON.stringify(j, null, 2)}\n`);
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
  // Only directories are stamps: a lock file, its tombs or a stray .DS_Store is not a journal layout this code could misread.
  const stamps = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
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
  gates: { ids: string[]; rc: number } | null;
  restored: string[];
  leftAlone: string[];
  changes: RepoChange[];
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
    restored: [],
    leftAlone: [],
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
      for (const f of files) if (dirty.has(f)) foreign.push(repo === '.' ? f : `${repo}/${f}`);
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

  const run = (cmd: string, cwdRel: string): number => {
    const r = o.runner(cmd, path.join(o.root, cwdRel));
    res.commands.push({ cmd, cwd: cwdRel, rc: r.rc });
    fs.appendFileSync(
      path.join(dir, 'commands.log'),
      `$ (cd ${cwdRel} && ${cmd})  # rc=${r.rc}\n${r.out}\n`
    );
    return r.rc;
  };

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
    if (ids.length > 0) {
      const rc = run(`npm run ci -- --only ${ids.join(',')}`, '.');
      res.gates = { ids, rc };
      if (rc !== 0) throw new Error(`gates failed (rc=${rc}): ${ids.join(', ')}`);
    }
  } catch (err) {
    res.failure = (err as Error).message;
    const r = compareAndRestore(o.root, j, o.mutant);
    res.restored = r.restored;
    res.leftAlone = [...new Set([...r.leftAlone, ...undeclared])];
    j.state = 'restored';
    saveJournal(dir, j);
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

/** The live pid holding the one-run-at-a-time lock, or null when nobody does. */
export function liveLockPid(root: string): number | null {
  try {
    return livePid(fs.readFileSync(path.join(journalRoot(root), '.lock'), 'utf8').trim());
  } catch {
    return null;
  }
}

/** Test seams for the stale-lock race windows. */
export interface LockSeams {
  /** Runs between judging a lock stale and clearing it, the window a second taker races in. */
  afterStaleVerdict?: () => void;
  /** Runs between moving the judged lock aside and putting a mis-moved fresh lock back. */
  afterMove?: () => void;
}

/** Take the one-run-at-a-time lock; null when a live run holds it. */
export function takeLock(root: string, seams: LockSeams = {}): (() => void) | null {
  const dir = journalRoot(root);
  fs.mkdirSync(dir, { recursive: true });
  const lock = path.join(dir, '.lock');
  // The lock appears only by a hard link from a file that already holds the pid, so a lock file never exists empty or half-written while its owner lives: one whose content is not a positive integer pid is debris from a crash and is stale, as is one naming a dead pid. A filesystem that refuses hard links falls back to an exclusive create of the lock itself.
  const tmp = `${lock}.${process.pid}.${crypto.randomBytes(4).toString('hex')}`;
  fs.writeFileSync(tmp, `${process.pid}\n`);
  const create = (): void => {
    try {
      fs.linkSync(tmp, lock);
    } catch (err) {
      const code = (err as NodeJS.ErrnoException).code;
      if (code !== 'EPERM' && code !== 'ENOTSUP' && code !== 'ENOSYS' && code !== 'EXDEV')
        throw err;
      fs.writeFileSync(lock, `${process.pid}\n`, { flag: 'wx' });
    }
  };
  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        create();
        return () => fs.rmSync(lock, { force: true });
      } catch (err) {
        if ((err as NodeJS.ErrnoException).code !== 'EEXIST') throw err;
        let text: string;
        try {
          text = fs.readFileSync(lock, 'utf8').trim();
        } catch {
          continue;
        }
        if (livePid(text) !== null) return null;
        seams.afterStaleVerdict?.();
        // A stale lock is cleared by renaming it to a name only this taker uses, never by a plain remove: two takers that both judged the same lock stale would otherwise each remove one, and the second remove would delete the first taker's fresh lock. A rename moves one file once, so only one taker gets it; that taker then checks the file it moved is the one it judged, and puts a fresh lock it moved by mistake straight back.
        const tomb = `${lock}.stale.${process.pid}.${crypto.randomBytes(4).toString('hex')}`;
        try {
          fs.renameSync(lock, tomb);
        } catch (e) {
          if ((e as NodeJS.ErrnoException).code === 'ENOENT') continue;
          throw e;
        }
        seams.afterMove?.();
        let moved = '';
        try {
          moved = fs.readFileSync(tomb, 'utf8').trim();
        } catch {
          moved = '';
        }
        if (moved !== text) {
          try {
            fs.linkSync(tomb, lock);
          } catch {
            // Another taker already holds a fresh lock here, so the tomb is the only place the moved lock stays named: it is kept for inspection, not removed.
            return null;
          }
          fs.rmSync(tomb, { force: true });
          return null;
        }
        fs.rmSync(tomb, { force: true });
      }
    }
    return null;
  } finally {
    fs.rmSync(tmp, { force: true });
  }
}
