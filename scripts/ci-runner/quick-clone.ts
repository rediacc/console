/**
 * `npm run ci:quick`: the whole quick lane, judged in a kept clean clone at HEAD (agent/plans/PLAN-fast-loop.md Part 1).
 *
 * WHY THE CLONE IS THE DEFAULT. The incremental receipt only carries when `isDisposableClone` holds (run.ts: `--receipt-out` outside the checkout and an empty `git status --porcelain`), and a shared checkout never meets it: the receipt at d2e3fa644 carried 0 of 379 gates over 1269 s of wall time. The clean clone was a hand-written recipe in two docs, so a session got it only by remembering a line. Here a plain `npm run ci:quick` gets it.
 *
 * WHERE THE CLONE LIVES. `${XDG_CACHE_HOME:-~/.cache}/rediacc/ci-quick-clones/<basename>-<sha8 of the checkout's real path>` (`CI_QUICK_CLONE_DIR` overrides it): outside every tracked tree, so `git status` of either tree cannot see the other, and no walker of the live tree can descend into a second copy of it. Two sessions on one checkout share one clone behind a pid lock: the second waits, and since it judges the same HEAD it then carries what the first judged.
 *
 * ITS OWN STATE SITS BESIDE THE CLONE (`<clone>.lock`, `<clone>.deps.json`, `<clone>.builds.json`), so no gate reads it and a deleted clone cannot leave a record claiming otherwise: each record is honoured only while the directory it describes exists.
 *
 * WHAT IT NEVER DOES. It reads the live tree and writes one file there, `.ci/cache/prepush-receipt.json` (plus the runner's archive and events beside it). It moves no live branch and touches no live working tree file. It judges HEAD, so an uncommitted edit changes nothing.
 *
 * DEPENDENCIES ARE A HARD-LINK COPY (`cp -al`), NOT A SYMLINK TO THE LIVE `node_modules`. A symlinked root makes `@rediacc/shared` resolve through `node_modules/@rediacc/shared -> ../../packages/shared` to the LIVE working tree (Node resolves real paths), so the run would judge dirty source while the receipt names HEAD. And a gate that runs `npm ci` in a linked directory (check:ci-account-portal does, in private/account) would empty the live one through the link. In a hard-link copy the relative workspace links resolve inside the clone, an `npm ci` only unlinks the clone's names, and a live `npm install` mid-run leaves the clone's inodes alone. Only the live hidden lockfile matching the HEAD lockfile admits the copy; anything else is a real `npm ci` in the clone. A toolchain cache that is read-only in practice is the one thing linked, and that link is spelled `ln -sfn`.
 *
 * NEVER A GREEN WITHOUT A JUDGED RECEIPT. A clone that cannot be set up falls back to the shared checkout with one loud line. Whichever tree ran, exit 0 needs a whole receipt written by this run, naming the judged tree, with `exitCode` 0 and an empty `failed`.
 */
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { isEntryPoint } from '../lib/entry-point.js';

const RECEIPT_REL = path.join('.ci', 'cache', 'prepush-receipt.json');
const RUNNER_REL = path.join('scripts', 'ci-runner', 'run.ts');
/** Set for the runner in the clone: nested `ci:quick` stays where it is. */
const IN_CLONE_ENV = 'CI_QUICK_IN_CLONE';
/** Set for the runner when nothing may carry: a clone made this run holds no build output, so a carried prerequisite would leave its dependents with nothing to read, and `--no-carry` asks for every gate to be judged again. */
export const NO_CARRY_ENV = 'CI_QUICK_NO_CARRY';
/** How long a second session waits for the clone before it runs in the shared checkout instead. */
const LOCK_WAIT_MS = 90 * 60_000;
const LOCK_POLL_MS = 2_000;
/** Linked with `ln -sfn` when the live tree has them: pinned tool installs, far too big to copy and addressed by version. */
const LINKED_CACHES = ['.ci/cache/toolchain', '.ci/cache/bin', '.venv'];
/** Copied once, when the clone has none: seeds its own measurement history. */
const SEEDED_FILES = ['.ci/cache/gate-durations.json'];
/**
 * Ignored build output a gate reads and no gate in its lane builds, re-seeded when the live directory moves: hard-link copied by default, or copied for real where an entry sets `link: false` (the renet embed assets). The go build behind `private/renet/bin` is a prerequisite only of slow gates, while check:ci-no-rclone-embedded refuses an empty scan and check:ci-proxy-ops-host-check exits 77 without the binary, and check:ci-proxy-image-smoke stages `private/bin` (all measured in clone runs). The live tree's own run reads this same output, so the clone is no staler than it. A hard-linked entry relies on a rebuild replacing the clone's name, not the shared inode; an entry whose rebuild may rewrite in place is copied instead.
 */
export interface SeededBuild {
  path: string;
  /** Hard links by default; `false` seeds a real copy, for output a rebuild may rewrite in place (a rewrite through a shared inode would reach the live tree). */
  link?: boolean;
}
const SEEDED_BUILDS: readonly SeededBuild[] = [
  // Hard-linked: the go build and the stage step behind these write a new file and replace the name, which leaves the shared inode alone.
  { path: 'private/renet/bin' },
  { path: 'private/bin' },
  // The staged renet embed assets (rsync, zot, k3s ...): gitignored, built by `./build.sh embed_assets`, read by check:ci-embed-asset-versions. A kept clone held its first copy for weeks after the pins moved, so the gate judged stale versions the live tree no longer had.
  // A real copy: a rebuild of the assets may rewrite a file in place, and through a hard link that write would corrupt the live tree's copy.
  { path: 'private/renet/pkg/embed/assets', link: false },
];
/** Flags a whole-lane run in the clone keeps; every other flag names a narrowed or hand-made run. */
const PASS_THROUGH_FLAGS = new Set(['--verbose', '--merge-output']);
const PASS_THROUGH_VALUE_FLAGS = new Set(['--jobs', '--gate-timeout']);

export type Route =
  | { kind: 'clone'; pass: string[]; noCarry: boolean }
  | { kind: 'here'; why: string; pass: string[] }
  | { kind: 'refused'; why: string };

/** A checkout's git directory and common directory, read from its files with no subprocess. */
function gitDirsOf(tree: string): { gitDir: string; common: string } | undefined {
  const dotgit = path.join(tree, '.git');
  try {
    let gitDir: string;
    if (fs.statSync(dotgit).isDirectory()) gitDir = fs.realpathSync(dotgit);
    else {
      const text = fs.readFileSync(dotgit, 'utf8').trim();
      if (!text.startsWith('gitdir:')) return undefined;
      gitDir = fs.realpathSync(path.resolve(tree, text.slice('gitdir:'.length).trim()));
    }
    const commondir = path.join(gitDir, 'commondir');
    if (!fs.existsSync(commondir)) return { gitDir, common: gitDir };
    const common = fs.readFileSync(commondir, 'utf8').trim();
    return { gitDir, common: fs.realpathSync(path.resolve(gitDir, common)) };
  } catch {
    return undefined;
  }
}

/** The checkout holding `tree` when `tree` is its lease, `<main>/.claude/worktrees/<id>`. The twin of `lease_main` in .claude/hooks/stop/wl_core.py: position and git's word together. */
export function leaseMainOf(tree: string): string | undefined {
  const holder = path.dirname(tree);
  if (path.basename(path.dirname(holder)) !== '.claude') return undefined;
  if (!fs.statSync(path.join(tree, '.git'), { throwIfNoEntry: false })?.isFile()) return undefined;
  const mine = gitDirsOf(tree);
  if (mine === undefined || mine.gitDir === mine.common) return undefined;
  const admin = path.dirname(mine.gitDir);
  if (path.dirname(admin) !== mine.common || path.basename(admin) !== path.basename(holder))
    return undefined;
  const main = path.dirname(path.dirname(holder));
  return gitDirsOf(main)?.common === mine.common ? main : undefined;
}

/** Where this invocation runs. A lease runs nothing here, whatever the flags: `cloneDirFor` keys on the checkout path, so each lease would make a kept clone, and the receipt the push guards read comes from the main checkout at landing. Only a plain whole-lane run goes to the clone: CI has no second tree to protect, and `--list`, `--only`, `--narrow` and a hand-given `--receipt-out` each already say what they want judged. */
export function routeOf(args: readonly string[], env: NodeJS.ProcessEnv, live: string): Route {
  const main = leaseMainOf(live);
  if (main !== undefined) {
    return {
      kind: 'refused',
      why: `${live} is a lease of ${main}, and full gates run only in the main checkout at landing, where the push guards read their receipt. Land the commits, then run npm run ci:quick in ${main}. npm run ci -- --narrow and named tests stay allowed in a lease.`,
    };
  }
  if (env[IN_CLONE_ENV] === '1')
    return {
      kind: 'here',
      why: 'already inside the kept clone',
      pass: [...args],
    };
  if (env.CI === 'true' || env.GITHUB_ACTIONS === 'true')
    return {
      kind: 'here',
      why: 'CI checks out one clean tree already',
      pass: [...args],
    };
  if (args.includes('--here')) {
    return {
      kind: 'here',
      why: '--here asked for this checkout',
      pass: args.filter((arg) => arg !== '--here'),
    };
  }
  const noCarry = args.includes('--no-carry');
  const pass = args.filter((arg) => arg !== '--no-carry');
  for (let i = 0; i < pass.length; i++) {
    if (PASS_THROUGH_FLAGS.has(pass[i])) continue;
    if (PASS_THROUGH_VALUE_FLAGS.has(pass[i])) {
      i++;
      continue;
    }
    return {
      kind: 'here',
      why: `${pass[i]} is not a whole-lane run`,
      pass: [...args],
    };
  }
  return { kind: 'clone', pass, noCarry };
}

