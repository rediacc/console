#!/usr/bin/env tsx
/**
 * path-trace: derive a gate's `paths` from what it actually reads (agent/plans/PLAN-ciquick-cpu.md A2).
 *
 * WHY. A gate with no `paths` hashes the whole tree (input-hash.ts `WHOLE_TREE_GLOB`), so any commit changes its input hash and it carries only across a byte-identical tree. On 2026-11-16, 349 of 397 lock entries declared none, and a receipt carried 23 gates while it ran 290. Hand-typed globs are the other failure: a glob that misses one file the gate reads makes carry UNSOUND, a stale green carried over a changed input.
 *
 * HOW. The gate's own `run` command executes once under `strace -ff -y --seccomp-bpf -e trace=%file,getdents,getdents64,fchdir`. Every path a process opened, stat'ed, exec'ed or resolved, and every directory it listed, is mapped onto the tracked tree:
 *   - a tracked file read is kept as itself;
 *   - a listed tracked directory becomes `dir/**` (a listing sees every name in it, so a new file there is a new input);
 *   - a directory with at least FOLD_MIN_FILES tracked files of which more than half were read becomes `dir/**`;
 *   - a read inside a submodule becomes `<gitlink>/**`, the one glob shape that reaches a gitlink entry (input-hash.ts `entryMatches`);
 *   - a path holding a glob metacharacter the hasher refuses (`?`, `[`, `{`, or `*`) folds to its nearest clean ancestor directory;
 *   - reads already inside GLOBAL_INPUTS are dropped, since every gate with `paths` hashes those anyway.
 *
 * WHEN THE ANSWER IS "WHOLE TREE", and it is written down with its reason rather than guessed: a gate that touches git metadata (its verdict depends on history or the index, not on file bytes), lists the repository root, reads more than WHOLE_TREE_FRACTION of the tracked entries, reads no tracked file at all, or exits non-zero under the trace (a red run may have stopped before reading everything). Carry-exempt gates and non-gate entries are not traced: their hash is null or never judged, so a trace would buy nothing.
 *
 * WHAT IT WRITES with `--write`, and nothing else: the entry in scripts/ci-runner/manifest.ts (`paths` plus `pathsOrigin: 'traced'`, placed before `leaves`, gen-manifest region markers repaired around it), the same two keys in scripts/ci-runner/gates.lock.json, and one row per traced gate in scripts/ci-runner/trace-ledger.ts, which also records every whole-tree verdict with its reason. An entry whose `paths` a human declared (`pathsOrigin: 'declared'`) is refused, never overwritten: the honesty gate (trace-honest.ts) judges a declared set, this tool does not replace one.
 *
 * WHAT A TRACE CANNOT SEE, stated so a clean trace is not read as more than it is: a read by a process that is not a descendant (a daemon the gate talks to over a socket), a read through io_uring (UV_USE_IO_URING=0 is set for the traced tree to keep libuv on plain syscalls), and a path the gate would read only on another branch of its logic. trace-honest.ts re-traces on every change to a gate's entry and on a rotation, and its sparse-clone mode is the independent check.
 *
 * Linux only, and strace is a hard requirement: a missing strace, or a kernel that refuses ptrace, is a loud failure with the fix in the message.
 *
 * Usage:
 *   tsx scripts/ci-runner/path-trace.ts --gate <id> [--gate <id> ...] [--write]
 *   tsx scripts/ci-runner/path-trace.ts --all-whole-tree [--jobs N] [--write] [--skip <id> ...]
 *   tsx scripts/ci-runner/path-trace.ts --selftest
 *   options: --root <dir> (default the repo), --keep-logs, --json
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { isEntryPoint } from '../lib/entry-point.js';
import {
  CARRY_EXEMPT_REL,
  exemptIdsOf,
  FORBIDDEN_GLOB_CHARS,
  GLOBAL_INPUTS,
  matchGlob,
} from './input-hash.js';

export const REPO_ROOT = path.resolve(import.meta.dirname, '..', '..');
export const MANIFEST_REL = 'scripts/ci-runner/manifest.ts';
export const LOCK_REL = 'scripts/ci-runner/gates.lock.json';
export const LEDGER_REL = 'scripts/ci-runner/trace-ledger.ts';
export const TRACED_ORIGIN = 'traced';

/** strace's %file class is every syscall taking a path; the getdents pair are listings, fchdir moves the cwd by fd. */
export const TRACE_SYSCALLS = '%file,getdents,getdents64,fchdir';
/** A directory folds to `dir/**` when more than this share of its tracked files was read... */
export const FOLD_DIR_FRACTION = 0.5;
/** ...and it holds at least this many tracked files, so a lone file stays exact. */
export const FOLD_MIN_FILES = 4;
/** A gate whose folded globs reach more than this share of the tracked entries stays whole-tree. */
export const WHOLE_TREE_FRACTION = 0.3;
/** Paths a traced process reads for a reason that is not the gate's: each one named, counted and printed, never silently dropped. */
export const GIT_DISCOVERY = 'git discovery';
export const IGNORED_PREFIXES: ReadonlyArray<{ prefix: string; why: string }> = [
  {
    prefix: GIT_DISCOVERY,
    why: 'the .git file, HEAD opened to find the repository, commondir, config and info/exclude: where the repository is and what it ignores, not what it holds. HEAD read as a revision (`git rev-parse HEAD`) is caught by its argv and counts as history',
  },
  {
    prefix: '.claude/hooks/profile/',
    why: 'the resprofile shell and python hooks (BASH_ENV, sitecustomize) every process on this host sources; they are the profiler, not a gate input',
  },
];
/**
 * Entries --all-whole-tree never traces, by name. check:ci-pytest is 36k tests: its strace log would run to tens of gigabytes, and W4.3 derives its inputs per test file through the impact map instead.
 */
export const NEVER_TRACED: Readonly<Record<string, string>> = {
  'check:ci-pytest':
    'W4.3 of PLAN-ciquick-cpu derives its paths per test file (pytest_impact.py); one whole-suite strace log is tens of gigabytes',
};

// ---------------------------------------------------------------------------
// strace output parsing (pure)
// ---------------------------------------------------------------------------

export interface Access {
  /** Absolute paths any syscall named, plus the resolved path of every fd an open returned. */
  files: Set<string>;
  /** Absolute directories a getdents call listed. */
  listed: Set<string>;
  /** Every successful execve: its argv and the cwd it ran in, which says which repository a git command reads. */
  execs: Exec[];
  /** When the traced run started (epoch ms): an untracked file modified after it was written by the run itself. */
  startedMs?: number;
}

export interface Exec {
  argv: string[];
  cwd?: string;
}

export function emptyAccess(): Access {
  return { files: new Set(), listed: new Set(), execs: [] };
}

/** strace's C-style escapes (`\"`, `\\`, `\n`, `\xHH`, `\ooo`) back to the UTF-8 string they encode. */
export function decodeCString(s: string): string {
  const bytes: number[] = [];
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c !== '\\') {
      for (const b of Buffer.from(c, 'utf8')) bytes.push(b);
      continue;
    }
    const n = s[i + 1];
    i++;
    const simple: Record<string, number> = { n: 10, t: 9, r: 13, v: 11, f: 12, '"': 34, '\\': 92 };
    if (n in simple) bytes.push(simple[n]);
    else if (n === 'x') {
      bytes.push(Number.parseInt(s.slice(i + 1, i + 3), 16));
      i += 2;
    } else if (/[0-7]/.test(n)) {
      let j = i;
      while (j < i + 3 && /[0-7]/.test(s[j] ?? '')) j++;
      bytes.push(Number.parseInt(s.slice(i, j), 8));
      i = j - 1;
    } else for (const b of Buffer.from(n ?? '', 'utf8')) bytes.push(b);
  }
  return Buffer.from(bytes).toString('utf8');
}

const QUOTED = /"((?:[^"\\]|\\.)*)"/g;
const DECORATED = /(AT_FDCWD|-?\d+)<((?:[^>\\]|\\.)*)>/g;

/** Which quoted-string arguments of a syscall are paths. Most take one, first; the link and rename families take two. */
function pathArgIndexes(name: string): number[] {
  if (/^(rename|renameat2?|link|linkat)$/.test(name)) return [0, 1];
  if (/^(symlink|symlinkat)$/.test(name)) return [1];
  return [0];
}

/** Whether a syscall's path arguments are relative to a dirfd argument (the `*at` family) rather than the cwd. */
function takesDirfd(name: string): boolean {
  return /at2?$/.test(name) || name === 'statx' || name === 'openat2';
}

/**
 * One strace `-ff -y` per-process log into the paths it named. `fallbackCwd` resolves a relative path seen before the process revealed its cwd (every `AT_FDCWD</cwd>` decoration does) and never after it did.
 */
export function parseStraceLog(
  text: string,
  fallbackCwd: string,
  into: Access = emptyAccess()
): Access {
  const p = straceParser(fallbackCwd, into);
  for (const line of text.split('\n')) p.line(line);
  return p.end();
}

