#!/usr/bin/env tsx
/**
 * path-trace: derive a gate's `paths` from what it actually reads (agent/plans/PLAN-ciquick-cpu.md A2).
 *
 * WHY. A gate with no `paths` hashes the whole tree (input-hash.ts `WHOLE_TREE_GLOB`), so any commit changes its input hash and it carries only across a byte-identical tree. On 2026-11-16, 349 of 397 lock entries declared none, and a receipt carried 23 gates while it ran 290. Hand-typed globs are the other failure: a glob that misses one file the gate reads makes carry UNSOUND, a stale green carried over a changed input.
 *
 * HOW. The gate's own `run` command executes once under `strace -ff -y --seccomp-bpf -e trace=%file,getdents,getdents64,fchdir,connect,clone,clone3,fork,vfork` (the fork family only so each child's starting cwd is known; `connect` so a gate that talks to the network is seen doing it). strace's own stderr lines are kept in their own file, apart from the gate's output, which reaches strace's stdout only (the traced shell runs `exec 2>&1` first). Every path a process opened, stat'ed, exec'ed or resolved, and every directory it listed, is mapped onto the tracked tree:
 *   - a tracked file read is kept as itself;
 *   - a listed tracked directory, the root included, goes to `lists` (a listing sees every name in it and no byte of any, so input-hash.ts hashes its tracked children's names); so does the nearest tracked directory above a lookup that found nothing, since a file added there would be found;
 *   - a `git ls-files` that prints only names (LS_FILES_NAME_FLAGS, a `--format` of only %(objectmode) and %(path)) gives `names: ['**']`, the tracked name set without its content, or with pathspecs the globs they reach relative to the exec's cwd (`*.sh` is `*.sh` plus `**\/*.sh`, a literal `p` is `p` or `p/**`); `--recurse-submodules` adds every gitlink to the content paths (PLAN-push-decoupling F2 B2, B3);
 *   - content read through git and narrowed by a pathspec (`ls-files -s -- <pathspec>`, `git diff --quiet <tracked file>`) is the content of what it names, not of every file (F2 B3, B4);
 *   - a history command whose argv names its revisions (`rev-parse HEAD`, `show origin/x:path`, `merge-base A B`, `log A..B`) is pinned to those plain ref names, written as `refs`, and its own ref and object reads are explained; an implicit HEAD, `describe`, `fetch`, `for-each-ref` or a shallow clone stays whole-tree history (F2 B5);
 *   - a directory with at least FOLD_MIN_FILES tracked files of which more than half were read becomes `dir/**`, or, when every read under it shares one extension, `dir/*.ext` plus `dir/**\/*.ext` (F2 B6);
 *   - a read inside a submodule names the bare gitlink path, which reaches the gitlink entry exactly as `<gitlink>/**` does (input-hash.ts `entryMatches`);
 *   - a path holding a glob metacharacter the hasher refuses (`?`, `[`, `{`, or `*`) folds to its nearest clean ancestor directory;
 *   - reads already inside GLOBAL_INPUTS are dropped, since every gate with `paths` hashes those anyway.
 *
 * WHEN THE ANSWER IS "WHOLE TREE", and it is written down with its reason rather than guessed: a gate that connects to an address that is neither loopback nor a unix socket (reason `network`: its verdict can move with nothing in the tree moving), a gate that touches git metadata (its verdict depends on history, on what files hold through the index, or on an index command other than a name-only `git ls-files`), reaches more than WHOLE_TREE_FRACTION of the tracked entries through its content globs (`lists` and `names` hash names, so they do not count toward that line), reads, lists and names nothing tracked at all, or exits non-zero under the trace (a red run may have stopped before reading everything). Under `--all-whole-tree`, non-gate entries and carry-exempt rows with no `kind` are not traced; an explicit `--gate <id>` traces the entry it names. A carry-exempt row WITH a kind (carry-exempt.json `network`, `history` or `cache`) is traced, and that kind waives its own whole-tree reason and no other (F2 B7).
 *
 * WHAT IT WRITES with `--write`, and nothing else: the entry in scripts/ci-runner/manifest.ts (each non-empty one of `paths`, `lists` and `names`, then `pathsOrigin: 'traced'`, placed before `leaves`, gen-manifest region markers repaired around it), the same keys in scripts/ci-runner/gates.lock.json, and one row per traced gate in scripts/ci-runner/trace-ledger.ts, which also records every whole-tree verdict with its reason. An entry whose `paths` a human declared (`pathsOrigin: 'declared'`) is refused, never overwritten, unless `--replace-declared` names that intent: the honesty gate (trace-honest.ts) judges a declared set, and this tool replaces one only when asked, with the traced set or, for a whole-tree verdict, with none.
 *
 * WHAT A TRACE CANNOT SEE, stated so a clean trace is not read as more than it is: a read by a process that is not a descendant (a daemon the gate talks to over a socket), a datagram sent with `sendto` to an address on a socket never connected, a read through io_uring (UV_USE_IO_URING=0 is set for the traced tree to keep libuv on plain syscalls), and a path the gate would read only on another branch of its logic. trace-honest.ts re-traces on every change to a gate's entry and on a rotation, and its sparse-clone mode is the independent check.
 *
 * Linux only, and strace is a hard requirement: a missing strace, or a kernel that refuses ptrace, is a loud failure with the fix in the message.
 *
 * Usage:
 *   tsx scripts/ci-runner/path-trace.ts --gate <id> [--gate <id> ...] [--write] [--replace-declared]
 *   tsx scripts/ci-runner/path-trace.ts --all-whole-tree [--jobs N] [--write] [--skip <id> ...]
 *   tsx scripts/ci-runner/path-trace.ts --selftest
 *   options: --root <dir> (default the repo), --keep-logs, --json, --no-seccomp (retry a trace without strace's seccomp-bpf filter, when strace's own lines name a seccomp problem)
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { isEntryPoint } from '../lib/entry-point.js';
import { policyPath } from '../lib/policy-paths.js';
import {
  CARRY_EXEMPT_REL,
  exemptRowsOf,
  FORBIDDEN_GLOB_CHARS,
  GLOBAL_INPUTS,
  matchGlob,
  nameInputProblem,
} from './input-hash.js';

export const REPO_ROOT = path.resolve(import.meta.dirname, '..', '..');
export const MANIFEST_REL = 'scripts/ci-runner/manifest.ts';
export const LOCK_REL = 'scripts/ci-runner/gates.lock.json';
export const LEDGER_REL = 'scripts/ci-runner/trace-ledger.ts';
export const TRACED_ORIGIN = 'traced';

/** strace's %file class is every syscall taking a path; the getdents pair are listings, fchdir moves the cwd by fd, connect names a peer address. */
export const TRACE_SYSCALLS = '%file,getdents,getdents64,fchdir,connect,clone,clone3,fork,vfork';
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
    why: 'the .git file, HEAD opened to find the repository, commondir, config and info/exclude: where the repository is and what it ignores, not what it holds. HEAD read as a revision is caught by its argv: `refs: [HEAD]` when the argv names it (`git rev-parse HEAD`), history when it is implicit (`git log -1`)',
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
  /** Every network peer a `connect` named that is neither loopback nor a unix socket, as `ip:port` or `[ip6]:port`. Optional so an Access built before `connect` was traced still reads as none. */
  network?: Set<string>;
  /** When the traced run started (epoch ms): an untracked file modified after it was written by the run itself. */
  startedMs?: number;
  /**
   * The pids that named each git-shaped path (GIT_SHAPED: under a `.git` component, or an index, ref, object or log path anywhere), keyed by the absolute path. `attribute` keeps only the paths under the view's own git directories, so a fixture repository's index or objects, read by a selftest's own `git -C /tmp/x`, never count as this repository's (F2 B1). Optional so an Access built without pids reads as unattributed: any name-only `git ls-files` then explains an index read, as before, and no history read is explained.
   */
  gitReaders?: Map<string, Set<number>>;
  /** The git-shaped paths some syscall FOUND (opened or stat'ed with success): a path in gitReaders and not here was only probed for, and found absent. Optional: absent, every git path counts as found. */
  gitFound?: Set<string>;
  /** The pids that LISTED each git-shaped directory, kept apart from gitReaders: every git process stats the bare `refs` directory to find the repository, and only the listing says who enumerated it. Optional: absent, no listing is a pinned exec's own. */
  gitListers?: Map<string, Set<number>>;
}

export interface Exec {
  argv: string[];
  cwd?: string;
  /** The process that ran it; a process keeps its pid across the exec, so its later reads are the program's own. */
  pid?: number;
}

export function emptyAccess(): Access {
  return { files: new Set(), listed: new Set(), execs: [], network: new Set() };
}

/** Whether an IPv4 or IPv6 address (a v4-mapped one included) is this host: 127/8, ::1, or the unspecified address, which Linux routes to the host. */
export function isLoopback(ip: string): boolean {
  const v4 = ip.toLowerCase().replace(/^::ffff:/, '');
  if (/^\d+\.\d+\.\d+\.\d+$/.test(v4)) return v4.startsWith('127.') || v4 === '0.0.0.0';
  return /^(0*:){2,7}0*1$|^::1$|^::$/.test(ip.toLowerCase());
}

/** A connect to port 53 is a name lookup even on loopback: systemd-resolved (127.0.0.53), Docker's embedded resolver (127.0.0.11) and a local dnsmasq may each forward upstream (a dnsmasq can also answer from its hosts file or cache), and from the trace alone the two cannot be told apart, so the verdict is taken to depend on the network (PLAN-two-track-merge-dev A1). */
const DNS_PORT = '53';

/**
 * The network peer of one `connect` line's arguments, or undefined for a peer on this host: loopback (except port 53, see DNS_PORT), a unix socket, netlink, AF_UNSPEC (a UDP disconnect). Any attempt counts, whatever the result: a refused or unreachable peer still made the verdict depend on the network.
 */
export function networkPeer(args: string): string | undefined {
  const v4 = /sa_family=AF_INET,.*?sin_port=htons\((\d+)\).*?sin_addr=inet_addr\("([^"]+)"\)/.exec(
    args
  );
  const fam = /sa_family=(AF_INET6?)\b/.exec(args);
  if (v4 !== null) return isLoopback(v4[2]) && v4[1] !== DNS_PORT ? undefined : `${v4[2]}:${v4[1]}`;
  const v6 = /sa_family=AF_INET6,.*?sin6_port=htons\((\d+)\).*?inet_pton\(AF_INET6, "([^"]+)"/.exec(
    args
  );
  if (v6 !== null)
    return isLoopback(v6[2]) && v6[1] !== DNS_PORT ? undefined : `[${v6[2]}]:${v6[1]}`;
  // An internet-family connect whose address strace printed in a shape the patterns above miss is still a connect: dropping it would keep a path-only verdict for a gate that reached the network.
  if (fam !== null) return `${fam[1]}:unparsed`;
  return undefined;
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
 * strace output into the paths it named: one `-ff` per-process log, or a `-f` log whose lines carry a pid prefix. `rootCwd` is the cwd of the traced command; every other process starts in the cwd its parent had when it forked (see straceParser).
 */
export function parseStraceLog(
  text: string,
  rootCwd: string,
  into: Access = emptyAccess()
): Access {
  const p = straceParser(rootCwd, into);
  for (const line of text.split('\n')) p.line(line);
  return p.end();
}

interface ProcState {
  pid: number;
  cwd?: string;
  /** The cwd this process started in: its parent's at fork, or the root's for a process whose fork the trace never showed. */
  start: string;
  /** Relative paths named before the cwd was known, each with whether its syscall found it. */
  pending: { s: string; found: boolean }[];
  execsWithoutCwd: Exec[];
  /** The processes sharing this one's cwd: itself, and every clone made with CLONE_FS or CLONE_THREAD. A chdir by any moves them all. */
  peers: Set<ProcState>;
  /** The flags of this process's last clone line, kept for the `<... clone resumed>` line that carries only the result. */
  cloneFlags?: string;
}

const FORKS = /^(clone|clone3|fork|vfork)$/;

/** A path that may be a git index, ref, object or log file: below a `.git` component, or shaped like one under a bare git directory. Over-inclusive on purpose: `attribute` keeps only the paths inside the view's own git directories. */
const GIT_SHAPED =
  /(^|\/)\.git(\/|$)|(^|\/)(index|sharedindex\.[^/]*|packed-refs|shallow|[A-Z_]*HEAD)$|\/(objects|refs|logs)(\/|$)/;

/**
 * The stateful line parser, so a large log streams in chunks with each process's cwd intact. The cwd is PER PID: a `chdir` or `fchdir` moves only the process that made it, and a successful clone, clone3, fork or vfork gives the new pid the cwd its parent had at that moment. `line(l, pid)` takes the pid from the argument (a `-ff` log, whose file name holds it) or from the line's own prefix (a `-f` log). For `-ff`, feed the logs in ascending pid order so a parent's fork is seen before its child's lines; a child seen first starts from the root cwd, and its start is corrected when the fork arrives, for every relative path it had not yet resolved.
 */
export function straceParser(
  rootCwd: string,
  into: Access = emptyAccess()
): { line: (l: string, pid?: number) => void; end: () => Access } {
  const procs = new Map<number, ProcState>();
  const proc = (pid: number): ProcState => {
    let st = procs.get(pid);
    if (st === undefined) {
      st = { pid, start: rootCwd, pending: [], execsWithoutCwd: [], peers: new Set() };
      st.peers.add(st);
      procs.set(pid, st);
    }
    return st;
  };
  /** A git-shaped path a process named or listed: its pid, and whether the syscall found it, so `attribute` can judge whether the git command that explains it (a name-only `git ls-files`, a history command whose refs are known) is the process that made it, and whether a probe found state or its absence. */
  const addGit = (st: ProcState, p: string, found: boolean): void => {
    if (!GIT_SHAPED.test(p)) return;
    into.gitReaders ??= new Map();
    // Kept beside gitReaders from the first git path on, so a trace whose every git lookup failed says so instead of reading as "all found".
    into.gitFound ??= new Set();
    let pids = into.gitReaders.get(p);
    if (pids === undefined) {
      pids = new Set();
      into.gitReaders.set(p, pids);
    }
    pids.add(st.pid);
    if (found) into.gitFound.add(p);
  };
  const addFile = (st: ProcState, p: string, found = true): void => {
    into.files.add(p);
    addGit(st, p, found);
  };
  const setCwd = (st: ProcState, cwd: string): void => {
    for (const peer of st.peers) peer.cwd = cwd;
  };
  /** A chdir or fchdir: every peer that never learned its cwd had named its relative paths against its start cwd, so those resolve there, not against the new directory; then the whole group moves. */
  const chdirTo = (st: ProcState, cwd: string): void => {
    for (const peer of st.peers) {
      if (peer.cwd !== undefined) continue;
      for (const p of peer.pending.splice(0))
        addFile(peer, path.posix.resolve(peer.start, p.s), p.found);
      for (const e of peer.execsWithoutCwd.splice(0)) e.cwd = peer.start;
    }
    setCwd(st, cwd);
  };
  const forked = (parent: ProcState, child: number, flags?: string): void => {
    const st = proc(child);
    if (st.cwd === undefined) st.start = parent.cwd ?? parent.start;
    if (flags !== undefined && /\bCLONE_(FS|THREAD)\b/.test(flags) && st.peers.size === 1) {
      st.cwd = parent.cwd;
      st.peers = parent.peers;
      st.peers.add(st);
    }
  };
  const line = (raw: string, pidArg?: number): void => {
    let l = raw;
    let pid = pidArg ?? 0;
    const pre = /^(\d+)\s+(.*)$/.exec(l);
    if (pidArg === undefined && pre !== null) {
      pid = Number(pre[1]);
      l = pre[2];
    }
    const st = proc(pid);
    const resumed = /^<\.\.\. (\w+) resumed>.*\)\s+=\s+(\d+)/.exec(l);
    if (resumed !== null) {
      if (FORKS.test(resumed[1])) forked(st, Number(resumed[2]), st.cloneFlags);
      return;
    }
    const m = /^(\w+)\((.*)$/.exec(l);
    if (m === null) return;
    const name = m[1];
    const rest = m[2];
    if (name === 'connect') {
      // A socket address, not a path: its quoted sun_path must not reach the path arguments below.
      const peer = networkPeer(rest);
      if (peer !== undefined) {
        into.network ??= new Set();
        into.network.add(peer);
      }
      return;
    }
    const decorations = [...rest.matchAll(DECORATED)].map((d) => ({
      fd: d[1],
      path: decodeCString(d[2]),
      at: d.index ?? 0,
    }));
    for (const d of decorations) if (d.fd === 'AT_FDCWD') setCwd(st, d.path);
    if (st.cwd !== undefined && st.pending.length > 0) {
      for (const p of st.pending.splice(0)) addFile(st, path.posix.resolve(st.cwd, p.s), p.found);
    }
    if (st.cwd !== undefined) for (const e of st.execsWithoutCwd.splice(0)) e.cwd = st.cwd;
    const retMatch = /\)\s+=\s+(-?\d+)(?:<((?:[^>\\]|\\.)*)>)?/.exec(rest);
    const ok = retMatch !== null && !retMatch[1].startsWith('-');
    // A lookup that found nothing (ENOENT, ENOTDIR) probed for the path's absence; any other result, an unfinished line included, counts as found, the direction that keeps a git read whole-tree.
    const found = ok || !/\)\s+=\s+-1\s+(ENOENT|ENOTDIR)\b/.test(rest);
    if (FORKS.test(name)) {
      const flags = /flags=([A-Za-z0-9_|]+)/.exec(rest)?.[1];
      st.cloneFlags = flags;
      if (ok && retMatch !== null) forked(st, Number(retMatch[1]), flags);
      return;
    }
    if (name.startsWith('getdents')) {
      const d = decorations[0];
      if (d !== undefined && d.fd !== 'AT_FDCWD') {
        const dir = path.posix.normalize(d.path);
        into.listed.add(dir);
        if (GIT_SHAPED.test(dir)) {
          into.gitListers ??= new Map();
          let pids = into.gitListers.get(dir);
          if (pids === undefined) {
            pids = new Set();
            into.gitListers.set(dir, pids);
          }
          pids.add(st.pid);
        }
      }
      return;
    }
    if (name === 'fchdir') {
      if (ok && decorations[0] !== undefined) chdirTo(st, decorations[0].path);
      return;
    }
    if (retMatch?.[2] !== undefined && /^(open|openat|openat2|creat)$/.test(name)) {
      addFile(st, path.posix.normalize(decodeCString(retMatch[2])));
    }
    const args = retMatch === null ? rest : rest.slice(0, retMatch.index);
    const strings = [...args.matchAll(QUOTED)].map((q) => ({
      s: decodeCString(q[1]),
      at: q.index ?? 0,
    }));
    for (const idx of pathArgIndexes(name)) {
      const str = strings[idx];
      if (str === undefined || str.s === '') continue;
      let base = st.cwd;
      if (takesDirfd(name)) {
        // The dirfd is the last decoration before this string.
        const d = decorations.filter((x) => x.at < str.at).pop();
        if (d !== undefined) base = d.path;
      }
      if (path.posix.isAbsolute(str.s)) addFile(st, path.posix.normalize(str.s), found);
      else if (base !== undefined) addFile(st, path.posix.resolve(base, str.s), found);
      else st.pending.push({ s: str.s, found });
    }
    if (name === 'chdir' && ok && strings[0] !== undefined) {
      // Paths seen before this process's first chdir belong to its start cwd, not the new one, and so do a peer's.
      chdirTo(st, path.posix.resolve(st.cwd ?? st.start, strings[0].s));
    }
    if ((name === 'execve' || name === 'execveat') && ok) {
      const argv = /\[((?:"(?:[^"\\]|\\.)*"(?:, )?)*)\]/.exec(args);
      if (argv !== null) {
        const ex: Exec = {
          argv: [...argv[1].matchAll(QUOTED)].map((q) => decodeCString(q[1])),
          cwd: st.cwd,
          pid,
        };
        into.execs.push(ex);
        if (st.cwd === undefined) st.execsWithoutCwd.push(ex);
      }
    }
  };
  const end = (): Access => {
    for (const st of procs.values()) {
      for (const p of st.pending.splice(0)) addFile(st, path.posix.resolve(st.start, p.s), p.found);
      for (const e of st.execsWithoutCwd.splice(0)) e.cwd = st.start;
    }
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
  /** The record set (record-paths.json) a traced set may not name; absent in a hand-built view, which then names none. */
  records?: RecordGlob[];
}

/** One record of record-paths.json as check:ci-record-paths cites it: the literal prefix of its glob, its probe paths, its excepted globs. */
export interface RecordGlob {
  glob: string;
  prefix: string;
  probes: string[];
  except: string[];
}