/** The kept clone of `live`. Per checkout, outside every tracked tree. */
export function cloneDirFor(live: string, env: NodeJS.ProcessEnv): string {
  if (env.CI_QUICK_CLONE_DIR) return path.resolve(env.CI_QUICK_CLONE_DIR);
  const base = env.XDG_CACHE_HOME || path.join(env.HOME || os.homedir(), '.cache');
  const real = fs.realpathSync(live);
  const key = createHash('sha256').update(real).digest('hex').slice(0, 8);
  return path.join(base, 'rediacc', 'ci-quick-clones', `${path.basename(real)}-${key}`);
}

/** Every setup write goes through here, and every path handed in is inside the kept clone or beside it: `prepareClone` refuses a clone inside the checkout before its first write. */
const cloneFs = {
  remove(target: string): void {
    // tree-write: safe a path in the kept clone, which prepareClone refuses to place inside the checkout
    fs.rmSync(target, { recursive: true, force: true });
  },
  ensureDir(dir: string): void {
    // tree-write: safe a directory in the kept clone, which prepareClone refuses to place inside the checkout
    fs.mkdirSync(dir, { recursive: true });
  },
  putState(file: string, text: string): void {
    // tree-write: safe a state file beside the kept clone, which prepareClone refuses to place inside the checkout
    fs.writeFileSync(file, text);
  },
  append(file: string, text: string): void {
    // tree-write: safe the kept clone's own .git/info/exclude
    fs.appendFileSync(file, text);
  },
  copy(from: string, to: string): void {
    // tree-write: safe the target is in the kept clone's ignored .ci/cache
    fs.copyFileSync(from, to);
  },
  move(from: string, to: string): void {
    // tree-write: safe a finished clone moving to its kept path, beside it and outside the checkout
    fs.renameSync(from, to);
  },
};