/** The stateful line parser behind parseStraceLog, so a large log streams in chunks with its cwd intact. */
export function straceParser(
  fallbackCwd: string,
  into: Access = emptyAccess()
): { line: (l: string) => void; end: () => Access } {
  let cwd: string | undefined;
  const pending: string[] = [];
  const execsWithoutCwd: Exec[] = [];
  const add = (base: string | undefined, p: string): void => {
    if (p === '') return;
    if (path.posix.isAbsolute(p)) into.files.add(path.posix.normalize(p));
    else if (base !== undefined) into.files.add(path.posix.resolve(base, p));
    else pending.push(p);
  };
  const line = (l: string): void => {
    const m = /^(\w+)\((.*)$/.exec(l);
    if (m === null) return;
    const name = m[1];
    const rest = m[2];
    const decorations = [...rest.matchAll(DECORATED)].map((d) => ({
      fd: d[1],
      path: decodeCString(d[2]),
      at: d.index ?? 0,
    }));
    for (const d of decorations) if (d.fd === 'AT_FDCWD') cwd = d.path;
    if (cwd !== undefined && pending.length > 0) {
      for (const p of pending.splice(0)) into.files.add(path.posix.resolve(cwd, p));
    }
    if (cwd !== undefined) for (const e of execsWithoutCwd.splice(0)) e.cwd = cwd;
    const retMatch = /\)\s+=\s+(-?\d+)(?:<((?:[^>\\]|\\.)*)>)?/.exec(rest);
    const ok = retMatch !== null && !retMatch[1].startsWith('-');
    if (name.startsWith('getdents')) {
      const d = decorations[0];
      if (d !== undefined && d.fd !== 'AT_FDCWD') into.listed.add(path.posix.normalize(d.path));
      return;
    }
    if (name === 'fchdir') {
      if (ok && decorations[0] !== undefined) cwd = decorations[0].path;
      return;
    }
    if (retMatch?.[2] !== undefined && /^(open|openat|openat2|creat)$/.test(name)) {
      into.files.add(path.posix.normalize(decodeCString(retMatch[2])));
    }
    const args = retMatch === null ? rest : rest.slice(0, retMatch.index);
    const strings = [...args.matchAll(QUOTED)].map((q) => ({
      s: decodeCString(q[1]),
      at: q.index ?? 0,
    }));
    for (const idx of pathArgIndexes(name)) {
      const s = strings[idx];
      if (s === undefined) continue;
      let base = cwd;
      if (takesDirfd(name)) {
        // The dirfd is the last decoration before this string.
        const d = decorations.filter((x) => x.at < s.at).pop();
        if (d !== undefined) base = d.path;
      }
      add(base, s.s);
    }
    if (name === 'chdir' && ok && strings[0] !== undefined) {
      // Paths seen before the first chdir belong to the start cwd, not the new one.
      if (cwd === undefined)
        for (const p of pending.splice(0)) into.files.add(path.posix.resolve(fallbackCwd, p));
      cwd = path.posix.resolve(cwd ?? fallbackCwd, strings[0].s);
    }
    if ((name === 'execve' || name === 'execveat') && ok) {
      const argv = /\[((?:"(?:[^"\\]|\\.)*"(?:, )?)*)\]/.exec(args);
      if (argv !== null) {
        const ex: Exec = {
          argv: [...argv[1].matchAll(QUOTED)].map((q) => decodeCString(q[1])),
          cwd,
        };
        into.execs.push(ex);
        if (cwd === undefined) execsWithoutCwd.push(ex);
      }
    }
  };
  const end = (): Access => {
    for (const p of pending.splice(0)) into.files.add(path.posix.resolve(fallbackCwd, p));
    for (const e of execsWithoutCwd.splice(0)) e.cwd = fallbackCwd;
    return into;
  };
  return { line, end };
}

// ---------------------------------------------------------------------------
// the tracked tree and the fold (pure)
// ---------------------------------------------------------------------------

export interface RepoView {
  root: string;
  /** Tracked blob paths, gitlinks excluded. */
  files: string[];
  gitlinks: string[];
  /** Absolute git directories (the worktree's own and the common one); any access below them is a git read. */
  gitDirs: string[];
}

export function repoView(root: string): RepoView {
  const out = spawnSync('git', ['ls-files', '-s', '-z'], {
    cwd: root,
    encoding: 'utf8',
    maxBuffer: 1 << 30,
  });
  if (out.status !== 0) throw new Error(`git ls-files failed in ${root}: ${out.stderr}`);
  const files: string[] = [];
  const gitlinks: string[] = [];
  for (const rec of out.stdout.split('\0')) {
    if (rec === '') continue;
    const tab = rec.indexOf('\t');
    const p = rec.slice(tab + 1);
    if (rec.startsWith('160000 ')) gitlinks.push(p);
    else files.push(p);
  }
  const gitDirs = new Set<string>();
  for (const flag of ['--absolute-git-dir', '--git-common-dir']) {
    const r = spawnSync('git', ['rev-parse', flag], { cwd: root, encoding: 'utf8' });
    if (r.status === 0 && r.stdout.trim() !== '') gitDirs.add(path.resolve(root, r.stdout.trim()));
  }
  return { root, files, gitlinks, gitDirs: [...gitDirs] };
}

export interface Attribution {
  reads: Set<string>;
  gitlinkReads: Set<string>;
  /** Tracked directories listed; '' is the repository root. */
  listed: Set<string>;
  /** Evidence that the verdict depends on git HISTORY (objects, refs, a history subcommand), at most a few lines. */
  gitHistory: string[];
  /** Evidence that the gate enumerates the tracked file list through the index (`git ls-files` and kin). */
  gitIndex: string[];
  ignored: Map<string, number>;
  /** Existing untracked files or directories read outside the dependency and toolchain trees: build output, a few examples. */
  buildOutput: string[];
  /** Untracked state under .ci/cache read outside the toolchain: the verdict can move with cache contents. */
  cacheState: string[];
}

/** Untracked trees a gate may read without making its verdict depend on anything but tracked inputs and the toolchain salt. */
const TOOLCHAIN_PREFIXES = ['.ci/cache/toolchain/', '.ci/cache/bin/', '.venv/'];
/** Repo-local tool caches keyed by content, under .ci/cache: mypy's incremental cache. */
const CONTENT_CACHE_PREFIXES = ['.ci/cache/mypy/'];
/** Tool caches keyed by the content they cache: reading one changes speed, never the verdict. */
const CONTENT_CACHE_SEGMENTS = new Set([
  '__pycache__',
  '.mypy_cache',
  '.ruff_cache',
  '.pytest_cache',
]);

/** How an untracked path under the root bears on a verdict. */
export type Untracked = 'deps' | 'toolchain' | 'cache' | 'build' | 'irrelevant';

/**
 * Classifies an untracked path a trace touched. `stat` answers undefined for a path that does not exist (a module-resolution probe), else its mtime and whether it is a directory; a file modified after `startedMs` was written by the run itself and is irrelevant.
 */
export function classifyUntracked(
  rel: string,
  stat: { mtimeMs: number; dir: boolean } | undefined,
  startedMs: number | undefined,
  listing: boolean
): Untracked {
  const segs = rel.split('/');
  if (segs.includes('node_modules')) return 'deps';
  if (TOOLCHAIN_PREFIXES.some((p) => rel.startsWith(p) || `${rel}/` === p)) return 'toolchain';
  if (
    segs.some((x) => CONTENT_CACHE_SEGMENTS.has(x)) ||
    rel.endsWith('.tsbuildinfo') ||
    CONTENT_CACHE_PREFIXES.some((p) => rel.startsWith(p) || `${rel}/` === p)
  )
    return 'irrelevant';
  if (stat === undefined) return 'irrelevant';
  if (stat.dir && !listing) return 'irrelevant';
  if (startedMs !== undefined && stat.mtimeMs >= startedMs) return 'irrelevant';
  if (rel === '.ci/cache' || rel.startsWith('.ci/cache/')) return 'cache';
  return 'build';
}

/** Git files whose content is history: any read of one makes the verdict move with commits, not with file bytes. */
const GIT_HISTORY_FILE =
  /^(objects|refs|logs)(\/|$)|^(packed-refs|FETCH_HEAD|ORIG_HEAD|MERGE_HEAD|CHERRY_PICK_HEAD|shallow)$/;
/** The index: the tracked name set. */
const GIT_INDEX_FILE = /^(index|sharedindex\..*)$/;
/** Subcommands that read only the index and the worktree. */
const GIT_INDEX_CMDS = new Set([
  'ls-files',
  'check-ignore',
  'check-attr',
  'status',
  'grep',
  'diff-files',
  'submodule',
]);
/** Subcommands that locate the repository or read its config and nothing else. */
const GIT_DISCOVERY_CMDS = new Set(['config', 'var', 'hash-object', 'version', 'help']);
/** `git rev-parse` flags that only locate the repository. */
const REV_PARSE_LOCATE =
  /^--(show-toplevel|git-dir|git-common-dir|absolute-git-dir|is-inside-work-tree|is-inside-git-dir|is-bare-repository|show-prefix|show-cdup|show-superproject-working-tree|path-format=.*|local-env-vars)$/;
/** git's global options that take a separate value. */
const GIT_VALUE_OPTS = new Set([
  '-C',
  '-c',
  '--git-dir',
  '--work-tree',
  '--namespace',
  '--exec-path',
]);

export type GitUse = 'history' | 'index' | 'discovery';

/**
 * Whether a git exec reads this repository: its working directory (the cwd, moved by every `-C`) lies inside the root or a git directory of it, and it is not `init` or `clone`, which make another repository. A cwd the trace never revealed counts as this repository: the inclusive direction.
 */
export function targetsRepo(ex: Exec, view: RepoView): boolean {
  const argv = ex.argv;
  if (path.posix.basename(argv[0] ?? '') !== 'git') return false;
  let dir = ex.cwd;
  let i = 1;
  while (i < argv.length && argv[i].startsWith('-')) {
    if (argv[i] === '-C' && argv[i + 1] !== undefined && dir !== undefined)
      dir = path.posix.resolve(dir, argv[i + 1]);
    if (
      argv[i] === '-C' &&
      argv[i + 1] !== undefined &&
      dir === undefined &&
      path.posix.isAbsolute(argv[i + 1])
    )
      dir = argv[i + 1];
    i += GIT_VALUE_OPTS.has(argv[i]) ? 2 : 1;
  }
  if (argv[i] === 'init' || argv[i] === 'clone') return false;
  if (dir === undefined) return true;
  return under(dir, view.root) || view.gitDirs.some((g) => under(dir as string, g));
}

/**
 * What one git invocation depends on. Unknown subcommands count as history: the conservative direction, since a false "history" only keeps a gate whole-tree, while a false "discovery" would let a stale verdict carry.
 */
export function classifyGitArgv(argv: readonly string[]): GitUse {
  if (path.posix.basename(argv[0] ?? '') !== 'git') return 'discovery';
  let i = 1;
  while (i < argv.length && argv[i].startsWith('-')) {
    if (argv[i] === '--version' || argv[i] === '--help') return 'discovery';
    i += GIT_VALUE_OPTS.has(argv[i]) ? 2 : 1;
  }
  const sub = argv[i];
  if (sub === undefined) return 'discovery';
  const rest = argv.slice(i + 1);
  if (sub === 'rev-parse')
    return rest.every((a) => REV_PARSE_LOCATE.test(a)) ? 'discovery' : 'history';
  if (GIT_DISCOVERY_CMDS.has(sub)) return 'discovery';
  if (GIT_INDEX_CMDS.has(sub)) return 'index';
  return 'history';
}

function under(abs: string, dir: string): boolean {
  return abs === dir || abs.startsWith(`${dir}/`);
}

function ancestors(p: string): string[] {
  const out: string[] = [];
  let d = path.posix.dirname(p);
  while (d !== '.' && d !== '/' && d !== '') {
    out.push(d);
    d = path.posix.dirname(d);
  }
  return out;
}

/** The trace's absolute paths mapped onto the tracked tree. */
export function attribute(access: Access, view: RepoView): Attribution {
  const tracked = new Set(view.files);
  const trackedDirs = new Set<string>();
  for (const f of [...view.files, ...view.gitlinks])
    for (const a of ancestors(f)) trackedDirs.add(a);
  const gitlinkOf = (rel: string): string | undefined =>
    view.gitlinks.find((g) => rel === g || rel.startsWith(`${g}/`));
  const res: Attribution = {
    reads: new Set(),
    gitlinkReads: new Set(),
    listed: new Set(),
    gitHistory: [],
    gitIndex: [],
    ignored: new Map(),
    buildOutput: [],
    cacheState: [],
  };
  let usesDeps = false;
  const statOf = (rel: string): { mtimeMs: number; dir: boolean } | undefined => {
    try {
      const st = fs.statSync(path.join(view.root, rel));
      return { mtimeMs: st.mtimeMs, dir: st.isDirectory() };
    } catch {
      return undefined;
    }
  };
  const noteUntracked = (rel: string, listing: boolean): void => {
    const kind = classifyUntracked(rel, statOf(rel), access.startedMs, listing);
    if (kind === 'deps') usesDeps = true;
    else if (kind === 'cache') {
      if (res.cacheState.length < 3) res.cacheState.push(rel);
    } else if (kind === 'build') {
      if (res.buildOutput.length < 3) res.buildOutput.push(rel);
    }
  };
  // The most specific git directory first: a worktree's own gitdir sits inside the common one.
  const gitDirs = [...view.gitDirs].sort((a, b) => b.length - a.length);
  /** The path relative to its git directory ('' for the directory or the `.git` file itself), or undefined outside git. */
  const gitRelOf = (abs: string, rel: string | undefined): string | undefined => {
    for (const g of gitDirs) if (under(abs, g)) return path.posix.relative(g, abs);
    if (rel === '.git') return '';
    if (rel?.startsWith('.git/')) return rel.slice('.git/'.length);
    return undefined;
  };
  const noteGit = (gitRel: string, shown: string): void => {
    if (GIT_HISTORY_FILE.test(gitRel)) {
      if (res.gitHistory.length < 3) res.gitHistory.push(shown);
    } else if (GIT_INDEX_FILE.test(gitRel)) {
      if (res.gitIndex.length < 3) res.gitIndex.push(shown);
    } else res.ignored.set(GIT_DISCOVERY, (res.ignored.get(GIT_DISCOVERY) ?? 0) + 1);
  };
  for (const ex of access.execs) {
    // Only a git command aimed at THIS repository says anything about its history: a selftest's `git init /tmp/x` or `git -C /tmp/x log` reads another one.
    if (!targetsRepo(ex, view)) continue;
    const argv = ex.argv;
    const use = classifyGitArgv(argv);
    const shown = argv.slice(0, 6).join(' ');
    if (use === 'history' && res.gitHistory.length < 3) res.gitHistory.push(shown);
    if (use === 'index' && res.gitIndex.length < 3) res.gitIndex.push(shown);
  }
  const relOf = (abs: string): string | undefined =>
    under(abs, view.root) ? path.posix.relative(view.root, abs) : undefined;
  const ignoredBy = (rel: string): string | undefined =>
    IGNORED_PREFIXES.find((x) => rel.startsWith(x.prefix))?.prefix;
  for (const abs of access.files) {
    const rel = relOf(abs);
    const gitRel = gitRelOf(abs, rel);
    if (gitRel !== undefined) {
      noteGit(gitRel, rel ?? abs);
      continue;
    }
    if (rel === undefined || rel === '') continue;
    const ig = ignoredBy(rel);
    if (ig !== undefined) {
      res.ignored.set(ig, (res.ignored.get(ig) ?? 0) + 1);
      continue;
    }
    if (tracked.has(rel)) res.reads.add(rel);
    else {
      const g = gitlinkOf(rel);
      if (g !== undefined) res.gitlinkReads.add(g);
      else noteUntracked(rel, false);
    }
  }
  for (const abs of access.listed) {
    const rel = relOf(abs);
    const gitRel = gitRelOf(abs, rel);
    if (gitRel !== undefined) {
      noteGit(gitRel, `list ${rel ?? abs}`);
      continue;
    }
    if (rel === undefined) continue;
    if (rel === '') res.listed.add('');
    else if (ignoredBy(rel) !== undefined) continue;
    else if (trackedDirs.has(rel)) res.listed.add(rel);
    else {
      const g = gitlinkOf(rel);
      if (g !== undefined) res.gitlinkReads.add(g);
      else noteUntracked(rel, true);
    }
  }
  // The dependency trees are what the ROOT lockfile installs, and input-hash.ts matches `**/package-lock.json` as `.*/package-lock.json`, so the root one is no global input: a gate that loads a dependency names it.
  if (usesDeps && tracked.has('package-lock.json')) res.reads.add('package-lock.json');
  return res;
}

export type Verdict =
  | {
      kind: 'paths';
      paths: string[];
      reads: number;
      listed: number;
      coveragePct: number;
    }
  | { kind: 'whole-tree'; reason: string; reads: number; listed: number; coveragePct: number };

/** Code-unit order, spelled out so the sort is not a locale question. */
const byteOrder = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

function hasForbidden(p: string): boolean {
  return p.includes('*') || FORBIDDEN_GLOB_CHARS.some((c) => p.includes(c));
}

/** The nearest ancestor directory of `p` with no glob metacharacter, or '' when only the root qualifies. */
function cleanDir(p: string): string {
  let d = p;
  while (d !== '' && d !== '.' && hasForbidden(d)) d = path.posix.dirname(d);
  return d === '.' ? '' : d;
}

/** Folds an attribution into `paths` globs, or a whole-tree verdict with its reason. */
export function fold(attr: Attribution, view: RepoView, needs: readonly string[] = []): Verdict {
  const counts = { reads: attr.reads.size, listed: attr.listed.size };
  const whole = (reason: string, coveragePct = 100): Verdict => ({
    kind: 'whole-tree',
    reason,
    ...counts,
    coveragePct,
  });
  if (attr.gitHistory.length > 0) return whole(`reads git history (${attr.gitHistory.join('; ')})`);
  if (attr.gitIndex.length > 0)
    return whole(
      `enumerates the tracked file list through the git index (${attr.gitIndex.join('; ')}), so a new file anywhere can change its verdict`
    );
  if (attr.listed.has('')) return whole('lists the repository root');
  if (attr.cacheState.length > 0)
    return whole(
      `reads untracked cache state (${attr.cacheState.join(', ')}), so its verdict can move with no tracked input moving; a carry-exempt.json candidate`
    );
  if (attr.buildOutput.length > 0 && needs.length === 0)
    return whole(
      `reads untracked build output (${attr.buildOutput.join(', ')}) and declares no needs edge naming its producer, so no input hash would move when that output does; add the producer to needs, then re-trace`
    );
  const isGlobal = (f: string): boolean => GLOBAL_INPUTS.some((g) => matchGlob(g, f));
  const files = [...attr.reads].filter((f) => !isGlobal(f));
  const dirGlobs = new Set<string>();
  const fileGlobs = new Set<string>();
  const addDir = (d: string): boolean => {
    const c = cleanDir(d);
    if (c === '') return false;
    dirGlobs.add(c);
    return true;
  };
  for (const d of attr.listed) {
    if (!addDir(d)) return whole(`lists ${d}, whose only glob-safe ancestor is the root`);
  }
  // A submodule read names the bare gitlink path: input-hash.ts `entryMatches` reaches the gitlink entry through it exactly as through `<gitlink>/**`, and it is the path `git ls-files` lists and a submodule bump changes, so the dead-glob checks (check:ci-gate-manifest, check:ci-paths-origin) and quick-select's rule 1 all see it.
  for (const g of attr.gitlinkReads) {
    if (hasForbidden(g)) return whole(`reads inside submodule ${g}, whose path no glob can name`);
    fileGlobs.add(g);
  }
  const covered = (p: string): boolean =>
    [...dirGlobs].some((d) => p === d || p.startsWith(`${d}/`));
  const total = new Map<string, number>();
  const read = new Map<string, number>();
  for (const f of view.files) for (const a of ancestors(f)) total.set(a, (total.get(a) ?? 0) + 1);
  for (const f of files) for (const a of ancestors(f)) read.set(a, (read.get(a) ?? 0) + 1);
  const dirs = [...read.keys()].sort(
    (a, b) => a.split('/').length - b.split('/').length || (a < b ? -1 : a > b ? 1 : 0)
  );
  for (const d of dirs) {
    if (covered(d)) continue;
    const t = total.get(d) ?? 0;
    if (t >= FOLD_MIN_FILES && (read.get(d) ?? 0) / t > FOLD_DIR_FRACTION) addDir(d);
  }
  for (const f of files) {
    if (covered(f)) continue;
    if (hasForbidden(f)) {
      if (!addDir(path.posix.dirname(f)))
        return whole(`reads ${f}, whose only glob-safe ancestor is the root`);
    } else fileGlobs.add(f);
  }
  // A dir glob inside another dir glob says nothing more; a file glob under a dir glob neither.
  const dirList = [...dirGlobs].filter(
    (d) => ![...dirGlobs].some((o) => o !== d && d.startsWith(`${o}/`))
  );
  const finalDirs = new Set(dirList);
  const isUnderDir = (p: string): boolean =>
    [...finalDirs].some((d) => p === d || p.startsWith(`${d}/`));
  const globs = [
    ...[...finalDirs].map((d) => `${d}/**`),
    ...[...fileGlobs].filter((f) => !isUnderDir(f)),
  ].sort(byteOrder);
  const entries = view.files.length + view.gitlinks.length;
  const reached =
    view.files.filter((f) => isUnderDir(f) || fileGlobs.has(f)).length +
    view.gitlinks.filter((g) => fileGlobs.has(g) || isUnderDir(g)).length;
  const coveragePct = entries === 0 ? 0 : Math.round((1000 * reached) / entries) / 10;
  if (globs.length === 0)
    return whole(
      'reads no tracked file outside the global inputs: an empty `paths` means whole-tree, and a gate that reads nothing from the tree belongs in carry-exempt.json',
      0
    );
  if (reached / Math.max(entries, 1) > WHOLE_TREE_FRACTION)
    return whole(
      `reaches ${coveragePct}% of the tracked entries, over the ${WHOLE_TREE_FRACTION * 100}% line`,
      coveragePct
    );
  return { kind: 'paths', paths: globs, ...counts, coveragePct };
}

// ---------------------------------------------------------------------------
// running a trace
// ---------------------------------------------------------------------------

/** Refuses loudly, with the fix, when this host cannot trace. Returns undefined when it can. */
export function traceRefusal(): string | undefined {
  if (process.platform !== 'linux')
    return `path-trace runs on Linux only (strace); this host is ${process.platform}. Trace on a Linux host or in the devcontainer.`;
  const v = spawnSync('strace', ['-V'], { encoding: 'utf8' });
  if (v.error !== undefined || v.status !== 0)
    return 'strace is not installed, so no gate can be traced. Install it: `sudo apt-get install -y strace` (the devcontainer image should carry it).';
  const probe = spawnSync('strace', ['-f', '-qq', '--seccomp-bpf', '-o', '/dev/null', 'true'], {
    encoding: 'utf8',
  });
  if (probe.status !== 0)
    return `strace is installed but cannot trace here (${(probe.stderr || '').trim().split('\n')[0]}). Grant ptrace: run with CAP_SYS_PTRACE (\`--cap-add=SYS_PTRACE\` on the container) or set kernel.yama.ptrace_scope to 0 or 1.`;
  return undefined;
}

/** Process groups of traces still running. Each runs detached (so a timeout can kill its whole tree), which also means a stopped path-trace would orphan them; the signal handler in main kills them first. */
const LIVE_GROUPS = new Set<number>();

function killLiveGroups(): void {
  for (const pid of LIVE_GROUPS) {
    try {
      process.kill(-pid, 'SIGKILL');
    } catch {
      // already gone
    }
  }
}

export interface TraceRun {
  exit: number;
  access: Access;
  seconds: number;
  logFiles: number;
  outputTail: string;
}

/** Runs `cmd` under bash in `cwd`, traced, and parses every per-process log. */
export async function traceCommand(
  cmd: string,
  cwd: string,
  opts: { env?: NodeJS.ProcessEnv; keepLogs?: boolean; label?: string; timeoutS?: number } = {}
): Promise<TraceRun> {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-'));
  const started = Date.now();
  const outFile = path.join(dir, 'output.txt');
  const outFd = fs.openSync(outFile, 'w');
  const env = { ...(opts.env ?? process.env), UV_USE_IO_URING: '0' };
  const exit = await new Promise<number>((resolve) => {
    const child = spawn(
      'strace',
      [
        '-ff',
        '-qq',
        '-y',
        '-s',
        '4096',
        '--seccomp-bpf',
        '-e',
        `trace=${TRACE_SYSCALLS}`,
        '-o',
        path.join(dir, 't'),
        'bash',
        '-c',
        cmd,
      ],
      { cwd, env, stdio: ['ignore', outFd, outFd], detached: true }
    );
    if (child.pid !== undefined) LIVE_GROUPS.add(child.pid);
    // A hung gate is killed with its whole process group and reported as exit 124, the timeout(1) convention.
    let timedOut = false;
    const timer =
      opts.timeoutS === undefined
        ? undefined
        : setTimeout(() => {
            timedOut = true;
            try {
              if (child.pid !== undefined) process.kill(-child.pid, 'SIGKILL');
            } catch {
              // already gone
            }
          }, opts.timeoutS * 1000);
    child.on('exit', (code, signal) => {
      if (child.pid !== undefined) LIVE_GROUPS.delete(child.pid);
      if (timer !== undefined) clearTimeout(timer);
      resolve(timedOut ? 124 : (code ?? (signal ? 128 : 1)));
    });
    child.on('error', () => resolve(127));
  });
  fs.closeSync(outFd);
  const access = emptyAccess();
  access.startedMs = started;
  const logs = fs.readdirSync(dir).filter((f) => /^t\.\d+$/.test(f));
  for (const f of logs) {
    // A log can exceed the largest string V8 holds: stream it in chunks and parse whole lines, carrying the partial last one.
    const parser = straceParser(cwd, access);
    const fd = fs.openSync(path.join(dir, f), 'r');
    const buf = Buffer.alloc(1 << 22);
    let tail = '';
    for (
      let n = fs.readSync(fd, buf, 0, buf.length, null);
      n > 0;
      n = fs.readSync(fd, buf, 0, buf.length, null)
    ) {
      const chunk = tail + buf.toString('utf8', 0, n);
      const cut = chunk.lastIndexOf('\n');
      for (const l of chunk.slice(0, cut + 1).split('\n')) parser.line(l);
      tail = chunk.slice(cut + 1);
    }
    parser.line(tail);
    parser.end();
    fs.closeSync(fd);
  }
  const output = fs.readFileSync(outFile, 'utf8');
  if (!opts.keepLogs) fs.rmSync(dir, { recursive: true, force: true });
  else process.stderr.write(`path-trace: kept ${opts.label ?? cmd} logs in ${dir}\n`);
  return {
    exit,
    access,
    seconds: Math.round((Date.now() - started) / 100) / 10,
    logFiles: logs.length,
    outputTail: output.split('\n').slice(-15).join('\n'),
  };
}

// ---------------------------------------------------------------------------
// the lock, the manifest literal and the ledger (pure text edits)
// ---------------------------------------------------------------------------

export interface LockEntry {
  id: string;
  run: string;
  gate: boolean;
  paths?: string[];
  pathsOrigin?: string;
  leaves?: string[];
  needs?: string[];
  mutex?: string[];
  slow?: boolean;
  ciOnly?: string;
  [k: string]: unknown;
}

export function readLock(root: string): LockEntry[] {
  return JSON.parse(fs.readFileSync(path.join(root, LOCK_REL), 'utf8')) as LockEntry[];
}

/** The lock text with `paths` and `pathsOrigin` set on one entry, placed before `leaves` the way the manifest literal orders them. */
export function lockWithPaths(lockText: string, id: string, paths: string[]): string {
  const entries = JSON.parse(lockText) as LockEntry[];
  const i = entries.findIndex((e) => e.id === id);
  if (i < 0) throw new Error(`${LOCK_REL}: no entry ${id}`);
  const out: Record<string, unknown> = {};
  let placed = false;
  for (const [k, v] of Object.entries(entries[i])) {
    if (k === 'paths' || k === 'pathsOrigin') continue;
    if (k === 'leaves' && !placed) {
      out.paths = paths;
      out.pathsOrigin = TRACED_ORIGIN;
      placed = true;
    }
    out[k] = v;
  }
  if (!placed) {
    out.paths = paths;
    out.pathsOrigin = TRACED_ORIGIN;
  }
  entries[i] = out as LockEntry;
  return `${JSON.stringify(entries, null, 2)}\n`;
}

const q = (s: string): string => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

/** The `paths:` lines as biome formats them at a 100-column line width. */
export function pathsLines(paths: string[]): string[] {
  const one = `    paths: [${paths.map(q).join(', ')}],`;
  if (one.length <= 100) return [one];
  return ['    paths: [', ...paths.map((p) => `      ${q(p)},`), '    ],'];
}

const BEGIN_RE = /^ {2}\/\/ >>> gen-manifest: region \d+$/;
const END_RE = /^ {2}\/\/ <<< gen-manifest: region \d+$/;

/** Entry spans `  {` .. `  },` at indent 2, the shape gen-manifest.ts scans. */
function entrySpans(lines: readonly string[]): [number, number][] {
  const out: [number, number][] = [];
  let open = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i] === '  {') open = i;
    else if (lines[i] === '  },' && open >= 0) {
      out.push([open, i]);
      open = -1;
    }
  }
  return out;
}