/** check_record_paths.py literal_prefix: the directory before the first wildcard, or a wildcard-free glob whole. */
export function recordPrefix(glob: string): string {
  const head = glob.split(/[*?[{]/, 1)[0];
  if (head === glob) return glob;
  return head.includes('/') ? head.slice(0, head.lastIndexOf('/')) : head;
}

export function readRecordGlobs(root: string): RecordGlob[] {
  const p = policyPath('record-paths.json', root);
  if (!fs.existsSync(p))
    throw new Error(
      `${p} is missing: without the record set the fold's record-path rule cannot apply, and a traced set could cite a record unchecked`
    );
  const doc = JSON.parse(fs.readFileSync(p, 'utf8')) as {
    records: Array<{ glob: string; probes?: string[]; except?: string[] }>;
  };
  return doc.records.map((r) => ({
    glob: r.glob,
    prefix: recordPrefix(r.glob),
    probes: r.probes ?? [],
    except: r.except ?? [],
  }));
}

/**
 * The record globs a traced set's tokens would cite once manifest.ts carries them, read the way check:ci-record-paths reads a gate's code: a token naming a record's literal prefix or a path below it (the cite tier), or a glob reaching one of its probes (the glob tier), unless an excepted glob covers it. A cited record makes every gate that reads the manifest an undeclared reader of it, so a record-only commit could no longer advance a receipt (review 22efb11e).
 */
export function recordCitations(
  tokens: readonly string[],
  records: readonly RecordGlob[]
): string[] {
  const hit = new Set<string>();
  for (const rec of records)
    for (const t of tokens) {
      if (rec.except.some((x) => matchGlob(x, t))) continue;
      const cites = t === rec.prefix || t.startsWith(`${rec.prefix}/`);
      const reaches = t.includes('*') && rec.probes.some((p) => matchGlob(t, p));
      if (cites || reaches) hit.add(rec.glob);
    }
  return [...hit].sort(byteOrder);
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
  // A relative --git-common-dir is relative to the cwd, and strace reports realpaths: resolve against the real root.
  const realRoot = fs.realpathSync(root);
  for (const flag of ['--absolute-git-dir', '--git-common-dir']) {
    const r = spawnSync('git', ['rev-parse', flag], { cwd: root, encoding: 'utf8' });
    if (r.status === 0 && r.stdout.trim() !== '')
      gitDirs.add(path.resolve(realRoot, r.stdout.trim()));
  }
  return { root: realRoot, files, gitlinks, gitDirs: [...gitDirs], records: readRecordGlobs(root) };
}

export interface Attribution {
  reads: Set<string>;
  gitlinkReads: Set<string>;
  /** Tracked directories listed, and the nearest tracked directory above a lookup that found nothing (a new file there would be found); '' is the repository root. */
  listed: Set<string>;
  /** Evidence that the verdict depends on git HISTORY no named ref pins (objects, refs, a history subcommand): every such exec and read, deduplicated, with no cap, so a pinned exec beside an unpinned one can never hide it (F2 B5). */
  gitHistory: string[];
  /** Evidence that the gate enumerates the tracked file list through the index (`git ls-files` and kin). */
  gitIndex: string[];
  /** Evidence that the gate reads what tracked files hold through the index (`git ls-files -s` and kin). A content use also counts as an index use, so gitIndex is never empty when this is not; gitIndex keeps at most 3 entries, so a content use after three index uses is shown here alone. Optional so an Attribution built by hand (trace-honest.ts selftest) needs no change. */
  gitContent?: string[];
  /** Network peers the gate connected to (neither loopback nor a unix socket), sorted. Optional for the same reason. */
  network?: string[];
  /** Evidence that the gate reads the tracked NAME set through `git ls-files` with name-only flags: `names: ['**']`, not whole-tree. Optional for the same reason. */
  gitNames?: string[];
  /** The `names` globs those scans fold to: `**` for a scan with no pathspec, the pathspec globs otherwise (F2 B3). Optional for the same reason: a hand-built Attribution with gitNames and no globs reads as `['**']`. */
  gitNameGlobs?: string[];
  /** Content globs read through git (`ls-files -s -- <pathspec>`, `git diff --quiet <tracked file>`, `git diff REV -- <pathspec>`): the lock entry's `paths` must cover them (F2 B3, B4). Optional for the same reason. */
  gitContentGlobs?: string[];
  /** The plain ref names every history exec was pinned to (F2 B5): the lock entry's `refs`. A history exec no ref pins is in gitHistory instead. Optional for the same reason. */
  gitRefs?: string[];
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

/** A submodule's git directory sits at `modules/<name>/` under its superproject's, and `<name>` may hold slashes but never a component named like a git directory entry (objects, refs, logs), so `modules/x/refs/heads/objects` is a branch of x, not x's objects directory; every git-file rule below applies inside one exactly as at the top. */
const SUBMODULE_GITDIR = '(?:modules/(?:(?!(?:objects|refs|logs)/)[^/]+/)+)?';
/** Git files whose content is history: any read of one makes the verdict move with commits, not with file bytes. The submodule prefix is the greedy `modules/.+/` here, not SUBMODULE_GITDIR: a name that is itself `objects`, `refs` or `logs` (`modules/objects/objects/ab/cd`) is ambiguous, and the ambiguity resolves to history, the whole-tree direction. The discovery exemption below keeps the strict prefix, the narrow direction. */
export const GIT_HISTORY_FILE = new RegExp(
  '^(?:modules/.+/)?(?:(objects|refs|logs)(/|$)|(packed-refs|FETCH_HEAD|ORIG_HEAD|MERGE_HEAD|CHERRY_PICK_HEAD|shallow)$)'
);
/**
 * Git paths that look like history but are discovery: git's own repository check (`setup.c` is_git_directory) is an `access(X_OK)` on the bare `objects` and `refs` directories, and opening `objects/info/alternates` says where more objects live, not what any of them hold. A LISTING of `objects` or `refs` enumerates history, so the exemption is for a path read, never a listing.
 */
export const GIT_DISCOVERY_FILE = new RegExp(
  `^${SUBMODULE_GITDIR}(objects|refs|objects/info/alternates)$`
);
/** The index: the tracked name set. */
export const GIT_INDEX_FILE = new RegExp(`^${SUBMODULE_GITDIR}(index|sharedindex\\..*)$`);
/** Subcommands that read only the index and the worktree. `status` is not one: it compares the index with HEAD, which is history. */
const GIT_INDEX_CMDS = new Set([
  'ls-files',
  'check-ignore',
  'check-attr',
  'grep',
  'diff-files',
  'submodule',
]);
/** `git ls-files` flags that print what a tracked file HOLDS (its staged blob, its line endings, whether it differs from the worktree), not only its name. `-u` forces `--stage`. */
const LS_FILES_CONTENT = new Set([
  '-s',
  '--stage',
  '--eol',
  '-m',
  '--modified',
  '-d',
  '--deleted',
  '-u',
  '--unmerged',
]);
/** `git ls-files` flags that only choose WHICH names it prints and how they are spelled. Untracked names (`-o`, `-i`, `-k`) are outside every input hash, the whole-tree one included, so they cost `names` nothing whole-tree would have bought. `--recurse-submodules` is read apart (lsFilesRead): it prints the names inside each submodule, which the root's name set does not hold, so `attribute` adds every gitlink to the content paths, whose commit moves with any committed change inside it (review bab2c5c8.1, F2 B2). */
const LS_FILES_NAME_FLAGS = new Set([
  '-z',
  '-c',
  '--cached',
  '-o',
  '--others',
  '-i',
  '--ignored',
  '-k',
  '--killed',
  '--exclude-standard',
  '--directory',
  '--no-empty-directory',
  '--full-name',
  '--error-unmatch',
  '--sparse',
  '--deduplicate',
]);
/** Name-shaping `git ls-files` flags that take the next argument as their value (a pattern or a file the trace sees read). */
const LS_FILES_NAME_VALUE_FLAGS = new Set([
  '-x',
  '--exclude',
  '-X',
  '--exclude-from',
  '--exclude-per-directory',
]);
/** `git diff` flags that bring a revision in: the comparison is against HEAD or a merge base, which is history. */
const DIFF_REVISION_FLAGS = new Set(['--cached', '--staged', '--merge-base']);
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

/**
 * `content` reads what tracked files hold through the index; it also enumerates the index's name set, so every content use is an index use as well. `names` is a `git ls-files` that prints only names (LS_FILES_NAME_FLAGS): the tracked name set, which `names: ['**']` hashes without any file's bytes. `index` is every other index use, still whole-tree.
 */
export type GitUse = 'history' | 'content' | 'index' | 'names' | 'discovery';

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
  // `remote -v` and `remote get-url` read the config; `remote show` or `update` talk to the remote, so only these two shapes are discovery.
  if (sub === 'remote')
    return rest.every((a) => a === '-v' || a === '--verbose') || rest[0] === 'get-url'
      ? 'discovery'
      : 'history';
  if (sub === 'diff') return diffUse(rest);
  if (sub === 'ls-files') return lsFilesRead(rest).use;
  if (GIT_INDEX_CMDS.has(sub)) return 'index';
  return 'history';
}

/** `--format` atoms that print only what `names` hashes (`name\t<mode>\t<path>`): the mode and the path. Any other atom (objectname, stage, eolinfo) prints what a file holds. `%%` and `%xNN` are literal text. */
const LS_FILES_NAME_ATOMS = new Set(['objectmode', 'path']);

/** Whether an `ls-files --format` value prints only names: every `%(atom)` is objectmode or path, and no other `%` directive appears. */
export function formatIsNames(fmt: string): boolean {
  const rest = fmt.replace(/%%|%x[0-9a-fA-F]{2}/g, '');
  for (const m of rest.matchAll(/%(\(([^)]*)\))?/g))
    if (m[2] === undefined || !LS_FILES_NAME_ATOMS.has(m[2])) return false;
  return true;
}

/** One `git ls-files` argv, read flag by flag. */
export interface LsFilesRead {
  use: GitUse;
  /** Pathspecs: the positionals, and everything after `--`. */
  pathspecs: string[];
  /** `--recurse-submodules`: the names inside every submodule too (F2 B2). */
  recurse: boolean;
  /** A flag outside every known set: the read stays whole-tree whatever its pathspecs narrow. */
  unknown: boolean;
}

/**
 * What one `git ls-files` reads: `content` when any flag prints what a file holds (a `--format` naming only %(objectmode) and %(path) does not, F2 B3), `history` for `--with-tree`, `names` when every flag only shapes the name list, else `index`, whole-tree: an unknown flag is not assumed harmless. `--recurse-submodules` is a name flag (F2 B2): `attribute` adds every gitlink, whose commit moves with any change inside the submodule. Pathspecs narrow a names or content read; `attribute` folds them against the tree (F2 B3).
 */
export function lsFilesRead(rest: readonly string[]): LsFilesRead {
  const pathspecs: string[] = [];
  let content = false;
  let unknown = false;
  let recurse = false;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === '--') {
      pathspecs.push(...rest.slice(i + 1));
      break;
    }
    if (a.startsWith('--with-tree')) return { use: 'history', pathspecs, recurse, unknown };
    if (a === '--format' || a.startsWith('--format=')) {
      const fmt = a === '--format' ? (rest[++i] ?? '') : a.slice('--format='.length);
      if (!formatIsNames(fmt)) content = true;
      continue;
    }
    if (LS_FILES_NAME_VALUE_FLAGS.has(a)) {
      i++;
      continue;
    }
    if (/^--(exclude|exclude-from|exclude-per-directory)=/.test(a)) continue;
    if (!a.startsWith('-') || a === '-') {
      pathspecs.push(a);
      continue;
    }
    if (a === '--recurse-submodules') {
      recurse = true;
      continue;
    }
    if (LS_FILES_CONTENT.has(a)) content = true;
    else if (LS_FILES_NAME_FLAGS.has(a)) continue;
    else if (/^-[a-zA-Z]{2,}$/.test(a)) {
      for (const c of a.slice(1)) {
        if ('smdu'.includes(c)) content = true;
        else if (!'zcoik'.includes(c)) unknown = true;
      }
    } else unknown = true;
  }
  return { use: content ? 'content' : unknown ? 'index' : 'names', pathspecs, recurse, unknown };
}

/** One `git diff` argv: its positionals before `--`, its pathspecs after, and whether a flag brings a revision in. */
export interface DiffRead {
  positionals: string[];
  pathspecs: string[];
  revisionFlag: boolean;
}

export function diffRead(rest: readonly string[]): DiffRead {
  const out: DiffRead = { positionals: [], pathspecs: [], revisionFlag: false };
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === '--') {
      out.pathspecs.push(...rest.slice(i + 1));
      break;
    }
    if (DIFF_REVISION_FLAGS.has(a) || a === '--no-index') out.revisionFlag = true;
    else if (!a.startsWith('-')) out.positionals.push(a);
  }
  return out;
}

/**
 * `git diff` with no revision compares the worktree with the index: it reads what the tracked files hold, so it is `content`, like `ls-files -m`. A positional argument before `--` may be a revision (git disambiguates against the tree at run time, and this argv-only classifier cannot), so it counts as history, the conservative direction; so do the flags that compare against HEAD. `attribute`, which holds the tree, reads a positional naming a tracked file as that file's content (F2 B4).
 */
function diffUse(rest: readonly string[]): GitUse {
  const d = diffRead(rest);
  return d.revisionFlag || d.positionals.length > 0 ? 'history' : 'content';
}

/** History subcommands whose answer is fixed by the commits their argv names, once no flag reaches past them (HISTORY_UNPINNED). `describe`, `fetch`, `for-each-ref`, `show-ref`, `status` and `blame` are not here: they read every ref, the network, the worktree, or an implicit HEAD, so they stay whole-tree history. */
const REF_PINNED_CMDS = new Set([
  'rev-parse',
  'log',
  'show',
  'rev-list',
  'merge-base',
  'cat-file',
  'ls-tree',
  'diff-tree',
  'diff',
]);
/** Flags that make a history answer depend on more than the named commits: every ref (`--all`, `--branches`, decorations, notes), the reflog, the clock (`--since`, a relative date), stdin, a symbolic name (`--abbrev-ref` prints the branch, which moves with no sha moving), or the index (`--cached`). */
const HISTORY_UNPINNED =
  /^(--all|--branches|--tags|--remotes|--glob|--exclude|--reflog|-g|--walk-reflogs|--decorate|--decorate-refs|--decorate-refs-exclude|--source|--since|--until|--after|--before|--max-age|--min-age|--since-as-filter|--bisect|--stdin|--not|--fork-point|--abbrev-ref|--symbolic|--symbolic-full-name|--simplify-by-decoration|--notes|--show-notes|--standard-notes|--batch|--batch-check|--batch-command|--batch-all-objects|--cached|--staged|--merge-base|--no-index|--alternate-refs|--indexed-objects|--relative-date)(=.*)?$/;
/** History flags that take the NEXT argument as their value, so it is never read as a revision. */
const HISTORY_VALUE_FLAGS = new Set([
  '-n',
  '--max-count',
  '--skip',
  '--format',
  '--pretty',
  '--date',
  '-L',
  '-S',
  '-G',
  '-O',
  '--grep',
  '--author',
  '--committer',
  '-U',
  '--unified',
  '--abbrev',
]);
/** Pretty-format placeholders that print ref names, the reflog, notes, or a date relative to now. */
const UNPINNED_FORMAT = /%(d|D|S|g[dDsnNeE]|N|ar|cr|ah|ch)/;
/** The object types a `git cat-file` first positional may name. */
const CAT_FILE_TYPES = new Set(['blob', 'tree', 'commit', 'tag']);
/** A full object id names one immutable commit: it pins history with no ref. */
const FULL_OID = /^([0-9a-f]{40}|[0-9a-f]{64})$/;

/**
 * The plain ref names one revision expression depends on, or undefined when no ref pins it: `HEAD` and `@`, `origin/x`, `A..B` and `A...B` (both sides, an empty side being HEAD), `REV:path` (the REV), with `^`, `~N`, `^N` and `^{type}` suffixes dropped, since a ref's sha fixes every ancestor. A full object id pins itself and names no ref. A reflog step (`@{1}`), an index path (`:path`) or anything `nameInputProblem` refuses as a ref name is undefined.
 */
export function refsOfRevision(expr: string): string[] | undefined {
  let e = expr.startsWith('^') ? expr.slice(1) : expr;
  const colon = e.indexOf(':');
  if (colon === 0) return undefined;
  if (colon > 0) e = e.slice(0, colon);
  if (e.includes('@{')) return undefined;
  const sides = e.includes('...') ? e.split('...') : e.includes('..') ? e.split('..') : [e];
  if (sides.length > 2) return undefined;
  const out: string[] = [];
  for (const side of sides) {
    let r = side === '' ? 'HEAD' : side;
    r = r.replace(/(\^\{[^}]*\}|\^-?\d*|~\d*|\^[@!])+$/, '');
    if (r === '@') r = 'HEAD';
    if (FULL_OID.test(r)) continue;
    if (r === '' || nameInputProblem({ id: 'x', refs: [r] }) !== null) return undefined;
    out.push(r);
  }
  return out;
}

/**
 * git's ref lookup rules for a name (refs.c `ref_rev_parse_rules`, measured on git 2.53 under strace for `git diff --quiet src/keep.txt`): the files a positional's "is this a revision?" probe reads under the git directory, beside packed-refs. A `git diff <tracked file>` that read only these for its positional, and then took it as a path, read no history. The stated limit: a ref created later with the exact name of a tracked file would make git refuse the argument as ambiguous, and no input hash moves for that.
 */
export const REF_PROBES: ReadonlyArray<(name: string) => string> = [
  (n) => `refs/${n}`,
  (n) => `refs/tags/${n}`,
  (n) => `refs/heads/${n}`,
  (n) => `refs/remotes/${n}`,
  (n) => `refs/remotes/${n}/HEAD`,
];

/** What a ref-pinned history exec reads: the refs it names, whether it compares one of them with the worktree (`git diff REV`), and the pathspecs narrowing that comparison. */
export interface HistoryPin {
  refs: string[];
  onDisk: boolean;
  pathspecs: string[];
}

/**
 * Pins one history exec to the refs its argv names (F2 B5), or says why it cannot be pinned: a subcommand outside REF_PINNED_CMDS, a flag in HISTORY_UNPINNED, a format printing refs or relative dates, no revision named at all (an implicit HEAD is not read off the argv, so `git log -1` stays history), or a revision no plain ref name pins. `isPath` says whether a positional is a tracked path, which git takes as a pathspec rather than a revision.
 */
export function pinHistory(
  sub: string,
  rest: readonly string[],
  isPath: (p: string) => boolean
): HistoryPin | { unpinned: string } {
  if (!REF_PINNED_CMDS.has(sub)) return { unpinned: `${sub} is not pinned by named refs` };
  const refs = new Set<string>();
  const pathspecs: string[] = [];
  let revs = 0;
  let ranged = false;
  let sawType = false;
  for (let i = 0; i < rest.length; i++) {
    const a = rest[i];
    if (a === '--') {
      pathspecs.push(...rest.slice(i + 1));
      break;
    }
    if (a.startsWith('-') && a !== '-') {
      if (HISTORY_UNPINNED.test(a)) return { unpinned: `${a} reaches past the named commits` };
      const eq = a.indexOf('=');
      const flag = eq < 0 ? a : a.slice(0, eq);
      const value =
        eq >= 0 ? a.slice(eq + 1) : HISTORY_VALUE_FLAGS.has(flag) ? (rest[++i] ?? '') : '';
      if ((flag === '--format' || flag === '--pretty') && UNPINNED_FORMAT.test(value))
        return { unpinned: `${flag} prints ref names, the reflog, notes or a relative date` };
      if (flag === '--date' && /^(relative|human|auto)/.test(value))
        return { unpinned: `--date ${value} prints a date relative to now` };
      if (
        sub === 'rev-parse' &&
        !/^(--verify|-q|--quiet|--short|--sq|--end-of-options)$/.test(flag) &&
        !REV_PARSE_LOCATE.test(a)
      )
        return { unpinned: `rev-parse ${a} is not a plain revision lookup` };
      if (sub === 'cat-file' && !/^-[ptse]$/.test(a))
        return { unpinned: `cat-file ${a} is not a single-object read` };
      continue;
    }
    if (sub === 'cat-file' && !sawType && CAT_FILE_TYPES.has(a)) {
      sawType = true;
      continue;
    }
    if (isPath(a)) {
      pathspecs.push(a);
      continue;
    }
    const r = refsOfRevision(a);
    if (r === undefined) return { unpinned: `${a} is not pinned by a plain ref name` };
    if (a.includes('..')) ranged = true;
    revs++;
    for (const x of r) refs.add(x);
  }
  if (revs === 0) return { unpinned: 'it names no revision, so the HEAD it reads is implicit' };
  return {
    refs: [...refs].sort(byteOrder),
    onDisk: sub === 'diff' && revs === 1 && !ranged,
    pathspecs,
  };
}