/** Git's repo-pointing variables win over `cwd`, and a hook sets them. */
function gitEnv(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const out = { ...env };
  for (const key of ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_PREFIX', 'GIT_COMMON_DIR'])
    delete out[key];
  return out;
}

/**
 * The runner's environment in the clone. npm prepends `<live>/node_modules/.bin` to PATH and the session exports `CLAUDE_PROJECT_DIR`, and either one would quietly point a gate back at the live tree, so every value naming the live path is rewritten to the clone. npm's own variables describe the invocation in the live tree, so they go.
 */
export function cloneEnv(
  env: NodeJS.ProcessEnv,
  live: string,
  clone: string,
  fresh: boolean
): NodeJS.ProcessEnv {
  const out = gitEnv(env);
  const named = new RegExp(`${live.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?=$|[/:])`, 'g');
  for (const key of Object.keys(out)) {
    if (key.startsWith('npm_') || key === 'INIT_CWD') {
      delete out[key];
      continue;
    }
    const value = out[key];
    if (value?.includes(live)) out[key] = value.replace(named, clone);
  }
  out.PWD = clone;
  out[IN_CLONE_ENV] = '1';
  if (fresh) out[NO_CARRY_ENV] = '1';
  else delete out[NO_CARRY_ENV];
  return out;
}

function sh(cmd: string, args: readonly string[], cwd: string): string {
  const r = spawnSync(cmd, [...args], {
    cwd,
    env: gitEnv(),
    encoding: 'utf8',
    maxBuffer: 1 << 28,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (r.error !== undefined) throw new Error(`${cmd} ${args.join(' ')}: ${r.error.message}`);
  if (r.status !== 0) {
    const tail = (r.stderr || r.stdout).trim().split('\n').slice(-3).join(' | ');
    throw new Error(`${cmd} ${args.slice(0, 4).join(' ')} exited ${r.status}: ${tail}`);
  }
  return r.stdout.trim();
}

function shTry(cmd: string, args: readonly string[], cwd: string): string | undefined {
  try {
    return sh(cmd, args, cwd);
  } catch {
    return undefined;
  }
}

/** `[path, oid]` of every gitlink in `commit`. */
function gitlinksAt(root: string, commit: string): [string, string][] {
  const out: [string, string][] = [];
  for (const rec of sh('git', ['ls-tree', '-r', '-z', '--full-tree', commit], root).split('\0')) {
    const tab = rec.indexOf('\t');
    if (tab < 0 || !rec.startsWith('160000 ')) continue;
    out.push([rec.slice(tab + 1), rec.slice(0, tab).split(' ')[2]]);
  }
  return out;
}

/** The commit a submodule needs, from the live submodule first because a commit on a local-only branch exists nowhere else, then from its own origin. Every local ref of the live submodule is fetched, not only the gitlink: a gitlink behind a branch tip is no tip itself. */
function fetchSubmoduleCommit(sub: string, liveSub: string, oid: string): void {
  const has = (): boolean => shTry('git', ['cat-file', '-e', `${oid}^{commit}`], sub) !== undefined;
  if (has()) return;
  shTry('git', ['fetch', '-q', liveSub, '+refs/heads/*:refs/ci-quick/heads/*'], sub);
  if (has()) return;
  shTry('git', ['fetch', '-q', 'origin', oid], sub);
  if (!has())
    throw new Error(`submodule commit ${oid.slice(0, 12)} is unreachable from ${liveSub}`);
}

/** Submodules at the gitlinks of `commit`. A live submodule that was never initialized stays absent here too, the state the live tree judges in. */
function syncSubmodules(clone: string, live: string, commit: string): void {
  const urls = new Map<string, string>();
  for (const line of (
    shTry(
      'git',
      ['config', '-f', '.gitmodules', '--get-regexp', '^submodule\\..*\\.path$'],
      clone
    ) ?? ''
  ).split('\n')) {
    const m = /^submodule\.(.*)\.path (.*)$/.exec(line);
    if (m !== null) urls.set(m[2], m[1]);
  }
  for (const [rel, oid] of gitlinksAt(clone, commit)) {
    const liveSub = path.join(live, rel);
    if (shTry('git', ['rev-parse', '--git-dir'], liveSub) === undefined) continue;
    if (
      fs.realpathSync(sh('git', ['rev-parse', '--show-toplevel'], liveSub)) !==
      fs.realpathSync(liveSub)
    )
      continue;
    const name = urls.get(rel);
    if (name === undefined) throw new Error(`gitlink ${rel} has no .gitmodules entry at HEAD`);
    const sub = path.join(clone, rel);
    const origin = shTry('git', ['remote', 'get-url', 'origin'], liveSub);
    if (!fs.existsSync(path.join(sub, '.git'))) {
      // Cloned from the live submodule, whatever .gitmodules says: only that copy holds a local-only commit, and file:// here is the operator's own disk.
      sh('git', ['config', `submodule.${name}.url`, liveSub], clone);
      sh(
        'git',
        [
          '-c',
          'protocol.file.allow=always',
          'submodule',
          'update',
          '--init',
          '--no-fetch',
          '--',
          rel,
        ],
        clone
      );
    }
    if (origin !== undefined) {
      sh('git', ['config', `submodule.${name}.url`, origin], clone);
      sh('git', ['remote', 'set-url', 'origin', origin], sub);
    }
    fetchSubmoduleCommit(sub, liveSub, oid);
    sh('git', ['checkout', '-q', '-f', '--detach', oid], sub);
    sh('git', ['clean', '-ffdq'], sub);
  }
}

interface HiddenPackage {
  version?: string;
  optional?: boolean;
  link?: boolean;
  peer?: boolean;
}

/**
 * Does the install `hidden` (`node_modules/.package-lock.json`) hold exactly what `lock` (a `package-lock.json`) asks for? Every installed package must be at the locked version, and every locked package must be installed unless it is optional, since a platform's optional binary is legitimately absent. Undefined means yes; a string names the first difference.
 */
export function lockDifference(lockText: string, hiddenText: string): string | undefined {
  const packagesOf = (text: string): Record<string, HiddenPackage> =>
    (JSON.parse(text) as { packages?: Record<string, HiddenPackage> }).packages ?? {};
  const lock = packagesOf(lockText);
  const hidden = packagesOf(hiddenText);
  for (const [key, entry] of Object.entries(hidden)) {
    if (entry.link === true) continue;
    if (lock[key] === undefined) return `${key} is installed but not locked`;
    if (lock[key].version !== entry.version)
      return `${key} is installed at ${entry.version}, locked at ${lock[key].version}`;
  }
  for (const [key, entry] of Object.entries(lock)) {
    if (!key.includes('node_modules/') || entry.link === true) continue;
    if (entry.optional === true || entry.peer === true) continue;
    if (hidden[key] === undefined) return `${key} is locked but not installed`;
  }
  return undefined;
}

/**
 * Does each package the hidden lockfile names sit on disk at the version the hidden lockfile records? Undefined means yes, or nothing to judge; a string names the first difference.
 *
 * The hidden lockfile alone cannot answer, because `npm install --package-lock-only` rewrites it without touching node_modules (measured under npm 11.21.0: after a wrangler bump the hidden lock read 4.157.0 while node_modules/wrangler/package.json stayed 4.156.2). `lockDifference` then reports a match, and the stale files get hard-linked into every clone. A package whose directory holds no package.json is a difference too, unless it is optional or a peer: a lockfile-only rewrite can add a nested package to both lockfiles and leave node_modules without it, and `lockDifference` compares the two lockfiles only, never the disk. An unparseable package.json is not judged.
 */
export function installedDifference(projectDir: string, hiddenText: string): string | undefined {
  const hidden =
    (JSON.parse(hiddenText) as { packages?: Record<string, HiddenPackage> }).packages ?? {};
  for (const [key, entry] of Object.entries(hidden)) {
    if (entry.link === true || entry.version === undefined || !key.startsWith('node_modules/'))
      continue;
    let onDisk: string | undefined;
    try {
      onDisk = (
        JSON.parse(fs.readFileSync(path.join(projectDir, key, 'package.json'), 'utf8')) as {
          version?: string;
        }
      ).version;
    } catch (error) {
      if (
        (error as NodeJS.ErrnoException).code === 'ENOENT' &&
        entry.optional !== true &&
        entry.peer !== true
      )
        return `${key} is in the hidden lockfile but not on disk`;
      continue;
    }
    if (onDisk !== undefined && onDisk !== entry.version)
      return `${key} is on disk at ${onDisk}, its hidden lockfile says ${entry.version}`;
  }
  return undefined;
}

/** Every `<dir>/node_modules` the live tree holds for a tracked `<dir>/package.json` at `commit`, grouped under the lockfile directory that owns it. A workspace member without its own lockfile belongs to the nearest ancestor with one. */
export function dependencyGroups(
  tracked: readonly string[],
  hasLiveModules: (dir: string) => boolean
): Map<string, string[]> {
  const lockDirs = tracked
    .filter((p) => path.posix.basename(p) === 'package-lock.json')
    .map((p) => path.posix.dirname(p));
  const groups = new Map<string, string[]>();
  for (const dir of lockDirs) groups.set(dir, []);
  for (const rel of tracked) {
    if (path.posix.basename(rel) !== 'package.json') continue;
    const dir = path.posix.dirname(rel);
    if (!hasLiveModules(dir)) continue;
    let owner: string | undefined;
    for (const candidate of lockDirs) {
      const inside = candidate === '.' || dir === candidate || dir.startsWith(`${candidate}/`);
      if (inside && (owner === undefined || candidate.length > owner.length)) owner = candidate;
    }
    if (owner !== undefined) groups.get(owner)?.push(dir);
  }
  for (const [dir, members] of groups) if (members.length === 0) groups.delete(dir);
  return groups;
}

export interface DepsSeams {
  /** A real install in `dir` of the clone. */
  install: (dir: string) => void;
}

function realInstall(dir: string): void {
  sh('npm', ['ci', '--no-audit', '--no-fund'], dir);
  const scripts = (
    JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8')) as {
      scripts?: Record<string, string>;
    }
  ).scripts;
  if (scripts?.['install:natives'] !== undefined) sh('npm', ['run', 'install:natives'], dir);
}

/** Paths tracked at `commit` in the console and in each initialized submodule, relative to the root. */
function trackedAt(clone: string, commit: string): string[] {
  const list = (root: string, rev: string, prefix: string): string[] =>
    sh('git', ['ls-tree', '-r', '-z', '--name-only', '--full-tree', rev], root)
      .split('\0')
      .filter(Boolean)
      .map((p) => `${prefix}${p}`);
  const out = list(clone, commit, '');
  for (const [rel, oid] of gitlinksAt(clone, commit)) {
    const sub = path.join(clone, rel);
    if (fs.existsSync(path.join(sub, '.git'))) out.push(...list(sub, oid, `${rel}/`));
  }
  if (out.length === 0) throw new Error(`VACUOUS: no tracked path at ${commit} in ${clone}`);
  return out;
}

/**
 * Dependencies for every lockfile directory the live tree has installed. The live install is hard-link copied when its hidden lockfile matches the lockfile at HEAD, and left alone when the clone already holds that exact install; a difference gets a real `npm ci` in the clone. Returns one line per group that changed.
 */
export function syncDependencies(
  clone: string,
  live: string,
  commit: string,
  seams: DepsSeams = { install: realInstall }
): string[] {
  const stampPath = `${clone}.deps.json`;
  let stamps: Record<string, string> = {};
  try {
    stamps = JSON.parse(fs.readFileSync(stampPath, 'utf8')) as Record<string, string>;
  } catch {
    stamps = {};
  }
  const groups = dependencyGroups(trackedAt(clone, commit), (dir) =>
    fs.existsSync(path.join(live, dir, 'node_modules'))
  );
  const notes: string[] = [];
  for (const [dir, members] of groups) {
    const lockText = fs.readFileSync(path.join(clone, dir, 'package-lock.json'), 'utf8');
    const hiddenPath = path.join(live, dir, 'node_modules', '.package-lock.json');
    const hiddenText = fs.existsSync(hiddenPath) ? fs.readFileSync(hiddenPath, 'utf8') : '{}';
    const difference =
      lockDifference(lockText, hiddenText) ?? installedDifference(path.join(live, dir), hiddenText);
    const digest = createHash('sha256')
      .update(difference === undefined ? `link\n${hiddenText}` : `install\n${lockText}`)
      .digest('hex');
    const present = members.every((m) => fs.existsSync(path.join(clone, m, 'node_modules')));
    if (stamps[dir] === digest && present) continue;
    for (const m of members) cloneFs.remove(path.join(clone, m, 'node_modules'));
    if (difference === undefined) {
      for (const m of members)
        sh(
          'cp',
          ['-al', path.join(live, m, 'node_modules'), path.join(clone, m, 'node_modules')],
          live
        );
      notes.push(`${dir}: hard-linked ${members.length} node_modules from the live install`);
    } else {
      seams.install(path.join(clone, dir));
      notes.push(`${dir}: real install, the live node_modules differs (${difference})`);
    }
    stamps[dir] = digest;
  }
  cloneFs.putState(stampPath, `${JSON.stringify(stamps, null, 2)}\n`);
  return notes;
}

function syncCaches(clone: string, live: string): void {
  const exclude = path.join(
    sh('git', ['rev-parse', '--absolute-git-dir'], clone),
    'info',
    'exclude'
  );
  cloneFs.ensureDir(path.dirname(exclude));
  // A `.venv/` ignore rule matches directories, and a link to one is not a directory, so the link would read as untracked and disable the carry.
  const wanted = LINKED_CACHES.map((rel) => `/${rel}`);
  const current = fs.existsSync(exclude) ? fs.readFileSync(exclude, 'utf8') : '';
  const missing = wanted.filter((line) => !current.split('\n').includes(line));
  if (missing.length > 0) cloneFs.append(exclude, `${missing.join('\n')}\n`);
  for (const rel of LINKED_CACHES) {
    const source = path.join(live, rel);
    if (!fs.existsSync(source)) continue;
    const dest = path.join(clone, rel);
    cloneFs.ensureDir(path.dirname(dest));
    sh('ln', ['-sfn', source, dest], clone);
  }
  for (const rel of SEEDED_FILES) {
    const source = path.join(live, rel);
    const dest = path.join(clone, rel);
    if (!fs.existsSync(source) || fs.existsSync(dest)) continue;
    cloneFs.ensureDir(path.dirname(dest));
    cloneFs.copy(source, dest);
  }
}

/** Path, size and mtime of every entry under a directory (stat only, no content read): what a rebuild moves. Each directory contributes its own relative name, so an added or removed empty subdirectory moves it too. A rebuild that rewrites a file in place leaves the parent directory's mtime alone, so a top-level listing would miss it. Recorded apart from the copy, because a file in the copy is the same inode as the live one, so an in-place write there would compare equal to itself. */
export function fingerprint(dir: string, prefix = ''): string {
  return fs
    .readdirSync(dir)
    .sort((x, y) => Number(x > y) - Number(x < y))
    .map((name) => {
      const full = path.join(dir, name);
      const stat = fs.lstatSync(full);
      if (stat.isDirectory()) {
        const inner = fingerprint(full, `${prefix}${name}/`);
        return inner === '' ? `${prefix}${name}/` : `${prefix}${name}/\n${inner}`;
      }
      return `${prefix}${name}:${stat.size}:${stat.mtimeMs}`;
    })
    .join('\n');
}

/** Copies each build output that moved since the last copy; a directory absent in the live tree stays absent, the state the live tree judges in. */
export function syncBuilds(
  clone: string,
  live: string,
  builds: readonly SeededBuild[] = SEEDED_BUILDS
): void {
  const recordPath = `${clone}.builds.json`;
  let record: Record<string, string> = {};
  try {
    record = JSON.parse(fs.readFileSync(recordPath, 'utf8')) as Record<string, string>;
  } catch {
    record = {};
  }
  for (const { path: build, link = true } of builds) {
    const source = path.join(live, build);
    if (!fs.existsSync(source)) continue;
    const dest = path.join(clone, build);
    const seen = fingerprint(source);
    if (fs.existsSync(dest) && record[build] === seen) continue;
    cloneFs.remove(dest);
    cloneFs.ensureDir(path.dirname(dest));
    sh('cp', [link ? '-al' : '-a', source, dest], live);
    record[build] = seen;
  }
  cloneFs.putState(recordPath, `${JSON.stringify(record, null, 2)}\n`);
}

/** A plain `ln -s` onto an existing link plants `node_modules/node_modules` in the live tree (2026-10-11), and npm then reads the root as empty. Nothing here spells that, and this says so on every run. */
export function assertNoSelfLoop(root: string): void {
  const loop = path.join(root, 'node_modules', 'node_modules');
  if (fs.lstatSync(loop, { throwIfNoEntry: false }) !== undefined)
    throw new Error(`${loop} exists: a self-link inside node_modules`);
}

export interface Prepared {
  clone: string;
  head: string;
  tree: string;
  branch: string;
  fresh: boolean;
  notes: string[];
}

export interface PrepareInput {
  live: string;
  clone: string;
  seams?: DepsSeams;
}

/** Makes or refreshes the clone at the live HEAD: full history, the live view of origin, the same branch name, submodules at the gitlinks, dependencies, an empty `git status`. Throws with the reason on anything it cannot do. */
export function prepareClone({ live, clone, seams }: PrepareInput): Prepared {
  const head = sh('git', ['rev-parse', 'HEAD'], live);
  const tree = sh('git', ['rev-parse', 'HEAD^{tree}'], live);
  const branch = sh('git', ['branch', '--show-current'], live);
  const relToLive = path.relative(fs.realpathSync(live), clone);
  if (!relToLive.startsWith('..') && !path.isAbsolute(relToLive))
    throw new Error(`the clone ${clone} would sit inside the checkout it judges`);
  const parent = path.dirname(clone);
  cloneFs.ensureDir(parent);
  const fresh = !fs.existsSync(path.join(clone, '.git'));
  if (fresh) {
    if (fs.existsSync(clone) && fs.readdirSync(clone).length > 0)
      throw new Error(`${clone} exists and is not a clone`);
    cloneFs.remove(clone);
    const partial = `${clone}.partial-${process.pid}`;
    cloneFs.remove(partial);
    sh('git', ['clone', '-q', '--local', '--no-checkout', live, partial], parent);
    cloneFs.move(partial, clone);
  }
  // The clone's origin is the checkout's origin, so a gate reading `origin/main` or the last push sees what the live tree sees.
  const origin = shTry('git', ['remote', 'get-url', 'origin'], live);
  if (origin !== undefined) sh('git', ['remote', 'set-url', 'origin', origin], clone);
  sh(
    'git',
    [
      'fetch',
      '-q',
      '--no-recurse-submodules',
      '--update-head-ok',
      '--tags',
      '--force',
      live,
      '+HEAD:refs/ci-quick/head',
      '+refs/remotes/origin/*:refs/remotes/origin/*',
    ],
    clone
  );
  // A LOCAL IDENTITY ONLY, and only when the checkout has one. A global one already reaches the clone, and a local copy of it is a second `--show-origin` line, which is exactly what block_unlinked_commit_author's frozen goldens read: 20 pytest cases went red in the clean clone on that alone.
  for (const key of ['user.name', 'user.email']) {
    const value = shTry('git', ['config', '--local', key], live);
    if (value !== undefined) sh('git', ['config', '--local', key, value], clone);
    else shTry('git', ['config', '--local', '--unset', key], clone);
  }
  if (branch === '') sh('git', ['checkout', '-q', '-f', '--detach', head], clone);
  else {
    sh('git', ['checkout', '-q', '-f', '-B', branch, head], clone);
    if (origin !== undefined) {
      sh('git', ['config', `branch.${branch}.remote`, 'origin'], clone);
      sh('git', ['config', `branch.${branch}.merge`, `refs/heads/${branch}`], clone);
    }
  }
  sh('git', ['reset', '-q', '--hard', head], clone);
  sh('git', ['clean', '-ffdq'], clone);
  syncSubmodules(clone, live, head);
  const notes = syncDependencies(clone, live, head, seams);
  syncCaches(clone, live);
  syncBuilds(clone, live);
  assertNoSelfLoop(live);
  assertNoSelfLoop(clone);
  const porcelain = sh('git', ['status', '--porcelain'], clone);
  if (porcelain !== '')
    throw new Error(
      `the clone is not clean after setup: ${porcelain.split('\n').slice(0, 3).join(' | ')}`
    );
  if (sh('git', ['rev-parse', 'HEAD^{tree}'], clone) !== tree)
    throw new Error('the clone did not reach the tree of the live HEAD');
  return { clone, head, tree, branch, fresh, notes };
}

interface LockBody {
  pid: number;
  at: string;
}

function lockHolder(lockPath: string): LockBody | undefined {
  try {
    return JSON.parse(fs.readFileSync(lockPath, 'utf8')) as LockBody;
  } catch {
    return undefined;
  }
}

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return (err as NodeJS.ErrnoException).code === 'EPERM';
  }
}