/**
 * The manifest text with traced `paths` on one entry. An entry carrying a hand-only field is never generated (gen-manifest.ts HAND_ONLY), so an entry inside a generated region leaves it, and every region is re-emitted (reemitRegions).
 */
export function manifestWithPaths(text: string, id: string, paths: string[]): string {
  const lines = text.split('\n');
  const spans = entrySpans(lines);
  const idLine = `    id: ${q(id)},`;
  const span = spans.find(([a, b]) => lines.slice(a, b + 1).includes(idLine));
  if (span === undefined) throw new Error(`${MANIFEST_REL}: no entry with ${idLine.trim()}`);
  const [a, b] = span;
  const body = lines.slice(a, b + 1);
  const originAt = body.findIndex((l) => l.startsWith('    pathsOrigin:'));
  if (originAt >= 0 && !body[originAt].includes(`'${TRACED_ORIGIN}'`))
    throw new Error(
      `${id}: its paths carry ${body[originAt].trim()}; a hand-declared set is judged by trace-honest.ts, never overwritten by a trace`
    );
  // Drop an earlier traced paths block.
  const kept: string[] = [];
  for (let i = 0; i < body.length; i++) {
    const l = body[i];
    if (l.startsWith('    paths:')) {
      if (!l.trimEnd().endsWith('],')) while (i < body.length && body[i] !== '    ],') i++;
      continue;
    }
    if (l.startsWith('    pathsOrigin:')) continue;
    kept.push(l);
  }
  const leavesAt = kept.findIndex((l) => l.startsWith('    leaves:'));
  const insertAt = leavesAt >= 0 ? leavesAt : kept.length - 1;
  kept.splice(insertAt, 0, ...pathsLines(paths), `    pathsOrigin: ${q(TRACED_ORIGIN)},`);
  const spliced = [...lines.slice(0, a), ...kept, ...lines.slice(b + 1)];
  return reemitRegions(spliced, idLine);
}

