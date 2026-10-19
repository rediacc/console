/**
 * The fixtures the embed, devcontainer and toolchain selftests share: a temporary console tree
 * copied from the live one (so a site that moves in the repo is caught by the selftest), a
 * driver context over it, and an upstream that answers from a URL map and refuses every other
 * URL the way an unreachable host does.
 *
 * Nothing here touches the live tree: every file is copied out, every write lands in the
 * temporary root, and `removeRoots()` deletes the roots when the selftest ends.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { ControlCase } from '../../controls.js';
import { REPO_ROOT } from '../../repo-root.js';
import { NotCompared, UnreadableListing } from '../../upstream.js';
import type { DriverContext } from '../driver.js';
import { loadRegistry, type PinEntry, type RepoPath } from '../registry.js';
import type { Upstream } from './toolchain-upstream.js';

export const LIVE_ROOT = REPO_ROOT;
const ROOTS: string[] = [];

export function removeRoots(): void {
  for (const r of ROOTS.splice(0)) fs.rmSync(r, { recursive: true, force: true });
}

const git = (cwd: string, ...args: string[]): void => {
  const r = spawnSync(
    'git',
    ['-C', cwd, '-c', 'user.email=fx@example.invalid', '-c', 'user.name=fx', ...args],
    { encoding: 'utf8' }
  );
  if (r.status !== 0) throw new Error(`git ${args.join(' ')} failed in ${cwd}: ${r.stderr}`);
};

/**
 * A temporary console: `files` copied from the live tree (paths relative to the console, a
 * `private/renet/...` path included), `extra` written as given, and a committed git repository at
 * the root and at each nested `repos` path, so the transaction's dirty check has a base to compare.
 */
export function makeTree(
  files: string[],
  extra: Record<string, string> = {},
  repos: string[] = ['private/renet']
): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pins-drivers-'));
  ROOTS.push(root);
  for (const rel of files) {
    const from = path.join(LIVE_ROOT, rel);
    if (!fs.existsSync(from))
      throw new Error(`the fixture needs ${rel}, and the live tree has none`);
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.copyFileSync(from, path.join(root, rel));
  }
  for (const [rel, text] of Object.entries(extra)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  fs.writeFileSync(path.join(root, '.gitignore'), 'private/\n.ci/cache/\n');
  for (const repo of [...repos.map((r) => path.join(root, r)), root]) {
    fs.mkdirSync(repo, { recursive: true });
    git(repo, 'init', '-q');
    git(repo, 'add', '-A');
    git(repo, 'commit', '-q', '-m', 'fixture');
  }
  return root;
}

/** Every file under `dir` (relative to the live console), for copying a small directory whole. */
export function liveFiles(dir: string): string[] {
  const out: string[] = [];
  const walk = (rel: string): void => {
    for (const e of fs.readdirSync(path.join(LIVE_ROOT, rel), { withFileTypes: true })) {
      const child = path.posix.join(rel, e.name);
      if (e.isDirectory()) walk(child);
      else out.push(child);
    }
  };
  walk(dir);
  if (out.length === 0)
    throw new Error(
      `VACUOUS: ${dir} holds no file in the live console, so a copy of it proves nothing`
    );
  return out;
}

/** A driver context over a temporary root and the live registry. Reads see `overlay` first. */
export function ctxOf(root: string): DriverContext & { overlay: Map<string, string> } {
  const overlay = new Map<string, string>();
  return {
    root,
    reg: loadRegistry(),
    fixture: null,
    mutant: null,
    overlay,
    read(p: RepoPath) {
      const k = p.repo === '.' ? p.file : `${p.repo}/${p.file}`;
      const hit = overlay.get(k);
      if (hit !== undefined) return hit;
      const abs = path.join(root, p.repo, p.file);
      return fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
    },
  };
}

export function entryOf(id: string): PinEntry {
  const e = loadRegistry().entries.find((x) => x.id === id);
  if (!e) throw new Error(`no pin ${id} in .ci/config/pins.json`);
  return e;
}

export type Answer = string | object | { lastModified: number };

/** An upstream that answers from `answers` by exact URL, and throws NotCompared for any other. */
export function stubUpstream(answers: Record<string, Answer>): Upstream & { asked: string[] } {
  const asked: string[] = [];
  const missing = (url: string): NotCompared => NotCompared.absentFromFixture(url);
  const get = (url: string): Answer => {
    asked.push(url);
    const hit = answers[url];
    if (hit === undefined) throw missing(url);
    return hit;
  };
  return {
    asked,
    json(url) {
      const a = get(url);
      if (typeof a === 'string') {
        try {
          return Promise.resolve(JSON.parse(a));
        } catch {
          return Promise.reject(new UnreadableListing('not JSON'));
        }
      }
      return Promise.resolve(a);
    },
    text(url) {
      const a = get(url);
      return Promise.resolve(typeof a === 'string' ? a : JSON.stringify(a));
    },
    sha256(url) {
      // Answered from the key `sha256:<url>`, so a digest is never mistaken for a listing body.
      const a = get(`sha256:${url}`);
      return typeof a === 'string'
        ? Promise.resolve(a)
        : Promise.reject(new UnreadableListing('not a digest'));
    },
    lastModified(url) {
      const a = answers[url];
      asked.push(url);
      return Promise.resolve(
        a !== undefined && typeof a === 'object' && 'lastModified' in a
          ? (a as { lastModified: number }).lastModified
          : null
      );
    },
  };
}

/** Bump the last numeric segment: 8.6.0 -> 8.6.1. */
export function patchOf(v: string): string {
  const [core, meta] = v.split('+');
  const parts = core.split('.');
  parts[parts.length - 1] = String(Number(parts[parts.length - 1]) + 1);
  return parts.join('.') + (meta === undefined ? '' : `+${meta}`);
}

export const hex = (c: string, n = 64): string => c.repeat(n).slice(0, n);

/**
 * Run `cases` once clean and once per mutant. The clean run must pass every control; each mutant
 * run must fail at least one (that is the proof the control can fail). Returns the failure count
 * of the whole, and prints one line per mutant.
 */
export function proveMutants<M extends string>(
  mutants: readonly M[],
  build: (mutant: M | null) => Promise<ControlCase[]>,
  log: (line: string) => void = (l) => console.log(l)
): Promise<{ clean: ControlCase[]; mutantFailures: string[] }> {
  return (async () => {
    const clean = await build(null);
    const mutantFailures: string[] = [];
    for (const m of mutants) {
      const red = (await build(m)).filter((c) => !c.ok).map((c) => c.name);
      if (red.length === 0) {
        mutantFailures.push(`MUTANT ${m}: every control still passed, so none of them can fail`);
      } else log(`MUTANT ${m}: red as it must be (${red.length}): ${red[0]}`);
    }
    return { clean, mutantFailures };
  })();
}