/** One `wx` create is the atomic step. A holder whose pid is gone left a stale file, and the rename makes that takeover atomic between two waiters. False when the holder is still alive after `waitMs`. */
export async function acquireLock(
  lockPath: string,
  log: (line: string) => void,
  waitMs = LOCK_WAIT_MS,
  pollMs = LOCK_POLL_MS
): Promise<boolean> {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const deadline = Date.now() + waitMs;
  let announced = false;
  for (;;) {
    try {
      const fd = fs.openSync(lockPath, 'wx');
      const body: LockBody = { pid: process.pid, at: new Date().toISOString() };
      fs.writeSync(fd, JSON.stringify(body));
      fs.closeSync(fd);
      return true;
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== 'EEXIST') throw err;
    }
    const holder = lockHolder(lockPath);
    if (holder !== undefined && !pidAlive(holder.pid)) {
      const stale = `${lockPath}.stale-${process.pid}`;
      try {
        fs.renameSync(lockPath, stale);
        fs.rmSync(stale, { force: true });
      } catch {
        /* a peer took it over first; the next create decides */
      }
      continue;
    }
    if (!announced) {
      log(
        `ci:quick: another session holds this checkout's clone (pid ${holder?.pid ?? '?'} since ${holder?.at ?? '?'}); waiting, and what it judges at this HEAD will carry\n`
      );
      announced = true;
    }
    if (Date.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}

export interface ReceiptShape {
  schema?: number;
  whole?: boolean;
  headTree?: string;
  exitCode?: number;
  failed?: string[];
  blocked?: string[];
  gates?: Record<string, { verdict?: string; carriedFrom?: unknown } | undefined>;
  advances?: { to?: string; gates?: Record<string, number> }[];
}

/** The tree a receipt vouches for: its own, moved along its advances. */
export function vouchedTree(receipt: ReceiptShape): string {
  const steps = receipt.advances ?? [];
  return steps.length > 0 ? (steps[steps.length - 1].to ?? '') : (receipt.headTree ?? '');
}

/** Why a whole-lane run did NOT leave a judged receipt, or undefined when it did. `writtenAfter` is when this run began: a receipt from an earlier run is no evidence about this one. */
export function unjudged(
  receipt: ReceiptShape | undefined,
  mtimeMs: number,
  writtenAfter: number,
  tree: string
): string | undefined {
  if (receipt === undefined) return 'no receipt exists';
  if (mtimeMs < writtenAfter) return 'the receipt on disk predates this run';
  if (receipt.whole !== true) return 'the receipt is not whole';
  if (vouchedTree(receipt) !== tree)
    return `the receipt vouches for ${vouchedTree(receipt) || 'no tree'}, this run judged ${tree}`;
  return undefined;
}

/** The exit of a whole-lane run: the runner's own when it failed, and otherwise what the receipt it left says. An advance over a red receipt used to exit 0 (#ea5e31cd). */
export function wholeExit(runnerExit: number, receipt: ReceiptShape | undefined): number {
  if (runnerExit !== 0) return runnerExit;
  if (receipt === undefined) return 1;
  return receipt.exitCode === 0 && (receipt.failed ?? []).length === 0 ? 0 : 1;
}

/** The one end-of-run line, plus the repair line on a red. */
export function summaryLines(input: {
  receipt: ReceiptShape | undefined;
  exit: number;
  wallMs: number;
  setupMs: number;
  where: string;
}): string[] {
  const { receipt, exit, wallMs, setupMs, where } = input;
  const seconds = (ms: number): string => `${Math.round(ms / 1000)} s`;
  const gates = Object.values(receipt?.gates ?? {});
  const carried = gates.filter(
    (g) => g?.carriedFrom !== undefined && g.carriedFrom !== null
  ).length;
  const ran = gates.filter(
    (g) =>
      (g?.carriedFrom === undefined || g.carriedFrom === null) &&
      (g?.verdict === 'ok' || g?.verdict === 'fail' || g?.verdict === 'blocked')
  ).length;
  const steps = receipt?.advances ?? [];
  const advanced = steps.length > 0 ? `, advanced ${steps.length} record-only step(s)` : '';
  const lines = [
    `ci:quick: carried ${carried}, ran ${ran}${advanced}, wall ${seconds(wallMs)} (setup ${seconds(setupMs)}), exit ${exit}, in ${where}\n`,
  ];
  if (exit !== 0) {
    const failed = receipt?.failed ?? [];
    if (failed.length > 0) lines.push(`ci:quick: RED: ${failed.join(', ')}\n`);
    const carriedRed = failed.filter((id) => {
      const from = receipt?.gates?.[id]?.carriedFrom;
      return from !== undefined && from !== null;
    });
    if (carriedRed.length > 0)
      lines.push(
        `ci:quick: carried, not re-judged, because their inputs have not changed: ${carriedRed.join(', ')}. If the cause lay outside the tree, re-judge with: npm run ci:quick -- --no-carry\n`
      );
    lines.push(
      'ci:quick: repair in this checkout with the narrow set, which judges the working tree and writes no receipt:\n  npm run ci -- --narrow\n'
    );
  }
  return lines;
}

function readReceipt(file: string): {
  receipt?: ReceiptShape;
  mtimeMs: number;
} {
  try {
    return {
      receipt: JSON.parse(fs.readFileSync(file, 'utf8')) as ReceiptShape,
      mtimeMs: fs.statSync(file).mtimeMs,
    };
  } catch {
    return { mtimeMs: 0 };
  }
}

/** Runs one child to exit with stdio inherited; a signal to this process goes on to it, so the runner's own handler stops its gates. */
function runChild(
  cmd: string,
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv
): Promise<number> {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { cwd, env, stdio: 'inherit' });
    const forward = (signal: NodeJS.Signals): void => {
      child.kill(signal);
    };
    process.on('SIGTERM', forward);
    process.on('SIGINT', forward);
    const done = (code: number): void => {
      process.off('SIGTERM', forward);
      process.off('SIGINT', forward);
      resolve(code);
    };
    child.on('error', (err) => {
      process.stderr.write(`ci:quick: could not start ${cmd}: ${err.message}\n`);
      done(127);
    });
    child.on('exit', (code, signal) => {
      done(code ?? 128 + (os.constants.signals[signal ?? 'SIGTERM'] ?? 15));
    });
  });
}

export interface QuickSeams {
  live: string;
  env: NodeJS.ProcessEnv;
  log: (text: string) => void;
  prepare: (input: PrepareInput) => Prepared;
  /** Runs `run.ts <args>` in `cwd`, returning its exit code. */
  runner: (cwd: string, args: string[], env: NodeJS.ProcessEnv) => Promise<number>;
  acquire: (lockPath: string) => Promise<boolean>;
  now: () => number;
}

/** `--selftest` first, because the receipt is minted only by a runner that proved it can fail; then the lane. */
async function selftestThenLane(
  seams: QuickSeams,
  cwd: string,
  lane: string[],
  env: NodeJS.ProcessEnv
): Promise<number> {
  const self = await seams.runner(cwd, ['--selftest'], env);
  return self !== 0 ? self : seams.runner(cwd, lane, env);
}