/**
 * Every gen-manifest region re-emitted the way `gen-manifest.ts --write` places them: membership is read off the existing markers (an entry is generated when its span sits inside a region), the edited entry leaves it, all markers are stripped, and one BEGIN goes directly before the first `  {` of each maximal run of generated spans and one END directly after its last `  },`. Prose lines between entries therefore stay outside the markers, as gen-manifest leaves them.
 */
export function reemitRegions(withMarkers: readonly string[], liftedIdLine: string): string {
  const generated: boolean[] = [];
  let inRegion = false;
  let open: { gen: boolean; lifted: boolean } | undefined;
  for (const l of withMarkers) {
    if (BEGIN_RE.test(l)) inRegion = true;
    else if (END_RE.test(l)) inRegion = false;
    else if (l === '  {') open = { gen: inRegion, lifted: false };
    else if (open !== undefined && l === liftedIdLine) open.lifted = true;
    else if (open !== undefined && l === '  },') {
      generated.push(open.gen && !open.lifted);
      open = undefined;
    }
  }
  const lines = withMarkers.filter((l) => !BEGIN_RE.test(l) && !END_RE.test(l));
  const spans = entrySpans(lines);
  if (spans.length !== generated.length)
    throw new Error(
      `${MANIFEST_REL}: ${spans.length} entry spans against ${generated.length} read through the markers; refusing to re-emit regions`
    );
  const out: string[] = [];
  let r = 0;
  for (let i = 0, k = 0; i < lines.length; i++) {
    if (k < spans.length && i === spans[k][0] && generated[k] && (k === 0 || !generated[k - 1]))
      out.push(`  // >>> gen-manifest: region ${++r}`);
    out.push(lines[i]);
    if (k < spans.length && i === spans[k][1]) {
      if (generated[k] && (k === spans.length - 1 || !generated[k + 1]))
        out.push(`  // <<< gen-manifest: region ${r}`);
      k++;
    }
  }
  return out.join('\n');
}