/** The leading part of a git argv: the subcommand, its arguments, the working directory every `-C` lands on, and whether a global option points git at a repository the cwd does not say (`--git-dir`, `--work-tree`). */
export function gitCommand(
  argv: readonly string[],
  cwd: string | undefined
): { sub: string | undefined; rest: string[]; dir: string | undefined; elsewhere: boolean } {
  let dir = cwd;
  let elsewhere = false;
  let i = 1;
  while (i < argv.length && argv[i].startsWith('-')) {
    const a = argv[i];
    const v = argv[i + 1];
    if (a === '-C' && v !== undefined)
      dir =
        dir !== undefined ? path.posix.resolve(dir, v) : path.posix.isAbsolute(v) ? v : undefined;
    if (/^--(git-dir|work-tree)(=|$)/.test(a)) elsewhere = true;
    i += GIT_VALUE_OPTS.has(a) ? 2 : 1;
  }
  return { sub: argv[i], rest: argv.slice(i + 1), dir, elsewhere };
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
    gitContent: [],
    gitNames: [],
    gitNameGlobs: [],
    gitContentGlobs: [],
    gitRefs: [],
    network: [...(access.network ?? [])].sort(byteOrder),
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
  /**
   * A lookup that found nothing (a module-resolution probe, a config searched for upward) inside a tracked directory: a file added there later would be found, so the nearest EXISTING ancestor is listed when it is a tracked directory or the root. A probe whose path runs through node_modules, a cache tree or a toolchain prefix names nothing tracked. A probe under another untracked directory (build output) that does not exist climbs to the nearest existing ancestor, which may be the root: the listing it adds is an over-declaration, the safe direction. A file the run wrote and removed reads the same way, which over-declares a listing: the safe direction.
   */
  const probedDir = (rel: string): string | undefined => {
    if (statOf(rel) !== undefined) return undefined;
    const segs = rel.split('/');
    if (
      segs.includes('node_modules') ||
      segs.some((x) => CONTENT_CACHE_SEGMENTS.has(x)) ||
      TOOLCHAIN_PREFIXES.some((p) => rel.startsWith(p)) ||
      CONTENT_CACHE_PREFIXES.some((p) => rel.startsWith(p))
    )
      return undefined;
    let d = path.posix.dirname(rel);
    while (d !== '.' && statOf(d) === undefined) d = path.posix.dirname(d);
    if (d === '.') return '';
    return trackedDirs.has(d) ? d : undefined;
  };
  const noteUntracked = (rel: string, listing: boolean): void => {
    const kind = classifyUntracked(rel, statOf(rel), access.startedMs, listing);
    if (kind === 'deps') usesDeps = true;
    else if (kind === 'cache') {
      if (res.cacheState.length < 3) res.cacheState.push(rel);
    } else if (kind === 'build') {
      // Every build-output read is kept: each one must have its producer among the gate's needs.
      if (!res.buildOutput.includes(rel)) res.buildOutput.push(rel);
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
  /** Every history exec and read no named ref pins, deduplicated and never capped (F2 B5). */
  const noteHistory = (shown: string): void => {
    if (!res.gitHistory.includes(shown)) res.gitHistory.push(shown);
  };
  /** The processes whose git reads an exec explains: index explainers (a names scan, a content read narrowed by pathspecs, a worktree diff) and ref-pinned history commands. */
  const indexPids = new Set<number>();
  let indexExplainers = 0;
  const refPids = new Set<number>();
  /** Per pid, the tracked paths a `git diff <file>` named before `--` (F2 B4): git first asks whether each is a ref, which reads the lookup rule set REF_PROBES spells and packed-refs. */
  const probes = new Map<number, string[]>();
  const nameGlobs = new Set<string>();
  const contentGlobs = new Set<string>();
  const refs = new Set<string>();
  /** The readers the trace recorded for one git path inside this repository's own git directories (F2 B1); undefined for an Access built without pids. */
  const readersOf = (abs: string): Set<number> | undefined =>
    access.gitReaders === undefined
      ? undefined
      : (access.gitReaders.get(abs) ?? new Set([UNKNOWN_INDEX_READER]));
  /**
   * Whether a history file read or listing is a pinned exec's own (F2 B5). An object read or a pack listing by a process that ran a ref-pinned history command or an index explainer: objects are named by content, so the commit or index entry that names one already fixes it. A loose or packed ref read, or the listing of the top `refs` directory git makes to look for replace refs, by a ref-pinned command: the ref's own sha moves with what it resolves to. A notes, replace or `shallow` path a pinned command only PROBED, and found absent (`git log` and `git show` probe all three on every run, measured on git 2.53): absence is what the run saw, and the stated limit is that creating one later moves no hash; one FOUND is history, so a shallow clone stays whole-tree. Logs, FETCH_HEAD and the other state files, any other listing, and anything inside a submodule's git directory are never explained: no ref the argv names fixes them.
   */
  const historyExplained = (abs: string, gitRel: string, listing: boolean): boolean => {
    if (gitRel.startsWith('modules/')) return false;
    const readers = listing ? access.gitListers?.get(abs) : readersOf(abs);
    if (readers === undefined || readers.size === 0) return false;
    const found = access.gitFound === undefined || access.gitFound.has(abs);
    let allowed: (pid: number) => boolean;
    if (gitRel.startsWith('objects/')) allowed = (p) => refPids.has(p) || indexPids.has(p);
    else if (listing) {
      if (gitRel !== 'refs') return false;
      allowed = (p) => refPids.has(p);
    } else if (/^refs\/(notes|replace)\/|^shallow$/.test(gitRel)) {
      if (found) return false;
      allowed = (p) => refPids.has(p);
    } else if (/^(refs\/|packed-refs$)/.test(gitRel))
      allowed = (p) =>
        refPids.has(p) ||
        (probes.get(p) ?? []).some(
          (n) => gitRel === 'packed-refs' || REF_PROBES.some((rule) => rule(n) === gitRel)
        );
    else return false;
    return [...readers].every(allowed);
  };
  /** Index file reads, judged after every exec is seen: a names scan or a narrowed content read explains them. */
  const indexFileReads: { abs: string; shown: string }[] = [];
  const noteGit = (abs: string, gitRel: string, shown: string, listing: boolean): void => {
    if (!listing && GIT_DISCOVERY_FILE.test(gitRel))
      res.ignored.set(GIT_DISCOVERY, (res.ignored.get(GIT_DISCOVERY) ?? 0) + 1);
    else if (GIT_HISTORY_FILE.test(gitRel)) {
      // A listing of refs or objects enumerates history: only the two listings historyExplained names are a pinned exec's own.
      if (!historyExplained(abs, gitRel, listing)) noteHistory(shown);
    } else if (GIT_INDEX_FILE.test(gitRel)) indexFileReads.push({ abs, shown });
    else res.ignored.set(GIT_DISCOVERY, (res.ignored.get(GIT_DISCOVERY) ?? 0) + 1);
  };
  const isTrackedDir = (d: string): boolean => d === '' || trackedDirs.has(d);
  /** The nearest tracked directory at or above `p`, '' (the root) when none is. */
  const nearestDir = (p: string): string => {
    let d = p;
    while (d !== '' && !trackedDirs.has(d)) {
      const up = path.posix.dirname(d);
      d = up === '.' ? '' : up;
    }
    return d;
  };
  const cover = (d: string): string => (d === '' ? '**' : `${d}/**`);
  /** check:ci-paths-origin refuses a traced glob matching no tracked entry, so a pathspec fold never emits one. */
  const alive = (g: string): boolean =>
    view.files.some((f) => matchGlob(g, f)) || view.gitlinks.some((f) => matchGlob(g, f));
  /**
   * One git pathspec, relative to the exec's directory `base` ('' the root), as the globs it reaches (F2 B3). git's `*` crosses `/`, so `*.sh` is `*.sh` plus `**\/*.sh`; a literal `p` is `p` (a tracked file or gitlink) and `p/**` (a tracked directory). A glob or literal that names nothing tracked today would be a dead glob, so it widens to a live cover instead: a one-level names glob to `lists` of its directory, anything else to the nearest tracked directory's `D/**`. A shape this fold does not model (magic `:(...)`, a `?` or `[` class, a `*` not leading its segment) widens the same way. `**` means the whole set: the caller decides what that costs.
   */
  const foldPathspec = (
    spec: string,
    base: string,
    ctx: 'names' | 'content'
  ): { globs: string[]; lists: string[] } => {
    const whole = { globs: ['**'], lists: [] };
    if (spec.startsWith(':')) return whole;
    const j = path.posix
      .normalize(path.posix.join(base === '' ? '.' : base, spec))
      .replace(/\/+$/, '');
    if (j === '.' || j === '' || j === '..' || j.startsWith('../')) return whole;
    const gi = j.search(/[*?[]/);
    if (gi < 0) {
      if (hasForbidden(j)) return { globs: [cover(nearestDir(cleanDir(j)))], lists: [] };
      const out: string[] = [];
      if (tracked.has(j) || view.gitlinks.includes(j)) out.push(j);
      if (trackedDirs.has(j)) out.push(`${j}/**`);
      if (out.length > 0) return { globs: out, lists: [] };
      const up = path.posix.dirname(j);
      return { globs: [cover(nearestDir(up === '.' ? '' : up))], lists: [] };
    }
    const cut = j.lastIndexOf('/', gi);
    const head = j.slice(0, cut + 1);
    const hdir = head.replace(/\/$/, '');
    const tail = j.slice(cut + 1);
    if (hdir !== '' && hasForbidden(hdir))
      return { globs: [cover(nearestDir(cleanDir(hdir)))], lists: [] };
    if (!/^\*[^*?[{/]*$/.test(tail)) return { globs: [cover(nearestDir(hdir))], lists: [] };
    const out = { globs: [] as string[], lists: [] as string[] };
    const one = `${head}${tail}`;
    const deep = `${head}**/${tail}`;
    if (alive(one)) out.globs.push(one);
    else if (ctx === 'names' && isTrackedDir(hdir)) out.lists.push(hdir);
    else out.globs.push(cover(nearestDir(hdir)));
    out.globs.push(alive(deep) ? deep : cover(nearestDir(hdir)));
    return out;
  };
  /** The content globs of a set of pathspecs, or undefined when one reaches the whole tree. */
  const contentOf = (specs: readonly string[], base: string): string[] | undefined => {
    const globs = specs.flatMap((s) => foldPathspec(s, base, 'content').globs);
    return globs.includes('**') ? undefined : globs;
  };
  const evidence = (list: string[] | undefined, shown: string): void => {
    if (list !== undefined && list.length < 3) list.push(shown);
  };
  for (const ex of access.execs) {
    // Only a git command aimed at THIS repository says anything about its history: a selftest's `git init /tmp/x` or `git -C /tmp/x log` reads another one.
    if (!targetsRepo(ex, view)) continue;
    const argv = ex.argv;
    const use = classifyGitArgv(argv);
    if (use === 'discovery') continue;
    // A remote URL in a git argv, bare (git remote-https origin <url>) or after an option prefix (-c remote.origin.url=<url>), is shown as <url>: it can carry credentials, and the ledger is committed.
    const shown = argv
      .slice(0, 6)
      .map((a) => a.replace(/[a-z][a-z0-9+.-]*:\/\/\S*/gi, '<url>'))
      .join(' ');
    const cmd = gitCommand(argv, ex.cwd);
    const sub = cmd.sub ?? '';
    const dir = cmd.dir;
    // The exec's directory relative to the root, when it is one: unknown, outside the root, inside a git directory, or set aside by --git-dir/--work-tree, a pathspec cannot be placed and no ref can be resolved against the root.
    const base =
      dir !== undefined &&
      !cmd.elsewhere &&
      under(dir, view.root) &&
      !view.gitDirs.some((g) => under(dir, g))
        ? path.posix.relative(view.root, dir)
        : undefined;
    const link = base === undefined || base === '' ? undefined : gitlinkOf(base);
    const explainIndex = (): void => {
      indexExplainers++;
      if (ex.pid !== undefined) indexPids.add(ex.pid);
    };
    const wholeContent = (): void => {
      evidence(res.gitContent, shown);
      evidence(res.gitIndex, shown);
    };
    const trackedPath = (p: string): boolean => {
      if (base === undefined) return false;
      const j = path.posix.normalize(path.posix.join(base === '' ? '.' : base, p));
      return tracked.has(j) || trackedDirs.has(j) || view.gitlinks.includes(j);
    };
    if (sub === 'ls-files' && (use === 'names' || use === 'content')) {
      const lf = lsFilesRead(cmd.rest);
      // F2 B2: the names inside every submodule are fixed by its gitlink's commit, which a content path on the bare gitlink hashes.
      if (lf.recurse) for (const g of view.gitlinks) res.gitlinkReads.add(g);
      if (link !== undefined) {
        // A scan run inside a submodule (the per-submodule child of --recurse-submodules among them) reads that submodule's index: its gitlink stands for it, as for any read inside it.
        res.gitlinkReads.add(link);
        evidence(res.gitNames, shown);
        explainIndex();
        continue;
      }
      if (use === 'names') {
        evidence(res.gitNames, shown);
        if (lf.pathspecs.length === 0 || base === undefined) nameGlobs.add('**');
        else
          for (const spec of lf.pathspecs) {
            const f = foldPathspec(spec, base, 'names');
            for (const g of f.globs) nameGlobs.add(g);
            for (const d of f.lists) res.listed.add(d);
          }
        explainIndex();
        continue;
      }
      const globs =
        !lf.unknown && lf.pathspecs.length > 0 && base !== undefined
          ? contentOf(lf.pathspecs, base)
          : undefined;
      if (globs === undefined) wholeContent();
      else {
        for (const g of globs) contentGlobs.add(g);
        explainIndex();
      }
      continue;
    }
    if (sub === 'diff') {
      const d = diffRead(cmd.rest);
      // An absolute path inside the checkout is the same pathspec as its relative spelling (git accepts both): placed relative to the exec's directory, `git diff --quiet /abs/root/a.json` reads a.json, as the relative form does (check:ci-subscription-schema, traced 2026-11-24). An absolute path outside the root stays as written, so it matches nothing tracked and keeps the read whole-tree.
      if (base !== undefined) {
        const rel = (p: string): string =>
          path.posix.isAbsolute(p) && under(p, view.root) && !view.gitDirs.some((g) => under(p, g))
            ? path.posix.relative(path.posix.join(view.root, base), p) || '.'
            : p;
        d.positionals = d.positionals.map(rel);
        d.pathspecs = d.pathspecs.map(rel);
      }
      // F2 B4: with no revision flag and every positional a tracked path, git reads them as pathspecs, and the comparison is the worktree against the index: the content of those paths.
      if (!d.revisionFlag && d.positionals.every(trackedPath)) {
        const specs = [...d.positionals, ...d.pathspecs];
        const globs =
          specs.length > 0 && base !== undefined && link === undefined
            ? contentOf(specs, base)
            : undefined;
        if (globs === undefined) wholeContent();
        else {
          for (const g of globs) contentGlobs.add(g);
          explainIndex();
          if (ex.pid !== undefined && d.positionals.length > 0) probes.set(ex.pid, d.positionals);
        }
        continue;
      }
    }
    if (use === 'history') {
      const pin =
        base !== undefined && link === undefined
          ? pinHistory(sub, cmd.rest, trackedPath)
          : { unpinned: 'its repository is not this checkout' };
      if ('unpinned' in pin) {
        noteHistory(shown);
        continue;
      }
      for (const r of pin.refs) refs.add(r);
      if (ex.pid !== undefined) refPids.add(ex.pid);
      if (pin.onDisk) {
        // `git diff REV [-- <pathspec>]` compares REV with the worktree: the content of what it names, besides the ref.
        const globs =
          base !== undefined
            ? contentOf(pin.pathspecs.length > 0 ? pin.pathspecs : ['.'], base)
            : undefined;
        if (globs === undefined) wholeContent();
        else {
          for (const g of globs) contentGlobs.add(g);
          explainIndex();
        }
      }
      continue;
    }
    if (use === 'content') wholeContent();
    else if (use === 'index') evidence(res.gitIndex, shown);
  }
  res.gitNameGlobs = nameGlobs.has('**') ? ['**'] : [...nameGlobs].sort(byteOrder);
  res.gitContentGlobs = [...contentGlobs].sort(byteOrder);
  res.gitRefs = [...refs].sort(byteOrder);
  const relOf = (abs: string): string | undefined =>
    under(abs, view.root) ? path.posix.relative(view.root, abs) : undefined;
  const ignoredBy = (rel: string): string | undefined =>
    IGNORED_PREFIXES.find((x) => rel.startsWith(x.prefix))?.prefix;
  for (const abs of access.files) {
    const rel = relOf(abs);
    const gitRel = gitRelOf(abs, rel);
    if (gitRel !== undefined) {
      noteGit(abs, gitRel, rel ?? abs, false);
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
      else {
        const parent = probedDir(rel);
        if (parent !== undefined) res.listed.add(parent);
        noteUntracked(rel, false);
      }
    }
  }
  for (const abs of access.listed) {
    const rel = relOf(abs);
    const gitRel = gitRelOf(abs, rel);
    if (gitRel !== undefined) {
      noteGit(abs, gitRel, `list ${rel ?? abs}`, true);
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
  // An index read with no names scan or narrowed content read to explain it (another git command, or a library reading .git/index itself) is whole-tree evidence. When the trace names the reading processes, an explainer explains only its own reads: a process that is not one reads the index for what it holds (review bab2c5c8.2). Only this repository's own index counts (F2 B1): a fixture repository's index, read by its own `git -C /tmp/x`, is never under view.gitDirs, so it never reaches indexFileReads at all.
  for (const r of indexFileReads) {
    const readers = readersOf(r.abs);
    const foreign = readers !== undefined && [...readers].some((pid) => !indexPids.has(pid));
    if ((indexExplainers === 0 || foreign) && res.gitIndex.length < 3) res.gitIndex.push(r.shown);
  }
  // The dependency trees are what the ROOT lockfile installs, and input-hash.ts matches `**/package-lock.json` as `.*/package-lock.json`, so the root one is no global input: a gate that loads a dependency names it.
  if (usesDeps && tracked.has('package-lock.json')) res.reads.add('package-lock.json');
  return res;
}

export type Verdict =
  | {
      kind: 'paths';
      /** Content globs; may be empty when lists or names carry the verdict. */
      paths: string[];
      /** Tracked directories whose listing the gate reads ('' is the root): the lock entry's `lists`. */
      lists?: string[];
      /** Globs whose matching tracked names the gate reads: the lock entry's `names`. */
      names?: string[];
      /** Plain ref names whose commit the gate's history reads depend on (F2 B5): the lock entry's `refs`. Never scopes the gate alone. */
      refs?: string[];
      /** The whole-tree reasons a carry-exempt kind waived for this gate (F2 B7), so a reader sees the verdict is a scoped trace of an exempt gate, not a clean one. */
      waived?: string[];
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

/**
 * Untracked build output a manifest node produces, by the prefix it writes under. A read of build output under no row here has no producer node, so no needs edge can cover it and the gate stays whole-tree: the safe direction for a row this table lacks. A row naming the wrong node would be unsound, so each one is the node whose own command writes that directory (package.json build:packages, build:cli, build:www).
 */
export const BUILD_PRODUCERS: ReadonlyArray<{ prefix: string; node: string }> = [
  { prefix: 'packages/shared/dist/', node: 'build:packages' },
  { prefix: 'packages/provisioning/dist/', node: 'build:packages' },
  { prefix: 'packages/cli/dist/', node: 'build:cli' },
  { prefix: 'packages/www/dist/', node: 'build:www' },
];

/** The manifest node that writes `rel` (a file under its output, or the output directory itself), or undefined when none does. */
export function producerOf(rel: string): string | undefined {
  return BUILD_PRODUCERS.find((x) => rel.startsWith(x.prefix) || `${rel}/` === x.prefix)?.node;
}

/** Every node `id` reaches through `needs`, transitively: a gate needing build:cli also runs after build:packages, whose hash its own then includes. */
export function needsClosure(id: string, byId: ReadonlyMap<string, LockEntry>): Set<string> {
  const out = new Set<string>();
  const queue = [...(byId.get(id)?.needs ?? [])];
  while (queue.length > 0) {
    const n = queue.shift() as string;
    if (out.has(n)) continue;
    out.add(n);
    queue.push(...(byId.get(n)?.needs ?? []));
  }
  return out;
}

/** The build-output reads whose producer is not among `closure`, each with that producer or the fact that none exists. */
export function uncoveredBuildOutput(
  buildOutput: readonly string[],
  closure: ReadonlySet<string>
): string[] {
  const out: string[] = [];
  for (const b of buildOutput) {
    const node = producerOf(b);
    if (node === undefined) out.push(`${b} (no manifest node builds it)`);
    else if (!closure.has(node)) out.push(`${b} (built by ${node})`);
  }
  return out;
}

/** Git evidence as the committed ledger shows it: the `-C <checkout>` pair dropped and a git directory written `<gitdir>`, since a lease path names a tree that is collected later. The command itself stays as git ran it (`git ls-files`, review 434f1d3b.1): the ledger is evidence, and check:ci-enumeration-vacuity judges a module that cannot run a process as inert rather than this text as disguised. `dirs` are the checkout and git directories the evidence may name; one holding whitespace is written without it first, so the two patterns below, which end a path at whitespace, take it whole (review 434f1d3b.2). */
export function evidenceText(s: string, dirs: readonly string[] = []): string {
  let t = s;
  for (const d of [...dirs].sort((a, b) => b.length - a.length))
    if (/\s/.test(d)) t = t.split(d).join(d.replace(/\s/g, '_'));
  return t
    .replace(
      /\/[^\s;]*?\.git\/(?:modules\/[^\s;]+?\/)?(?:[a-z]+\/[^/\s;]+\/)?(?=index\b)/g,
      '<gitdir>/'
    )
    .replace(/\bgit\s+-C\s+\S+\s+/g, 'git ');
}

/** A clean file extension (`.ts`, `.json`): the only shape an extension fold names. */
const CLEAN_EXT = /^\.[A-Za-z0-9_+-]+$/;

/** The extension of a path's last segment, '' for none or a dotfile (`.eslintrc`). */
function extOf(p: string): string {
  return path.posix.extname(path.posix.basename(p));
}

/** What `fold` may waive: a carry-exempt row's kind (F2 B7). */
export interface FoldOpts {
  /** The carry-exempt.json kind of the gate: `network`, `history` or `cache` waives that one whole-tree reason and no other; `clock`, which no trace can see, waives nothing. */
  waive?: string | null;
}

/** Folds an attribution into `paths` globs, or a whole-tree verdict with its reason. */
export function fold(
  attr: Attribution,
  view: RepoView,
  needs: Iterable<string> = [],
  opts: FoldOpts = {}
): Verdict {
  const closure = new Set(needs);
  const counts = { reads: attr.reads.size, listed: attr.listed.size };
  const viewDirs = [view.root, ...view.gitDirs];
  const whole = (reason: string, coveragePct = 100): Verdict => ({
    kind: 'whole-tree',
    reason,
    ...counts,
    coveragePct,
  });
  // F2 B7: a carry-exempt kind names why the gate's hash is null already, so that one reason buys nothing as a whole-tree verdict; every OTHER reason still stands, and the waiver is printed with the verdict.
  const waived: string[] = [];
  const waives = (kind: 'network' | 'history' | 'cache'): boolean => {
    if (opts.waive !== kind) return false;
    waived.push(kind);
    return true;
  };
  // The network first: no tracked input, history included, can stand for what a remote answers.
  const net = attr.network ?? [];
  if (net.length > 0 && !waives('network'))
    return whole(
      `network: connects to ${net.slice(0, 3).join(', ')}${net.length > 3 ? `, and ${net.length - 3} more` : ''}, so its verdict can move with nothing in the tree moving; a carry-exempt.json candidate`
    );
  if (attr.gitHistory.length > 0 && !waives('history')) {
    const more = attr.gitHistory.length - 3;
    return whole(
      `reads git history no named ref pins (${evidenceText(attr.gitHistory.slice(0, 3).join('; '), viewDirs)}${more > 0 ? `; and ${more} more` : ''})`
    );
  }
  if ((attr.gitContent ?? []).length > 0)
    return whole(
      `reads what every tracked file holds through the git index (${evidenceText((attr.gitContent ?? []).join('; '), viewDirs)}), so a change to any tracked file can change its verdict`
    );
  if (attr.gitIndex.length > 0)
    return whole(
      `enumerates the tracked file list through the git index (${evidenceText(attr.gitIndex.join('; '), viewDirs)}), so a new file anywhere can change its verdict`
    );
  if (attr.cacheState.length > 0 && !waives('cache'))
    return whole(
      `reads untracked cache state (${attr.cacheState.join(', ')}), so its verdict can move with no tracked input moving; a carry-exempt.json candidate`
    );
  const uncovered = uncoveredBuildOutput(attr.buildOutput, closure);
  if (uncovered.length > 0)
    return whole(
      `reads untracked build output with no needs edge naming its producer (${uncovered.slice(0, 3).join(', ')}${uncovered.length > 3 ? `, and ${uncovered.length - 3} more` : ''}), so no input hash would move when that output does; add the producer to needs, then re-trace`
    );
  const isGlobal = (f: string): boolean => GLOBAL_INPUTS.some((g) => matchGlob(g, f));
  const files = [...attr.reads].filter((f) => !isGlobal(f));
  const dirGlobs = new Set<string>();
  const fileGlobs = new Set<string>();
  /** F2 B6: directories folded by extension, to `D/*.ext` plus `D/**\/*.ext`. */
  const extDirs = new Map<string, string>();
  const addDir = (d: string): boolean => {
    const c = cleanDir(d);
    if (c === '') return false;
    dirGlobs.add(c);
    return true;
  };
  // A listing is names, not content: it goes to `lists` (the root included), which hashes the directory's tracked children and none of their bytes. A directory whose own name holds a glob character cannot be a `lists` item (input-hash.ts refuses it), so it keeps the content glob of its nearest clean ancestor.
  const listDirs = new Set<string>();
  for (const d of attr.listed) {
    if (d === '' || !hasForbidden(d)) listDirs.add(d);
    else if (!addDir(d)) return whole(`lists ${d}, whose only glob-safe ancestor is the root`);
  }
  // A hand-built Attribution with name-only scans and no folded globs reads as the whole name set, as before F2.
  const nameGlobs = attr.gitNameGlobs ?? ((attr.gitNames ?? []).length > 0 ? ['**'] : []);
  const names = nameGlobs.includes('**') ? ['**'] : [...nameGlobs].sort(byteOrder);
  // A submodule read names the bare gitlink path: input-hash.ts `entryMatches` reaches the gitlink entry through it exactly as through `<gitlink>/**`, and it is the path `git ls-files` lists and a submodule bump changes, so the dead-glob checks (check:ci-gate-manifest, check:ci-paths-origin) and quick-select's rule 1 all see it.
  for (const g of attr.gitlinkReads) {
    if (hasForbidden(g)) return whole(`reads inside submodule ${g}, whose path no glob can name`);
    fileGlobs.add(g);
  }
  const underExt = (p: string, file: boolean): boolean =>
    [...extDirs].some(([d, e]) => (p === d || p.startsWith(`${d}/`)) && (!file || p.endsWith(e)));
  // A directory under an extension fold is covered too: every read under the folded directory shares that extension, so the fold reaches each of them.
  const covered = (p: string, file = false): boolean =>
    [...dirGlobs].some((d) => p === d || p.startsWith(`${d}/`)) || underExt(p, file);
  const total = new Map<string, number>();
  const read = new Map<string, number>();
  const totalExt = new Map<string, number>();
  const readExts = new Map<string, Set<string>>();
  for (const f of view.files)
    for (const a of ancestors(f)) {
      total.set(a, (total.get(a) ?? 0) + 1);
      const k = `${a}\0${extOf(f)}`;
      totalExt.set(k, (totalExt.get(k) ?? 0) + 1);
    }
  for (const f of files)
    for (const a of ancestors(f)) {
      read.set(a, (read.get(a) ?? 0) + 1);
      let s = readExts.get(a);
      if (s === undefined) {
        s = new Set();
        readExts.set(a, s);
      }
      s.add(extOf(f));
    }
  const anyTracked = (g: string): boolean => view.files.some((f) => matchGlob(g, f));
  const dirs = [...read.keys()].sort(
    (a, b) => a.split('/').length - b.split('/').length || (a < b ? -1 : a > b ? 1 : 0)
  );
  for (const d of dirs) {
    if (covered(d)) continue;
    const r = read.get(d) ?? 0;
    const exts = readExts.get(d) ?? new Set();
    // F2 B6: every read under D shares one extension, and more than half of D's tracked files with it were read: fold to that extension, when both halves of the pair name a tracked file (check:ci-paths-origin refuses a dead glob; a flat directory keeps the plain D/** fold).
    if (exts.size === 1 && !hasForbidden(d)) {
      const e = [...exts][0];
      const te = totalExt.get(`${d}\0${e}`) ?? 0;
      if (
        CLEAN_EXT.test(e) &&
        te >= FOLD_MIN_FILES &&
        r / te > FOLD_DIR_FRACTION &&
        anyTracked(`${d}/*${e}`) &&
        anyTracked(`${d}/**/*${e}`)
      ) {
        extDirs.set(d, e);
        continue;
      }
    }
    const t = total.get(d) ?? 0;
    if (t >= FOLD_MIN_FILES && r / t > FOLD_DIR_FRACTION) addDir(d);
  }
  for (const f of files) {
    if (covered(f, true)) continue;
    if (hasForbidden(f)) {
      if (!addDir(path.posix.dirname(f)))
        return whole(`reads ${f}, whose only glob-safe ancestor is the root`);
    } else fileGlobs.add(f);
  }
  // A dir glob inside another dir glob says nothing more; a file glob under a dir glob neither; nor an extension fold under a dir glob.
  const dirList = [...dirGlobs].filter(
    (d) => ![...dirGlobs].some((o) => o !== d && d.startsWith(`${o}/`))
  );
  const finalDirs = new Set(dirList);
  const isUnderDir = (p: string): boolean =>
    [...finalDirs].some((d) => p === d || p.startsWith(`${d}/`));
  const extGlobs = [...extDirs]
    .filter(([d]) => !isUnderDir(d))
    .flatMap(([d, e]) => [`${d}/*${e}`, `${d}/**/*${e}`]);
  // F2 B3/B4: content read through git (a narrowed `ls-files -s`, a `git diff` of named paths) is content like any read.
  const gitGlobs = (attr.gitContentGlobs ?? []).filter((g) => {
    const lit = g.split(/[*]/, 1)[0].replace(/\/$/, '');
    return !(lit !== '' && isUnderDir(lit) && (g === lit || g.startsWith(`${lit}/`)));
  });
  const globs = [
    ...new Set([
      ...[...finalDirs].map((d) => `${d}/**`),
      ...extGlobs,
      ...gitGlobs,
      ...[...fileGlobs].filter((f) => !isUnderDir(f)),
    ]),
  ].sort(byteOrder);
  const entries = view.files.length + view.gitlinks.length;
  const reaches = (p: string): boolean =>
    isUnderDir(p) || fileGlobs.has(p) || [...extGlobs, ...gitGlobs].some((g) => matchGlob(g, p));
  const reached = view.files.filter(reaches).length + view.gitlinks.filter(reaches).length;
  // The 30% line weighs content globs only: `lists` and `names` hash names, which is what lets a listing or an ls-files scan stay cheap.
  const coveragePct = entries === 0 ? 0 : Math.round((1000 * reached) / entries) / 10;
  // A listing inside a content dir glob says nothing more: `D/**` already moves with every name under D. An extension fold does not reach a new child of another extension, so a listing under one stays.
  const lists = [...listDirs].filter((d) => d === '' || !isUnderDir(d)).sort(byteOrder);
  if (globs.length === 0 && lists.length === 0 && names.length === 0)
    return whole(
      'reads no tracked file outside the global inputs: an empty `paths` means whole-tree, and a gate that reads nothing from the tree belongs in carry-exempt.json',
      0
    );
  if (reached / Math.max(entries, 1) > WHOLE_TREE_FRACTION)
    return whole(
      `reaches ${coveragePct}% of the tracked entries through its content globs, over the ${WHOLE_TREE_FRACTION * 100}% line`,
      coveragePct
    );
  const cited = recordCitations([...globs, ...lists], view.records ?? []);
  if (cited.length > 0)
    return whole(
      `its traced set names record paths (${cited.join(', ')}), and manifest.ts citing them makes every gate that reads the manifest a reader of those records, so a record-only commit could no longer advance a receipt (record-paths.json); whole-tree until it reads no record`,
      coveragePct
    );
  const refs = attr.gitRefs ?? [];
  return {
    kind: 'paths',
    paths: globs,
    ...(lists.length > 0 ? { lists } : {}),
    ...(names.length > 0 ? { names } : {}),
    ...(refs.length > 0 ? { refs: [...refs] } : {}),
    ...(waived.length > 0 ? { waived } : {}),
    ...counts,
    coveragePct,
  };
}

// ---------------------------------------------------------------------------
// running a trace
// ---------------------------------------------------------------------------

/** Refuses loudly, with the fix, when this host cannot trace. Returns undefined when it can. */
export function traceRefusal(opts: { noSeccomp?: boolean } = {}): string | undefined {
  if (process.platform !== 'linux')
    return `path-trace runs on Linux only (strace); this host is ${process.platform}. Trace on a Linux host or in the devcontainer.`;
  const v = spawnSync('strace', ['-V'], { encoding: 'utf8' });
  if (v.error !== undefined || v.status !== 0)
    return 'strace is not installed, so no gate can be traced. Install it: `sudo apt-get install -y strace` (the devcontainer image should carry it).';
  const probe = spawnSync(
    'strace',
    ['-f', '-qq', ...(opts.noSeccomp ? [] : ['--seccomp-bpf']), '-o', '/dev/null', 'true'],
    { encoding: 'utf8' }
  );
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
  /** strace's OWN stderr lines (warnings, refusals), never mixed into the gate's output. */
  straceNotes: string[];
}

/**
 * The strace argv for one traced command. The traced shell runs `exec 2>&1` before the command, so the gate's stderr joins its stdout, and strace's own stderr, which the tracee would otherwise inherit, carries only strace's lines. `noSeccomp` drops `--seccomp-bpf`: slower, and the retry for a host or a tracee where the filter misbehaves.
 */
export function straceArgv(logPrefix: string, cmd: string, noSeccomp = false): string[] {
  return [
    '-ff',
    '-qq',
    '-y',
    '-s',
    '4096',
    ...(noSeccomp ? [] : ['--seccomp-bpf']),
    '-e',
    `trace=${TRACE_SYSCALLS}`,
    '-o',
    logPrefix,
    'bash',
    '-c',
    `exec 2>&1\n${cmd}`,
  ];
}

/** Parses a `-ff` log directory (`t.<pid>` files) into `access`, in ascending numeric pid order so a parent's fork is parsed before its child's lines (straceParser); the pid comes from the file name. */
export function parseStraceDir(dir: string, cwd: string, access: Access): number {
  const logs = fs
    .readdirSync(dir)
    .filter((f) => /^t\.\d+$/.test(f))
    .sort((a, b) => Number(a.slice(2)) - Number(b.slice(2)));
  const parser = straceParser(cwd, access);
  for (const f of logs) {
    // A log can exceed the largest string V8 holds: stream it in chunks and parse whole lines, carrying the partial last one.
    const pid = Number(f.slice(2));
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
      for (const l of chunk.slice(0, cut + 1).split('\n')) parser.line(l, pid);
      tail = chunk.slice(cut + 1);
    }
    parser.line(tail, pid);
    fs.closeSync(fd);
  }
  parser.end();
  return logs.length;
}

/** Runs `cmd` under bash in `cwd`, traced, and parses every per-process log. `straceBin` replaces the strace executable (a selftest wrapper). */
export async function traceCommand(
  cmd: string,
  cwd: string,
  opts: {
    env?: NodeJS.ProcessEnv;
    keepLogs?: boolean;
    label?: string;
    timeoutS?: number;
    noSeccomp?: boolean;
    straceBin?: string;
  } = {}
): Promise<TraceRun> {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-'));
  const started = Date.now();
  const outFile = path.join(dir, 'output.txt');
  const outFd = fs.openSync(outFile, 'w');
  const straceErrFile = path.join(dir, 'strace-stderr.txt');
  const straceErrFd = fs.openSync(straceErrFile, 'w');
  const env = { ...(opts.env ?? process.env), UV_USE_IO_URING: '0' };
  const exit = await new Promise<number>((resolve) => {
    const child = spawn(
      opts.straceBin ?? 'strace',
      straceArgv(path.join(dir, 't'), cmd, opts.noSeccomp),
      { cwd, env, stdio: ['ignore', outFd, straceErrFd], detached: true }
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
  fs.closeSync(straceErrFd);
  const access = emptyAccess();
  access.startedMs = started;
  const logCount = parseStraceDir(dir, cwd, access);
  // strace's stderr file holds strace's own `strace:` lines, plus anything the shell printed before its `exec 2>&1` (a BASH_ENV hook), which is the gate's side and goes back with its output.
  const errLines = fs
    .readFileSync(straceErrFile, 'utf8')
    .split('\n')
    .filter((l) => l.trim() !== '');
  const straceNotes = errLines.filter((l) => l.startsWith('strace: '));
  const preamble = errLines.filter((l) => !l.startsWith('strace: '));
  const output = [...preamble, fs.readFileSync(outFile, 'utf8')].join('\n');
  if (!opts.keepLogs) fs.rmSync(dir, { recursive: true, force: true });
  else process.stderr.write(`path-trace: kept ${opts.label ?? cmd} logs in ${dir}\n`);
  return {
    exit,
    access,
    seconds: Math.round((Date.now() - started) / 100) / 10,
    logFiles: logCount,
    outputTail: output.split('\n').slice(-15).join('\n'),
    straceNotes,
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
  /** W2.4 (gate-spec.ts): tracked directories whose listing the gate reads, '' the root. */
  lists?: string[];
  /** W2.4 (gate-spec.ts): globs whose matching tracked names the gate reads. */
  names?: string[];
  /** W2.4 (gate-spec.ts): ref names whose commit the gate's verdict depends on; a trace writes them for pinned history reads (F2 B5). */
  refs?: string[];
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

/** The fields that scope a gate (a gate declaring none hashes the whole tree). `refs` is not one: input-hash.ts reads a ref as no tree read. */
const SCOPE_FIELDS = ['paths', 'lists', 'names'] as const;
/** The input fields a trace writes, in the order gate-spec.ts declares them; `pathsOrigin` follows them. */
const TRACED_FIELDS = [...SCOPE_FIELDS, 'refs'] as const;

/** A trace's input sets: content globs plus the W2.4 name-shaped fields and the F2 B5 refs. An empty one is omitted, never written as `[]`. */
export interface TracedInputs {
  lists?: string[];
  names?: string[];
  refs?: string[];
}

/** The fields to write for one verdict, each non-empty, in TRACED_FIELDS order. */
function tracedFields(paths: string[], extra: TracedInputs): [string, string[]][] {
  const all: Record<string, string[] | undefined> = { paths, ...extra };
  return TRACED_FIELDS.flatMap((k) => ((all[k] ?? []).length > 0 ? [[k, all[k] as string[]]] : []));
}

/** The lock text with `paths`, `lists`, `names` and `pathsOrigin` set on one entry, placed before `leaves` the way the manifest literal orders them. */
export function lockWithPaths(
  lockText: string,
  id: string,
  paths: string[],
  extra: TracedInputs = {}
): string {
  const entries = JSON.parse(lockText) as LockEntry[];
  const i = entries.findIndex((e) => e.id === id);
  if (i < 0) throw new Error(`${LOCK_REL}: no entry ${id}`);
  const out: Record<string, unknown> = {};
  let placed = false;
  const place = (): void => {
    for (const [k, v] of tracedFields(paths, extra)) out[k] = v;
    out.pathsOrigin = TRACED_ORIGIN;
    placed = true;
  };
  for (const [k, v] of Object.entries(entries[i])) {
    if ((TRACED_FIELDS as readonly string[]).includes(k) || k === 'pathsOrigin') continue;
    if (k === 'leaves' && !placed) place();
    out[k] = v;
  }
  if (!placed) place();
  entries[i] = out as LockEntry;
  return `${JSON.stringify(entries, null, 2)}\n`;
}

const q = (s: string): string => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

/** One array field's lines as biome formats them at a 100-column line width. */
export function fieldLines(field: string, values: string[]): string[] {
  const one = `    ${field}: [${values.map(q).join(', ')}],`;
  if (one.length <= 100) return [one];
  return [`    ${field}: [`, ...values.map((p) => `      ${q(p)},`), '    ],'];
}

/** The `paths:` lines as biome formats them at a 100-column line width. */
export function pathsLines(paths: string[]): string[] {
  return fieldLines('paths', paths);
}

/** An entry body without its traced input fields (`paths`, `lists`, `names`, single- or multi-line) and its `pathsOrigin`. */
function withoutTracedFields(body: readonly string[]): string[] {
  const kept: string[] = [];
  for (let i = 0; i < body.length; i++) {
    const l = body[i];
    if (TRACED_FIELDS.some((f) => l.startsWith(`    ${f}:`))) {
      if (!l.trimEnd().endsWith('],')) while (i < body.length && body[i] !== '    ],') i++;
      continue;
    }
    if (l.startsWith('    pathsOrigin:')) continue;
    kept.push(l);
  }
  return kept;
}

/** The lock text with a TRACED `paths` and `pathsOrigin` removed from one entry; a declared set, or none, leaves the text as it was, unless `replaceDeclared` removes a declared set too. */
export function lockWithoutTracedPaths(
  lockText: string,
  id: string,
  opts: { replaceDeclared?: boolean } = {}
): string {
  const entries = JSON.parse(lockText) as LockEntry[];
  const e = entries.find((x) => x.id === id);
  if (e === undefined || e.pathsOrigin === undefined) return lockText;
  if (e.pathsOrigin !== TRACED_ORIGIN && !opts.replaceDeclared) return lockText;
  for (const f of TRACED_FIELDS) delete e[f];
  delete e.pathsOrigin;
  return `${JSON.stringify(entries, null, 2)}\n`;
}

/** The manifest text with a TRACED `paths` block and `pathsOrigin` line removed from one entry; a declared set, or none, leaves the text as it was, unless `replaceDeclared` removes a declared set too. */
export function manifestWithoutTracedPaths(
  text: string,
  id: string,
  opts: { replaceDeclared?: boolean } = {}
): string {
  const lines = text.split('\n');
  const idLine = `    id: ${q(id)},`;
  const span = entrySpans(lines).find(([a, b]) => lines.slice(a, b + 1).includes(idLine));
  if (span === undefined) return text;
  const [a, b] = span;
  const body = lines.slice(a, b + 1);
  const origin = body.find((l) => l.startsWith('    pathsOrigin:'));
  if (origin === undefined) return text;
  if (origin !== `    pathsOrigin: ${q(TRACED_ORIGIN)},` && !opts.replaceDeclared) return text;
  return [...lines.slice(0, a), ...withoutTracedFields(body), ...lines.slice(b + 1)].join('\n');
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
export function manifestWithPaths(
  text: string,
  id: string,
  paths: string[],
  opts: { replaceDeclared?: boolean } & TracedInputs = {}
): string {
  const lines = text.split('\n');
  const spans = entrySpans(lines);
  const idLine = `    id: ${q(id)},`;
  const span = spans.find(([a, b]) => lines.slice(a, b + 1).includes(idLine));
  if (span === undefined) throw new Error(`${MANIFEST_REL}: no entry with ${idLine.trim()}`);
  const [a, b] = span;
  const body = lines.slice(a, b + 1);
  const originAt = body.findIndex((l) => l.startsWith('    pathsOrigin:'));
  if (originAt >= 0 && !body[originAt].includes(`'${TRACED_ORIGIN}'`) && !opts.replaceDeclared)
    throw new Error(
      `${id}: its paths carry ${body[originAt].trim()}; a hand-declared set is judged by trace-honest.ts, never overwritten by a trace unless --replace-declared asks for it`
    );
  // Drop an earlier traced block (paths, lists, names, pathsOrigin).
  const kept = withoutTracedFields(body);
  const leavesAt = kept.findIndex((l) => l.startsWith('    leaves:'));
  const insertAt = leavesAt >= 0 ? leavesAt : kept.length - 1;
  kept.splice(
    insertAt,
    0,
    ...tracedFields(paths, { lists: opts.lists, names: opts.names, refs: opts.refs }).flatMap(
      ([k, v]) => fieldLines(k, v)
    ),
    `    pathsOrigin: ${q(TRACED_ORIGIN)},`
  );
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
  for (const [at, l] of withMarkers.entries()) {
    if (BEGIN_RE.test(l)) {
      if (inRegion)
        throw new Error(
          `${MANIFEST_REL}: region opened at line ${at + 1} inside an open region; refusing to re-emit regions`
        );
      inRegion = true;
    } else if (END_RE.test(l)) {
      if (!inRegion)
        throw new Error(
          `${MANIFEST_REL}: region end at line ${at + 1} with no open region; refusing to re-emit regions`
        );
      inRegion = false;
    } else if (l === '  {') open = { gen: inRegion, lifted: false };
    else if (open !== undefined && l === liftedIdLine) open.lifted = true;
    else if (open !== undefined && l === '  },') {
      generated.push(open.gen && !open.lifted);
      open = undefined;
    }
  }
  if (inRegion)
    throw new Error(`${MANIFEST_REL}: a region never closes; refusing to re-emit regions`);
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
    .replace(/'((?:[^'\\]|\\.)*)'/g, (_, s: string) =>
      JSON.stringify(s.replace(/\\(['\\])/g, '$1'))
    )
    .replace(/([{,]\s*)([A-Za-z_]\w*)\s*:/g, '$1"$2":')
    .replace(/,(\s*[}\]])/g, '$1');
  return JSON.parse(json) as Record<string, LedgerRow>;
}

/** One ledger row, or undefined when the ledger has none for `id` (a parsed ledger may lack any id). */
function ledgerRow(text: string, id: string): LedgerRow | undefined {
  return parseLedger(text)[id];
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
  /** Traces without `--seccomp-bpf` (straceArgv). */
  noSeccomp: boolean;
  /** Lets `--write` and `--apply` replace a hand-declared `paths` set. */
  replaceDeclared: boolean;
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
    noSeccomp: false,
    replaceDeclared: false,
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
    else if (t === '--no-seccomp') a.noSeccomp = true;
    else if (t === '--replace-declared') a.replaceDeclared = true;
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
  /** strace's own stderr lines for this trace (TraceRun.straceNotes). */
  straceNotes?: string[];
  /** The part of the trace that bears on this repository, kept so a changed fold re-folds without re-tracing (`--refold`). */
  raw?: RawAccess;
}

/** An Access cut down to this repository: paths under the root or a git directory, listings under the root, git execs. */
export interface RawAccess {
  files: string[];
  listed: string[];
  execs: Exec[];
  /** Network peers (Access.network); absent in an `--out` file written before `connect` was traced. */
  network?: string[];
  startedMs?: number;
  /** The pids that named each git-shaped path of this repository (Access.gitReaders, F2 B1): `--refold` needs them to tell an explaining exec's own git read from a foreign one. Absent in a file written before they were kept: accessOfRaw then charges every index and history read to an unknown reader, the whole-tree direction, and refold names the gate. */
  gitReaders?: Record<string, number[]>;
  /** Access.gitFound, cut to this repository; absent, every git path counts as found. */
  gitFound?: string[];
  /** Access.gitListers, cut to this repository; absent, no git listing is a pinned exec's own. */
  gitListers?: Record<string, number[]>;
}

/** A path -> pids map as JSON, the keys cut by `keep` and sorted. */
function pidRecord(
  m: Map<string, Set<number>> | undefined,
  keep: (p: string) => boolean
): Record<string, number[]> | undefined {
  if (m === undefined) return undefined;
  const out: Record<string, number[]> = {};
  for (const p of [...m.keys()].filter(keep).sort(byteOrder))
    out[p] = [...(m.get(p) ?? [])].sort((a, b) => a - b);
  return out;
}

function pidMap(r: Record<string, number[]>): Map<string, Set<number>> {
  return new Map(Object.entries(r).map(([p, pids]) => [p, new Set(pids)]));
}

export function rawOf(access: Access, view: RepoView): RawAccess {
  const ours = (p: string): boolean => under(p, view.root) || view.gitDirs.some((g) => under(p, g));
  const gitReaders = pidRecord(access.gitReaders, ours);
  const gitListers = pidRecord(access.gitListers, ours);
  return {
    files: [...access.files].filter(ours).sort(byteOrder),
    listed: [...access.listed].filter(ours).sort(byteOrder),
    execs: access.execs.filter((e) => path.posix.basename(e.argv[0] ?? '') === 'git'),
    network: [...(access.network ?? [])].sort(byteOrder),
    startedMs: access.startedMs,
    ...(gitReaders !== undefined ? { gitReaders } : {}),
    ...(access.gitFound !== undefined
      ? { gitFound: [...access.gitFound].filter(ours).sort(byteOrder) }
      : {}),
    ...(gitListers !== undefined ? { gitListers } : {}),
  };
}

/** A pid no process has: the reader charged for a git read the trace holds no pid for (a raw record from before `gitReaders` was kept), so it counts as foreign. */
export const UNKNOWN_INDEX_READER = -1;

/** A path shaped like a git index or history file, the reads whose reader decides a verdict. */
const GIT_JUDGED = /(^|\/)(index|sharedindex\.[^/]*|packed-refs|shallow)$|\/(objects|refs|logs)\/./;

/**
 * The Access a raw record stands for, the inverse of rawOf. A record written before `gitReaders` was kept cannot say which process read its git files; each one is charged to UNKNOWN_INDEX_READER, a foreign reader, so the fold takes the whole-tree direction instead of letting an explaining exec explain a read it may not have made, and `legacy` is true when such a record holds an index or history read, so the caller says so (review 434f1d3b.3). A live trace leaves `gitReaders` unset only when no process named a git-shaped path, so a record without the field and without such a read is judged in full. `gitFound` and `gitListers` are read only beside `gitReaders`: a legacy record counts every git path as found and no listing as explained.
 */
export function accessOfRaw(raw: RawAccess): { access: Access; legacy: boolean } {
  const legacy = raw.gitReaders === undefined && raw.files.some((f) => GIT_JUDGED.test(f));
  let gitReaders: Map<string, Set<number>> | undefined;
  if (raw.gitReaders !== undefined) gitReaders = pidMap(raw.gitReaders);
  else if (legacy)
    gitReaders = new Map(
      raw.files.filter((f) => GIT_SHAPED.test(f)).map((f) => [f, new Set([UNKNOWN_INDEX_READER])])
    );
  const current = raw.gitReaders !== undefined;
  return {
    access: {
      files: new Set(raw.files),
      listed: new Set(raw.listed),
      execs: raw.execs,
      network: new Set(raw.network ?? []),
      startedMs: raw.startedMs,
      ...(gitReaders !== undefined ? { gitReaders } : {}),
      ...(current && raw.gitFound !== undefined ? { gitFound: new Set(raw.gitFound) } : {}),
      ...(current && raw.gitListers !== undefined ? { gitListers: pidMap(raw.gitListers) } : {}),
    },
    legacy,
  };
}

/** The verdict a trace earns: the fold, unless the gate was red, which makes the read set untrustworthy. */
export function verdictOf(
  attr: Attribution,
  view: RepoView,
  exit: number,
  needs: Iterable<string> = [],
  opts: FoldOpts = {}
): Verdict {
  const verdict = fold(attr, view, needs, opts);
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
  opts: {
    keepLogs?: boolean;
    timeoutS?: number;
    /** Every node the gate reaches through `needs`, transitively (needsClosure): the direct edges alone would miss a producer behind another producer. */
    closure: ReadonlySet<string>;
    noSeccomp?: boolean;
    /** The gate's carry-exempt kind (F2 B7), which fold waives alone. */
    waive?: string | null;
  }
): Promise<GateResult> {
  const run = await traceCommand(entry.run, view.root, {
    timeoutS: opts.timeoutS,
    keepLogs: opts.keepLogs,
    label: entry.id,
    noSeccomp: opts.noSeccomp,
  });
  const attr = attribute(run.access, view);
  return {
    id: entry.id,
    verdict: verdictOf(attr, view, run.exit, opts.closure, {
      waive: opts.waive,
    }),
    exit: run.exit,
    seconds: run.seconds,
    ignored: attr.ignored,
    outputTail: run.outputTail,
    straceNotes: run.straceNotes,
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

/** Writes one result into the manifest, the lock and the ledger under `root`. `replaceDeclared` lets the result replace a hand-declared set (`--replace-declared`); without it a declared set is refused or left alone. */
export function writeResult(
  root: string,
  r: GateResult,
  tree: string,
  tracedMs?: number,
  opts: { replaceDeclared?: boolean } = {}
): void {
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
  const mPath = path.join(root, MANIFEST_REL);
  const lPath = path.join(root, LOCK_REL);
  if (r.verdict.kind === 'whole-tree') {
    const red = r.exit !== 0;
    // A red run may have stopped before reading everything, which is no evidence against an earlier green trace: its traced globs and ledger row stay.
    if (red && rows[r.id]?.verdict === 'paths') {
      console.error(
        `path-trace: ${r.id} exited ${r.exit}; its traced paths and ledger row are kept, a red run is no evidence against them`
      );
      return;
    }
    row.reason = r.verdict.reason;
    // A whole-tree re-trace must not leave the earlier traced globs behind: the gate would keep carrying on a read set the new trace no longer vouches for. A declared set is never touched.
    const m = fs.readFileSync(mPath, 'utf8');
    const stripped = red ? m : manifestWithoutTracedPaths(m, r.id, opts);
    if (stripped !== m) {
      fs.writeFileSync(mPath, stripped);
      fs.writeFileSync(lPath, lockWithoutTracedPaths(fs.readFileSync(lPath, 'utf8'), r.id, opts));
      console.error(
        `path-trace: ${r.id} is whole-tree now; its traced paths are removed. It may be generable again: run npx tsx scripts/gen/gen-manifest.ts --write`
      );
    }
  } else {
    fs.writeFileSync(
      mPath,
      manifestWithPaths(fs.readFileSync(mPath, 'utf8'), r.id, r.verdict.paths, {
        ...opts,
        lists: r.verdict.lists,
        names: r.verdict.names,
        refs: r.verdict.refs,
      })
    );
    fs.writeFileSync(
      lPath,
      lockWithPaths(fs.readFileSync(lPath, 'utf8'), r.id, r.verdict.paths, {
        lists: r.verdict.lists,
        names: r.verdict.names,
        refs: r.verdict.refs,
      })
    );
  }
  rows[r.id] = row;
  fs.writeFileSync(ledgerPath, renderLedger(rows));
}

/** One stdout line per gate with paths: `<id>\t<paths space-joined>`, then `\tlists=<json>`, `\tnames=<json>`, `\trefs=<json>` and `\twaived=<json>` when present (JSON, so the root's '' stays visible). */
export function verdictLine(id: string, v: Extract<Verdict, { kind: 'paths' }>): string {
  return [
    `${id}\t${v.paths.join(' ')}`,
    ...(v.lists !== undefined ? [`lists=${JSON.stringify(v.lists)}`] : []),
    ...(v.names !== undefined ? [`names=${JSON.stringify(v.names)}`] : []),
    ...(v.refs !== undefined ? [`refs=${JSON.stringify(v.refs)}`] : []),
    ...(v.waived !== undefined ? [`waived=${JSON.stringify(v.waived)}`] : []),
  ].join('\t');
}

/** The carry-exempt rows as id -> kind (null for a row naming none), read from `root`; an absent file is no row. */
export function exemptKinds(root: string): Map<string, string | null> {
  const p = path.join(root, CARRY_EXEMPT_REL);
  return exemptRowsOf(fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null);
}

/** Whether the entry's scoped inputs are a human's: it declares `paths`, `lists` or `names` and they are not marked as traced, or it carries `pathsOrigin: 'declared'` with every set empty (a statement that nothing selects it, select.ts). An entry with a set and NO `pathsOrigin` is declared too. */
export function declaresInputs(e: LockEntry): boolean {
  if (e.pathsOrigin === 'declared') return true;
  return SCOPE_FIELDS.some((f) => (e[f] ?? []).length > 0) && e.pathsOrigin !== TRACED_ORIGIN;
}

/**
 * Why --all-whole-tree leaves an entry untraced, or undefined when it traces it. A carry-exempt row with no `kind` is refused: nothing says which whole-tree reason its exemption stands for. A row WITH a kind is traced, and `fold` waives that kind's reason alone (F2 B7), so the trace still names every other reason it reads.
 */
export function untracedReason(
  e: LockEntry,
  exempt: ReadonlyMap<string, string | null>
): string | undefined {
  if (declaresInputs(e)) return 'declares paths already';
  if (!e.gate)
    return 'not a gate: a prerequisite or an operator command, never judged, so never carried';
  if (exempt.has(e.id) && (exempt.get(e.id) ?? null) === null)
    return `carry-exempt (${CARRY_EXEMPT_REL}) with no kind: its hash is null, and no kind says which reason a trace may waive; add one (clock, history, network or cache)`;
  if (NEVER_TRACED[e.id] !== undefined) return NEVER_TRACED[e.id];
  if (e.ciOnly !== undefined) return 'ciOnly: never runs in the local lane';
  return undefined;
}

/** Re-folds every raw trace in an `--out` file against the current tree, printing new result lines on stdout and the shape on stderr. */
export function refold(root: string, file: string): number {
  const view = repoView(root);
  const byId = new Map(readLock(root).map((e) => [e.id, e]));
  const exempt = exemptKinds(root);
  let n = 0;
  let paths = 0;
  const legacyIds: string[] = [];
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
    const { access, legacy } = accessOfRaw(r.raw);
    if (legacy) {
      legacyIds.push(r.id);
      console.error(
        `path-trace: ${r.id}'s raw trace in ${file} predates gitReaders, so no reader of its git index or history files can be told apart; each such read counts as foreign (whole-tree). Re-trace it for a full verdict.`
      );
    }
    const verdict = verdictOf(attribute(access, view), view, r.exit, needsClosure(r.id, byId), {
      waive: exempt.get(r.id),
    });
    if (verdict.kind === 'paths') paths++;
    n++;
    process.stdout.write(`${JSON.stringify({ ...r, verdict })}\n`);
  }
  console.error(
    `path-trace: re-folded ${n} trace(s): ${paths} with paths, ${n - paths} whole-tree${legacyIds.length > 0 ? `; ${legacyIds.length} judged without gitReaders (${legacyIds.join(', ')})` : ''}`
  );
  return n === 0 ? 1 : 0;
}

/** Writes every result line of an `--out` file; the last line per gate wins. */
export function applyResults(
  root: string,
  file: string,
  opts: { replaceDeclared?: boolean } = {}
): number {
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
    if (e.pathsOrigin !== undefined && e.pathsOrigin !== TRACED_ORIGIN && !opts.replaceDeclared) {
      console.error(
        `path-trace: ${r.id} declares its paths by hand (${e.pathsOrigin}); not overwritten (--replace-declared replaces it)`
      );
      continue;
    }
    writeResult(root, r, r.tree, undefined, opts);
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
  if (args.apply !== undefined)
    return applyResults(args.root, args.apply, { replaceDeclared: args.replaceDeclared });
  if (args.refold !== undefined) return refold(args.root, args.refold);
  if (args.gates.length === 0 && !args.allWholeTree) {
    console.error(
      'path-trace: name --gate <id> (repeatable) or --all-whole-tree. Nothing to trace.'
    );
    return 2;
  }
  const refusal = traceRefusal({ noSeccomp: args.noSeccomp });
  if (refusal !== undefined) {
    console.error(`path-trace: REFUSED. ${refusal}`);
    return 1;
  }
  const lock = readLock(args.root);
  const byId = new Map(lock.map((e) => [e.id, e]));
  const exempt = exemptKinds(args.root);
  const todo: LockEntry[] = [];
  const untraced = new Map<string, string>();
  for (const id of args.gates) {
    const e = byId.get(id);
    if (e === undefined) {
      console.error(`path-trace: no lock entry ${id} in ${LOCK_REL}`);
      return 2;
    }
    // Refused before the trace, not after it: a declared set is a human's claim, replaced only on request.
    if (args.write && !args.replaceDeclared && declaresInputs(e)) {
      console.error(
        `path-trace: ${id} carries ${e.pathsOrigin === undefined ? 'a hand-declared set with no pathsOrigin' : `pathsOrigin '${e.pathsOrigin}'`}: a declared set is judged by trace-honest.ts, never overwritten by a trace. Add --replace-declared to replace it with the traced set (or with none, on a whole-tree verdict).`
      );
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
        ? `${v.paths.length} glob(s), ${v.coveragePct}% of the tree${v.refs !== undefined ? `, refs ${v.refs.join(' ')}` : ''}${v.waived !== undefined ? `, carry-exempt kind waived ${v.waived.join(', ')}` : ''}`
        : `WHOLE-TREE: ${v.reason}`;
    console.error(
      `  [${results.length}/${todo.length}] ${r.id} (${r.seconds}s, exit ${r.exit}, ${v.reads} reads, ${v.listed} listings): ${shape}`
    );
    if (r.exit !== 0) console.error(r.outputTail.replace(/^/gm, '      | '));
    for (const note of r.straceNotes ?? []) console.error(`      strace| ${note}`);
    if (!args.noSeccomp && (r.straceNotes ?? []).some((l) => /seccomp/i.test(l)))
      console.error(
        `      strace named seccomp; retry this gate without the filter: npx tsx scripts/ci-runner/path-trace.ts --gate ${r.id} --no-seccomp`
      );
    if (args.write)
      writeResult(args.root, r, tree, undefined, { replaceDeclared: args.replaceDeclared });
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
        onDone(
          await traceGate(e, view, {
            keepLogs: args.keepLogs,
            timeoutS: args.timeoutS,
            closure: needsClosure(e.id, byId),
            noSeccomp: args.noSeccomp,
            waive: exempt.get(e.id),
          })
        );
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
      if (r.verdict.kind === 'paths') console.log(verdictLine(r.id, r.verdict));
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
  // Per-pid cwd, in a `-f` log: child 101 chdirs to /tmp/x; the parent's LATER relative stat stays in /r.
  const forkLog = [
    '100 clone3({flags=CLONE_VM|CLONE_VFORK, exit_signal=SIGCHLD}, 88) = 101',
    '101 chdir("/tmp/x")                     = 0',
    '101 stat("c.txt", {st_mode=S_IFREG|0644, ...}) = 0',
    '100 stat("later.txt", {st_mode=S_IFREG|0644, ...}) = 0',
  ].join('\n');
  const fa = parseStraceLog(forkLog, '/r');
  check(
    fa.files.has('/r/later.txt') &&
      fa.files.has('/tmp/x/c.txt') &&
      !fa.files.has('/tmp/x/later.txt'),
    "a child's chdir moves only the child: the parent's later relative path stays in its own cwd"
  );
  // Inheritance: the parent chdirs first, then forks; the child's first relative path resolves in the parent's cwd, including through an interleaved <... resumed> fork.
  const inherit = parseStraceLog(
    [
      '200 chdir("/r/sub") = 0',
      '200 clone(child_stack=NULL, flags=CLONE_CHILD_SETTID|SIGCHLD <unfinished ...>',
      '200 <... clone resumed>, child_tidptr=0x7f) = 201',
      '201 access("k.txt", R_OK) = 0',
    ].join('\n'),
    '/r'
  );
  check(
    inherit.files.has('/r/sub/k.txt'),
    "a child starts in its parent's cwd at fork, read through a resumed clone"
  );
  // A THREAD (CLONE_FS) shares the cwd: its chdir moves the process, so the parent's later relative read lands in the new directory (4936a0f3.1). CONTROL: a plain fork does not.
  const threadLog = (flags: string): Access =>
    parseStraceLog(
      [
        `300 clone(child_stack=NULL, flags=${flags} <unfinished ...>`,
        '300 <... clone resumed>, child_tidptr=0x7f) = 301',
        '301 chdir("/r/sub") = 0',
        '300 access("k.txt", R_OK) = 0',
      ].join('\n'),
      '/r'
    );
  check(
    threadLog('CLONE_VM|CLONE_FS|CLONE_THREAD|CLONE_SIGHAND').files.has('/r/sub/k.txt'),
    "a thread's chdir moves the process: the parent's relative read resolves in the new cwd"
  );
  check(
    threadLog('CLONE_CHILD_SETTID|SIGCHLD').files.has('/r/k.txt'),
    'CONTROL: a plain fork keeps the parent cwd when the child chdirs'
  );
  // A peer's relative path named before any cwd was known belongs to the START cwd, not to the directory a sibling thread chdirs into (d1c98d2e.1).
  const peerPre = parseStraceLog(
    [
      '500 access("pre.txt", R_OK) = 0',
      '500 clone(child_stack=NULL, flags=CLONE_VM|CLONE_FS|CLONE_THREAD|CLONE_SIGHAND <unfinished ...>',
      '500 <... clone resumed>, child_tidptr=0x7f) = 501',
      '501 chdir("/r/sub") = 0',
      '500 access("post.txt", R_OK) = 0',
    ].join('\n'),
    '/r'
  );
  check(
    peerPre.files.has('/r/pre.txt') &&
      !peerPre.files.has('/r/sub/pre.txt') &&
      peerPre.files.has('/r/sub/post.txt'),
    "a thread's chdir leaves the peer's earlier relative read in the start cwd (d1c98d2e.1); CONTROL: its later read lands in the new one"
  );
  // An exec before the first chdir ran in the start cwd (cd353e9c.2).
  const execFirst = parseStraceLog(
    [
      '400 execve("/usr/bin/git", ["git", "status"], 0x7ff /* 3 vars */) = 0',
      '400 chdir("/r/elsewhere") = 0',
      '400 access("z", R_OK) = 0',
    ].join('\n'),
    '/r/start'
  );
  check(
    execFirst.execs[0]?.cwd === '/r/start' && execFirst.files.has('/r/elsewhere/z'),
    'an exec seen before the first chdir keeps the start cwd, not the post-chdir one'
  );
  // The -ff log directory is read in NUMERIC pid order with the pid from the file name (4936a0f3.2): t.10 sorts before t.9 as text, and its relative read must still land in its parent's cwd.
  const logDir = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-logs-'));
  try {
    fs.writeFileSync(
      path.join(logDir, 't.9'),
      ['chdir("/r/sub") = 0', 'clone(child_stack=NULL, flags=SIGCHLD) = 10', ''].join('\n')
    );
    fs.writeFileSync(
      path.join(logDir, 't.10'),
      ['access("pre.txt", R_OK) = 0', 'chdir("/r/z") = 0', ''].join('\n')
    );
    const dirAccess = emptyAccess();
    parseStraceDir(logDir, '/r', dirAccess);
    check(
      dirAccess.files.has('/r/sub/pre.txt') && !dirAccess.files.has('/r/pre.txt'),
      'a log directory is parsed in numeric pid order: the child t.10 starts in the cwd its parent t.9 had'
    );
  } finally {
    fs.rmSync(logDir, { recursive: true, force: true });
  }
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
    v1.kind === 'paths' &&
      v1.paths.join(',') === 'a/one.txt,a/two.txt' &&
      JSON.stringify(v1.lists) === '["c/listed"]' &&
      v1.names === undefined,
    `CONTROL: two files read plus one listed directory give those two paths and lists: ['c/listed'], not c/listed/** (got ${v1.kind === 'paths' ? `${v1.paths.join(',')} lists=${JSON.stringify(v1.lists)}` : v1.reason})`
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
    v4d.kind === 'paths' &&
      v4d.paths.join(',') === 'a/one.txt' &&
      JSON.stringify(v4d.refs) === '["HEAD"]',
    `HEAD read as a revision by argv is pinned to refs ['HEAD'] (F2 B5; got ${v4d.kind === 'paths' ? JSON.stringify(v4d.refs) : v4d.reason})`
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
    'CONTROL: the same read with its producer among the needs keeps its paths'
  );
  const vbo = fold(buildAttr, view, ['build:other']);
  check(
    vbo.kind === 'whole-tree' && vbo.reason.includes('built by build:www'),
    'an unrelated needs entry does not cover build output another node produces'
  );
  const lockById = new Map<string, LockEntry>([
    ['g', { id: 'g', run: 'x', gate: true, needs: ['build:cli'] }],
    ['build:cli', { id: 'build:cli', run: 'y', gate: false, needs: ['build:packages'] }],
    ['build:packages', { id: 'build:packages', run: 'z', gate: false }],
  ]);
  const sharedAttr = {
    ...attribute(mk(['a/one.txt']), view),
    buildOutput: ['packages/shared/dist/index.js'],
  };
  const vt = fold(sharedAttr, view, needsClosure('g', lockById));
  check(
    vt.kind === 'paths',
    'a producer reached through needs transitively (build:cli -> build:packages) covers its output'
  );
  const vj = fold(
    { ...attribute(mk(['a/one.txt']), view), buildOutput: ['packages/json/dist/x.json'] },
    view,
    ['build:www', 'build:packages', 'build:cli']
  );
  check(
    vj.kind === 'whole-tree' && vj.reason.includes('no manifest node builds it'),
    'build output no manifest node builds is never covered'
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
  const urlC = mk(['a/one.txt']);
  urlC.execs.push({
    argv: ['/usr/lib/git-core/git', 'remote-https', 'origin', 'https://u:t@example.test/x.git'],
    cwd: '/r',
  });
  const vu = fold(attribute(urlC, view), view);
  check(
    vu.kind === 'whole-tree' &&
      vu.reason.includes('origin <url>') &&
      !vu.reason.includes('example.test'),
    'a remote URL in a git argv is shown as <url>, never verbatim'
  );
  {
    // A symlinked root: a relative --git-common-dir stays under the real root, where strace reports its reads (d1c98d2e.2).
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-link-'));
    try {
      const realDir = path.join(tmp, 'real');
      fs.mkdirSync(path.join(realDir, '.ci', 'policy'), { recursive: true });
      fs.writeFileSync(
        path.join(realDir, policyPath('record-paths.json', '.')),
        `${JSON.stringify({ records: [] })}\n`
      );
      fs.writeFileSync(path.join(realDir, 'f.txt'), 'x');
      spawnSync('git', ['init', '-q'], { cwd: realDir });
      spawnSync('git', ['add', '-A'], { cwd: realDir });
      fs.symlinkSync(realDir, path.join(tmp, 'link'));
      const lv = repoView(path.join(tmp, 'link'));
      check(
        lv.gitDirs.length > 0 &&
          lv.gitDirs.every((g) => g.startsWith(`${fs.realpathSync(realDir)}/`)),
        `a symlinked root keeps every git directory under the real root (${lv.gitDirs.join(',')})`
      );
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  }
  const urlOpt = mk(['a/one.txt']);
  urlOpt.execs.push({
    argv: ['git', '-c', 'remote.origin.url=https://user:tok@host.test/x.git', 'log', '-1'],
    cwd: '/r',
  });
  const vo = fold(attribute(urlOpt, view), view);
  check(
    vo.kind === 'whole-tree' &&
      vo.reason.includes('remote.origin.url=<url>') &&
      !vo.reason.includes('tok') &&
      !vo.reason.includes('host.test'),
    'a credentialed URL after an option prefix (-c remote.origin.url=...) is shown as <url> too (012ebca8.1)'
  );
  check(
    classifyGitArgv(['git', '-C', 'x', 'rev-parse', '--show-toplevel']) === 'discovery' &&
      classifyGitArgv(['/usr/bin/git', 'ls-files', '-z']) === 'names' &&
      classifyGitArgv(['git', 'grep', 'x']) === 'index' &&
      classifyGitArgv(['git', 'log', '-1']) === 'history' &&
      classifyGitArgv(['git', 'frobnicate']) === 'history' &&
      classifyGitArgv(['node', 'x']) === 'discovery',
    'git argv classes: locate, names, index, history, unknown-is-history, not-git'
  );
  const v5 = fold(attribute(mk(['a/one.txt'], ['']), view), view);
  check(
    v5.kind === 'paths' &&
      v5.paths.join(',') === 'a/one.txt' &&
      JSON.stringify(v5.lists) === '[""]',
    "listing the root is lists: [''], no longer whole-tree"
  );
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
    vp.kind === 'paths' && vp.lists?.includes('private') === true,
    'a listing of a directory holding only gitlinks is a tracked listing, not build output'
  );
  const v10 = fold(attribute(mk(['private/sub/go.mod', 'a/one.txt']), view), view);
  check(
    v10.kind === 'paths' &&
      v10.paths.includes('private/sub') &&
      !v10.paths.includes('private/sub/**'),
    'a read inside a submodule names the gitlink'
  );
  // Absolute paths, not mk(): mk prefixes /r/, which once turned '/usr/lib/x.so' into an in-root path and left this control testing nothing out of the repository.
  const v11 = fold(
    attribute(
      {
        files: new Set(['/r/a/one.txt', '/r/.claude/hooks/profile/bash_env.sh', '/usr/lib/x.so']),
        listed: new Set(['/usr/lib']),
        execs: [],
      },
      view
    ),
    view
  );
  check(
    v11.kind === 'paths' && v11.paths.join(',') === 'a/one.txt' && v11.lists === undefined,
    'profiler hook and out-of-repo reads and listings are not inputs'
  );

  // The profiler rule, with the file TRACKED: without the rule a tracked profile file a gate never meant to read would be a path (ffa5756e.4).
  const profileView: RepoView = {
    ...view,
    files: [...view.files, '.claude/hooks/profile/bash_env.sh'],
  };
  const vProfile = attribute(
    {
      files: new Set(['/r/a/one.txt', '/r/.claude/hooks/profile/bash_env.sh']),
      listed: new Set(),
      execs: [],
    },
    profileView
  );
  check(
    !vProfile.reads.has('.claude/hooks/profile/bash_env.sh') && vProfile.reads.has('a/one.txt'),
    'a TRACKED profiler hook is ignored by its prefix; CONTROL: an ordinary tracked read stays'
  );
  // A dependency read names the root lockfile when it is tracked (1b2c643e.3).
  const lockView: RepoView = { ...view, files: [...view.files, 'package-lock.json'] };
  check(
    attribute(mk(['node_modules/x/index.js']), lockView).reads.has('package-lock.json') &&
      !attribute(mk(['node_modules/x/index.js']), view).reads.has('package-lock.json') &&
      !attribute(mk(['a/one.txt']), lockView).reads.has('package-lock.json'),
    'a node_modules read names the tracked root lockfile; CONTROL: no lockfile tracked, or no dependency read, names none'
  );
  // A set with no pathsOrigin is declared, not overwritable (ffa5756e.2).
  const base = { id: 'g:x', run: 'x', gate: true } as unknown as LockEntry;
  check(
    declaresInputs({ ...base, paths: ['a/**'] } as LockEntry) &&
      declaresInputs({ ...base, paths: ['a/**'], pathsOrigin: 'declared' } as LockEntry) &&
      !declaresInputs({ ...base, paths: ['a/**'], pathsOrigin: TRACED_ORIGIN } as LockEntry) &&
      !declaresInputs(base) &&
      declaresInputs({ ...base, pathsOrigin: 'declared' } as LockEntry) &&
      !declaresInputs({ ...base, pathsOrigin: TRACED_ORIGIN } as LockEntry),
    "declaresInputs: a set with no origin or a declared one is a human's, and so is origin declared with every set empty (83f9183b.1); a traced set and no set are not"
  );

  // W2.3: discovery is not history, history is still history, the network is its own verdict.
  const lsAcc = parseStraceLog(
    [
      'access("/r/.git/objects", X_OK) = 0',
      'access("/r/.git/refs", X_OK) = 0',
      'openat(AT_FDCWD</r>, "/r/.git/objects/info/alternates", O_RDONLY) = -1 ENOENT (No such file or directory)',
      'openat(AT_FDCWD</r>, "/r/.git/index", O_RDONLY) = 3</r/.git/index>',
      'execve("/usr/bin/git", ["git", "ls-files", "-z"], 0x7ff /* 3 vars */) = 0',
      'openat(AT_FDCWD</r>, "a/one.txt", O_RDONLY) = 4</r/a/one.txt>',
    ].join('\n'),
    root
  );
  const vls = fold(attribute(lsAcc, view), view);
  check(
    vls.kind === 'paths' &&
      vls.paths.join(',') === 'a/one.txt' &&
      JSON.stringify(vls.names) === '["**"]',
    `CONTROL: git ls-files -z plus access(.git/objects), .git/refs, objects/info/alternates and the .git/index it reads is names: ['**'], not history (got ${vls.kind === 'whole-tree' ? vls.reason : `${vls.paths} names=${JSON.stringify(vls.names)}`})`
  );
  const tAcc = mk(['a/one.txt', '.git/objects', '.git/index']);
  tAcc.execs.push({ argv: ['git', 'ls-files', '-t'], cwd: '/r' });
  const vt2 = fold(attribute(tAcc, view), view);
  check(
    vt2.kind === 'whole-tree' &&
      vt2.reason.includes('git index') &&
      !vt2.reason.includes('history'),
    'an ls-files flag outside the name-only set (-t) stays the whole-tree index, still not history'
  );
  const bareIdx = fold(attribute(mk(['a/one.txt', '.git/index']), view), view);
  check(
    bareIdx.kind === 'whole-tree' && bareIdx.reason.includes('.git/index'),
    'a .git/index read no name-only ls-files explains is the whole-tree index'
  );
  const mixIdx = mk(['a/one.txt', '.git/index']);
  mixIdx.execs.push(
    { argv: ['git', 'ls-files', '-z'], cwd: '/r' },
    { argv: ['git', 'check-attr', 'x', '--', 'a'], cwd: '/r' }
  );
  const vmix = fold(attribute(mixIdx, view), view);
  check(
    vmix.kind === 'whole-tree' && vmix.reason.includes('check-attr'),
    'a name-only ls-files beside another index command is still whole-tree'
  );
  // bab2c5c8.2: the reader of .git/index is judged by pid. Pid 7 ran `git ls-files -z` and read the index; pid 8 is a non-git process reading it too.
  const pidLog = (readerPid: number): string =>
    [
      `7 execve("/usr/bin/git", ["git", "ls-files", "-z"], 0x7ff /* 3 vars */) = 0`,
      `7 openat(AT_FDCWD</r>, "/r/.git/index", O_RDONLY) = 3</r/.git/index>`,
      `${readerPid} openat(AT_FDCWD</r>, "/r/.git/index", O_RDONLY) = 4</r/.git/index>`,
      `7 openat(AT_FDCWD</r>, "a/one.txt", O_RDONLY) = 5</r/a/one.txt>`,
    ].join('\n');
  const ownRead = fold(attribute(parseStraceLog(pidLog(7), '/r'), view), view);
  check(
    ownRead.kind === 'paths' && JSON.stringify(ownRead.names) === '["**"]',
    "CONTROL: the index read by the name-only git ls-files's own pid is explained: names ['**']"
  );
  const foreignRead = fold(attribute(parseStraceLog(pidLog(8), '/r'), view), view);
  check(
    foreignRead.kind === 'whole-tree' && foreignRead.reason.includes('.git/index'),
    'a non-git process reading .git/index beside a name-only ls-files is the whole-tree index'
  );
  const nonGitIndex = fold(
    attribute(
      parseStraceLog(
        [
          `7 execve("/usr/bin/git", ["git", "ls-files", "-z"], 0x7ff /* 3 vars */) = 0`,
          `7 openat(AT_FDCWD</r>, "/r/.git/index", O_RDONLY) = 3</r/.git/index>`,
          `9 openat(AT_FDCWD</r>, "/r/a/index", O_RDONLY) = 4</r/a/index>`,
        ].join('\n'),
        '/r'
      ),
      view
    ),
    view
  );
  check(
    nonGitIndex.kind === 'paths' && JSON.stringify(nonGitIndex.names) === '["**"]',
    'a non-git process reading an unrelated file named index (a/index) is no foreign index reader: the name-only ls-files still explains .git/index'
  );
  check(
    classifyGitArgv(['git', 'ls-files', '-z', '--recurse-submodules']) === 'names' &&
      classifyGitArgv(['git', 'ls-files', '-s', '--recurse-submodules']) === 'content',
    'git ls-files --recurse-submodules is a names scan (F2 B2; attribute adds the gitlinks), and with -s it is still content'
  );
  check(
    classifyGitArgv(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard']) ===
      'names' &&
      classifyGitArgv(['git', 'ls-files', '-co', '-x', '*.md', '--', 'a']) === 'names' &&
      classifyGitArgv(['git', 'ls-files', '--exclude-from=.gitignore', 'a/']) === 'names' &&
      classifyGitArgv(['git', 'ls-files', '-t']) === 'index' &&
      classifyGitArgv(['git', 'ls-files', '--with-tree=HEAD']) === 'history',
    'ls-files with only name-shaping flags (and pathspecs) is names; an unknown flag is index; --with-tree is history'
  );
  const names30 = mk(['a/one.txt'], ['e']);
  names30.execs.push({ argv: ['git', 'ls-files', '-z'], cwd: '/r' });
  const v30 = fold(attribute(names30, view), view);
  check(
    v30.kind === 'paths' &&
      v30.paths.join(',') === 'a/one.txt' &&
      JSON.stringify(v30.lists) === '["e"]' &&
      JSON.stringify(v30.names) === '["**"]' &&
      v30.coveragePct < 30,
    `the 30% line weighs content globs only: lists of a 40-file directory and names ['**'] stay under it (got ${v30.kind === 'paths' ? v30.coveragePct : v30.reason})`
  );
  const vunder = fold(attribute(mk(['b/x.ts', 'b/y.ts', 'b/z.ts'], ['b']), view), view);
  check(
    vunder.kind === 'paths' && vunder.paths.join(',') === 'b/**' && vunder.lists === undefined,
    'a listing inside a content dir glob is dropped: b/** already moves with every name under b'
  );
  const vonly = fold(attribute(mk([], ['c/listed']), view), view);
  check(
    vonly.kind === 'paths' &&
      vonly.paths.length === 0 &&
      JSON.stringify(vonly.lists) === '["c/listed"]',
    'a gate that only lists a directory is scoped by lists alone, with no paths'
  );
  const logAcc = mk(['a/one.txt', '.git/objects', '.git/objects/pack/p.idx']);
  logAcc.execs.push({ argv: ['git', 'log', '-1'], cwd: '/r' });
  const vlog = fold(attribute(logAcc, view), view);
  check(
    vlog.kind === 'whole-tree' &&
      vlog.reason.includes('history') &&
      vlog.reason.includes('git log -1') &&
      vlog.reason.includes('.git/objects/pack/p.idx'),
    'git log still reads history, by argv and by its pack read'
  );
  const vlist = fold(attribute(mk(['a/one.txt'], ['.git/refs']), view), view);
  check(
    vlist.kind === 'whole-tree' && vlist.reason.includes('list .git/refs'),
    'a LISTING of .git/refs is history: the existence exemption is for a path read only'
  );
  const vsub = fold(
    attribute(mk(['a/one.txt', '.git/modules/private/sub/refs/heads/main']), view),
    view
  );
  check(
    vsub.kind === 'whole-tree' && vsub.reason.includes('modules/private/sub/refs/heads/main'),
    'a submodule refs read (.git/modules/<name>/refs) is history'
  );
  const vsubp = fold(
    attribute(mk(['a/one.txt', '.git/modules/private/sub/packed-refs']), view),
    view
  );
  const vsubl = fold(
    attribute(mk(['a/one.txt', '.git/modules/private/sub/logs/HEAD']), view),
    view
  );
  check(
    vsubp.kind === 'whole-tree' && vsubl.kind === 'whole-tree',
    'a submodule packed-refs or logs read is history'
  );
  const vsubd = fold(
    attribute(
      mk(['a/one.txt', '.git/modules/private/sub/objects', '.git/modules/private/sub/HEAD']),
      view
    ),
    view
  );
  check(
    vsubd.kind === 'paths' && vsubd.paths.join(',') === 'a/one.txt',
    "CONTROL: a submodule's bare objects existence check and its HEAD are discovery"
  );
  check(
    GIT_DISCOVERY_FILE.test('modules/x/objects') &&
      GIT_DISCOVERY_FILE.test('modules/a/b/refs') &&
      !GIT_DISCOVERY_FILE.test('modules/x/refs/heads/objects') &&
      !GIT_DISCOVERY_FILE.test('modules/a/b/logs/refs') &&
      GIT_HISTORY_FILE.test('modules/x/refs/heads/objects') &&
      GIT_HISTORY_FILE.test('modules/objects/objects/ab/cd') &&
      GIT_HISTORY_FILE.test('modules/logs/refs/heads/main') &&
      GIT_HISTORY_FILE.test('modules/objects/refs') &&
      !GIT_DISCOVERY_FILE.test('modules/objects/refs') &&
      !GIT_HISTORY_FILE.test('modules/x/config') &&
      !GIT_DISCOVERY_FILE.test('modules/x/config'),
    'a submodule branch file named objects is history, not discovery, and so are an ambiguous modules/objects/objects/ab/cd, modules/logs/refs/heads/main and the bare modules/objects/refs (the greedy history prefix, dd5103a3.3); CONTROL: modules/<name>/objects and nested names stay discovery, modules/x/config is neither'
  );
  check(
    networkPeer('3<socket:[1]>, {sa_family=AF_INET, sin_addr=inet_addr("1.1.1.1")}, 16) = 0') ===
      'AF_INET:unparsed' &&
      networkPeer('3<socket:[1]>, {sa_family=AF_INET6, sin6_port=0}, 28) = 0') ===
        'AF_INET6:unparsed' &&
      networkPeer('3<socket:[4]>, {sa_family=AF_UNIX, sun_path="/r/a"}, 12) = 0') === undefined &&
      networkPeer('3<socket:[4]>, {sa_family=AF_UNSPEC}, 16) = 0') === undefined,
    'an AF_INET connect strace printed in an unknown shape is still a network peer; CONTROL: AF_UNIX and AF_UNSPEC are not'
  );
  // A shared-index file whose path has no `.git` component (here /g, a git directory named elsewhere than the cwd /r) counts as a repository read (b71d19c7.2).
  const shared = parseStraceLog(
    [
      '500 openat(AT_FDCWD</r>, "/g/sharedindex.abc", O_RDONLY) = 3</g/sharedindex.abc>',
      '500 openat(AT_FDCWD</r>, "/g/notes.abc", O_RDONLY) = 4</g/notes.abc>',
    ].join('\n'),
    '/r'
  );
  check(
    shared.gitReaders?.has('/g/sharedindex.abc') === true &&
      shared.gitReaders?.has('/g/notes.abc') !== true,
    'a sharedindex.* file is a repository read; CONTROL: an ordinary file beside it is not'
  );
  const idx3 = mk(['a/one.txt']);
  for (const a of ['-t', '-t', '-t']) idx3.execs.push({ argv: ['git', 'ls-files', a], cwd: '/r' });
  idx3.execs.push({ argv: ['git', 'ls-files', '-s'], cwd: '/r' });
  const aIdx3 = attribute(idx3, view);
  check(
    aIdx3.gitIndex.length === 3 &&
      (aIdx3.gitContent ?? []).includes('git ls-files -s') &&
      !aIdx3.gitIndex.includes('git ls-files -s'),
    'a content use after three index uses is in gitContent alone, and gitIndex stays non-empty (the documented invariant)'
  );
  check(
    classifyGitArgv(['git', 'status', '--porcelain']) === 'history' &&
      classifyGitArgv(['git', 'remote', '-v']) === 'discovery' &&
      classifyGitArgv(['git', 'remote', 'get-url', 'origin']) === 'discovery' &&
      classifyGitArgv(['git', 'remote', 'show', 'origin']) === 'history' &&
      classifyGitArgv(['git', 'rev-list', '--max-parents=0', 'HEAD']) === 'history' &&
      classifyGitArgv(['git', 'rev-list', 'HEAD']) === 'history' &&
      classifyGitArgv(['git', 'rev-list', '--max-parents=0', 'main']) === 'history',
    'status is history; remote -v|get-url and a root-commit rev-list (it walks history) is history; remote show and other rev-lists are history'
  );
  check(
    classifyGitArgv(['git', 'diff']) === 'content' &&
      classifyGitArgv(['git', 'diff', '--exit-code', '--', 'a/one.txt']) === 'content' &&
      classifyGitArgv(['git', 'diff', '--name-only', 'HEAD']) === 'history' &&
      classifyGitArgv(['git', 'diff', 'a/one.txt']) === 'history' &&
      classifyGitArgv(['git', 'diff', '--cached', '--', 'a/one.txt']) === 'history',
    'diff with no revision and only paths after -- reads content; a positional before -- or --cached is history'
  );
  check(
    classifyGitArgv(['git', 'ls-files', '-s']) === 'content' &&
      classifyGitArgv(['git', 'ls-files', '--stage', '-z']) === 'content' &&
      classifyGitArgv(['git', 'ls-files', '--eol']) === 'content' &&
      classifyGitArgv(['git', 'ls-files', '--format=%(objectname) %(path)']) === 'content' &&
      classifyGitArgv(['git', 'ls-files', '-m']) === 'content' &&
      classifyGitArgv(['git', 'ls-files', '-d']) === 'content' &&
      classifyGitArgv(['git', 'ls-files', '-sz']) === 'content' &&
      classifyGitArgv(['git', 'ls-files', '-z', '--cached', '--others']) === 'names' &&
      classifyGitArgv(['git', 'ls-files', '-co']) === 'names',
    'ls-files with -s|--stage|--eol|--format|-m|-d (bundled too) is content; name-only flags are names'
  );
  const lsS = mk(['a/one.txt']);
  lsS.execs.push({ argv: ['git', 'ls-files', '-s'], cwd: '/r' });
  const aS = attribute(lsS, view);
  const vS = fold(aS, view);
  check(
    vS.kind === 'whole-tree' &&
      vS.reason.includes('holds') &&
      aS.gitIndex.includes('git ls-files -s'),
    'a content use is whole-tree naming the content, and is in gitIndex too (trace-honest still flags it)'
  );
  const netAcc = parseStraceLog(
    [
      'connect(3<socket:[1]>, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("1.1.1.1")}, 16) = -1 EINPROGRESS (Operation now in progress)',
      'openat(AT_FDCWD</r>, "a/one.txt", O_RDONLY) = 4</r/a/one.txt>',
    ].join('\n'),
    root
  );
  const vnet = fold(attribute(netAcc, view), view);
  check(
    vnet.kind === 'whole-tree' &&
      vnet.reason.startsWith('network') &&
      vnet.reason.includes('1.1.1.1:443'),
    `a fixture connect to 1.1.1.1 is a whole-tree "network" verdict (got ${vnet.kind === 'whole-tree' ? vnet.reason : vnet.kind})`
  );
  const loAcc = parseStraceLog(
    [
      'connect(3<socket:[1]>, {sa_family=AF_INET, sin_port=htons(9), sin_addr=inet_addr("127.0.0.1")}, 16) = -1 ECONNREFUSED (Connection refused)',
      'connect(3<socket:[2]>, {sa_family=AF_INET6, sin6_port=htons(9), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = -1 ECONNREFUSED (Connection refused)',
      'connect(3<socket:[3]>, {sa_family=AF_INET6, sin6_port=htons(9), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::ffff:127.0.0.53", &sin6_addr), sin6_scope_id=0}, 28) = 0',
      'connect(3<socket:[4]>, {sa_family=AF_UNIX, sun_path="/r/a/two.txt"}, 12) = -1 ENOENT (No such file or directory)',
      'openat(AT_FDCWD</r>, "a/one.txt", O_RDONLY) = 4</r/a/one.txt>',
    ].join('\n'),
    root
  );
  const vlo = fold(attribute(loAcc, view), view);
  check(
    vlo.kind === 'paths' &&
      vlo.paths.join(',') === 'a/one.txt' &&
      (loAcc.network?.size ?? -1) === 0,
    'CONTROL: loopback (127/8, ::1, v4-mapped) and a unix socket are not network, and a sun_path is no file read'
  );
  check(
    networkPeer(
      '3<socket:[1]>, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "2606:4700::1111", &sin6_addr), sin6_scope_id=0}, 28) = 0'
    ) === '[2606:4700::1111]:443',
    'a non-loopback IPv6 peer is network'
  );
  const dnsLine = (addr: string): string =>
    `3<socket:[1]>, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("${addr}")}, 16) = 0`;
  check(
    networkPeer(dnsLine('127.0.0.53')) === '127.0.0.53:53' &&
      networkPeer(dnsLine('127.0.0.11')) === '127.0.0.11:53' &&
      networkPeer(dnsLine('0.0.0.0')) === '0.0.0.0:53' &&
      networkPeer(
        '3<socket:[1]>, {sa_family=AF_INET6, sin6_port=htons(53), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::ffff:127.0.0.1", &sin6_addr), sin6_scope_id=0}, 28) = 0'
      ) === '[::ffff:127.0.0.1]:53' &&
      networkPeer(
        '3<socket:[1]>, {sa_family=AF_INET6, sin6_port=htons(53), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = 0'
      ) === '[::1]:53' &&
      networkPeer(
        '3<socket:[1]>, {sa_family=AF_INET, sin_port=htons(8787), sin_addr=inet_addr("127.0.0.1")}, 16) = 0'
      ) === undefined,
    'a loopback resolver (127.0.0.53:53, 127.0.0.11:53, 0.0.0.0:53, [::ffff:127.0.0.1]:53, [::1]:53) is network, since it forwards upstream; CONTROL: 127.0.0.1:8787 is not'
  );
  const fromRaw: Access = {
    files: new Set(['/r/a/one.txt']),
    listed: new Set(),
    execs: [],
    network: new Set(rawOf(netAcc, view).network),
  };
  const vraw = fold(attribute(fromRaw, view), view);
  check(
    vraw.kind === 'whole-tree' && vraw.reason.startsWith('network'),
    'the raw record keeps the network peers, so --refold re-derives the network verdict'
  );
  check(
    straceArgv('/x/t', 'true').includes(`trace=${TRACE_SYSCALLS}`) &&
      TRACE_SYSCALLS.split(',').includes('connect') &&
      straceArgv('/x/t', 'true').includes('--seccomp-bpf') &&
      !straceArgv('/x/t', 'true', true).includes('--seccomp-bpf') &&
      straceArgv('/x/t', 'true').at(-1) === 'exec 2>&1\ntrue',
    'strace traces connect; --no-seccomp drops --seccomp-bpf; the traced shell sends its stderr to its stdout'
  );

  // ---- F2 (PLAN-push-decoupling): each fold beside a twin that must stay whole-tree. ----
  const pv = (lines: string[], v: RepoView = view): Verdict =>
    fold(attribute(parseStraceLog(lines.join('\n'), '/r'), v), v);
  const shape = (v: Verdict): string =>
    v.kind === 'paths'
      ? `${v.paths.join(',')} lists=${JSON.stringify(v.lists)} names=${JSON.stringify(v.names)} refs=${JSON.stringify(v.refs)}`
      : v.reason;
  const ex = (pid: number, argv: string[], cwd = '/r'): string =>
    `${pid} chdir("${cwd}") = 0\n${pid} execve("/usr/bin/git", [${argv.map((a) => JSON.stringify(a)).join(', ')}], 0x7ff /* 3 vars */) = 0`;
  const open = (pid: number, abs: string): string =>
    `${pid} openat(AT_FDCWD</r>, "${abs}", O_RDONLY) = 3<${abs}>`;

  // B1: a fixture repository's own index, read by its own git, is not this repository's index.
  const b1 = pv([
    ex(7, ['git', 'ls-files', '-z']),
    open(7, '/r/.git/index'),
    ex(9, ['git', '-C', '/tmp/fx', 'ls-files', '-s']),
    open(9, '/tmp/fx/.git/index'),
    open(7, '/r/a/one.txt'),
  ]);
  check(
    b1.kind === 'paths' && JSON.stringify(b1.names) === '["**"]',
    `B1: a selftest's own \`git -C /tmp/fx ls-files -s\` reading /tmp/fx/.git/index is no foreign reader of this index: names ['**'] (got ${shape(b1)})`
  );
  const b1c = pv([
    ex(7, ['git', 'ls-files', '-z']),
    open(7, '/r/.git/index'),
    `8 openat(AT_FDCWD</r>, "/r/.git/index", O_RDONLY) = 4</r/.git/index>`,
    open(9, '/tmp/fx/.git/index'),
  ]);
  check(
    b1c.kind === 'whole-tree' && b1c.reason.includes('.git/index'),
    `B1 CONTROL: a process with no name-only listing reading THIS index is still foreign, fixture beside it or not (got ${shape(b1c)})`
  );
  const b1n = pv([open(9, '/tmp/fx/.git/index'), open(9, '/r/a/one.txt')]);
  check(
    b1n.kind === 'paths' && b1n.paths.join(',') === 'a/one.txt',
    'B1: a fixture index read alone, with no git command aimed here, adds nothing'
  );

  // B2: --recurse-submodules folds to names ['**'] plus every gitlink; the submodule index the scan reads is its own.
  const b2 = pv([
    ex(7, ['git', 'ls-files', '-z', '--recurse-submodules']),
    open(7, '/r/.git/index'),
    open(7, '/r/.git/modules/private/sub/index'),
    ex(11, ['git', 'ls-files', '--recurse-submodules', '-z'], '/r/private/sub'),
    open(11, '/r/.git/modules/private/sub/index'),
  ]);
  check(
    b2.kind === 'paths' &&
      b2.paths.join(',') === 'private/sub' &&
      JSON.stringify(b2.names) === '["**"]',
    `B2: ls-files --recurse-submodules gives names ['**'] plus the gitlink private/sub in paths, the per-submodule child's index read its own (got ${shape(b2)})`
  );
  // git 2.53 reads each submodule's index in-process (measured 2026-11-18 under strace): no child, so the flag alone must name the gitlinks.
  const b2in = pv([
    ex(7, ['git', 'ls-files', '-z', '--recurse-submodules']),
    open(7, '/r/.git/index'),
    open(7, '/r/.git/modules/private/sub/index'),
  ]);
  check(
    b2in.kind === 'paths' &&
      b2in.paths.join(',') === 'private/sub' &&
      JSON.stringify(b2in.names) === '["**"]',
    `B2: with no per-submodule child (git 2.53 reads the submodule index in-process), the flag alone puts every gitlink in paths (got ${shape(b2in)})`
  );
  const b2c = pv([
    ex(7, ['git', 'ls-files', '-z', '--recurse-submodules']),
    open(7, '/r/.git/index'),
    `12 openat(AT_FDCWD</r>, "/r/.git/modules/private/sub/index", O_RDONLY) = 4</r/.git/modules/private/sub/index>`,
  ]);
  check(
    b2c.kind === 'whole-tree' && b2c.reason.includes('modules/private/sub/index'),
    `B2 CONTROL: a non-git process reading the submodule index beside the scan is foreign (got ${shape(b2c)})`
  );

  // B3: pathspecs fold to globs relative to the exec's cwd; -s with a pathspec is content of it; a names-only --format is names.
  const b3 = pv([ex(7, ['git', 'ls-files', '-z', '--', '*.ts']), open(7, '/r/.git/index')]);
  check(
    b3.kind === 'paths' &&
      JSON.stringify(b3.names) === '["**/*.ts"]' &&
      JSON.stringify(b3.lists) === '[""]',
    `B3: ls-files -- '*.ts' gives names ['**/*.ts'] and, since no root .ts exists (a dead '*.ts' would be refused), lists [''] (got ${shape(b3)})`
  );
  const b3cwd = pv([
    ex(7, ['git', 'ls-files', '-z', 'one.txt', 'listed'], '/r/a'),
    open(7, '/r/.git/index'),
  ]);
  const b3c = pv([ex(7, ['git', '-C', 'c', 'ls-files', 'listed'], '/r'), open(7, '/r/.git/index')]);
  check(
    b3cwd.kind === 'paths' &&
      JSON.stringify(b3cwd.names) === '["a/**","a/one.txt"]' &&
      b3c.kind === 'paths' &&
      JSON.stringify(b3c.names) === '["c/listed/**"]',
    `B3: literal pathspecs resolve against the exec cwd and -C: a tracked file is itself, a missing one widens to its tracked directory, a directory is D/** (got ${shape(b3cwd)} | ${shape(b3c)})`
  );
  const b3s = pv([ex(7, ['git', 'ls-files', '-s', '--', 'a/one.txt']), open(7, '/r/.git/index')]);
  check(
    b3s.kind === 'paths' && b3s.paths.join(',') === 'a/one.txt' && b3s.names === undefined,
    `B3: ls-files -s -- a/one.txt is the content of a/one.txt, not every file (got ${shape(b3s)})`
  );
  const b3sc = pv([ex(7, ['git', 'ls-files', '-s']), open(7, '/r/.git/index')]);
  check(
    b3sc.kind === 'whole-tree' && b3sc.reason.includes('holds'),
    'B3 CONTROL: ls-files -s with no pathspec still reads what every tracked file holds'
  );
  const b3f = pv([
    ex(7, ['git', 'ls-files', '-z', '--format=%(objectmode) %(path)']),
    open(7, '/r/.git/index'),
  ]);
  const b3fc = pv([
    ex(7, ['git', 'ls-files', '--format=%(objectmode) %(objectname) %(path)']),
    open(7, '/r/.git/index'),
  ]);
  check(
    b3f.kind === 'paths' &&
      JSON.stringify(b3f.names) === '["**"]' &&
      b3fc.kind === 'whole-tree' &&
      formatIsNames('%(path)%x00') &&
      !formatIsNames('%(path) %(eolinfo:index)'),
    `B3: --format with only %(objectmode) and %(path) is names; CONTROL: adding %(objectname) is content (got ${shape(b3f)} | ${shape(b3fc)})`
  );
  const b3m = pv([ex(7, ['git', 'ls-files', '-z', ':(glob)**/*.ts']), open(7, '/r/.git/index')]);
  const b3u = pv([
    ex(7, ['git', 'ls-files', '-s', '-t', '--', 'a/one.txt']),
    open(7, '/r/.git/index'),
  ]);
  check(
    b3m.kind === 'paths' && JSON.stringify(b3m.names) === '["**"]' && b3u.kind === 'whole-tree',
    `B3 CONTROL: pathspec magic widens to the whole name set, and an unknown flag (-t) beside -s keeps it whole-tree content (got ${shape(b3m)} | ${shape(b3u)})`
  );

  // B4: `git diff --quiet <tracked file>` is the content of that path.
  const b4 = pv([ex(7, ['git', 'diff', '--quiet', 'a/one.txt']), open(7, '/r/.git/index')]);
  check(
    b4.kind === 'paths' && b4.paths.join(',') === 'a/one.txt' && b4.refs === undefined,
    `B4: git diff --quiet a/one.txt is the content of a/one.txt (got ${shape(b4)})`
  );
  const b4p = pv([
    ex(7, ['git', 'diff', '--quiet', 'a/one.txt']),
    open(7, '/r/.git/packed-refs'),
    open(7, '/r/.git/refs/tags/a/one.txt'),
    open(7, '/r/.git/refs/remotes/a/one.txt/HEAD'),
    open(7, '/r/.git/index'),
  ]);
  const b4pc = pv([
    ex(7, ['git', 'diff', '--quiet', 'a/one.txt']),
    open(7, '/r/.git/refs/heads/main'),
    open(7, '/r/.git/index'),
  ]);
  check(
    b4p.kind === 'paths' &&
      b4p.paths.join(',') === 'a/one.txt' &&
      b4pc.kind === 'whole-tree' &&
      b4pc.reason.includes('refs/heads/main'),
    `B4: the diff's own "is a/one.txt a ref?" probes (git's lookup rules, packed-refs) are no history read; CONTROL: the same process reading another ref is (got ${shape(b4p)} | ${shape(b4pc)})`
  );
  // An absolute spelling of a tracked path is that path, from the root and from a subdirectory alike; CONTROL: an absolute path outside the checkout is no tracked path, and the read stays whole-tree.
  const b4abs = pv([ex(7, ['git', 'diff', '--quiet', '/r/a/one.txt']), open(7, '/r/.git/index')]);
  const b4absSub = pv([
    ex(7, ['git', 'diff', '--quiet', '/r/a/one.txt'], '/r/b'),
    open(7, '/r/.git/index'),
  ]);
  const b4absOut = pv([
    ex(7, ['git', 'diff', '--quiet', '/elsewhere/a/one.txt']),
    open(7, '/r/.git/index'),
  ]);
  check(
    b4abs.kind === 'paths' &&
      b4abs.paths.join(',') === 'a/one.txt' &&
      b4absSub.kind === 'paths' &&
      b4absSub.paths.join(',') === 'a/one.txt' &&
      b4absOut.kind === 'whole-tree',
    `B4: git diff --quiet /r/a/one.txt is the content of a/one.txt from / and from b/; CONTROL: /elsewhere/a/one.txt stays whole-tree (got ${shape(b4abs)} | ${shape(b4absSub)} | ${shape(b4absOut)})`
  );
  const b4c = pv([ex(7, ['git', 'diff', '--quiet', 'HEAD']), open(7, '/r/.git/index')]);
  const b4cached = pv([ex(7, ['git', 'diff', '--cached', '--quiet', 'a/one.txt'])]);
  check(
    b4c.kind === 'whole-tree' &&
      b4c.reason.includes('holds') &&
      b4cached.kind === 'whole-tree' &&
      b4cached.reason.includes('history'),
    `B4 CONTROL: git diff HEAD compares every tracked file with HEAD (whole-tree content), and --cached stays history (got ${shape(b4c)} | ${shape(b4cached)})`
  );
  const b4r = pv([
    ex(7, ['git', 'diff', '--quiet', 'origin/main', '--', 'a/one.txt']),
    open(7, '/r/.git/index'),
  ]);
  check(
    b4r.kind === 'paths' &&
      b4r.paths.join(',') === 'a/one.txt' &&
      JSON.stringify(b4r.refs) === '["origin/main"]',
    `B4/B5: git diff origin/main -- a/one.txt is that file's content plus refs ['origin/main'] (got ${shape(b4r)})`
  );

  // B5: history pinned to the refs its argv names; every unpinned exec collected.
  check(
    JSON.stringify(refsOfRevision('HEAD~2^{tree}')) === '["HEAD"]' &&
      JSON.stringify(refsOfRevision('origin/main..HEAD')) === '["origin/main","HEAD"]' &&
      JSON.stringify(refsOfRevision('main...')) === '["main","HEAD"]' &&
      JSON.stringify(refsOfRevision('origin/x:docs/a.md')) === '["origin/x"]' &&
      JSON.stringify(refsOfRevision('^@')) === '["HEAD"]' &&
      JSON.stringify(refsOfRevision('0123456789abcdef0123456789abcdef01234567')) === '[]' &&
      refsOfRevision('HEAD@{1}') === undefined &&
      refsOfRevision(':a/one.txt') === undefined &&
      refsOfRevision('a b') === undefined,
    'B5: refsOfRevision reads HEAD, ranges, REV:path and suffixes; a full oid pins itself; a reflog step, an index path or a non-ref is unpinned'
  );
  const b5 = pv([
    ex(7, ['git', 'rev-parse', 'HEAD']),
    open(7, '/r/.git/refs/heads/main'),
    ex(8, ['git', 'merge-base', 'HEAD', 'origin/main']),
    open(8, '/r/.git/packed-refs'),
    open(8, '/r/.git/objects/pack/p.pack'),
    ex(9, ['git', 'show', 'origin/x:a/one.txt']),
    ex(10, ['git', 'log', '-1', '--format=%H %cI', 'HEAD', '--', 'a/one.txt']),
    open(10, '/r/a/one.txt'),
  ]);
  check(
    b5.kind === 'paths' &&
      b5.paths.join(',') === 'a/one.txt' &&
      JSON.stringify(b5.refs) === '["HEAD","origin/main","origin/x"]',
    `B5: rev-parse, merge-base, show REV:path and log REV -- path are pinned, their own ref and object reads explained (got ${shape(b5)})`
  );
  const b5f = pv([
    ex(7, ['git', 'rev-parse', 'HEAD']),
    `8 openat(AT_FDCWD</r>, "/r/.git/refs/heads/main", O_RDONLY) = 4</r/.git/refs/heads/main>`,
  ]);
  check(
    b5f.kind === 'whole-tree' && b5f.reason.includes('refs/heads/main'),
    `B5 CONTROL: a ref read by a process that ran no pinned command is history (got ${shape(b5f)})`
  );
  const b5c = (argv: string[]): Verdict => pv([ex(7, argv), open(7, '/r/a/one.txt')]);
  const stays = [
    ['git', 'log', '-1'],
    ['git', 'describe', '--tags'],
    ['git', 'fetch', 'origin'],
    ['git', 'for-each-ref', 'refs/heads'],
    ['git', 'log', '--all', 'HEAD'],
    ['git', 'log', '--format=%d', 'HEAD'],
    ['git', 'log', '--since=2.weeks', 'HEAD'],
    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
    ['git', 'rev-parse', 'HEAD@{1}'],
    ['git', 'merge-base', '--fork-point', 'origin/main'],
  ].filter((argv) => b5c(argv).kind !== 'whole-tree');
  check(
    stays.length === 0,
    `B5 CONTROL: git log (implicit HEAD), describe, fetch, for-each-ref, --all, a %d format, --since, --abbrev-ref, a reflog step and --fork-point stay whole-tree history (pinned by mistake: ${JSON.stringify(stays)})`
  );
  const b5s = pv([
    ex(7, ['git', 'rev-parse', 'HEAD']),
    open(7, '/r/.git/shallow'),
    open(7, '/r/a/one.txt'),
  ]);
  check(
    b5s.kind === 'whole-tree' && b5s.reason.includes('.git/shallow'),
    `B5 CONTROL: a shallow-file read is history even by a pinned command (got ${shape(b5s)})`
  );
  const enoent = (pid: number, abs: string): string =>
    `${pid} openat(AT_FDCWD</r>, "${abs}", O_RDONLY) = -1 ENOENT (No such file or directory)`;
  const lists = (pid: number, abs: string): string =>
    `${pid} getdents64(3<${abs}>, 0x5a /* 4 entries */, 32768) = 104`;
  const b5abs = pv([
    ex(7, ['git', 'show', 'HEAD:a/one.txt']),
    enoent(7, '/r/.git/shallow'),
    enoent(7, '/r/.git/refs/notes/commits'),
    lists(7, '/r/.git/refs'),
    lists(7, '/r/.git/objects/pack'),
    open(7, '/r/a/one.txt'),
  ]);
  check(
    b5abs.kind === 'paths' && JSON.stringify(b5abs.refs) === '["HEAD"]',
    `B5: a pinned show that only probed shallow and notes (ENOENT) and listed refs/ and objects/pack, as git 2.53 does, keeps its paths (got ${shape(b5abs)})`
  );
  const b5ctl = [
    pv([
      ex(7, ['git', 'show', 'HEAD:a/one.txt']),
      open(7, '/r/.git/refs/replace/abc'),
      open(7, '/r/a/one.txt'),
    ]),
    pv([
      ex(7, ['git', 'show', 'HEAD:a/one.txt']),
      lists(7, '/r/.git/refs/tags'),
      open(7, '/r/a/one.txt'),
    ]),
    pv([
      ex(7, ['git', 'show', 'HEAD:a/one.txt']),
      lists(8, '/r/.git/refs'),
      open(7, '/r/a/one.txt'),
    ]),
    pv([ex(7, ['git', 'ls-files', '-z']), enoent(7, '/r/.git/shallow'), open(7, '/r/a/one.txt')]),
  ].map((v) => v.kind);
  check(
    b5ctl.every((k) => k === 'whole-tree'),
    `B5 CONTROL: a replace ref FOUND, a listing of refs/tags, a refs/ listing by another process, and a shallow probe by a names scan (no pinned command) all stay history (got ${b5ctl.join(',')})`
  );
  const manyLog = mk(['a/one.txt']);
  for (const n of ['1', '2', '3', '4', '5'])
    manyLog.execs.push({ argv: ['git', 'describe', `--abbrev=${n}`], cwd: '/r', pid: 20 });
  manyLog.execs.push({ argv: ['git', 'rev-parse', 'HEAD'], cwd: '/r', pid: 21 });
  const aMany = attribute(manyLog, view);
  const vMany = fold(aMany, view);
  check(
    aMany.gitHistory.length === 5 &&
      vMany.kind === 'whole-tree' &&
      vMany.reason.includes('and 2 more') &&
      JSON.stringify(aMany.gitRefs) === '["HEAD"]',
    `B5: every unpinned history exec is collected (no cap of 3), the reason names how many it did not print, and a pinned one beside them still names its ref (got ${aMany.gitHistory.length}: ${vMany.kind === 'whole-tree' ? vMany.reason : 'paths'})`
  );
  const sub = pv([ex(7, ['git', 'rev-parse', 'HEAD'], '/r/private/sub'), open(7, '/r/a/one.txt')]);
  check(
    sub.kind === 'whole-tree' && sub.reason.includes('history'),
    'B5 CONTROL: a history command run inside a submodule names that submodule refs, which the root cannot resolve: history'
  );

  // B6: every read under a directory sharing one extension folds to D/*.ext plus D/**/*.ext.
  const extView: RepoView = {
    ...view,
    files: [
      ...view.files,
      'f/a.ts',
      'f/b.ts',
      'f/c.ts',
      'f/sub/e.ts',
      'f/sub/g.ts',
      'f/x.json',
      'f/y.json',
      'f/z.json',
      'f/w.json',
      'f/sub/v.json',
      'f/sub/u.json',
    ],
  };
  const b6 = fold(attribute(mk(['f/a.ts', 'f/b.ts', 'f/c.ts', 'f/sub/e.ts']), extView), extView);
  check(
    b6.kind === 'paths' && b6.paths.join(',') === 'f/**/*.ts,f/*.ts',
    `B6: four of five .ts files under f (four of eleven files) fold to f/*.ts plus f/**/*.ts (got ${shape(b6)})`
  );
  const b6c = fold(attribute(mk(['f/a.ts', 'f/b.ts', 'f/c.ts', 'f/x.json']), extView), extView);
  check(
    b6c.kind === 'paths' && b6c.paths.join(',') === 'f/a.ts,f/b.ts,f/c.ts,f/x.json',
    `B6 CONTROL: mixed extensions under f fold by no extension, and four of eleven stays exact (got ${shape(b6c)})`
  );
  const b6flat = fold(attribute(mk(['b/x.ts', 'b/y.ts', 'b/z.ts']), extView), extView);
  check(
    b6flat.kind === 'paths' && b6flat.paths.join(',') === 'b/**',
    'B6 CONTROL: a flat directory, where b/**/*.ts would match nothing (a dead glob), keeps b/**'
  );

  // B7: a carry-exempt kind waives its own reason and no other.
  const netAttr = { ...attribute(mk(['a/one.txt']), view), network: ['1.1.1.1:443'] };
  const b7 = fold(netAttr, view, [], { waive: 'network' });
  check(
    b7.kind === 'paths' &&
      b7.paths.join(',') === 'a/one.txt' &&
      JSON.stringify(b7.waived) === '["network"]',
    `B7: kind network waives the network reason and says so (got ${shape(b7)})`
  );
  const b7h = fold({ ...netAttr, gitHistory: ['git log -1'] }, view, [], { waive: 'network' });
  const b7clock = fold(netAttr, view, [], { waive: 'clock' });
  const b7none = fold(netAttr, view);
  check(
    b7h.kind === 'whole-tree' &&
      b7h.reason.includes('history') &&
      b7clock.kind === 'whole-tree' &&
      b7clock.reason.startsWith('network') &&
      b7none.kind === 'whole-tree',
    'B7 CONTROL: kind network does not waive history, kind clock waives nothing, and no kind waives nothing'
  );
  const b7hist = fold(
    { ...attribute(mk(['a/one.txt']), view), gitHistory: ['git describe'] },
    view,
    [],
    { waive: 'history' }
  );
  const b7cache = fold(
    { ...attribute(mk(['a/one.txt']), view), cacheState: ['.ci/cache/x.json'] },
    view,
    [],
    { waive: 'cache' }
  );
  check(
    b7hist.kind === 'paths' && b7cache.kind === 'paths',
    'B7: kind history waives unpinned history, kind cache waives cache state'
  );
  const kinds = new Map<string, string | null>([
    ['g:kind', 'network'],
    ['g:nokind', null],
  ]);
  const ge = (id: string): LockEntry => ({ id, run: 'x', gate: true });
  check(
    untracedReason(ge('g:kind'), kinds) === undefined &&
      untracedReason(ge('g:nokind'), kinds)?.includes('no kind') === true &&
      untracedReason(ge('g:plain'), kinds) === undefined,
    'B7: --all-whole-tree traces a carry-exempt row with a kind and refuses one with none'
  );
  const lockRefs = lockWithPaths(
    `${JSON.stringify([{ id: 'g:a', run: 'r', gate: true, leaves: ['x'] }], null, 2)}\n`,
    'g:a',
    ['a/one.txt'],
    { refs: ['HEAD'] }
  );
  const mRefs = manifestWithPaths(
    [
      'export const GATES = [',
      '  {',
      "    id: 'g:r',",
      "    run: 'x',",
      '    gate: true,',
      "    leaves: ['x.ts'],",
      '  },',
      '];',
    ].join('\n'),
    'g:r',
    ['a/one.txt'],
    { names: ['**'], refs: ['HEAD', 'origin/main'] }
  );
  check(
    Object.keys(JSON.parse(lockRefs)[0]).join(',') ===
      'id,run,gate,paths,refs,pathsOrigin,leaves' &&
      mRefs.includes(
        "    names: ['**'],\n    refs: ['HEAD', 'origin/main'],\n    pathsOrigin: 'traced',"
      ) &&
      !manifestWithoutTracedPaths(mRefs, 'g:r').includes('refs:') &&
      JSON.parse(lockWithoutTracedPaths(lockRefs, 'g:a'))[0].refs === undefined &&
      verdictLine('g', {
        kind: 'paths',
        paths: ['a'],
        refs: ['HEAD'],
        reads: 1,
        listed: 0,
        coveragePct: 1,
      }) === 'g\ta\trefs=["HEAD"]',
    'B5: refs is written after names, before pathsOrigin, in the lock and the manifest, leaves with a strip, and shows on the stdout line'
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
  // A BROKEN MARKER STRUCTURE IS REFUSED, never repaired by stripping (35e89088.1).
  const refuses = (lines: string[]): boolean => {
    try {
      reemitRegions(lines, "    id: 'none',");
      return false;
    } catch {
      return true;
    }
  };
  const balanced = manifest.split('\n');
  const firstBegin = balanced.findIndex((l) => BEGIN_RE.test(l));
  const firstEnd = balanced.findIndex((l) => END_RE.test(l));
  check(!refuses(balanced), 'CONTROL: the balanced manifest re-emits without refusing');
  check(
    refuses(balanced.filter((_l, i) => i !== firstEnd)),
    'a BEGIN marker that never closes is refused'
  );
  check(
    refuses(balanced.filter((_l, i) => i !== firstBegin)),
    'an END marker with no BEGIN is refused'
  );
  // THE LEDGER STAMP IS THE TRACE'S START, not the apply time (35e89088.2).
  const wroot = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-stamp-'));
  try {
    for (const rel of [MANIFEST_REL, LOCK_REL]) {
      fs.mkdirSync(path.dirname(path.join(wroot, rel)), { recursive: true });
      fs.writeFileSync(path.join(wroot, rel), rel === MANIFEST_REL ? manifest : '[]\n');
    }
    const started = Date.UTC(2020, 0, 2, 3, 4, 59);
    writeResult(
      wroot,
      {
        id: 'g:z',
        verdict: { kind: 'whole-tree', reason: 'x', reads: 0, listed: 0, coveragePct: 0 },
        exit: 0,
        seconds: 1,
        ignored: new Map(),
        outputTail: '',
        raw: { files: [], listed: [], execs: [], startedMs: started },
      } as unknown as GateResult,
      'tree1'
    );
    const row = ledgerRow(fs.readFileSync(path.join(wroot, LEDGER_REL), 'utf8'), 'g:z');
    check(
      row?.tracedAt === '2020-01-02T03:04Z',
      `the ledger stamps the trace start, got ${row?.tracedAt}`
    );
  } finally {
    fs.rmSync(wroot, { recursive: true, force: true });
  }
  // A RED RUN OVER A TRACED ENTRY changes nothing; the same verdict from a green run strips it (7a9a97ba.1).
  const rroot = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-red-'));
  try {
    const traced = manifestWithPaths(manifest, 'g:b', ['a/one.txt']);
    const seed = (): void => {
      for (const rel of [MANIFEST_REL, LOCK_REL, LEDGER_REL])
        fs.mkdirSync(path.dirname(path.join(rroot, rel)), { recursive: true });
      fs.writeFileSync(path.join(rroot, MANIFEST_REL), traced);
      fs.writeFileSync(path.join(rroot, LOCK_REL), '[]\n');
      fs.writeFileSync(
        path.join(rroot, LEDGER_REL),
        renderLedger({
          'g:b': {
            tracedAt: '2026-01-01T00:00Z',
            tree: 't0',
            verdict: 'paths',
            reads: 1,
            listed: 0,
            coveragePct: 1,
            seconds: 1,
          },
        })
      );
    };
    const whole = (exit: number): GateResult =>
      ({
        id: 'g:b',
        verdict: { kind: 'whole-tree', reason: 'x', reads: 0, listed: 0, coveragePct: 0 },
        exit,
        seconds: 1,
        ignored: new Map(),
        outputTail: '',
      }) as unknown as GateResult;
    seed();
    writeResult(rroot, whole(1), 't1');
    check(
      fs.readFileSync(path.join(rroot, MANIFEST_REL), 'utf8') === traced &&
        ledgerRow(fs.readFileSync(path.join(rroot, LEDGER_REL), 'utf8'), 'g:b')?.verdict ===
          'paths',
      'a red run over a traced entry leaves its paths and ledger row alone'
    );
    seed();
    writeResult(rroot, whole(0), 't1');
    check(
      fs.readFileSync(path.join(rroot, MANIFEST_REL), 'utf8') !== traced &&
        ledgerRow(fs.readFileSync(path.join(rroot, LEDGER_REL), 'utf8'), 'g:b')?.verdict ===
          'whole-tree',
      'CONTROL: the same whole-tree verdict from a green run strips the paths and records it'
    );
  } finally {
    fs.rmSync(rroot, { recursive: true, force: true });
  }
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
  const tracedManifest = manifestWithPaths(manifest, 'g:b', ['a/one.txt']);
  const unTraced = manifestWithoutTracedPaths(tracedManifest, 'g:b');
  check(
    !unTraced.split("    id: 'g:b',")[1].split('  },')[0].includes('paths') &&
      manifestWithoutTracedPaths(unTraced, 'g:d') === unTraced &&
      unTraced.includes("    paths: ['k'],\n    pathsOrigin: 'declared',"),
    'a whole-tree re-trace removes the traced paths and pathsOrigin; a declared set is untouched (control)'
  );
  const tracedLock = lockWithPaths(
    `${JSON.stringify(
      [
        { id: 'g:b', run: 'r', gate: true, leaves: [] },
        { id: 'g:d', run: 'r', gate: true, paths: ['k'], pathsOrigin: 'declared', leaves: [] },
      ],
      null,
      2
    )}\n`,
    'g:b',
    ['p/**']
  );
  const ul = JSON.parse(
    lockWithoutTracedPaths(lockWithoutTracedPaths(tracedLock, 'g:b'), 'g:d')
  ) as LockEntry[];
  check(
    ul[0].paths === undefined &&
      ul[0].pathsOrigin === undefined &&
      ul[1].pathsOrigin === 'declared',
    'the lock loses the traced paths of a whole-tree re-trace; the declared entry keeps its own (control)'
  );
  let refused = false;
  try {
    manifestWithPaths(manifest, 'g:d', ['x']);
  } catch (e) {
    refused = (e as Error).message.includes('declared');
  }
  check(refused, 'CONTROL: a declared paths set is refused, never overwritten');
  let replaced = '';
  try {
    replaced = manifestWithPaths(manifest, 'g:d', ['x/**'], { replaceDeclared: true });
  } catch {
    // Left empty: the check below reports the refusal as a FAIL rather than a crash.
  }
  const dBody = replaced.split("    id: 'g:d',")[1]?.split('  },')[0] ?? '';
  check(
    dBody.includes("    paths: ['x/**'],\n    pathsOrigin: 'traced',") &&
      !dBody.includes("'declared'"),
    '--replace-declared replaces a declared set with the traced one'
  );
  const dropped = manifestWithoutTracedPaths(manifest, 'g:d', { replaceDeclared: true });
  const dl = JSON.parse(
    lockWithoutTracedPaths(
      JSON.stringify([
        { id: 'g:d', run: 'r', gate: true, paths: ['k'], pathsOrigin: 'declared', leaves: [] },
      ]),
      'g:d',
      { replaceDeclared: true }
    )
  ) as LockEntry[];
  check(
    !dropped.split("    id: 'g:d',")[1].split('  },')[0].includes('paths') &&
      dl[0].paths === undefined &&
      dl[0].pathsOrigin === undefined,
    '--replace-declared with a whole-tree verdict removes the declared set from the manifest and the lock'
  );
  // W2.5: the name-shaped fields are written beside paths, in gate-spec.ts order, and leave with them.
  const mL = manifestWithPaths(manifest, 'g:b', ['a/one.txt'], {
    lists: ['', '.ci'],
    names: ['**'],
  });
  const bL = mL.split("    id: 'g:b',")[1].split('  },')[0].split('\n');
  const at = (prefix: string): number => bL.findIndex((l) => l.startsWith(prefix));
  check(
    bL[at('    lists:')] === "    lists: ['', '.ci']," &&
      bL[at('    names:')] === "    names: ['**']," &&
      at('    paths:') < at('    lists:') &&
      at('    lists:') < at('    names:') &&
      at('    names:') < at('    pathsOrigin:') &&
      at('    pathsOrigin:') < at('    leaves:'),
    'the manifest gains paths, lists, names, pathsOrigin in that order, before leaves'
  );
  const mNoPaths = manifestWithPaths(manifest, 'g:b', [], { lists: ['c/listed'] });
  const bN = mNoPaths.split("    id: 'g:b',")[1].split('  },')[0];
  check(
    !bN.includes('paths:') && bN.includes("    lists: ['c/listed'],"),
    'an empty paths is omitted, never written as []'
  );
  const mRe = manifestWithPaths(mL, 'g:b', ['b/**']).split("    id: 'g:b',")[1].split('  },')[0];
  const mStrip = manifestWithoutTracedPaths(mL, 'g:b').split("    id: 'g:b',")[1].split('  },')[0];
  check(
    !mRe.includes('lists:') &&
      !mRe.includes('names:') &&
      !mStrip.includes('lists:') &&
      !mStrip.includes('names:') &&
      !mStrip.includes('paths'),
    'a re-trace or a whole-tree strip removes an earlier lists and names'
  );
  const lockL = lockWithPaths(
    `${JSON.stringify([{ id: 'g:a', run: 'r', gate: true, leaves: ['x'], ci: {} }], null, 2)}\n`,
    'g:a',
    [],
    { lists: [''], names: ['**'] }
  );
  const lockLStripped = JSON.parse(lockWithoutTracedPaths(lockL, 'g:a')) as LockEntry[];
  check(
    Object.keys(JSON.parse(lockL)[0]).join(',') ===
      'id,run,gate,lists,names,pathsOrigin,leaves,ci' &&
      lockLStripped[0].lists === undefined &&
      lockLStripped[0].names === undefined,
    'the lock gains lists and names in manifest order (no empty paths) and loses them on a strip'
  );
  check(
    verdictLine('g', {
      kind: 'paths',
      paths: ['a.txt'],
      lists: ['', '.ci'],
      names: ['**'],
      reads: 1,
      listed: 2,
      coveragePct: 1,
    }) === 'g\ta.txt\tlists=["",".ci"]\tnames=["**"]',
    "the stdout line carries lists and names as JSON, so the root's '' stays visible"
  );
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
    // A BACKSLASH in a reason must survive every read and write unchanged (ffa5756e.5).
    'g:bs': {
      tracedAt: '2026-11-17T10:00Z',
      tree: 'abc',
      verdict: 'whole-tree',
      reason: "path C:\\x and a regex \\d+ and a quote \\' mixed",
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
  check(
    ledgerRow(renderLedger(parseLedger(renderLedger(back))), 'g:bs')?.reason ===
      rows['g:bs'].reason,
    'a reason with backslashes is stable across repeated read and write cycles'
  );

  // A --root reached through a symlink is the realpath strace reports (ffa5756e.6).
  const linkBase = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-link-'));
  try {
    const here = path.resolve(import.meta.dirname, '..', '..');
    fs.symlinkSync(here, path.join(linkBase, 'link'));
    check(
      repoView(path.join(linkBase, 'link')).root === fs.realpathSync(here),
      'repoView resolves a symlinked root to its realpath, as strace reports paths'
    );
  } finally {
    fs.rmSync(linkBase, { recursive: true, force: true });
  }

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
    const ns = await traceCommand('cat in/a.txt >/dev/null', dir, { noSeccomp: true });
    check(
      ns.exit === 0 && ns.access.files.has(`${real}/in/a.txt`),
      '--no-seccomp traces the same read without the filter'
    );
    // A wrapper standing in for strace prints a strace-style line on ITS stderr, the stream the tracee would inherit without the fix.
    const wrap = path.join(dir, 'strace-wrap.sh');
    fs.writeFileSync(wrap, '#!/bin/sh\necho "strace: wrapper note" >&2\nexec strace "$@"\n', {
      mode: 0o755,
    });
    // The gate's own stderr line that happens to start with `strace: ` is still gate output.
    const sep = await traceCommand(
      'echo gate-out; echo gate-err >&2; echo "strace: said by the gate" >&2',
      dir,
      { straceBin: wrap }
    );
    check(
      sep.exit === 0 &&
        sep.outputTail.includes('gate-out') &&
        sep.outputTail.includes('gate-err') &&
        sep.outputTail.includes('strace: said by the gate') &&
        !sep.outputTail.includes('wrapper note') &&
        sep.straceNotes.join('|') === 'strace: wrapper note',
      `strace's own lines are kept apart from the gate's stdout and stderr (output ${JSON.stringify(sep.outputTail)}, notes ${JSON.stringify(sep.straceNotes)})`
    );
    // W2.5 accept fixture: `python3 -m` from the root, reading two tracked files, gives those two plus lists ['', '.ci']: the root and .ci are sys.path entries Python lists and probes, not content.
    const py = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-py-'));
    const pyFiles: Record<string, string> = {
      '.ci/tool.py': "open('conf/x.txt').read()\n",
      '.ci/other.py': 'pass\n',
      'conf/x.txt': 'x',
      'src/keep.txt': 'k',
    };
    for (let i = 0; i < 40; i++) pyFiles[`filler/f${i}.txt`] = 'f';
    for (const [rel, text] of Object.entries(pyFiles)) {
      fs.mkdirSync(path.dirname(path.join(py, rel)), { recursive: true });
      fs.writeFileSync(path.join(py, rel), text);
    }
    // repoView reads the record set from the root's own policy dir and refuses a root without one (review 502ce0ee.2).
    fs.mkdirSync(path.join(py, '.ci', 'policy'), { recursive: true });
    fs.writeFileSync(
      path.join(py, '.ci', 'policy', 'record-paths.json'),
      JSON.stringify({ records: [{ glob: 'agent/reviews/**', probes: ['agent/reviews/x.md'] }] })
    );
    const gitEnv = {
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
      spawnSync('git', a, { cwd: py, env: gitEnv });
    const pyView = repoView(fs.realpathSync(py));
    check(
      pyView.records?.length === 1 && pyView.records[0]?.prefix === 'agent/reviews',
      'repoView carries the root record set (review 502ce0ee.3: a dropped records field would leave every hand-built view green)'
    );
    const noPol = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-nopol-'));
    let noPolThrew = false;
    try {
      readRecordGlobs(noPol);
    } catch {
      noPolThrew = true;
    }
    fs.rmSync(noPol, { recursive: true, force: true });
    check(
      noPolThrew,
      'a root with no record-paths.json is refused, not read as an empty record set (review 502ce0ee.2)'
    );
    const pyRun = await traceCommand('PYTHONPATH=.ci python3 -m tool', pyView.root);
    const pyV = verdictOf(attribute(pyRun.access, pyView), pyView, pyRun.exit);
    check(
      pyV.kind === 'paths' &&
        pyV.paths.join(',') === '.ci/tool.py,conf/x.txt' &&
        JSON.stringify(pyV.lists) === '["",".ci"]' &&
        pyV.names === undefined,
      `python3 -m from the root reading 2 files gives those 2 plus lists ['', '.ci'] (got ${pyV.kind === 'paths' ? `${pyV.paths.join(',')} lists=${JSON.stringify(pyV.lists)}` : pyV.reason})`
    );
    // Missed lookups: inside a tracked directory its nearest existing tracked ancestor is listed; under untracked node_modules nothing is.
    fs.mkdirSync(path.join(pyView.root, 'node_modules', 'dep'), { recursive: true });
    const probeRun = await traceCommand(
      'test -e src/nope.txt; test -e src/a/b/c.txt; test -e node_modules/dep/zz.js; test -e conf/node_modules/q/i.js; cat conf/x.txt >/dev/null',
      pyView.root
    );
    const probeV = verdictOf(attribute(probeRun.access, pyView), pyView, probeRun.exit);
    check(
      probeV.kind === 'paths' &&
        probeV.paths.join(',') === 'conf/x.txt' &&
        JSON.stringify(probeV.lists) === '["src"]',
      `a missed lookup inside tracked src (and src/a/b beneath it) lists src; one under node_modules, existing or not, lists nothing (got ${probeV.kind === 'paths' ? `${probeV.paths.join(',')} lists=${JSON.stringify(probeV.lists)}` : probeV.reason})`
    );
    // F2 on a real trace: pinned history and narrowed git content keep paths; an implicit-HEAD log does not; a fixture repository's own index read is not this one's.
    const pinRun = await traceCommand(
      'git rev-parse HEAD >/dev/null && git show HEAD:conf/x.txt >/dev/null && git ls-files -s -- conf >/dev/null && git diff --quiet src/keep.txt',
      pyView.root
    );
    const pinV = verdictOf(attribute(pinRun.access, pyView), pyView, pinRun.exit);
    check(
      pinV.kind === 'paths' &&
        pinV.paths.join(',') === 'conf/**,src/keep.txt' &&
        JSON.stringify(pinV.refs) === '["HEAD"]',
      `B3/B4/B5 real: rev-parse HEAD, show HEAD:path, ls-files -s -- conf and diff --quiet <file> give conf/** and src/keep.txt plus refs ['HEAD'] (got ${shape(pinV)})`
    );
    const logRun = await traceCommand('git log -1 >/dev/null && cat conf/x.txt', pyView.root);
    const logV = verdictOf(attribute(logRun.access, pyView), pyView, logRun.exit);
    check(
      logV.kind === 'whole-tree' && logV.reason.includes('git log -1'),
      `B5 CONTROL real: git log -1 (implicit HEAD) stays history (got ${shape(logV)})`
    );
    const fx = fs.mkdtempSync(path.join(os.tmpdir(), 'path-trace-fx-'));
    const fxRun = await traceCommand(
      `git init -q ${fx} && git -C ${fx} read-tree --empty && git -C ${fx} ls-files -s >/dev/null && git ls-files -z >/dev/null && cat conf/x.txt >/dev/null`,
      pyView.root
    );
    const fxV = verdictOf(attribute(fxRun.access, pyView), pyView, fxRun.exit);
    fs.rmSync(fx, { recursive: true, force: true });
    check(
      fxV.kind === 'paths' &&
        fxV.paths.join(',') === 'conf/x.txt' &&
        JSON.stringify(fxV.names) === '["**"]' &&
        [...(fxRun.access.gitReaders?.keys() ?? [])].some(
          (p) =>
            p.startsWith(fs.realpathSync(os.tmpdir())) &&
            p.endsWith('/index') &&
            !p.startsWith(pyView.root)
        ),
      `B1 real: a fixture repository's own \`ls-files -s\` beside this tree's name-only scan leaves names ['**'], and the trace did see the fixture index (got ${shape(fxV)})`
    );
    fs.rmSync(py, { recursive: true, force: true });
    // A real connect: loopback is refused at once, a TEST-NET-1 peer (RFC 5737, documentation only) is cut by the timeout.
    const net = await traceCommand(
      ': </dev/tcp/127.0.0.1/9 2>/dev/null; timeout 1 bash -c ": </dev/tcp/192.0.2.1/9" 2>/dev/null; true',
      dir
    );
    check(
      net.exit === 0 &&
        net.access.network?.has('192.0.2.1:9') === true &&
        ![...(net.access.network ?? [])].some((x) => x.startsWith('127.')),
      `a real strace connect to a routable peer is network and loopback is not (got ${JSON.stringify([...(net.access.network ?? [])])})`
    );
    fs.rmSync(dir, { recursive: true, force: true });
  } else {
    console.log(`  NOTE  no real trace on this host: ${refusal}`);
  }

  const shownEvidence = evidenceText(
    'git -C /x/y ls-files -z --recurse-submodules; /x/.git/wt/agent-1/index; git log'
  );
  check(
    shownEvidence === 'git ls-files -z --recurse-submodules; <gitdir>/index; git log',
    `ledger evidence drops the checkout path and keeps the command git ran, \`git ls-files\` included (review 434f1d3b.1; got ${shownEvidence})`
  );
  const spaced = 'git -C /x y/tree ls-files -z; /x y/.git/wt/a/index';
  const spacedShown = evidenceText(spaced, ['/x y/tree', '/x y/.git/wt/a']);
  check(
    spacedShown === 'git ls-files -z; <gitdir>/index',
    `a checkout or git directory holding a space is dropped whole (review 434f1d3b.2; got ${spacedShown})`
  );
  check(
    evidenceText(spaced).includes('y/tree'),
    'CONTROL: without the directories named, a spaced checkout path survives the patterns, so the directories are what drop it'
  );

  // 434f1d3b.3/.4: rawOf and accessOfRaw round-trip the git readers, and a record without them is judged in the whole-tree direction.
  for (const readerPid of [7, 8]) {
    const live = parseStraceLog(pidLog(readerPid), '/r');
    const raw = JSON.parse(JSON.stringify(rawOf(live, view))) as RawAccess;
    const back = accessOfRaw(raw);
    const liveV = fold(attribute(live, view), view);
    const backV = fold(attribute(back.access, view), view);
    check(
      !back.legacy &&
        JSON.stringify(raw.gitReaders?.['/r/.git/index']) ===
          JSON.stringify([...new Set([7, readerPid])]) &&
        JSON.stringify(backV) === JSON.stringify(liveV),
      `gitReaders survive rawOf, JSON and accessOfRaw, and the refolded verdict is the live one (reader pid ${readerPid}: ${liveV.kind})`
    );
  }
  const ownRaw = JSON.parse(
    JSON.stringify(rawOf(parseStraceLog(pidLog(7), '/r'), view))
  ) as RawAccess;
  delete ownRaw.gitReaders;
  const legacyBack = accessOfRaw(ownRaw);
  const legacyV = fold(attribute(legacyBack.access, view), view);
  check(
    legacyBack.legacy && legacyV.kind === 'whole-tree' && legacyV.reason.includes('.git/index'),
    `a raw record from before gitReaders that reads the index is flagged legacy and folds whole-tree, not to the names verdict its own-pid twin earns (got ${legacyV.kind})`
  );
  const noIndexRaw = rawOf(mk(['a/one.txt']), view);
  check(
    noIndexRaw.gitReaders === undefined && !accessOfRaw(noIndexRaw).legacy,
    'CONTROL: a record with no index read and no gitReaders is no legacy record'
  );

  // 22efb11e: a traced set naming a record path stays whole-tree, generated by the fold rather than written into the ledger by hand.
  const recView: RepoView = {
    ...view,
    files: [...view.files, 'agent/reviews/b/c.md', 'agent/reviews/b/d.md'],
    records: [
      {
        glob: 'agent/reviews/**',
        prefix: recordPrefix('agent/reviews/**'),
        probes: ['agent/reviews/main/clean.jsonl'],
        except: [],
      },
    ],
  };
  const recAcc = mk(['a/one.txt'], ['agent/reviews/b']);
  const recV = fold(attribute(recAcc, recView), recView);
  check(
    recV.kind === 'whole-tree' &&
      recV.reason.includes('agent/reviews/**') &&
      recV.coveragePct < 100 &&
      recV.listed === 1,
    `a listing under agent/reviews is whole-tree with the record named and the coverage it measured (got ${recV.kind === 'whole-tree' ? `${recV.coveragePct}% ${recV.reason}` : 'paths'})`
  );
  const plainV = fold(attribute(recAcc, { ...recView, records: [] }), { ...recView, records: [] });
  check(
    plainV.kind === 'paths' && JSON.stringify(plainV.lists) === '["agent/reviews/b"]',
    'CONTROL: the same trace with no record set keeps its lists'
  );
  check(
    recordCitations(['agent/**'], recView.records ?? []).length === 1 &&
      recordCitations(['agent/archive'], recView.records ?? []).length === 0 &&
      recordPrefix('agent/worklist/*.jsonl') === 'agent/worklist' &&
      recordPrefix('.ci/config/plan-boxes.json') === '.ci/config/plan-boxes.json',
    'a glob reaching a probe cites the record, a sibling directory does not, and the prefix is check_record_paths.py literal_prefix'
  );

  // 53bbd61a.1: a bare `agent` list entry cites only a record whose literal prefix IS `agent` (check_record_paths.py literal_prefix: `agent/*/STATE.md`, added 2026-11-23 by PLAN-stop-hook-retro-20261123 R20261123.4, cuts back to `agent`), never one below a deeper directory such as agent/reviews/** or agent/worklist/*.jsonl. Since that record landed, check:ci-python-gate-deps' `lists: ['agent']` cites it, so a re-trace leaves that gate whole-tree until the record or literal_prefix changes.
  const realRecords = readRecordGlobs(REPO_ROOT);
  const bareAgent = recordCitations(['agent'], realRecords);
  check(
    bareAgent.every((g) => recordPrefix(g) === 'agent') &&
      !bareAgent.includes('agent/reviews/**') &&
      recordCitations(['agent/reviews'], realRecords).includes('agent/reviews/**'),
    `a bare \`agent\` list entry cites only records whose literal prefix is \`agent\` (got ${JSON.stringify(bareAgent)}), and CONTROL: agent/reviews is cited`
  );

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