/** Whichever tree ran, the end of a whole-lane run is the same: judge what it left. */
function finishWhole(
  seams: QuickSeams,
  input: {
    runnerExit: number;
    startedAt: number;
    setupMs: number;
    tree: string;
    where: string;
  }
): number {
  const receiptPath = path.join(seams.live, RECEIPT_REL);
  const { receipt, mtimeMs } = readReceipt(receiptPath);
  const why = unjudged(receipt, mtimeMs, input.startedAt, input.tree);
  let exit = wholeExit(input.runnerExit, receipt);
  if (why !== undefined) {
    seams.log(`ci:quick: NO JUDGED RECEIPT at ${receiptPath}: ${why}\n`);
    if (exit === 0) exit = 1;
  }
  for (const line of summaryLines({
    receipt: why === undefined ? receipt : undefined,
    exit,
    wallMs: seams.now() - input.startedAt,
    setupMs: input.setupMs,
    where: input.where,
  }))
    seams.log(line);
  return exit;
}

export async function quickMain(args: readonly string[], seams: QuickSeams): Promise<number> {
  const startedAt = seams.now();
  const route = routeOf(args, seams.env, seams.live);
  if (route.kind === 'refused') {
    seams.log(`ci:quick: REFUSED: ${route.why}\n`);
    return 1;
  }
  const lane = ['--quick', ...route.pass];
  if (route.kind === 'here') {
    const whole = route.pass.length === 0;
    seams.log(`ci:quick: running in this checkout, ${seams.live} (${route.why})\n`);
    const exit = await selftestThenLane(seams, seams.live, lane, seams.env);
    if (!whole || seams.env[IN_CLONE_ENV] === '1') return exit;
    return finishWhole(seams, {
      runnerExit: exit,
      startedAt,
      setupMs: 0,
      tree: sh('git', ['rev-parse', 'HEAD^{tree}'], seams.live),
      where: `this checkout (${route.why})`,
    });
  }

  const clone = cloneDirFor(seams.live, seams.env);
  const receiptPath = path.join(seams.live, RECEIPT_REL);
  const lockPath = `${clone}.lock`;
  let prepared: Prepared | undefined;
  let why = '';
  let locked = false;
  try {
    locked = await seams.acquire(lockPath);
    if (locked) prepared = seams.prepare({ live: seams.live, clone });
    else why = `another session held ${lockPath} past the wait`;
  } catch (err) {
    why = (err as Error).message;
  }
  try {
    if (prepared === undefined) {
      seams.log(
        `ci:quick: !!! FALLBACK TO THE SHARED CHECKOUT, nothing will carry and tree writers are dropped: the clean clone could not be set up: ${why}\n`
      );
      const exit = await selftestThenLane(seams, seams.live, lane, seams.env);
      return finishWhole(seams, {
        runnerExit: exit,
        startedAt,
        setupMs: 0,
        tree: sh('git', ['rev-parse', 'HEAD^{tree}'], seams.live),
        where: `this shared checkout, ${seams.live} (fallback)`,
      });
    }
    const setupMs = seams.now() - startedAt;
    seams.log(
      `ci:quick: judging HEAD ${prepared.head.slice(0, 12)} tree ${prepared.tree.slice(0, 12)} on ${prepared.branch || '(detached)'} in the kept clean clone ${prepared.clone}; uncommitted edits in ${seams.live} are NOT judged; receipt: ${receiptPath}\n`
    );
    for (const note of prepared.notes) seams.log(`ci:quick: ${note}\n`);
    const env = cloneEnv(seams.env, seams.live, prepared.clone, prepared.fresh || route.noCarry);
    const exit = await selftestThenLane(
      seams,
      prepared.clone,
      [...lane, '--receipt-out', receiptPath],
      env
    );
    const moved = shTry('git', ['rev-parse', 'HEAD^{tree}'], seams.live);
    if (moved !== prepared.tree)
      seams.log(
        `ci:quick: HEAD moved in ${seams.live} during this run: the receipt judges tree ${prepared.tree.slice(0, 12)}, HEAD is now ${(moved ?? '?').slice(0, 12)}, so the push guard will ask for another run\n`
      );
    return finishWhole(seams, {
      runnerExit: exit,
      startedAt,
      setupMs,
      tree: prepared.tree,
      where: `the kept clean clone ${prepared.clone}`,
    });
  } finally {
    if (locked) fs.rmSync(lockPath, { force: true });
  }
}

function realSeams(): QuickSeams {
  const live = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
  return {
    live,
    env: process.env,
    log: (text) => {
      process.stdout.write(text);
    },
    prepare: prepareClone,
    runner: (cwd, args, env) =>
      runChild(
        path.join(cwd, 'node_modules', '.bin', 'tsx'),
        [path.join(cwd, RUNNER_REL), ...args],
        cwd,
        env
      ),
    acquire: (lockPath) =>
      acquireLock(lockPath, (line) => {
        process.stdout.write(line);
      }),
    now: () => Date.now(),
  };
}