export interface LedgerRow {
  tracedAt: string;
  tree: string;
  verdict: 'paths' | 'whole-tree';
  reason?: string;
  reads: number;
  listed: number;
  coveragePct: number;
  seconds: number;
}

const LEDGER_HEAD = `/**
 * GENERATED by scripts/ci-runner/path-trace.ts --write; do not hand-edit.
 *
 * One row per gate path-trace has traced: when, at which tree, and its verdict. A \`paths\` row is the provenance behind that entry's \`pathsOrigin: 'traced'\` in manifest.ts; a \`whole-tree\` row is the named reason the entry still hashes the whole tree. trace-honest.ts re-traces the \`paths\` rows (agent/plans/PLAN-ciquick-cpu.md A3).
 */
export interface TraceRow {
  tracedAt: string;
  tree: string;
  verdict: 'paths' | 'whole-tree';
  reason?: string;
  reads: number;
  listed: number;
  coveragePct: number;
  seconds: number;
}

export const TRACE_LEDGER: Readonly<Record<string, TraceRow>> = {
`;

/** Parses the ledger file this tool writes. Throws on any shape it does not write itself. */
export function parseLedger(text: string): Record<string, LedgerRow> {
  const start = text.indexOf('export const TRACE_LEDGER');
  if (start < 0) return {};
  const body = text.slice(text.indexOf('{', text.indexOf('=', start)));
  // The literal is JSON-compatible once keys and single quotes are normalised; parse via Function-free conversion.
  const json = body
    .replace(/;\s*$/, '')
    .replace(/'((?:[^'\\]|\\.)*)'/g, (_, s: string) => JSON.stringify(s.replace(/\\'/g, "'")))
    .replace(/([{,]\s*)([A-Za-z_]\w*)\s*:/g, '$1"$2":')
    .replace(/,(\s*[}\]])/g, '$1');
  return JSON.parse(json) as Record<string, LedgerRow>;
}

export function renderLedger(rows: Record<string, LedgerRow>): string {
  const ids = Object.keys(rows).sort(byteOrder);
  const out: string[] = [LEDGER_HEAD.replace(/\n$/, '')];
  for (const id of ids) {
    const r = rows[id];
    out.push(`  ${q(id)}: {`);
    out.push(`    tracedAt: ${q(r.tracedAt)},`);
    out.push(`    tree: ${q(r.tree)},`);
    out.push(`    verdict: ${q(r.verdict)},`);
    if (r.reason !== undefined) {
      const one = `    reason: ${q(r.reason)},`;
      out.push(one.length <= 100 ? one : `    reason:\n      ${q(r.reason)},`);
    }
    out.push(`    reads: ${r.reads},`);
    out.push(`    listed: ${r.listed},`);
    out.push(`    coveragePct: ${r.coveragePct},`);
    out.push(`    seconds: ${r.seconds},`);
    out.push('  },');
  }
  out.push('};', '');
  return out.join('\n');
}

// ---------------------------------------------------------------------------
// the CLI
// ---------------------------------------------------------------------------

interface Args {
  gates: string[];
  allWholeTree: boolean;
  write: boolean;
  jobs: number;
  root: string;
  keepLogs: boolean;
  json: boolean;
  skip: Set<string>;
  selftest: boolean;
  /** Appends each result as one JSON line, so a long run that dies keeps what it traced. */
  out?: string;
  /** Writes the results of an earlier `--out` file instead of tracing. */
  apply?: string;
  /** Re-folds the raw traces of an `--out` file under today's fold, printing a fresh `--out` stream to stdout. */
  refold?: string;
  timeoutS: number;
}

function parseArgs(argv: string[]): Args {
  const a: Args = {
    gates: [],
    allWholeTree: false,
    write: false,
    jobs: Math.max(1, Math.floor(os.cpus().length / 3)),
    root: REPO_ROOT,
    keepLogs: false,
    json: false,
    skip: new Set(),
    selftest: false,
    timeoutS: 1800,
  };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    const val = (): string => {
      const v = argv[++i];
      if (v === undefined) throw new Error(`${t} needs a value`);
      return v;
    };
    if (t === '--gate') a.gates.push(val());
    else if (t === '--all-whole-tree') a.allWholeTree = true;
    else if (t === '--write') a.write = true;
    else if (t === '--jobs') a.jobs = Number(val());
    else if (t === '--root') a.root = path.resolve(val());
    else if (t === '--keep-logs') a.keepLogs = true;
    else if (t === '--json') a.json = true;
    else if (t === '--skip') a.skip.add(val());
    else if (t === '--selftest') a.selftest = true;
    else if (t === '--out') a.out = path.resolve(val());
    else if (t === '--apply') a.apply = path.resolve(val());
    else if (t === '--refold') a.refold = path.resolve(val());
    else if (t === '--timeout-s') a.timeoutS = Number(val());
    else throw new Error(`unknown argument ${t}`);
  }
  return a;
}

export interface GateResult {
  id: string;
  verdict: Verdict;
  exit: number;
  seconds: number;
  ignored: Map<string, number>;
  outputTail: string;
  /** The part of the trace that bears on this repository, kept so a changed fold re-folds without re-tracing (`--refold`). */
  raw?: RawAccess;
}

/** An Access cut down to this repository: paths under the root or a git directory, listings under the root, git execs. */
export interface RawAccess {
  files: string[];
  listed: string[];
  execs: Exec[];
  startedMs?: number;
}

export function rawOf(access: Access, view: RepoView): RawAccess {
  const ours = (p: string): boolean => under(p, view.root) || view.gitDirs.some((g) => under(p, g));
  return {
    files: [...access.files].filter(ours).sort(byteOrder),
    listed: [...access.listed].filter(ours).sort(byteOrder),
    execs: access.execs.filter((e) => path.posix.basename(e.argv[0] ?? '') === 'git'),
    startedMs: access.startedMs,
  };
}

/** The verdict a trace earns: the fold, unless the gate was red, which makes the read set untrustworthy. */
export function verdictOf(
  attr: Attribution,
  view: RepoView,
  exit: number,
  needs: readonly string[] = []
): Verdict {
  const verdict = fold(attr, view, needs);
  if (exit === 0) return verdict;
  return {
    kind: 'whole-tree',
    reason: `exited ${exit} under the trace, so the read set may be partial; fix the gate or its environment and re-trace`,
    reads: attr.reads.size,
    listed: attr.listed.size,
    coveragePct: verdict.coveragePct,
  };
}

/** Traces one lock entry in `root` and folds the result. A red run is a whole-tree verdict: it may have stopped before reading everything. */
export async function traceGate(
  entry: LockEntry,
  view: RepoView,
  opts: { keepLogs?: boolean; timeoutS?: number } = {}
): Promise<GateResult> {
  const run = await traceCommand(entry.run, view.root, {
    timeoutS: opts.timeoutS,
    keepLogs: opts.keepLogs,
    label: entry.id,
  });
  const attr = attribute(run.access, view);
  return {
    id: entry.id,
    verdict: verdictOf(attr, view, run.exit, entry.needs ?? []),
    exit: run.exit,
    seconds: run.seconds,
    ignored: attr.ignored,
    outputTail: run.outputTail,
    raw: rawOf(run.access, view),
  };
}

function headTree(root: string): string {
  const r = spawnSync('git', ['rev-parse', 'HEAD^{tree}'], { cwd: root, encoding: 'utf8' });
  return r.status === 0 ? r.stdout.trim() : 'unknown';
}

/** The UTC minute of an instant (default now), the ledger's stamp. */
function utcMinute(ms: number = Date.now()): string {
  return `${new Date(ms).toISOString().slice(0, 16)}Z`;
}

/** Writes one result into the manifest, the lock and the ledger under `root`. */
export function writeResult(root: string, r: GateResult, tree: string, tracedMs?: number): void {
  const ledgerPath = path.join(root, LEDGER_REL);
  const rows = fs.existsSync(ledgerPath) ? parseLedger(fs.readFileSync(ledgerPath, 'utf8')) : {};
  const row: LedgerRow = {
    tracedAt: utcMinute(tracedMs ?? r.raw?.startedMs),
    tree,
    verdict: r.verdict.kind,
    reads: r.verdict.reads,
    listed: r.verdict.listed,
    coveragePct: r.verdict.coveragePct,
    seconds: r.seconds,
  };
  if (r.verdict.kind === 'whole-tree') row.reason = r.verdict.reason;
  else {
    const mPath = path.join(root, MANIFEST_REL);
    const lPath = path.join(root, LOCK_REL);
    fs.writeFileSync(
      mPath,
      manifestWithPaths(fs.readFileSync(mPath, 'utf8'), r.id, r.verdict.paths)
    );
    fs.writeFileSync(lPath, lockWithPaths(fs.readFileSync(lPath, 'utf8'), r.id, r.verdict.paths));
  }
  rows[r.id] = row;
  fs.writeFileSync(ledgerPath, renderLedger(rows));
}

/** Why --all-whole-tree leaves an entry untraced, or undefined when it traces it. */
export function untracedReason(e: LockEntry, exempt: Set<string>): string | undefined {
  if ((e.paths ?? []).length > 0) return 'declares paths already';
  if (!e.gate)
    return 'not a gate: a prerequisite or an operator command, never judged, so never carried';
  if (exempt.has(e.id))
    return `carry-exempt (${CARRY_EXEMPT_REL}): its hash is null, so paths buy nothing`;
  if (NEVER_TRACED[e.id] !== undefined) return NEVER_TRACED[e.id];
  if (e.ciOnly !== undefined) return 'ciOnly: never runs in the local lane';
  return undefined;
}

/** Re-folds every raw trace in an `--out` file against the current tree, printing new result lines on stdout and the shape on stderr. */
export function refold(root: string, file: string): number {
  const view = repoView(root);
  let n = 0;
  let paths = 0;
  for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
    if (line.trim() === '') continue;
    const r = JSON.parse(line) as {
      id: string;
      exit: number;
      seconds: number;
      tree: string;
      raw?: RawAccess;
    };
    if (r.raw === undefined) {
      console.error(`path-trace: ${r.id} has no raw trace in ${file}; re-trace it`);
      return 1;
    }
    const access: Access = {
      files: new Set(r.raw.files),
      listed: new Set(r.raw.listed),
      execs: r.raw.execs,
      startedMs: r.raw.startedMs,
    };
    const needs = readLock(root).find((e) => e.id === r.id)?.needs ?? [];
    const verdict = verdictOf(attribute(access, view), view, r.exit, needs);
    if (verdict.kind === 'paths') paths++;
    n++;
    process.stdout.write(`${JSON.stringify({ ...r, verdict })}\n`);
  }
  console.error(
    `path-trace: re-folded ${n} trace(s): ${paths} with paths, ${n - paths} whole-tree`
  );
  return n === 0 ? 1 : 0;
}

/** Writes every result line of an `--out` file; the last line per gate wins. */
export function applyResults(root: string, file: string): number {
  const last = new Map<string, GateResult & { tree: string }>();
  for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
    if (line.trim() === '') continue;
    const r = JSON.parse(line) as {
      id: string;
      exit: number;
      seconds: number;
      tree: string;
      verdict: Verdict;
      raw?: RawAccess;
    };
    // The ledger stamps when the trace RAN (the raw record's start), not when its result was applied.
    last.set(r.id, { ...r, ignored: new Map(), outputTail: '' });
  }
  if (last.size === 0) {
    console.error(`path-trace: ${file} holds ZERO results; nothing to apply is not a success.`);
    return 1;
  }
  const lock = new Map(readLock(root).map((e) => [e.id, e]));
  let paths = 0;
  let whole = 0;
  for (const r of last.values()) {
    const e = lock.get(r.id);
    if (e === undefined) {
      console.error(`path-trace: ${r.id} is no longer in ${LOCK_REL}; skipped`);
      continue;
    }
    if (e.pathsOrigin !== undefined && e.pathsOrigin !== TRACED_ORIGIN) {
      console.error(
        `path-trace: ${r.id} declares its paths by hand (${e.pathsOrigin}); not overwritten`
      );
      continue;
    }
    writeResult(root, r, r.tree);
    if (r.verdict.kind === 'paths') paths++;
    else whole++;
  }
  console.error(
    `path-trace: applied ${last.size} result(s) from ${file}: ${paths} with paths, ${whole} whole-tree`
  );
  return 0;
}

async function main(argv: string[]): Promise<number> {
  const args = parseArgs(argv);
  if (args.selftest) return selftest();
  if (args.apply !== undefined) return applyResults(args.root, args.apply);
  if (args.refold !== undefined) return refold(args.root, args.refold);
  if (args.gates.length === 0 && !args.allWholeTree) {
    console.error(
      'path-trace: name --gate <id> (repeatable) or --all-whole-tree. Nothing to trace.'
    );
    return 2;
  }
  const refusal = traceRefusal();
  if (refusal !== undefined) {
    console.error(`path-trace: REFUSED. ${refusal}`);
    return 1;
  }
  const lock = readLock(args.root);
  const byId = new Map(lock.map((e) => [e.id, e]));
  const exemptPath = path.join(args.root, CARRY_EXEMPT_REL);
  const exempt = exemptIdsOf(
    fs.existsSync(exemptPath) ? fs.readFileSync(exemptPath, 'utf8') : null
  );
  const todo: LockEntry[] = [];
  const untraced = new Map<string, string>();
  for (const id of args.gates) {
    const e = byId.get(id);
    if (e === undefined) {
      console.error(`path-trace: no lock entry ${id} in ${LOCK_REL}`);
      return 2;
    }
    todo.push(e);
  }
  if (args.allWholeTree) {
    for (const e of lock) {
      if (args.skip.has(e.id)) {
        untraced.set(e.id, 'skipped by --skip');
        continue;
      }
      const why = untracedReason(e, exempt);
      if (why === undefined) todo.push(e);
      else if (why !== 'declares paths already') untraced.set(e.id, why);
    }
  }
  const view = repoView(args.root);
  if (view.files.length === 0) {
    console.error(
      `path-trace: ${args.root} tracks ZERO files; a fold against nothing means nothing.`
    );
    return 1;
  }
  const tree = headTree(args.root);
  console.error(
    `path-trace: ${todo.length} gate(s) to trace in ${args.root} at tree ${tree.slice(0, 12)} ` +
      `(${view.files.length} tracked files, ${view.gitlinks.length} gitlinks), ${args.jobs} at a time`
  );
  // The runner's own exclusion, kept: two gates sharing a mutex group never overlap, and a `tree:` claimant runs with nothing else beside it, since it may write what another gate reads.
  const pending = [...todo];
  const results: GateResult[] = [];
  const onDone = (r: GateResult): void => {
    results.push(r);
    const v = r.verdict;
    const shape =
      v.kind === 'paths'
        ? `${v.paths.length} glob(s), ${v.coveragePct}% of the tree`
        : `WHOLE-TREE: ${v.reason}`;
    console.error(
      `  [${results.length}/${todo.length}] ${r.id} (${r.seconds}s, exit ${r.exit}, ${v.reads} reads, ${v.listed} listings): ${shape}`
    );
    if (r.exit !== 0) console.error(r.outputTail.replace(/^/gm, '      | '));
    if (args.write) writeResult(args.root, r, tree);
    if (args.out !== undefined)
      fs.appendFileSync(
        args.out,
        `${JSON.stringify({ id: r.id, exit: r.exit, seconds: r.seconds, tree, verdict: r.verdict, raw: r.raw })}\n`
      );
  };
  const held = new Set<string>();
  let running = 0;
  let soloRunning = false;
  const isSolo = (e: LockEntry): boolean => (e.mutex ?? []).some((m) => m.startsWith('tree:'));
  const pickable = (e: LockEntry): boolean =>
    isSolo(e) ? running === 0 : !soloRunning && (e.mutex ?? []).every((m) => !held.has(m));
  const worker = async (): Promise<void> => {
    while (pending.length > 0) {
      const at = pending.findIndex(pickable);
      if (at < 0) {
        await new Promise((r) => setTimeout(r, 500));
        continue;
      }
      const [e] = pending.splice(at, 1);
      running++;
      if (isSolo(e)) soloRunning = true;
      for (const m of e.mutex ?? []) held.add(m);
      try {
        onDone(await traceGate(e, view, { keepLogs: args.keepLogs, timeoutS: args.timeoutS }));
      } finally {
        running--;
        if (isSolo(e)) soloRunning = false;
        for (const m of e.mutex ?? []) held.delete(m);
      }
    }
  };
  await Promise.all(Array.from({ length: Math.max(1, args.jobs) }, worker));

  const paths = results.filter((r) => r.verdict.kind === 'paths');
  const wholeT = results.filter((r) => r.verdict.kind === 'whole-tree');
  const red = results.filter((r) => r.exit !== 0);
  const ignored = new Map<string, number>();
  for (const r of results)
    for (const [k, n] of r.ignored) ignored.set(k, (ignored.get(k) ?? 0) + n);
  if (args.json) {
    process.stdout.write(
      `${JSON.stringify(
        results.map((r) => ({ id: r.id, exit: r.exit, seconds: r.seconds, verdict: r.verdict })),
        null,
        2
      )}\n`
    );
  } else {
    for (const r of paths)
      if (r.verdict.kind === 'paths') console.log(`${r.id}\t${r.verdict.paths.join(' ')}`);
  }
  for (const [prefix, n] of ignored) {
    const why = IGNORED_PREFIXES.find((x) => x.prefix === prefix)?.why ?? '';
    console.error(`path-trace: ignored ${n} read(s) under ${prefix}: ${why}`);
  }
  for (const [id, why] of untraced) console.error(`path-trace: untraced ${id}: ${why}`);
  console.error(
    `path-trace: ${results.length} traced -> ${paths.length} with paths, ${wholeT.length} whole-tree ` +
      `(${red.length} red under the trace), ${untraced.size} untraced by rule${args.write ? '; written' : '; nothing written (no --write)'}`
  );
  if (results.length === 0) {
    console.error(
      'path-trace: traced ZERO gates; that is a selection that saw nothing, not a result.'
    );
    return 1;
  }
  return red.length > 0 && args.gates.length > 0 ? 1 : 0;
}