/** Real git over scratch repositories, with the live tree's `git status` compared byte for byte. Every case names what reverting its code would do. */
export async function quickCloneSelftest(
  tmpDir: string
): Promise<{ failures: string[]; assertions: number }> {
  const failures: string[] = [];
  let assertions = 0;
  const check = (ok: boolean, message: string): void => {
    assertions++;
    if (!ok) failures.push(message);
  };
  // tree-write: safe the only caller passes os.tmpdir(), so every fixture repository lives outside the checkout
  const root = fs.mkdtempSync(path.join(tmpDir, 'quick-clone-'));
  const git = (cwd: string, ...args: string[]): string =>
    sh(
      'git',
      [
        '-c',
        'user.name=Fixture',
        '-c',
        'user.email=fixture@example.invalid',
        '-c',
        'protocol.file.allow=always',
        ...args,
      ],
      cwd
    );
  const write = (file: string, text: string): void => {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, text);
  };
  try {
    // ROUTING: a plain run goes to the clone, and only a plain run does.
    const routeAt = (args: readonly string[], env: NodeJS.ProcessEnv): Route =>
      routeOf(args, env, root);
    const plain = {} as NodeJS.ProcessEnv;
    check(routeAt([], plain).kind === 'clone', 'a plain ci:quick must route to the clone');
    check(
      routeAt(['--jobs', '4', '--verbose'], plain).kind === 'clone',
      'a flag that keeps the lane whole must still route to the clone'
    );
    for (const flag of ['--list', '--only', '--narrow', '--receipt-out', '--here'])
      check(routeAt([flag], plain).kind === 'here', `${flag} must stay in this checkout`);
    check(
      (routeAt(['--here'], plain) as { pass: string[] }).pass.length === 0,
      "--here is this wrapper's flag and must not reach the runner, which refuses an unknown one"
    );
    check(
      routeAt([], { CI: 'true' } as NodeJS.ProcessEnv).kind === 'here',
      'CI must not make a second tree'
    );
    check(
      routeAt([], { [IN_CLONE_ENV]: '1' } as NodeJS.ProcessEnv).kind === 'here',
      'a run inside the clone must not recurse'
    );

    // THE ENVIRONMENT: npm's PATH entry and CLAUDE_PROJECT_DIR must not lead a gate back to the live tree.
    const moved = cloneEnv(
      {
        PATH: '/live/tree/node_modules/.bin:/usr/bin',
        CLAUDE_PROJECT_DIR: '/live/tree',
        OTHER: '/live/tree-sibling/x',
        npm_lifecycle_event: 'ci:quick',
        INIT_CWD: '/live/tree',
        GIT_DIR: '/live/tree/.git',
      } as NodeJS.ProcessEnv,
      '/live/tree',
      '/clone',
      true
    );
    check(
      moved.PATH === '/clone/node_modules/.bin:/usr/bin',
      `PATH must lead to the clone's tools, got ${moved.PATH}`
    );
    check(moved.CLAUDE_PROJECT_DIR === '/clone', 'CLAUDE_PROJECT_DIR must name the clone');
    check(moved.OTHER === '/live/tree-sibling/x', 'CONTROL: a sibling path must not be rewritten');
    check(
      moved.npm_lifecycle_event === undefined && moved.INIT_CWD === undefined,
      "npm's variables describe the live invocation and must go"
    );
    check(moved.GIT_DIR === undefined, 'GIT_DIR would aim every git call at the live repository');
    check(moved[NO_CARRY_ENV] === '1', 'a fresh clone must tell the runner it holds no outputs');
    const askedFresh = routeAt(['--no-carry', '--verbose'], plain);
    check(
      askedFresh.kind === 'clone' && askedFresh.noCarry && askedFresh.pass.join() === '--verbose',
      "--no-carry is this wrapper's flag: it must stay in the clone and not reach the runner"
    );
    check(
      routeAt(['--verbose'], plain).kind === 'clone' &&
        (routeAt([], plain) as { noCarry: boolean }).noCarry === false,
      'CONTROL: a plain run keeps the carry'
    );

    // THE DEPENDENCY MATCH, both directions.
    const lockOf = (version: string): string =>
      JSON.stringify({
        packages: {
          '': {},
          'node_modules/a': { version },
          'node_modules/opt': { version: '1.0.0', optional: true },
        },
      });
    const hiddenOf = (version: string): string =>
      JSON.stringify({ packages: { 'node_modules/a': { version } } });
    check(
      lockDifference(lockOf('1.0.0'), hiddenOf('1.0.0')) === undefined,
      'an install at the locked versions must match, with an optional package absent'
    );
    check(
      lockDifference(lockOf('2.0.0'), hiddenOf('1.0.0')) !== undefined,
      'a version the lockfile moved past must not match, or the gates judge wrong dependencies'
    );
    check(
      lockDifference(lockOf('1.0.0'), '{}') !== undefined,
      'an empty install must not match the lockfile'
    );
    // THE DISK MATCH: the hidden lockfile can name a package node_modules does not hold.
    const diskRoot = path.join(root, 'disk-match');
    write(path.join(diskRoot, 'node_modules', 'a', 'package.json'), '{"version":"1.0.0"}\n');
    const hiddenDisk = (extra: Record<string, HiddenPackage>): string =>
      JSON.stringify({ packages: { 'node_modules/a': { version: '1.0.0' }, ...extra } });
    check(
      installedDifference(diskRoot, hiddenDisk({})) === undefined,
      'a hidden lockfile matching the disk must match'
    );
    check(
      installedDifference(
        diskRoot,
        hiddenDisk({ 'node_modules/a/node_modules/n': { version: '1.0.0' } })
      ) !== undefined,
      'a nested package the hidden lockfile names and the disk lacks must not match'
    );
    check(
      installedDifference(
        diskRoot,
        hiddenDisk({ 'node_modules/o': { version: '1.0.0', optional: true } })
      ) === undefined,
      'CONTROL: an optional package absent from disk is legitimate'
    );
    check(
      installedDifference(
        diskRoot,
        hiddenDisk({ 'node_modules/p': { version: '1.0.0', peer: true } })
      ) === undefined,
      'CONTROL: a peer package absent from disk is legitimate'
    );
    check(
      installedDifference(diskRoot, hiddenDisk({ 'node_modules/p': { version: '1.0.0' } })) !==
        undefined,
      'CONTROL: the same package, neither optional nor peer, absent from disk must not match'
    );
    const groups = dependencyGroups(
      [
        'package-lock.json',
        'package.json',
        'members/a/package.json',
        'workers/w/package-lock.json',
        'workers/w/package.json',
        'workers/gone/package-lock.json',
        'workers/gone/package.json',
      ],
      (dir) => dir !== 'workers/gone'
    );
    check(
      groups.get('.')?.join() === '.,members/a' &&
        groups.get('workers/w')?.join() === 'workers/w' &&
        !groups.has('workers/gone'),
      `a workspace member must join its lockfile's group, got ${JSON.stringify([...groups])}`
    );

    // THE CLONE, against a real repository with a submodule on a local-only commit and a dirty working tree.
    const upstream = path.join(root, 'sub-upstream');
    write(path.join(upstream, 'f.txt'), 'pushed\n');
    git(root, 'init', '-q', '-b', 'main', upstream);
    git(upstream, 'add', '-A');
    git(upstream, 'commit', '-q', '-m', 'pushed');
    const live = path.join(root, 'live');
    write(path.join(live, 'kept.txt'), 'committed\n');
    write(path.join(live, '.gitignore'), 'node_modules/\n.ci/cache/\n');
    write(path.join(live, 'package.json'), '{"name":"fixture","workspaces":["packages/*"]}\n');
    write(path.join(live, 'packages', 'shared', 'package.json'), '{"name":"s"}\n');
    write(path.join(live, 'packages', 'shared', 'index.js'), 'export const at = "HEAD";\n');
    const locked = JSON.stringify({
      packages: { 'node_modules/dep': { version: '1.0.0' } },
    });
    write(path.join(live, 'package-lock.json'), locked);
    git(root, 'init', '-q', '-b', 'main', live);
    git(live, 'submodule', 'add', '-q', upstream, 'private/sub');
    const liveSub = path.join(live, 'private', 'sub');
    git(liveSub, 'checkout', '-q', '-b', 'local-only');
    write(path.join(liveSub, 'f.txt'), 'local-only commit\n');
    git(liveSub, 'add', '-A');
    git(liveSub, 'commit', '-q', '-m', 'local only');
    const localOid = git(liveSub, 'rev-parse', 'HEAD');
    git(live, 'add', '-A');
    git(live, 'commit', '-q', '-m', 'base');
    git(live, 'update-ref', 'refs/remotes/origin/main', 'HEAD');
    git(live, 'checkout', '-q', '-b', 'topic');
    // A live install, holding the lockfile's version and a workspace link: `@x/shared` must resolve inside the clone.
    write(path.join(live, 'node_modules', 'dep', 'index.js'), 'dep\n');
    write(path.join(live, 'node_modules', 'dep', 'package.json'), '{"version":"1.0.0"}\n');
    write(
      path.join(live, 'node_modules', '.package-lock.json'),
      JSON.stringify({
        packages: { 'node_modules/dep': { version: '1.0.0' } },
      })
    );
    fs.mkdirSync(path.join(live, 'node_modules', '@x'), { recursive: true });
    fs.symlinkSync('../../packages/shared', path.join(live, 'node_modules', '@x', 'shared'));
    // The live working tree moves on from HEAD in every way a session's does.
    write(path.join(live, 'kept.txt'), 'UNCOMMITTED\n');
    write(path.join(live, 'packages', 'shared', 'index.js'), 'export const at = "DIRTY";\n');
    write(path.join(live, 'untracked.txt'), 'scratch\n');
    const statusBefore = git(live, 'status', '--porcelain=v1', '--ignored');
    const branchBefore = git(live, 'branch', '--show-current');

    const clone = path.join(root, 'kept', 'clone');
    const first = prepareClone({ live, clone });
    const firstTree = git(clone, 'rev-parse', 'HEAD^{tree}');
    check(first.fresh, 'the first prepare must report a fresh clone');
    check(
      firstTree === git(live, 'rev-parse', 'HEAD^{tree}'),
      'the clone must sit at the live tree'
    );
    check(
      git(clone, 'branch', '--show-current') === 'topic',
      'the clone must carry the live branch name, which gates and the receipt read'
    );
    check(
      fs.readFileSync(path.join(clone, 'kept.txt'), 'utf8') === 'committed\n',
      'the clone must hold HEAD, not the dirty working tree'
    );
    check(
      !fs.existsSync(path.join(clone, 'untracked.txt')),
      'an untracked live file must not reach the clone'
    );
    check(
      git(clone, 'rev-parse', 'origin/main') === git(live, 'rev-parse', 'origin/main'),
      "the clone must see the checkout's origin/main, or the last-push diff is wrong"
    );
    check(
      git(path.join(clone, 'private', 'sub'), 'rev-parse', 'HEAD') === localOid,
      'a gitlink on a local-only submodule commit must be reachable through the live submodule'
    );
    check(
      !/^[+-]/.test(git(clone, 'submodule', 'status')),
      `a submodule off its gitlink makes the receipt vouch for no tree: ${git(clone, 'submodule', 'status')}`
    );
    check(
      git(clone, 'status', '--porcelain') === '',
      'the clone must be clean, or nothing carries'
    );
    check(
      fs.realpathSync(path.join(clone, 'node_modules', '@x', 'shared')) ===
        fs.realpathSync(path.join(clone, 'packages', 'shared')),
      'a workspace link must resolve inside the clone, never to the live working tree'
    );
    check(
      fs
        .readFileSync(path.join(clone, 'node_modules', '@x', 'shared', 'index.js'), 'utf8')
        .includes('"HEAD"'),
      'a workspace package must read HEAD through node_modules, not the dirty live source'
    );
    check(
      fs.statSync(path.join(clone, 'node_modules', 'dep', 'index.js')).ino ===
        fs.statSync(path.join(live, 'node_modules', 'dep', 'index.js')).ino,
      'a matching install must be a hard-link copy, or every prepare costs its size in disk'
    );
    check(
      !fs.lstatSync(path.join(clone, 'node_modules')).isSymbolicLink(),
      'a symlinked node_modules would let `npm ci` in the clone empty the live install'
    );

    // LIVE TREE UNCHANGED: the same status bytes, the same branch, the same dirty file, and no loop.
    check(
      git(live, 'status', '--porcelain=v1', '--ignored') === statusBefore,
      'prepare must not change `git status` in the live tree'
    );
    check(git(live, 'branch', '--show-current') === branchBefore, 'the live branch must not move');
    check(
      fs.readFileSync(path.join(live, 'kept.txt'), 'utf8') === 'UNCOMMITTED\n',
      'a live uncommitted edit must survive'
    );
    check(
      !fs.existsSync(path.join(live, 'node_modules', 'node_modules')),
      'the self-loop must not appear in the live node_modules'
    );

    // A KEPT CLONE: a new commit arrives, the gate's leftovers go, the build output stays.
    write(path.join(clone, 'stray.txt'), 'a gate left this\n');
    write(path.join(clone, '.ci', 'cache', 'build-output'), 'kept\n');
    fs.mkdirSync(path.join(clone, 'node_modules', '.cache'), {
      recursive: true,
    });
    write(path.join(clone, 'kept.txt'), 'a gate rewrote this\n');
    write(path.join(live, 'second.txt'), 'second\n');
    git(live, 'add', 'second.txt');
    git(live, 'commit', '-q', '-m', 'second', '--', 'second.txt');
    const second = prepareClone({ live, clone });
    check(!second.fresh, 'the second prepare must reuse the clone');
    check(
      git(clone, 'rev-parse', 'HEAD') === git(live, 'rev-parse', 'HEAD'),
      'the kept clone must follow the live HEAD'
    );
    check(!fs.existsSync(path.join(clone, 'stray.txt')), "a gate's untracked leftover must go");
    check(
      fs.readFileSync(path.join(clone, 'kept.txt'), 'utf8') === 'committed\n',
      "a gate's tracked edit must go"
    );
    check(
      fs.existsSync(path.join(clone, '.ci', 'cache', 'build-output')),
      'ignored build output must survive between runs, or nothing is saved'
    );

    // A MOVED LOCKFILE gets a real install in the clone, never the live node_modules.
    write(
      path.join(live, 'package-lock.json'),
      JSON.stringify({
        packages: { 'node_modules/dep': { version: '2.0.0' } },
      })
    );
    git(live, 'add', 'package-lock.json');
    git(live, 'commit', '-q', '-m', 'bump', '--', 'package-lock.json');
    const installed: string[] = [];
    prepareClone({
      live,
      clone,
      seams: {
        install: (dir) => {
          installed.push(dir);
        },
      },
    });
    check(
      installed.length === 1 && installed[0] === clone,
      `a lockfile the live install does not hold must install in the clone, got ${installed.join()}`
    );

    // A HIDDEN LOCKFILE THAT MOVED WITHOUT ITS PACKAGES (`npm install --package-lock-only` rewrites it and leaves node_modules): the lock and the hidden lock agree, the files do not, and the clone must install.
    write(path.join(live, 'node_modules', 'dep', 'package.json'), '{"version":"1.0.0"}\n');
    write(
      path.join(live, 'node_modules', '.package-lock.json'),
      JSON.stringify({ packages: { 'node_modules/dep': { version: '2.0.0' } } })
    );
    const stale: string[] = [];
    prepareClone({ live, clone, seams: { install: (dir) => void stale.push(dir) } });
    check(
      stale.length === 1 && stale[0] === clone,
      `a hidden lockfile ahead of the installed package must install in the clone, got ${stale.join()}`
    );
    write(path.join(live, 'node_modules', 'dep', 'package.json'), '{"version":"2.0.0"}\n');
    const matching: string[] = [];
    prepareClone({ live, clone, seams: { install: (dir) => void matching.push(dir) } });
    check(
      matching.length === 0,
      `CONTROL: a package on disk at the hidden lockfile's version must be linked, got ${matching.join()}`
    );

    // A SEEDED BUILD: copied once, kept while the stamp holds, and never a shared name.
    const buildSpec: SeededBuild[] = [{ path: 'out/bin' }];
    const buildLive = path.join(root, 'build-live');
    const buildClone = path.join(root, 'build-clone');
    write(path.join(buildLive, 'out', 'bin', 'tool'), 'v1\n');
    write(path.join(buildLive, 'out', 'bin', '.stamp'), 'one\n');
    fs.mkdirSync(buildClone, { recursive: true });
    syncBuilds(buildClone, buildLive, buildSpec);
    check(
      fs.readFileSync(path.join(buildClone, 'out', 'bin', 'tool'), 'utf8') === 'v1\n',
      'a build output a fast gate reads must reach the clone'
    );
    fs.rmSync(path.join(buildClone, 'out', 'bin', 'tool'));
    write(path.join(buildClone, 'out', 'bin', 'tool'), 'rebuilt in the clone\n');
    check(
      fs.readFileSync(path.join(buildLive, 'out', 'bin', 'tool'), 'utf8') === 'v1\n',
      'a rebuild in the clone must leave the live output alone'
    );
    syncBuilds(buildClone, buildLive, buildSpec);
    check(
      fs.readFileSync(path.join(buildClone, 'out', 'bin', 'tool'), 'utf8') ===
        'rebuilt in the clone\n',
      'an unmoved live output must keep what the clone built'
    );
    write(path.join(buildLive, 'out', 'bin', '.stamp'), 'a rebuild moved this\n');
    syncBuilds(buildClone, buildLive, buildSpec);
    check(
      fs.readFileSync(path.join(buildClone, 'out', 'bin', 'tool'), 'utf8') === 'v1\n',
      'a moved live output must refresh the copy'
    );

    // EMBED ASSETS: a clone holding stale staged assets is refreshed from the live copy, in place-rewritten nested files included; a live tree with none leaves the clone as it is.
    check(
      SEEDED_BUILDS.some((b) => b.path === 'private/renet/pkg/embed/assets' && b.link === false),
      'the renet embed assets must be a seeded real copy, never hard links'
    );
    const assetSpec: SeededBuild[] = [{ path: 'private/renet/pkg/embed/assets', link: false }];
    const assetLive = path.join(root, 'asset-live');
    const assetClone = path.join(root, 'asset-clone');
    const assetFile = (tree: string): string =>
      path.join(tree, assetSpec[0].path, 'amd64', 'base', 'rsync');
    write(assetFile(assetClone), 'rsync 3.5.1\n');
    fs.mkdirSync(assetLive, { recursive: true });
    syncBuilds(assetClone, assetLive, assetSpec);
    check(
      fs.readFileSync(assetFile(assetClone), 'utf8') === 'rsync 3.5.1\n',
      'CONTROL: a live tree without embed assets must leave the clone untouched'
    );
    write(assetFile(assetLive), 'rsync 3.5.2\n');
    syncBuilds(assetClone, assetLive, assetSpec);
    check(
      fs.readFileSync(assetFile(assetClone), 'utf8') === 'rsync 3.5.2\n',
      'stale embed assets in the clone must be refreshed from the live tree'
    );
    // A fresh inode, as a rebuild that replaces the name writes it: only the nested directory's mtime moves, never the top level's.
    fs.rmSync(assetFile(assetLive));
    write(assetFile(assetLive), 'rsync 3.5.3 replaced\n');
    syncBuilds(assetClone, assetLive, assetSpec);
    check(
      fs.readFileSync(assetFile(assetClone), 'utf8') === 'rsync 3.5.3 replaced\n',
      'a nested asset replaced under an unmoved top level must refresh the clone'
    );
    // The same inode rewritten in place: size and mtime move, so the fingerprint does, and the copy shares no inode with the live file.
    const beforeInPlace = fingerprint(path.join(assetLive, assetSpec[0].path));
    fs.writeFileSync(assetFile(assetLive), 'rsync 3.5.4 in place, longer\n');
    check(
      fingerprint(path.join(assetLive, assetSpec[0].path)) !== beforeInPlace,
      'a same-inode in-place rewrite must move the fingerprint'
    );
    syncBuilds(assetClone, assetLive, assetSpec);
    check(
      fs.readFileSync(assetFile(assetClone), 'utf8') === 'rsync 3.5.4 in place, longer\n',
      'an in-place rewrite of a live asset must refresh the clone'
    );
    fs.writeFileSync(assetFile(assetClone), 'clobbered in the clone\n');
    check(
      fs.readFileSync(assetFile(assetLive), 'utf8') === 'rsync 3.5.4 in place, longer\n',
      'an in-place write to the clone copy must leave the live asset unchanged'
    );
    // An empty directory moves the fingerprint.
    const emptyBefore = fingerprint(path.join(assetLive, assetSpec[0].path));
    fs.mkdirSync(path.join(assetLive, assetSpec[0].path, 'empty-dir'));
    check(
      fingerprint(path.join(assetLive, assetSpec[0].path)) !== emptyBefore,
      'an added empty subdirectory must move the fingerprint'
    );
    // An empty directory nested in an empty directory: the old listing returned '' for both shapes.
    const nestedBefore = fingerprint(path.join(assetLive, assetSpec[0].path));
    fs.mkdirSync(path.join(assetLive, assetSpec[0].path, 'empty-dir', 'deeper'));
    check(
      fingerprint(path.join(assetLive, assetSpec[0].path)) !== nestedBefore,
      'an empty subdirectory added inside an empty directory must move the fingerprint'
    );

    // THE CLONE MAY NOT BE THE CHECKOUT IT JUDGES, or sit inside it: its setup discards tracked edits.
    for (const inside of [live, path.join(live, '.ci', 'cache', 'clone')]) {
      let refused = false;
      try {
        prepareClone({ live, clone: inside });
      } catch {
        refused = true;
      }
      check(refused, `a clone at ${inside} must be refused, or setup would discard live edits`);
    }
    check(
      fs.readFileSync(path.join(live, 'kept.txt'), 'utf8') === 'UNCOMMITTED\n',
      'the refusal must come before anything touched the live tree'
    );

    // THE SELF-LOOP GUARD, on the shape the 2026-10-11 `ln -s` planted.
    const looped = path.join(root, 'looped');
    fs.mkdirSync(path.join(looped, 'node_modules'), { recursive: true });
    fs.symlinkSync('../node_modules', path.join(looped, 'node_modules', 'node_modules'));
    let caught = false;
    try {
      assertNoSelfLoop(looped);
    } catch {
      caught = true;
    }
    check(caught, 'node_modules/node_modules must refuse the run');
    let quiet = true;
    try {
      assertNoSelfLoop(live);
    } catch {
      quiet = false;
    }
    check(quiet, 'CONTROL: a healthy tree must pass the self-loop guard');

    // THE LOCK: exclusive while the holder lives, taken over once it is gone.
    const lockPath = path.join(root, 'locks', 'a.lock');
    const noted: string[] = [];
    const note = (line: string): void => {
      noted.push(line);
    };
    check(await acquireLock(lockPath, note, 0, 1), 'a free lock must be taken');
    check(
      !(await acquireLock(lockPath, note, 0, 1)),
      'a live holder must keep the lock, or two sessions rewrite one clone'
    );
    check(noted.length === 1, 'a waiter must say who it waits for');
    fs.writeFileSync(lockPath, JSON.stringify({ pid: 2 ** 22 + 7, at: 'gone' }));
    check(await acquireLock(lockPath, note, 0, 1), "a dead holder's lock must be taken over");

    // THE VERDICT: exit 0 needs a judged, green receipt.
    const green: ReceiptShape = {
      whole: true,
      headTree: 'T',
      exitCode: 0,
      failed: [],
    };
    check(wholeExit(0, green) === 0, 'CONTROL: a green run over a green receipt exits 0');
    check(
      wholeExit(0, { ...green, exitCode: 1, failed: ['g'] }) === 1,
      '#ea5e31cd: a runner exiting 0 over a red receipt must exit non-zero'
    );
    check(
      wholeExit(0, { ...green, failed: ['g'] }) === 1,
      '#ea5e31cd: a non-empty failed list must exit non-zero on its own'
    );
    check(wholeExit(0, undefined) === 1, 'no receipt at all must exit non-zero');
    check(wholeExit(3, green) === 3, "the runner's own failure code must survive");
    check(unjudged(green, 10, 5, 'T') === undefined, 'CONTROL: a fresh whole receipt is judged');
    check(unjudged(undefined, 0, 5, 'T') !== undefined, 'no receipt is not judged');
    check(unjudged(green, 1, 5, 'T') !== undefined, "an earlier run's receipt is not judged");
    check(unjudged({ ...green, whole: false }, 10, 5, 'T') !== undefined, 'a narrowed one is not');
    check(unjudged(green, 10, 5, 'OTHER') !== undefined, "another tree's receipt is not judged");
    check(
      unjudged({ ...green, advances: [{ to: 'OTHER' }] }, 10, 5, 'OTHER') === undefined,
      'a receipt advanced to this tree is judged'
    );

    const linkedTree = (main: string, rel: string): string => {
      const tree = path.join(main, rel);
      git(main, 'worktree', 'add', '-q', '--detach', tree);
      return tree;
    };

    // THE ORCHESTRATOR, routing and fallback, through its seams.
    const drive = async (over: {
      prepare?: (input: PrepareInput) => Prepared;
      receipt?: ReceiptShape;
      args?: string[];
      env?: NodeJS.ProcessEnv;
      lease?: boolean;
    }): Promise<{
      exit: number;
      calls: { cwd: string; args: string[] }[];
      log: string;
    }> => {
      const scratch = fs.mkdtempSync(path.join(root, 'drive-'));
      git(root, 'init', '-q', '-b', 'main', scratch);
      write(path.join(scratch, 'a.txt'), 'a\n');
      git(scratch, 'add', '-A');
      git(scratch, 'commit', '-q', '-m', 'a');
      const tree = git(scratch, 'rev-parse', 'HEAD^{tree}');
      const calls: { cwd: string; args: string[] }[] = [];
      let log = '';
      const live = over.lease === true ? linkedTree(scratch, '.claude/worktrees/x') : scratch;
      const exit = await quickMain(over.args ?? [], {
        live,
        env: { HOME: root, ...over.env } as NodeJS.ProcessEnv,
        log: (text) => {
          log += text;
        },
        prepare:
          over.prepare ??
          ((input) => ({
            clone: input.clone,
            head: 'H',
            tree,
            branch: 'topic',
            fresh: false,
            notes: [],
          })),
        runner: (cwd, runArgs) => {
          calls.push({ cwd, args: runArgs });
          if (over.receipt !== undefined && runArgs[0] === '--quick')
            write(
              path.join(scratch, RECEIPT_REL),
              JSON.stringify({
                ...over.receipt,
                headTree: over.receipt.headTree ?? tree,
              })
            );
          return Promise.resolve(0);
        },
        acquire: () => Promise.resolve(true),
        now: () => Date.now() - 1000,
      });
      return { exit, calls, log };
    };
    const greenAtTree = {
      whole: true,
      exitCode: 0,
      failed: [],
      gates: {},
    } as ReceiptShape;
    const routed = await drive({ receipt: greenAtTree });
    check(routed.exit === 0, `a green clone run must exit 0, got ${routed.exit}: ${routed.log}`);
    check(
      routed.calls.length === 2 &&
        routed.calls.every((c) => c.cwd !== '' && c.cwd.includes('ci-quick-clones')) &&
        routed.calls[0].args[0] === '--selftest' &&
        routed.calls[1].args.includes('--receipt-out'),
      `a plain run must run selftest then lane in the clone, got ${JSON.stringify(routed.calls)}`
    );
    check(
      /carried \d+, ran \d+, wall \d+ s/.test(routed.log) &&
        routed.log.includes('in the kept clean clone'),
      `the summary line must give the counts and the place, got: ${routed.log}`
    );
    const fellBack = await drive({
      prepare: () => {
        throw new Error('no disk');
      },
      receipt: greenAtTree,
    });
    check(
      fellBack.log.includes('FALLBACK TO THE SHARED CHECKOUT') && fellBack.log.includes('no disk'),
      `a clone that cannot be set up must say why, loudly: ${fellBack.log}`
    );
    check(
      fellBack.calls.every((c) => !c.args.includes('--receipt-out')),
      'the fallback must run the shared lane, writing its own receipt'
    );
    check(fellBack.exit === 0, 'CONTROL: a fallback that judged its tree may exit 0');
    const fellBackEmpty = await drive({
      prepare: () => {
        throw new Error('no disk');
      },
    });
    check(
      fellBackEmpty.exit === 1 && fellBackEmpty.log.includes('NO JUDGED RECEIPT'),
      `a fallback that wrote no receipt must not exit 0: ${fellBackEmpty.log}`
    );
    const redAdvance = await drive({
      receipt: { ...greenAtTree, exitCode: 1, failed: ['check:red'] },
    });
    check(
      redAdvance.exit === 1 &&
        redAdvance.log.includes('npm run ci -- --narrow') &&
        redAdvance.log.includes('check:red'),
      `a red receipt must exit non-zero and print the repair line: ${redAdvance.log}`
    );
    const carriedRedRun = await drive({
      receipt: {
        ...greenAtTree,
        exitCode: 1,
        failed: ['check:old', 'check:new'],
        gates: {
          'check:old': { verdict: 'fail', carriedFrom: { headTree: 'T' } },
          'check:new': { verdict: 'fail', carriedFrom: null },
        },
      },
    });
    check(
      /carried, not re-judged[^\n]*check:old\.[^\n]*--no-carry/.test(carriedRedRun.log) &&
        !/carried, not re-judged[^\n]*check:new/.test(carriedRedRun.log),
      `a red that only carried must be named as carried, with the way to judge it again: ${carriedRedRun.log}`
    );
    const redFresh = await drive({
      receipt: { ...greenAtTree, exitCode: 1, failed: ['check:new'] },
    });
    check(
      !redFresh.log.includes('carried, not re-judged'),
      'CONTROL: a red judged this run must not be called carried'
    );
    const listed = await drive({ args: ['--list'] });
    check(
      listed.exit === 0 && listed.calls[1]?.args.join(' ') === '--quick --list',
      `--list must run in this checkout with no receipt required: ${JSON.stringify(listed.calls)}`
    );

    // A LEASE: refused before any lock or clone, with the real prepareClone behind the seam so a regression would really make the directory.
    const clonesUnder = (name: string): string =>
      path.join(root, name, 'rediacc', 'ci-quick-clones');
    const cacheEnv = (name: string): NodeJS.ProcessEnv =>
      ({ XDG_CACHE_HOME: path.join(root, name) }) as NodeJS.ProcessEnv;
    for (const args of [[], ['--here'], ['--list'], ['--no-carry']]) {
      const leased = await drive({
        lease: true,
        args,
        prepare: prepareClone,
        env: cacheEnv('lease-cache'),
      });
      const shown = `[${args.join(' ')}]`;
      check(leased.exit === 1, `a lease ${shown} must exit 1, got ${leased.exit}: ${leased.log}`);
      check(
        leased.log.includes('REFUSED') && leased.log.includes('main checkout at landing'),
        `a lease ${shown} must say why it is refused: ${leased.log}`
      );
      check(leased.calls.length === 0, `a lease ${shown} must run no gate`);
    }
    check(
      !fs.existsSync(path.join(root, 'lease-cache')),
      'a lease must create nothing under ci-quick-clones'
    );
    const leasedInCi = await drive({
      lease: true,
      env: { CI: 'true' } as NodeJS.ProcessEnv,
    });
    check(
      leasedInCi.exit === 1 && leasedInCi.calls.length === 0,
      'CI=true must not open a lease to the lane'
    );
    const mainRun = await drive({
      prepare: prepareClone,
      env: cacheEnv('main-cache'),
      receipt: greenAtTree,
    });
    check(
      mainRun.calls.length === 2 &&
        mainRun.calls.every((c) => c.cwd.startsWith(clonesUnder('main-cache'))) &&
        fs.readdirSync(clonesUnder('main-cache')).length > 0,
      `CONTROL: the main checkout must still route to a real clone, got ${JSON.stringify(mainRun.calls)}: ${mainRun.log}`
    );

    // WHAT IS A LEASE: the position and git's word, each alone is not enough.
    const leaseFixture = fs.mkdtempSync(path.join(root, 'lease-'));
    git(root, 'init', '-q', '-b', 'main', leaseFixture);
    write(path.join(leaseFixture, 'a.txt'), 'a\n');
    git(leaseFixture, 'add', '-A');
    git(leaseFixture, 'commit', '-q', '-m', 'a');
    const leaseTree = linkedTree(leaseFixture, '.claude/worktrees/y');
    check(
      routeOf([], plain, leaseTree).kind === 'refused' && leaseMainOf(leaseTree) === leaseFixture,
      'a linked tree under .claude/worktrees is a lease of its main checkout'
    );
    check(routeOf([], plain, leaseFixture).kind === 'clone', 'CONTROL: the main checkout is none');
    check(
      routeOf([], plain, linkedTree(leaseFixture, '.worktrees/0128-1')).kind === 'clone',
      "an operator's .worktrees tree keeps its route"
    );
    const standalone = path.join(leaseFixture, '.claude', 'worktrees', 'z');
    git(root, 'init', '-q', '-b', 'main', standalone);
    check(leaseMainOf(standalone) === undefined, 'a plain repository there has no shared store');
    const elsewhere = fs.mkdtempSync(path.join(root, 'other-'));
    git(root, 'init', '-q', '-b', 'main', elsewhere);
    write(path.join(elsewhere, 'a.txt'), 'a\n');
    git(elsewhere, 'add', '-A');
    git(elsewhere, 'commit', '-q', '-m', 'a');
    check(
      leaseMainOf(
        linkedTree(
          elsewhere,
          path.relative(elsewhere, path.join(leaseFixture, '.claude/worktrees/w'))
        )
      ) === undefined,
      'CONTROL: a tree at the right position from another repository is no lease of it'
    );
  } catch (err) {
    failures.push(`threw: ${(err as Error).stack ?? String(err)}`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
  return { failures, assertions };
}

if (isEntryPoint(import.meta.filename)) {
  quickMain(process.argv.slice(2), realSeams())
    .then((code) => {
      process.exitCode = code;
    })
    .catch((err: unknown) => {
      process.stderr.write(`ci:quick: ${err instanceof Error ? err.message : String(err)}\n`);
      process.exitCode = 1;
    });
}