// ---------------------------------------------------------------------------
// selftest: the pure helpers, both directions, plus one real trace when strace is present
// ---------------------------------------------------------------------------

async function selftest(): Promise<number> {
  let bad = 0;
  let n = 0;
  const check = (ok: boolean, label: string): void => {
    n++;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
    if (!ok) bad++;
  };
  const root = '/r';
  const view: RepoView = {
    root,
    files: [
      'a/one.txt',
      'a/two.txt',
      'b/x.ts',
      'b/y.ts',
      'b/z.ts',
      'b/w.ts',
      'c/listed/k.txt',
      'c/listed/deep/l.txt',
      'd/[slug].astro',
      'package.json',
      'scripts/ci-runner/run.ts',
      ...Array.from({ length: 40 }, (_, i) => `e/f${i}.md`),
    ],
    gitlinks: ['private/sub'],
    gitDirs: ['/r/.git'],
  };

  // Parsing.
  const log = [
    'newfstatat(AT_FDCWD</r>, "a/one.txt", {st_mode=S_IFREG|0644, ...}, 0) = 0',
    'openat(AT_FDCWD</r/a>, "two.txt", O_RDONLY|O_CLOEXEC) = 3</r/a/two.txt>',
    'openat(AT_FDCWD</r>, "c/listed", O_RDONLY|O_DIRECTORY) = 4</r/c/listed>',
    'getdents64(4</r/c/listed>, 0x5a /* 3 entries */, 32768) = 80',
    'openat(AT_FDCWD</r>, "missing.txt", O_RDONLY) = -1 ENOENT (No such file or directory)',
    'chdir("/r/b")                           = 0',
    'execve("/usr/bin/node", ["node", "x.js"], 0x7ff /* 3 vars */) = 0',
    '--- SIGCHLD {si_signo=SIGCHLD} ---',
    '+++ exited with 0 +++',
  ].join('\n');
  const acc = parseStraceLog(log, root);
  check(
    acc.files.has('/r/a/one.txt'),
    'a stat relative to AT_FDCWD resolves against the decorated cwd'
  );
  check(acc.files.has('/r/a/two.txt'), 'an open records its resolved fd path');
  check(acc.listed.has('/r/c/listed'), 'getdents64 on a decorated fd records a listing');
  check(acc.files.has('/r/missing.txt'), 'a failed lookup is still recorded (inclusive direction)');
  check(
    acc.execs.some((a) => a.argv.join(' ') === 'node x.js' && a.cwd === '/r/b'),
    'execve argv is captured'
  );
  const rel = parseStraceLog(
    'access("rel.txt", F_OK) = 0\nchdir("sub") = 0\nstat("q", {}) = 0',
    '/r'
  );
  check(
    rel.files.has('/r/rel.txt') && rel.files.has('/r/sub/q'),
    'a cwd-relative path before any decoration falls back to the start cwd, and chdir moves it'
  );
  check(
    decodeCString('a\\"b\\\\c\\x41\\101') === 'a"b\\cAA',
    'C escapes decode (quote, backslash, hex, octal)'
  );
  check(decodeCString('\\303\\251') === 'é', 'octal UTF-8 bytes decode to one character');

  // Attribution and fold.
  const mk = (files: string[], listed: string[] = []): Access => ({
    files: new Set(files.map((f) => `/r/${f}`)),
    listed: new Set(listed.map((d) => (d === '' ? '/r' : `/r/${d}`))),
    execs: [],
  });
  const v1 = fold(attribute(mk(['a/one.txt', 'a/two.txt'], ['c/listed']), view), view);
  check(
    v1.kind === 'paths' && v1.paths.join(',') === 'a/one.txt,a/two.txt,c/listed/**',
    `CONTROL: two files read plus one listed directory give exactly those (got ${v1.kind === 'paths' ? v1.paths.join(',') : v1.reason})`
  );
  const v2 = fold(attribute(mk(['b/x.ts', 'b/y.ts', 'b/z.ts']), view), view);
  check(
    v2.kind === 'paths' && v2.paths.join(',') === 'b/**',
    'three of four files in a directory fold to dir/**'
  );
  const v3 = fold(attribute(mk(['b/x.ts', 'b/y.ts']), view), view);
  check(
    v3.kind === 'paths' && v3.paths.join(',') === 'b/x.ts,b/y.ts',
    'CONTROL: exactly half does not fold'
  );
  const v4 = fold(attribute(mk(['a/one.txt', '.git/index']), view), view);
  check(
    v4.kind === 'whole-tree' && v4.reason.includes('index'),
    'a .git/index read is whole-tree, reason naming the index'
  );
  const v4b = fold(attribute(mk(['a/one.txt', '.git/objects/pack/p.pack']), view), view);
  check(
    v4b.kind === 'whole-tree' && v4b.reason.includes('history'),
    'a .git/objects read is history'
  );
  const v4c = fold(
    attribute(mk(['a/one.txt', '.git', '.git/HEAD', '.git/config', '.git/info/exclude']), view),
    view
  );
  check(
    v4c.kind === 'paths' && v4c.paths.join(',') === 'a/one.txt',
    'CONTROL: discovery reads (.git, HEAD, config, info/exclude) leave the gate with paths'
  );
  const withExec = mk(['a/one.txt', '.git/HEAD']);
  withExec.execs.push({ argv: ['git', 'rev-parse', 'HEAD'], cwd: '/r/b' });
  const v4d = fold(attribute(withExec, view), view);
  check(
    v4d.kind === 'whole-tree' && v4d.reason.includes('rev-parse HEAD'),
    'HEAD read as a revision by argv is history'
  );
  check(
    classifyUntracked('node_modules/x/index.js', undefined, 0, false) === 'deps' &&
      classifyUntracked('.ci/cache/toolchain/uv/bin/ruff', { mtimeMs: 1, dir: false }, 5, false) ===
        'toolchain' &&
      classifyUntracked('a/__pycache__/m.pyc', { mtimeMs: 1, dir: false }, 5, false) ===
        'irrelevant' &&
      classifyUntracked('nope/missing.js', undefined, 5, false) === 'irrelevant' &&
      classifyUntracked('out/report.json', { mtimeMs: 9, dir: false }, 5, false) === 'irrelevant' &&
      classifyUntracked('.ci/cache/gate-durations.json', { mtimeMs: 1, dir: false }, 5, false) ===
        'cache' &&
      classifyUntracked('.ci/cache/mypy/3.12/x.json', { mtimeMs: 1, dir: false }, 5, false) ===
        'irrelevant' &&
      classifyUntracked('packages/www/dist/index.html', { mtimeMs: 1, dir: false }, 5, false) ===
        'build' &&
      classifyUntracked('packages/www/dist', { mtimeMs: 1, dir: true }, 5, true) === 'build' &&
      classifyUntracked('packages/www/dist', { mtimeMs: 1, dir: true }, 5, false) === 'irrelevant',
    'untracked classes: deps, toolchain, content cache, probe, self-written, cache state, build output (read and listed), a bare dir stat'
  );
  const buildAttr = {
    ...attribute(mk(['a/one.txt']), view),
    buildOutput: ['packages/www/dist/index.html'],
  };
  const vb = fold(buildAttr, view);
  check(
    vb.kind === 'whole-tree' && vb.reason.includes('no needs edge'),
    'build output read with no needs edge is whole-tree'
  );
  const vbn = fold(buildAttr, view, ['build:www']);
  check(
    vbn.kind === 'paths' && vbn.paths.join(',') === 'a/one.txt',
    'CONTROL: the same read with a needs edge keeps its paths'
  );
  const vc = fold(
    { ...attribute(mk(['a/one.txt']), view), cacheState: ['.ci/cache/x.json'] },
    view,
    ['build:www']
  );
  check(
    vc.kind === 'whole-tree' && vc.reason.includes('cache state'),
    'cache state is whole-tree even with a needs edge'
  );
  const foreign = mk(['a/one.txt']);
  foreign.execs.push(
    { argv: ['git', 'init', '-q', '/tmp/x'], cwd: '/r' },
    { argv: ['git', '-C', '/tmp/x', 'log'], cwd: '/r' },
    { argv: ['git', 'log'], cwd: '/tmp/y' }
  );
  const vf = fold(attribute(foreign, view), view);
  check(
    vf.kind === 'paths' && vf.paths.join(',') === 'a/one.txt',
    'CONTROL: git init, git -C elsewhere and git run in another cwd read another repository, not this one'
  );
  const relC = mk(['a/one.txt']);
  relC.execs.push({ argv: ['git', '-C', '..', 'log'], cwd: '/r/a' });
  const vr = fold(attribute(relC, view), view);
  check(
    vr.kind === 'whole-tree' && vr.reason.includes('history'),
    'a relative -C landing inside the root is this repository'
  );
  check(
    classifyGitArgv(['git', '-C', 'x', 'rev-parse', '--show-toplevel']) === 'discovery' &&
      classifyGitArgv(['/usr/bin/git', 'ls-files', '-z']) === 'index' &&
      classifyGitArgv(['git', 'log', '-1']) === 'history' &&
      classifyGitArgv(['git', 'frobnicate']) === 'history' &&
      classifyGitArgv(['node', 'x']) === 'discovery',
    'git argv classes: locate, index, history, unknown-is-history, not-git'
  );
  const v5 = fold(attribute(mk(['a/one.txt'], ['']), view), view);
  check(v5.kind === 'whole-tree' && v5.reason.includes('root'), 'listing the root is whole-tree');
  const v6 = fold(attribute(mk(view.files.filter((f) => f.startsWith('e/'))), view), view);
  check(
    v6.kind === 'whole-tree' && v6.reason.includes('%'),
    'reaching over 30% of the entries is whole-tree'
  );
  const v7 = fold(attribute(mk(['package.json', 'scripts/ci-runner/run.ts']), view), view);
  check(
    v7.kind === 'paths' && v7.paths.join(',') === 'package.json',
    'a read inside GLOBAL_INPUTS is dropped, an ordinary root file is kept'
  );
  const v8 = fold(attribute(mk(['scripts/ci-runner/run.ts']), view), view);
  check(
    v8.kind === 'whole-tree' && v8.reason.includes('no tracked file'),
    'zero non-global reads is whole-tree, never an empty paths'
  );
  const v9 = fold(attribute(mk(['d/[slug].astro']), view), view);
  check(
    v9.kind === 'paths' && v9.paths.join(',') === 'd/**',
    'a path with a forbidden glob char folds to its clean parent'
  );
  const vp = fold(attribute(mk(['a/one.txt'], ['private']), view), view);
  check(
    vp.kind === 'paths' && vp.paths.includes('private/**'),
    'a listing of a directory holding only gitlinks is a tracked listing, not build output'
  );
  const v10 = fold(attribute(mk(['private/sub/go.mod', 'a/one.txt']), view), view);
  check(
    v10.kind === 'paths' &&
      v10.paths.includes('private/sub') &&
      !v10.paths.includes('private/sub/**'),
    'a read inside a submodule names the gitlink'
  );
  const v11 = fold(
    attribute(mk(['a/one.txt', '.claude/hooks/profile/bash_env.sh', '/usr/lib/x.so']), view),
    view
  );
  check(
    v11.kind === 'paths' && v11.paths.join(',') === 'a/one.txt',
    'profiler hook and out-of-repo reads are not inputs'
  );

  // Text edits.
  const manifest = [
    'export const GATES = [',
    '  // >>> gen-manifest: region 1',
    '  {',
    "    id: 'g:a',",
    "    run: 'npm run g:a',",
    '    gate: true,',
    "    leaves: ['x.ts'],",
    '  },',
    '  {',
    "    id: 'g:b',",
    "    run: 'npm run g:b',",
    '    gate: true,',
    "    leaves: ['y.ts'],",
    '  },',
    '  {',
    "    id: 'g:c',",
    "    run: 'npm run g:c',",
    '    gate: true,',
    "    leaves: ['z.ts'],",
    '  },',
    '  // <<< gen-manifest: region 1',
    '  {',
    "    id: 'g:d',",
    "    run: 'npm run g:d',",
    '    gate: true,',
    "    paths: ['k'],",
    "    pathsOrigin: 'declared',",
    "    leaves: ['w.ts'],",
    '  },',
    '];',
  ].join('\n');
  const m1 = manifestWithPaths(manifest, 'g:b', ['a/one.txt', 'c/**']);
  const m1l = m1.split('\n');
  check(
    m1l.indexOf("    paths: ['a/one.txt', 'c/**'],") === m1l.indexOf("    id: 'g:b',") + 3 &&
      m1l.includes("    pathsOrigin: 'traced',"),
    'paths and pathsOrigin land before leaves in the named entry'
  );
  check(
    m1l.filter((l) => BEGIN_RE.test(l)).length === 2 &&
      m1l.filter((l) => END_RE.test(l)).length === 2 &&
      m1l[m1l.indexOf("    id: 'g:b',") - 2] === '  // <<< gen-manifest: region 1' &&
      m1.includes('  // >>> gen-manifest: region 2'),
    'a middle entry splits its generated region in two, renumbered'
  );
  const withProse = manifest.replace(
    "  {\n    id: 'g:c',",
    "  // prose about g:c\n  {\n    id: 'g:c',"
  );
  const mp = manifestWithPaths(withProse, 'g:b', ['a/one.txt']).split('\n');
  const proseAt = mp.indexOf('  // prose about g:c');
  check(
    mp[proseAt - 1] === '  },' && mp[proseAt + 1] === '  // >>> gen-manifest: region 2',
    'a prose line above the next entry stays outside the re-emitted region, as gen-manifest places it'
  );
  const m2 = manifestWithPaths(manifest, 'g:a', ['a/one.txt']);
  check(
    m2.split('\n')[1] === '  {' &&
      m2.includes("  // >>> gen-manifest: region 1\n  {\n    id: 'g:b'"),
    'a first entry moves the region start past it'
  );
  const m3 = manifestWithPaths(m1, 'g:b', ['b/**']);
  check(
    m3.includes("    paths: ['b/**'],") &&
      !m3.includes("'c/**'") &&
      m3.split("pathsOrigin: 'traced'").length === 2,
    'a re-trace replaces the earlier traced paths, never stacks them'
  );
  let refused = false;
  try {
    manifestWithPaths(manifest, 'g:d', ['x']);
  } catch (e) {
    refused = (e as Error).message.includes('declared');
  }
  check(refused, 'CONTROL: a declared paths set is refused, never overwritten');
  const long = pathsLines(Array.from({ length: 8 }, (_, i) => `packages/www/src/thing-${i}.ts`));
  check(
    long[0] === '    paths: [' && long.at(-1) === '    ],',
    'a long paths list breaks one glob per line'
  );
  const lockText = `${JSON.stringify([{ id: 'g:a', run: 'r', gate: true, leaves: ['x'], ci: {} }], null, 2)}\n`;
  const l1 = lockWithPaths(lockText, 'g:a', ['p/**']);
  check(
    Object.keys(JSON.parse(l1)[0]).join(',') === 'id,run,gate,paths,pathsOrigin,leaves,ci',
    'the lock keys follow the manifest literal order'
  );
  const rows: Record<string, LedgerRow> = {
    'g:a': {
      tracedAt: '2026-11-17T10:00Z',
      tree: 'abc',
      verdict: 'paths',
      reads: 2,
      listed: 1,
      coveragePct: 0.1,
      seconds: 3.2,
    },
    "g:'q": {
      tracedAt: '2026-11-17T10:00Z',
      tree: 'abc',
      verdict: 'whole-tree',
      reason:
        "reads git metadata (.git/index), and it's long enough to need a second line of its own",
      reads: 0,
      listed: 0,
      coveragePct: 100,
      seconds: 1,
    },
  };
  const back = parseLedger(renderLedger(rows));
  check(
    Object.keys(rows).every((k) => JSON.stringify(back[k]) === JSON.stringify(rows[k])) &&
      Object.keys(back).length === Object.keys(rows).length,
    'the ledger round-trips through render and parse'
  );

  // One real trace, when this host can trace.
  const refusal = traceRefusal();
  if (refusal === undefined) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-self-'));
    fs.mkdirSync(path.join(dir, 'in'));
    for (const f of ['in/a.txt', 'in/b.txt', 'in/c.txt', 'in/d.txt', 'other.txt'])
      fs.writeFileSync(path.join(dir, f), f);
    const r = await traceCommand(
      'cat in/a.txt >/dev/null; ls in >/dev/null; cd in && cat b.txt >/dev/null',
      dir
    );
    const real = fs.realpathSync(dir);
    check(
      r.exit === 0 &&
        r.access.files.has(`${real}/in/a.txt`) &&
        r.access.files.has(`${real}/in/b.txt`) &&
        r.access.listed.has(`${real}/in`) &&
        !r.access.files.has(`${real}/other.txt`) &&
        !r.access.files.has(`${real}/in/c.txt`),
      'a real strace run sees exactly the two cats and the ls, and not the untouched files'
    );
    const rr = await traceCommand('exit 3', dir);
    check(rr.exit === 3, 'CONTROL: the traced command exit code survives strace');
    fs.rmSync(dir, { recursive: true, force: true });
  } else {
    console.log(`  NOTE  no real trace on this host: ${refusal}`);
  }

  console.log(`path-trace selftest: ${n - bad}/${n} passed`);
  return bad === 0 ? 0 : 1;
}

if (isEntryPoint(import.meta.filename)) {
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP'] as const) {
    process.on(sig, () => {
      killLiveGroups();
      process.exit(130);
    });
  }
  main(process.argv.slice(2)).then(
    (code) => {
      process.exitCode = code;
    },
    (err: unknown) => {
      console.error(`path-trace: ${(err as Error).stack ?? String(err)}`);
      process.exitCode = 1;
    }
  );
}
