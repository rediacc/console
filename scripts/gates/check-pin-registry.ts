#!/usr/bin/env tsx
/**
 * check:ci-pin-registry -- every pinned version in the tree is in .ci/config/pins.json,
 * and every site the registry names is still where it says.
 *
 * WHY. A pin bump is only as complete as the list of places the pin is written, and until
 * the registry those lists were four hand-kept copies with nothing asking whether a fifth
 * site existed (agent/plans/PLAN-pins-command.md, Survey). The Leap Ceph pin moved by hand
 * three times in fifteen days across three files; a csi-snapshotter bump waited as hand
 * patches across nine. This gate asks the question in both directions, offline:
 *
 *   FORWARD   scanners walk every tracked file of the console and of each scanned
 *             submodule, and each hit must be claimed: by a leaf's site, a family's scope,
 *             or a reasoned ignore. An unclaimed hit is red, printed with the entry shape
 *             that would claim it.
 *   REVERSE   each site must match exactly `expect` times (zero is a site that moved, two
 *             is a copy the next bump would half-move), and the sites of one role in one
 *             entry must agree on their value.
 *   LITERALS  each entry's context regexes run over tracked text, and an occurrence of the
 *             pin's CURRENT value outside a site, a derive output or an ignore is red: a
 *             prose or comment copy that the next bump would leave behind.
 *   LIVENESS  an ignore that claims nothing, a family scope that matches nothing and a
 *             literal exclusion that covers no file are red; a reason (`source: none`, an
 *             ignore, an exclusion, an unscanned submodule) must pass the shared BLOCKER
 *             validator; a gate id must be a manifest gate; a hold or derive output must
 *             exist.
 *   PRESENCE  every .gitmodules path is scanned or excused, and a scanned submodule that is
 *             not checked out fails closed under CI (scripts/lib/submodule-presence.ts).
 *
 * SCANNERS (one hit per pin-shaped line, or per file for a lockfile):
 *   dockerfile-arg  Dockerfile*: ARG <NAME>_VERSION|_COMMIT|_DIGEST|_SHA256[_<X>]=<v>
 *   toolchain-env   toolchain.env: <NAME>_VERSION|_SHA256[_<X>]=<v>
 *   shell-const     *.sh, *.bash: [readonly|export|local] <NAME>_<suffix as above>="<literal>"
 *   from-image      Dockerfile*: FROM <image>, an ARG-defaulted image located at its ARG line
 *   action-uses     *.yml, *.yaml: uses: owner/repo[/path]@<40-hex sha>
 *   npm-lockfile    package-lock.json (file)
 *   go-mod          go.mod (file), and its `go` and `toolchain` lines
 *   pin-lock-json   *.lock.json (file)
 *   ceph-pin        .ceph-image-pin: image= and host.<target>= lines
 *
 * THE CONTROLS. `--selftest` runs the loader's field controls, then a clean fixture tree
 * (zero findings, the negative control) and one planted defect per check: an unclaimed hit
 * for every scanner, a literal copy, a dead site, a duplicate match, a disagreeing site, a
 * dead ignore, a dead scope, a dead exclusion, a hollow reason and a missing submodule
 * under CI. Each is red, and each has a MUTANT that removes the check it relies on (the
 * scanner returning nothing, the reverse count skipped, ...) under which the same plant
 * must turn green, so a case cannot pass by a finding some other check happened to raise.
 *
 * ---- gate ----
 * step: Pin registry covers every pin
 * needs: node, private/renet, private/account
 * selftest: true
 * why: a pin bump is only as complete as the list of places the pin is written. The
 *      registry is that list, and this gate is what keeps it the whole list: a pin no
 *      entry claims, a site that moved, and a prose copy the next bump would leave behind
 *      are each red here before they are a half-bumped tree
 * ---- end gate ----
 *
 * Usage:
 *   npx tsx scripts/gates/check-pin-registry.ts [--selftest] [--json]
 *
 * Exit codes: 0 = every hit claimed, every site at its count and in agreement, no unclaimed
 * literal, nothing dead; 1 = any finding, a malformed registry, or a scan that saw nothing.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { GATES } from '../ci-runner/manifest.js';
import { validateBlockerQuality } from '../lib/blocker-validator.js';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { type ControlCase, runControls } from '../lib/controls.js';
import {
  compile,
  selftestCases as loaderCases,
  loadRegistry,
  type PinEntry,
  type PinRegistry,
  type PinSite,
  RegistryError,
  registryPath,
  SCANNERS,
  type ScannerId,
  type SiteMatch,
  siteMatches,
} from '../lib/pins/registry.js';
import { envRoot } from '../lib/repo-root.js';
import { inCi, submoduleVerdict } from '../lib/submodule-presence.js';

// ---- the tree ---------------------------------------------------------------------------

/** What the checks read: tracked files per repo. A real run lists them with git; the selftest builds one in memory. */
export interface Tree {
  /** Repos actually present (a scanned submodule that is not checked out is absent). */
  repos: string[];
  files(repo: string): string[];
  /** Text of a tracked file, or null when it is absent, binary or too large to be a pin file. */
  read(repo: string, file: string): string | null;
  /** The console's .gitmodules paths. */
  gitmodules: string[];
}

const MAX_BYTES = 4 * 1024 * 1024;
/** The fewest scanner hits a real run may see: 535 on 2026-10-14 (console plus renet and account). A scan that collapses below it lost a repo or a scanner, not pins. */
const MIN_HITS = 200;

function gitFiles(dir: string): string[] {
  const res = spawnSync('git', ['-C', dir, 'ls-files', '-z'], {
    encoding: 'utf8',
    maxBuffer: 256 * 1024 * 1024,
  });
  if (res.error || res.status !== 0) {
    throw new Error(
      `git -C ${dir} ls-files failed (status ${res.status}): ${res.stderr ?? res.error}`
    );
  }
  return res.stdout.split('\0').filter(Boolean);
}

/** The real tree under `root`: git-tracked files, submodule gitlinks dropped (their content is its own repo). */
export function gitTree(root: string, reg: PinRegistry, note: (line: string) => void): Tree {
  const gitmodules = fs.existsSync(path.join(root, '.gitmodules'))
    ? [
        ...fs
          .readFileSync(path.join(root, '.gitmodules'), 'utf8')
          .matchAll(/^\s*path\s*=\s*(\S+)\s*$/gm),
      ].map((m) => m[1])
    : [];
  const listed = new Map<string, string[]>();
  listed.set(
    '.',
    gitFiles(root).filter((f) => !gitmodules.includes(f))
  );
  for (const sub of reg.submodules.scanned) {
    const dir = path.join(root, sub);
    if (fs.existsSync(path.join(dir, '.git'))) listed.set(sub, gitFiles(dir));
    else note(sub);
  }
  const cache = new Map<string, string | null>();
  return {
    repos: [...listed.keys()],
    files: (repo) => listed.get(repo) ?? [],
    gitmodules,
    read(repo, file) {
      const key = `${repo}\0${file}`;
      if (cache.has(key)) return cache.get(key) ?? null;
      let text: string | null = null;
      try {
        const abs = path.join(root, repo, file);
        const st = fs.statSync(abs);
        if (st.isFile() && st.size <= MAX_BYTES) {
          const buf = fs.readFileSync(abs);
          text = buf.includes(0) ? null : buf.toString('utf8');
        }
      } catch {
        text = null;
      }
      cache.set(key, text);
      return text;
    },
  };
}

/** An in-memory tree: `{ ".": { "path": "text" }, "private/renet": {...} }`. */
export function memTree(files: Record<string, Record<string, string>>, gitmodules: string[]): Tree {
  return {
    repos: Object.keys(files),
    files: (repo) => Object.keys(files[repo] ?? {}).sort((a, b) => Number(a > b) - Number(a < b)),
    read: (repo, file) => (Object.hasOwn(files[repo] ?? {}, file) ? files[repo][file] : null),
    gitmodules,
  };
}

// ---- scanners ---------------------------------------------------------------------------

export interface Hit {
  scanner: ScannerId;
  repo: string;
  file: string;
  /** 1-based line; 0 for a file-level hit (a lockfile). */
  line: number;
  text: string;
  key: string;
  value: string;
}

const base = (file: string): string => file.slice(file.lastIndexOf('/') + 1);
const isDockerfile = (file: string): boolean => base(file).startsWith('Dockerfile');
const PIN_NAME = '[A-Z0-9_]*?(?:_VERSION|_COMMIT|_DIGEST|_SHA256(?:_[A-Z0-9_]+)?)';

type Scanner = (repo: string, file: string, text: string) => Hit[];

function lineHits(
  scanner: ScannerId,
  repo: string,
  file: string,
  text: string,
  re: RegExp,
  pick: (m: RegExpExecArray) => { key: string; value: string } | null
): Hit[] {
  const out: Hit[] = [];
  text.split('\n').forEach((raw, i) => {
    const m = re.exec(raw);
    if (!m) return;
    const kv = pick(m);
    if (kv) out.push({ scanner, repo, file, line: i + 1, text: raw, ...kv });
  });
  return out;
}

const fileHit = (scanner: ScannerId, repo: string, file: string): Hit => ({
  scanner,
  repo,
  file,
  line: 0,
  text: '',
  key: file,
  value: '',
});

export const SCANNER_IMPLS: Record<ScannerId, Scanner> = {
  'dockerfile-arg': (repo, file, text) =>
    isDockerfile(file)
      ? lineHits(
          'dockerfile-arg',
          repo,
          file,
          text,
          new RegExp(`^\\s*ARG\\s+(${PIN_NAME})=(\\S+)`),
          (m) => ({
            key: m[1],
            value: m[2],
          })
        )
      : [],
  'toolchain-env': (repo, file, text) =>
    base(file) === 'toolchain.env'
      ? lineHits('toolchain-env', repo, file, text, new RegExp(`^(${PIN_NAME})=(\\S*)$`), (m) => ({
          key: m[1],
          value: m[2],
        }))
      : [],
  'shell-const': (repo, file, text) =>
    /\.(sh|bash)$/.test(file)
      ? lineHits(
          'shell-const',
          repo,
          file,
          text,
          new RegExp(
            `^\\s*(?:readonly\\s+|export\\s+|local\\s+|declare\\s+-r\\s+)?(${PIN_NAME})=["']?([0-9A-Za-z][^"'\\s]*)`
          ),
          (m) => ({ key: m[1], value: m[2] })
        )
      : [],
  'from-image': (repo, file, text) => {
    if (!isDockerfile(file)) return [];
    const lines = text.split('\n');
    const argAt = new Map<string, { line: number; value: string }>();
    const stages = new Set<string>(['scratch']);
    const out: Hit[] = [];
    lines.forEach((raw, i) => {
      const a = /^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(\S+)/.exec(raw);
      if (a && !argAt.has(a[1])) argAt.set(a[1], { line: i + 1, value: a[2] });
      const f = /^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?/i.exec(raw);
      if (!f) return;
      const ref = f[1];
      if (f[2]) stages.add(f[2]);
      if (stages.has(ref) && ref !== f[2]) return;
      const v =
        /^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?(.*)$/.exec(ref) ??
        /^(.*?)\$\{([A-Za-z_][A-Za-z0-9_]*)\}(.*)$/.exec(ref);
      if (v) {
        // An ARG-defaulted image: the pin is the ARG line, so that is where it must be claimed.
        const name = v.length === 3 ? v[1] : v[2];
        const at = argAt.get(name);
        if (at) {
          out.push({
            scanner: 'from-image',
            repo,
            file,
            line: at.line,
            text: lines[at.line - 1],
            key: name,
            value: ref.replace(/\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/, at.value),
          });
          return;
        }
      }
      out.push({ scanner: 'from-image', repo, file, line: i + 1, text: raw, key: ref, value: ref });
    });
    return out;
  },
  'action-uses': (repo, file, text) =>
    /\.ya?ml$/.test(file)
      ? lineHits(
          'action-uses',
          repo,
          file,
          text,
          /^\s*-?\s*uses:\s*["']?([A-Za-z0-9_.-]+\/[A-Za-z0-9_./-]+)@([0-9a-f]{40})\b/,
          (m) => ({ key: m[1], value: m[2] })
        )
      : [],
  'npm-lockfile': (repo, file) =>
    base(file) === 'package-lock.json' ? [fileHit('npm-lockfile', repo, file)] : [],
  'go-mod': (repo, file, text) =>
    base(file) === 'go.mod'
      ? [
          fileHit('go-mod', repo, file),
          ...lineHits('go-mod', repo, file, text, /^(go|toolchain)\s+(\S+)\s*$/, (m) => ({
            key: m[1],
            value: m[2],
          })),
        ]
      : [],
  'pin-lock-json': (repo, file) =>
    file.endsWith('.lock.json') ? [fileHit('pin-lock-json', repo, file)] : [],
  'ceph-pin': (repo, file, text) =>
    base(file) === '.ceph-image-pin'
      ? lineHits('ceph-pin', repo, file, text, /^(image|host\.[A-Za-z0-9.-]+)=(\S+)/, (m) => ({
          key: m[1],
          value: m[2],
        }))
      : [],
};

// ---- globs ------------------------------------------------------------------------------

const globCache = new Map<string, RegExp>();
/** `*` within a segment, `**` across segments (and zero of them), `?` one character. */
export function globMatch(glob: string, file: string): boolean {
  let re = globCache.get(glob);
  if (!re) {
    let src = '';
    for (let i = 0; i < glob.length; i++) {
      const c = glob[i];
      if (c === '*' && glob[i + 1] === '*') {
        i++;
        if (glob[i + 1] === '/') {
          i++;
          src += '(?:.*/)?';
        } else src += '.*';
      } else if (c === '*') src += '[^/]*';
      else if (c === '?') src += '[^/]';
      else src += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    }
    re = new RegExp(`^${src}$`);
    globCache.set(glob, re);
  }
  return re.test(file);
}

// ---- the check --------------------------------------------------------------------------

export type FindingKind =
  | 'unclaimed'
  | 'count'
  | 'disagree'
  | 'literal'
  | 'dead-ignore'
  | 'dead-scope'
  | 'dead-exclude'
  | 'reason'
  | 'gate-id'
  | 'missing-file'
  | 'submodule';

export interface Finding {
  kind: FindingKind;
  where: string;
  message: string;
}

/** The checks a mutant can remove, for the selftest's proof that each case depends on its check. */
export type Mutant =
  | `scanner:${ScannerId}`
  | 'no-reverse-count'
  | 'no-agreement'
  | 'no-literals'
  | 'no-ignore-liveness'
  | 'no-scope-liveness'
  | 'no-exclude-liveness'
  | 'no-reason-check'
  | 'no-submodule-presence';

export interface CheckOptions {
  mutants?: ReadonlySet<Mutant>;
  /** Manifest gate ids; a registry `gates` id outside it is red. */
  gateIds: ReadonlySet<string>;
  /** The BLOCKER quality rule; null when the reason is acceptable. */
  reasonProblem: (id: string, reason: string) => string | null;
  /** True on a CI runner (a missing scanned submodule is then red). */
  ci: boolean;
  /** Existence of a console-relative path (holds). */
  exists: (rel: string) => boolean;
}

export interface CheckStats {
  files: number;
  hits: number;
  sites: number;
  literalFiles: number;
  literalOccurrences: number;
  ignoresUsed: number;
  absentRepos: string[];
}

interface Claimed {
  /** repo\0file -> claimed line numbers. */
  lines: Map<string, Set<number>>;
  /** repo\0file of json sites and derive outputs: every line of the file is claimed for literals. */
  wholeFiles: Set<string>;
  jsonFiles: Set<string>;
}

const k = (repo: string, file: string): string => `${repo}\0${file}`;
const where = (repo: string, file: string, line?: number): string =>
  `${repo === '.' ? '' : `${repo}/`}${file}${line ? `:${line}` : ''}`;

function suggestion(h: Hit): string {
  const site =
    h.line === 0
      ? `{"scanner": "${h.scanner}", "repo": "${h.repo}", "files": ["${h.file}"]} in a family's scope`
      : h.scanner === 'dockerfile-arg'
        ? `{"repo": "${h.repo}", "file": "${h.file}", "role": "version", "arg": "${h.key}", "expect": 1}`
        : h.scanner === 'toolchain-env'
          ? `{"repo": "${h.repo}", "file": "${h.file}", "role": "version", "env": "${h.key}", "expect": 1}`
          : `{"repo": "${h.repo}", "file": "${h.file}", "role": "version", "match": ${JSON.stringify(
              `^${h.text
                .trim()
                .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
                .replace(h.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), '(?<value>\\S+)')}`
            )}, "expect": 1}`;
  return h.line === 0
    ? `claim it with ${site}, or a {"scanner": "${h.scanner}", "repo": "${h.repo}", "file": "${h.file}", "reason": "BLOCKER: ..."} ignore`
    : `add the site ${site} to the entry that owns ${h.key} (or a new leaf {"id": "<kind>:<name>", "kind": "leaf", "driver": ..., "source": ..., "sites": [that site]}), or a reasoned ignore`;
}

export function checkRegistry(
  reg: PinRegistry,
  tree: Tree,
  opts: CheckOptions
): { findings: Finding[]; stats: CheckStats } {
  const m = opts.mutants ?? new Set<Mutant>();
  const findings: Finding[] = [];
  const add = (kind: FindingKind, at: string, message: string): void => {
    findings.push({ kind, where: at, message });
  };
  const present = new Set(tree.repos);
  const absentRepos = ['.', ...reg.submodules.scanned].filter((r) => !present.has(r));

  // PRESENCE: every .gitmodules path is scanned or excused, and a scanned one that is absent fails closed in CI.
  const declared = new Set([
    ...reg.submodules.scanned,
    ...reg.submodules.unscanned.map((u) => u.path),
  ]);
  for (const g of tree.gitmodules)
    if (!declared.has(g))
      add(
        'submodule',
        '.gitmodules',
        `${g} is a submodule the registry neither scans (submodules.scanned) nor excuses (submodules.unscanned with a BLOCKER reason)`
      );
  for (const d of declared)
    if (!tree.gitmodules.includes(d))
      add(
        'submodule',
        '.ci/config/pins.json',
        `${d} is declared in submodules but is not in .gitmodules`
      );
  if (!m.has('no-submodule-presence') && absentRepos.length > 0) {
    const verdict = submoduleVerdict(absentRepos, opts.ci ? { CI: 'true' } : {}, () => false);
    if (verdict.state === 'absent-ci')
      for (const r of absentRepos)
        add(
          'submodule',
          r,
          `${r} is scanned by the registry but not checked out; in CI that is a gate that checked nothing (fix the workflow checkout: submodules: true)`
        );
  }

  // SCAN
  let files = 0;
  const hits: Hit[] = [];
  for (const repo of tree.repos)
    for (const file of tree.files(repo)) {
      files++;
      const want = (Object.keys(SCANNER_IMPLS) as ScannerId[]).filter(
        (s) => !m.has(`scanner:${s}`)
      );
      const b = base(file);
      // Only read files some scanner could hit; the literal pass reads the rest.
      if (
        !(
          isDockerfile(file) ||
          b === 'toolchain.env' ||
          /\.(sh|bash|ya?ml)$/.test(b) ||
          b === 'package-lock.json' ||
          b === 'go.mod' ||
          b.endsWith('.lock.json') ||
          b === '.ceph-image-pin'
        )
      )
        continue;
      const text =
        b === 'package-lock.json' || b.endsWith('.lock.json') ? '' : tree.read(repo, file);
      if (text === null) continue;
      for (const s of want) hits.push(...SCANNER_IMPLS[s](repo, file, text));
    }

  // SITES: reverse counts, agreement, and the lines they claim.
  const claimed: Claimed = { lines: new Map(), wholeFiles: new Set(), jsonFiles: new Set() };
  let siteCount = 0;
  const versionOf = new Map<string, string>();
  for (const e of reg.entries) {
    const byRole = new Map<string, Array<{ at: string; value: string }>>();
    for (const s of e.sites) {
      if (!present.has(s.repo)) continue;
      siteCount++;
      const text = tree.read(s.repo, s.file);
      const at = where(s.repo, s.file);
      if (text === null) {
        add('missing-file', at, `${e.id}: site file is absent from the tree`);
        continue;
      }
      const found: SiteMatch[] = siteMatches(s, text);
      if (!m.has('no-reverse-count') && found.length !== s.expect)
        add(
          'count',
          at,
          `${e.id}: site ${describe(s)} matches ${found.length} time(s), expected ${s.expect}. ${found.length === 0 ? 'The site moved or was renamed: update its locator.' : 'A copy appeared: claim it (raise expect, or make it its own site) so a bump moves every copy.'}`
        );
      if (s.json !== undefined) {
        claimed.jsonFiles.add(k(s.repo, s.file));
        claimed.wholeFiles.add(k(s.repo, s.file));
      }
      const set = claimed.lines.get(k(s.repo, s.file)) ?? new Set<number>();
      for (const f of found) for (let l = f.line; l <= f.lastLine; l++) if (l > 0) set.add(l);
      claimed.lines.set(k(s.repo, s.file), set);
      const list = byRole.get(s.role) ?? [];
      for (const f of found)
        list.push({ at: f.line ? `${at}:${f.line}` : `${at}${s.json}`, value: f.value });
      byRole.set(s.role, list);
    }
    if (!m.has('no-agreement'))
      for (const [role, list] of byRole) {
        const values = [...new Set(list.map((x) => x.value))];
        if (values.length > 1)
          add(
            'disagree',
            e.id,
            `${e.id}: its ${role} sites disagree: ${list.map((x) => `${x.at} = ${x.value}`).join(', ')}. A bump that moved some copies and not others; set every site to one value.`
          );
      }
    const v = byRole.get('version')?.[0]?.value;
    if (v !== undefined) versionOf.set(e.id, v);
    for (const d of e.derive)
      for (const w of d.writes) {
        if (!present.has(w.repo)) continue;
        claimed.wholeFiles.add(k(w.repo, w.file));
        if (tree.read(w.repo, w.file) === null)
          add(
            'missing-file',
            where(w.repo, w.file),
            `${e.id}: derive output is absent from the tree`
          );
      }
  }

  // FORWARD: every hit claimed.
  const ignoreUse = new Map<number, number>();
  const scopeUse = new Map<string, number>();
  const ignoreRes = reg.ignores.map((g) => (g.match ? compile(g.match, '') : null));
  const ignoreClaims = (scanner: string, repo: string, file: string, text: string): boolean => {
    let hit = false;
    reg.ignores.forEach((g, i) => {
      if (g.scanner !== scanner || g.repo !== repo || g.file !== file) return;
      const re = ignoreRes[i];
      if (re && !re.test(text)) return;
      ignoreUse.set(i, (ignoreUse.get(i) ?? 0) + 1);
      hit = true;
    });
    return hit;
  };
  for (const h of hits) {
    let ok = false;
    if (h.line > 0) ok = claimed.lines.get(k(h.repo, h.file))?.has(h.line) ?? false;
    else if (h.scanner === 'pin-lock-json') ok = claimed.jsonFiles.has(k(h.repo, h.file));
    for (const e of reg.entries)
      (e.scope ?? []).forEach((sc, j) => {
        if (
          sc.scanner === h.scanner &&
          sc.repo === h.repo &&
          sc.files.some((g) => globMatch(g, h.file))
        ) {
          ok = true;
          const key = `${e.id}#${j}`;
          scopeUse.set(key, (scopeUse.get(key) ?? 0) + 1);
        }
      });
    if (ignoreClaims(h.scanner, h.repo, h.file, h.text)) ok = true;
    if (!ok)
      add(
        'unclaimed',
        where(h.repo, h.file, h.line),
        `${h.scanner} found ${h.key}${h.value && h.value !== h.key ? ` = ${h.value}` : ''}${h.text ? ` (${h.text.trim()})` : ''}, which no registry entry claims; ${suggestion(h)}`
      );
  }

  // LITERALS
  let literalFiles = 0;
  let literalOccurrences = 0;
  const excludeUse = new Map<number, number>();
  const literalEntries = reg.entries.filter((e) => e.literals.length > 0);
  if (!m.has('no-literals') && literalEntries.length > 0) {
    const plan: Array<{ e: PinEntry; value: string; res: RegExp[] }> = [];
    for (const e of literalEntries) {
      const value = versionOf.get(e.id);
      if (value === undefined) {
        add(
          'literal',
          e.id,
          `${e.id}: has literals but no version site in a present repo to read its current value from`
        );
        continue;
      }
      plan.push({ e, value, res: e.literals.map((l) => compile(l.re, 'g')) });
    }
    for (const repo of tree.repos)
      for (const file of tree.files(repo)) {
        const ex = reg.literalExclude.findIndex((x) => x.repo === repo && globMatch(x.glob, file));
        if (ex >= 0) {
          excludeUse.set(ex, (excludeUse.get(ex) ?? 0) + 1);
          continue;
        }
        if (/(^|\/)package-lock\.json$|(^|\/)go\.sum$/.test(file)) continue;
        literalFiles++;
        const live = plan.filter(() => true);
        let text: string | null | undefined;
        for (const p of live) {
          text ??= tree.read(repo, file);
          if (text === null) break;
          if (!text.includes(p.value)) continue;
          for (const re of p.res) {
            re.lastIndex = 0;
            for (const mm of text.matchAll(re)) {
              if (mm.groups?.value !== p.value) continue;
              literalOccurrences++;
              const line = text.slice(0, mm.index ?? 0).split('\n').length;
              const lineText = text.split('\n')[line - 1] ?? '';
              const ok =
                claimed.wholeFiles.has(k(repo, file)) ||
                (claimed.lines.get(k(repo, file))?.has(line) ?? false) ||
                ignoreClaims('literal', repo, file, lineText);
              if (!ok)
                add(
                  'literal',
                  where(repo, file, line),
                  `${p.e.id}: a copy of its current value ${p.value} (${lineText.trim().slice(0, 160)}) sits outside every site, derive output and ignore, so the next bump would leave it behind. Make it a site of ${p.e.id}, or add a {"scanner": "literal", "repo": "${repo}", "file": "${file}", "match": ..., "reason": "BLOCKER: ..."} ignore when it is a dated record rather than a copy.`
                );
            }
          }
        }
      }
  }

  // LIVENESS (only for repos present: an absent submodule's ignores cannot be judged here)
  if (!m.has('no-ignore-liveness'))
    reg.ignores.forEach((g, i) => {
      if (!present.has(g.repo)) return;
      if (g.scanner === 'literal' && m.has('no-literals')) return;
      if (!ignoreUse.has(i))
        add(
          'dead-ignore',
          where(g.repo, g.file),
          `ignores[${i}] (${g.scanner}${g.match ? ` /${g.match}/` : ''}) claims nothing; the line it excused is gone, so delete the ignore`
        );
    });
  if (!m.has('no-scope-liveness'))
    for (const e of reg.entries)
      (e.scope ?? []).forEach((sc, j) => {
        if (
          present.has(sc.repo) &&
          !scopeUse.has(`${e.id}#${j}`) &&
          !m.has(`scanner:${sc.scanner}`)
        )
          add(
            'dead-scope',
            e.id,
            `${e.id}: scope[${j}] (${sc.scanner} in ${sc.repo}: ${sc.files.join(', ')}) matches no hit; the files it names are gone or renamed`
          );
      });
  if (!m.has('no-exclude-liveness') && !m.has('no-literals'))
    reg.literalExclude.forEach((x, i) => {
      if (present.has(x.repo) && !excludeUse.has(i))
        add(
          'dead-exclude',
          where(x.repo, x.glob),
          `literalExclude[${i}] covers no tracked file; delete it`
        );
    });

  // REASONS, GATES, HOLDS
  if (!m.has('no-reason-check')) {
    const reasons: [string, string][] = [];
    for (const e of reg.entries)
      if (e.source.type === 'none') reasons.push([`${e.id} source`, e.source.reason ?? '']);
    reg.ignores.forEach((g, i) =>
      reasons.push([`ignores[${i}] ${where(g.repo, g.file)}`, g.reason])
    );
    reg.literalExclude.forEach((x, i) =>
      reasons.push([`literalExclude[${i}] ${x.glob}`, x.reason])
    );
    reg.submodules.unscanned.forEach((u) =>
      reasons.push([`submodules.unscanned ${u.path}`, u.reason])
    );
    for (const [id, reason] of reasons) {
      const why = opts.reasonProblem(id, reason.replace(/^BLOCKER:\s*/, ''));
      if (why) add('reason', id, why);
    }
  }
  for (const e of reg.entries) {
    for (const g of e.gates)
      if (!opts.gateIds.has(g))
        add('gate-id', e.id, `${e.id}: gates names ${g}, which is not a manifest gate id`);
    for (const h of e.holds)
      if (!opts.exists(h)) add('missing-file', h, `${e.id}: hold file is absent`);
  }

  return {
    findings,
    stats: {
      files,
      hits: hits.length,
      sites: siteCount,
      literalFiles,
      literalOccurrences,
      ignoresUsed: ignoreUse.size,
      absentRepos,
    },
  };
}

function describe(s: PinSite): string {
  return s.arg ? `ARG ${s.arg}` : s.env ? `${s.env}=` : s.json ? `json ${s.json}` : `/${s.match}/`;
}

// ---- selftest ---------------------------------------------------------------------------

const SHA = 'a'.repeat(40);

function fixtureRegistry(): PinRegistry {
  return {
    version: 1,
    submodules: {
      scanned: ['private/renet'],
      unscanned: [
        {
          path: 'private/elite',
          reason:
            'BLOCKER: the elite submodule carries no pinned third-party version; it holds operator notes only',
        },
      ],
    },
    literalExclude: [
      {
        repo: '.',
        glob: 'notes/**',
        reason:
          'BLOCKER: session records quote versions as history, never as copies a bump must move',
      },
    ],
    entries: [
      {
        id: 'embed:snap',
        kind: 'leaf',
        name: 'snap',
        driver: 'embed',
        source: { type: 'github-release', repo: 'kubernetes-csi/external-snapshotter' },
        safety: { mode: 'release-age', major: 'assisted' },
        holds: [],
        gates: ['check:x'],
        sites: [
          {
            repo: 'private/renet',
            file: 'Dockerfile',
            role: 'version',
            arg: 'SNAP_VERSION',
            expect: 1,
          },
          {
            repo: 'private/renet',
            file: 'units.go',
            role: 'version',
            match: '^\\tSnapVersion = "v(?<value>[^"]+)"$',
            expect: 1,
          },
          {
            repo: 'private/renet',
            file: 'assets.lock.json',
            role: 'version',
            json: '/components/snap/version',
            expect: 1,
          },
        ],
        derive: [
          {
            run: 'gen',
            cwd: 'private/renet',
            writes: [{ repo: 'private/renet', file: 'credits.go' }],
          },
        ],
        literals: [{ re: 'external-snapshotter v(?<value>\\d+\\.\\d+\\.\\d+)' }],
      },
      {
        id: 'toolchain:go',
        kind: 'leaf',
        name: 'Go',
        driver: 'toolchain',
        source: { type: 'go-dl' },
        safety: { mode: 'release-age', major: 'assisted' },
        holds: [],
        gates: ['check:x'],
        sites: [
          {
            repo: '.',
            file: '.devcontainer/toolchain.env',
            role: 'version',
            env: 'GO_VERSION',
            expect: 1,
          },
          {
            repo: 'private/renet',
            file: 'go.mod',
            role: 'version',
            match: '^go (?<value>\\S+)$',
            expect: 1,
          },
          {
            repo: '.',
            file: 'tools/run.sh',
            role: 'version',
            match: '^readonly GO_PIN_VERSION="(?<value>[^"]+)"$',
            expect: 1,
          },
        ],
        derive: [],
        literals: [],
      },
      {
        id: 'os:leap',
        kind: 'leaf',
        name: 'Leap ceph',
        driver: 'os-ceph-host',
        source: {
          type: 'none',
          reason: 'BLOCKER: the fixture has no upstream to read; the OBS origin is the real one',
        },
        safety: { mode: 'mirror-tag', major: 'refuse' },
        holds: [],
        gates: ['check:x'],
        sites: [
          {
            repo: 'private/renet',
            file: '.ceph-image-pin',
            role: 'version',
            match: '^host\\.leap=(?<value>\\S+)$',
            expect: 1,
          },
        ],
        derive: [],
        literals: [],
      },
      {
        id: 'image:base',
        kind: 'leaf',
        name: 'base image',
        driver: 'docker',
        source: { type: 'dockerhub', image: 'node' },
        safety: { mode: 'assisted', major: 'assisted' },
        holds: [],
        gates: [],
        sites: [
          {
            repo: '.',
            file: '.ci/img/Dockerfile',
            role: 'version',
            match: '^ARG BASE_IMAGE=(?<value>\\S+)$',
            expect: 1,
          },
        ],
        derive: [],
        literals: [],
      },
      {
        id: 'npm',
        kind: 'family',
        name: 'npm',
        driver: 'npm',
        source: { type: 'npm-registry', package: '*' },
        safety: { mode: 'release-age', major: 'allow-file' },
        holds: [],
        gates: ['check:x'],
        scope: [
          {
            scanner: 'npm-lockfile',
            repo: '.',
            files: ['package-lock.json', 'workers/*/package-lock.json'],
          },
        ],
        sites: [],
        derive: [],
        literals: [],
      },
      {
        id: 'go-mod',
        kind: 'family',
        name: 'go modules',
        driver: 'go-mod',
        source: { type: 'go-list', module: 'all' },
        safety: { mode: 'release-age', major: 'refuse' },
        holds: [],
        gates: ['check:x'],
        scope: [{ scanner: 'go-mod', repo: 'private/renet', files: ['go.mod'] }],
        sites: [],
        derive: [],
        literals: [],
      },
      {
        id: 'actions',
        kind: 'family',
        name: 'actions',
        driver: 'actions',
        source: { type: 'github-tags', repo: 'actions/checkout' },
        safety: { mode: 'release-age', major: 'assisted' },
        holds: [],
        gates: ['check:x'],
        scope: [{ scanner: 'action-uses', repo: '.', files: ['.github/**'] }],
        sites: [],
        derive: [],
        literals: [],
      },
      {
        id: 'docker',
        kind: 'family',
        name: 'docker',
        driver: 'docker',
        source: { type: 'dockerhub' },
        safety: { mode: 'assisted', major: 'assisted' },
        holds: [],
        gates: ['check:x'],
        scope: [{ scanner: 'from-image', repo: 'private/renet', files: ['Dockerfile'] }],
        sites: [],
        derive: [],
        literals: [],
      },
    ],
    ignores: [
      {
        scanner: 'dockerfile-arg',
        repo: 'private/renet',
        file: 'Dockerfile',
        match: '^ARG BUILD_VERSION=',
        reason:
          'BLOCKER: BUILD_VERSION is the build stamp injected at build time, not a pinned third-party version',
      },
      {
        scanner: 'literal',
        repo: '.',
        file: 'docs/spec.md',
        match: 'research',
        reason:
          'BLOCKER: a dated research record naming the version that was current then, not a copy of the pin',
      },
    ],
  };
}

function fixtureFiles(): Record<string, Record<string, string>> {
  return {
    '.': {
      '.devcontainer/toolchain.env': '# pins\nGO_VERSION=1.0.7\n',
      'tools/run.sh': '#!/bin/bash\nreadonly GO_PIN_VERSION="1.0.7"\n',
      '.ci/img/Dockerfile': 'ARG BASE_IMAGE=node:24-slim\nFROM ${BASE_IMAGE}\n',
      'package-lock.json': '{}',
      'workers/a/package-lock.json': '{}',
      '.github/workflows/ci.yml': `jobs:\n  a:\n    steps:\n      - uses: actions/checkout@${SHA} # v5\n`,
      'docs/spec.md':
        '| snap | external-snapshotter v9.9.1 |\n\nresearch: external-snapshotter v9.9.1 was current then.\n',
      'notes/plan.md': 'external-snapshotter v9.9.1 is pinned\n',
    },
    'private/renet': {
      Dockerfile:
        'ARG BUILD_VERSION=dev\nFROM golang:1.26 AS b\nARG SNAP_VERSION=9.9.1\nFROM b AS c\n',
      'units.go': 'const (\n\tSnapVersion = "v9.9.1"\n)\n',
      'assets.lock.json':
        '{"components":{"snap":{"version":"9.9.1","url":"external-snapshotter v9.9.1"}}}',
      'credits.go': '// external-snapshotter v9.9.1\n',
      'go.mod': 'module x\n\ngo 1.0.7\n',
      '.ceph-image-pin': 'host.leap=0.0.1-lp160.0.1\n',
    },
  };
}

/** The fixture, with the docs table row made a site so the clean run claims it. */
function cleanRegistry(): PinRegistry {
  const reg = fixtureRegistry();
  reg.entries[0].sites.push({
    repo: '.',
    file: 'docs/spec.md',
    role: 'version',
    match: '^\\| snap \\| external-snapshotter v(?<value>\\S+) \\|$',
    expect: 1,
  });
  return reg;
}

const fakeReason = (_id: string, reason: string): string | null =>
  /^(tbd|todo|later|n\/a)$/i.test(reason.trim()) ? `low-effort reason: ${reason}` : null;

function run(
  reg: PinRegistry,
  files: Record<string, Record<string, string>>,
  mutants: Mutant[] = [],
  ci = false
): Finding[] {
  return checkRegistry(reg, memTree(files, ['private/renet', 'private/elite']), {
    mutants: new Set(mutants),
    gateIds: new Set(['check:x']),
    reasonProblem: fakeReason,
    ci,
    exists: () => true,
  }).findings;
}

interface Plant {
  name: string;
  kind: FindingKind;
  /** Substring the finding's location or message must carry, so an unrelated red cannot pass the case. */
  mark: string;
  mutant: Mutant;
  apply(reg: PinRegistry, files: Record<string, Record<string, string>>): void;
  ci?: boolean;
}

const PLANTS: Plant[] = [
  {
    name: 'an unclaimed Dockerfile ARG',
    kind: 'unclaimed',
    mark: 'FOO_VERSION',
    mutant: 'scanner:dockerfile-arg',
    apply: (_r, f) => (f['private/renet'].Dockerfile += 'ARG FOO_VERSION=1.2.3\n'),
  },
  {
    name: 'an unclaimed toolchain.env line',
    kind: 'unclaimed',
    mark: 'RUFF_VERSION',
    mutant: 'scanner:toolchain-env',
    apply: (_r, f) => (f['.']['.devcontainer/toolchain.env'] += 'RUFF_VERSION=0.16.1\n'),
  },
  {
    name: 'an unclaimed shell constant',
    kind: 'unclaimed',
    mark: 'NFPM_SHA256_X64',
    mutant: 'scanner:shell-const',
    apply: (_r, f) => (f['.']['tools/run.sh'] += `readonly NFPM_SHA256_X64="${'b'.repeat(64)}"\n`),
  },
  {
    name: 'an unclaimed FROM',
    kind: 'unclaimed',
    mark: 'alpine:3.20',
    mutant: 'scanner:from-image',
    apply: (_r, f) => (f['.']['.ci/other/Dockerfile'] = 'FROM alpine:3.20\n'),
  },
  {
    name: 'an unclaimed uses: sha',
    kind: 'unclaimed',
    mark: 'docker/login-action',
    mutant: 'scanner:action-uses',
    apply: (_r, f) =>
      (f['.']['.ci/breakpoint/wf.yml'] = `steps:\n  - uses: docker/login-action@${SHA}\n`),
  },
  {
    name: 'an unclaimed package-lock.json',
    kind: 'unclaimed',
    mark: 'tools/x/package-lock.json',
    mutant: 'scanner:npm-lockfile',
    apply: (_r, f) => (f['.']['tools/x/package-lock.json'] = '{}'),
  },
  {
    name: 'an unclaimed go.mod',
    kind: 'unclaimed',
    mark: 'tools/mint/go.mod',
    mutant: 'scanner:go-mod',
    apply: (_r, f) => (f['.']['tools/mint/go.mod'] = 'module m\n'),
  },
  {
    name: 'an unclaimed *.lock.json pin file',
    kind: 'unclaimed',
    mark: 'e2e/provider.lock.json',
    mutant: 'scanner:pin-lock-json',
    apply: (_r, f) => (f['.']['e2e/provider.lock.json'] = '{}'),
  },
  {
    name: 'an unclaimed .ceph-image-pin host line',
    kind: 'unclaimed',
    mark: 'host.arch',
    mutant: 'scanner:ceph-pin',
    apply: (_r, f) => (f['private/renet']['.ceph-image-pin'] += 'host.arch=19.2.3-1\n'),
  },
  {
    name: 'a literal copy outside every site',
    kind: 'literal',
    mark: 'README.md',
    mutant: 'no-literals',
    apply: (_r, f) => (f['.']['README.md'] = 'Ships external-snapshotter v9.9.1.\n'),
  },
  {
    name: 'a dead site (the line moved)',
    kind: 'count',
    mark: 'matches 0 time',
    mutant: 'no-reverse-count',
    apply: (_r, f) =>
      (f['private/renet']['units.go'] = 'const (\n\tSnapshotterVersion = "v9.9.1"\n)\n'),
  },
  {
    name: 'a duplicate match of one site',
    kind: 'count',
    mark: 'matches 2 time',
    mutant: 'no-reverse-count',
    apply: (_r, f) => (f['.']['.devcontainer/toolchain.env'] += 'GO_VERSION=1.0.7\n'),
  },
  {
    name: 'sites of one role that disagree',
    kind: 'disagree',
    mark: 'toolchain:go',
    mutant: 'no-agreement',
    apply: (_r, f) => (f['private/renet']['go.mod'] = 'module x\n\ngo 1.0.6\n'),
  },
  {
    name: 'a dead ignore',
    kind: 'dead-ignore',
    mark: 'BUILD_VERSION',
    mutant: 'no-ignore-liveness',
    apply: (_r, f) =>
      (f['private/renet'].Dockerfile = f['private/renet'].Dockerfile.replace(
        'ARG BUILD_VERSION=dev\n',
        ''
      )),
  },
  {
    name: 'a dead family scope',
    kind: 'dead-scope',
    mark: 'npm',
    mutant: 'no-scope-liveness',
    apply: (r) =>
      (r.entries[4].scope = [
        { scanner: 'npm-lockfile', repo: '.', files: ['gone/package-lock.json'] },
        ...(r.entries[4].scope ?? []),
      ]),
  },
  {
    name: 'a dead literal exclusion',
    kind: 'dead-exclude',
    mark: 'archive/**',
    mutant: 'no-exclude-liveness',
    apply: (r) =>
      r.literalExclude.push({
        repo: '.',
        glob: 'archive/**',
        reason: 'BLOCKER: archived records quote old versions as history only',
      }),
  },
  {
    name: 'a hollow source:none reason',
    kind: 'reason',
    mark: 'os:leap',
    mutant: 'no-reason-check',
    apply: (r) => (r.entries[2].source.reason = 'BLOCKER: tbd'),
  },
  {
    name: 'a scanned submodule missing under CI',
    kind: 'submodule',
    mark: 'private/renet',
    mutant: 'no-submodule-presence',
    ci: true,
    apply: (_r, f) => delete f['private/renet'],
  },
];

function gateCases(): ControlCase[] {
  const cases: ControlCase[] = [];
  const clean = run(cleanRegistry(), fixtureFiles());
  cases.push({
    name: 'CONTROL: the clean fixture has no finding (every scanner fires on it and every hit is claimed)',
    ok: clean.length === 0,
    detail: clean.map((f) => `${f.kind} ${f.where}: ${f.message}`).join('\n'),
  });
  // The clean fixture must exercise every scanner, or a case below could pass on a scanner that never fires.
  const tree = memTree(fixtureFiles(), ['private/renet', 'private/elite']);
  const fired = new Set<string>();
  for (const repo of tree.repos)
    for (const file of tree.files(repo))
      for (const s of SCANNERS)
        if (SCANNER_IMPLS[s](repo, file, tree.read(repo, file) ?? '').length > 0) fired.add(s);
  const silent = SCANNERS.filter((s) => !fired.has(s));
  cases.push({
    name: 'CONTROL: every scanner fires on the clean fixture',
    ok: silent.length === 0,
    detail: `silent: ${silent.join(', ')}`,
  });

  // Locally a missing submodule is NOT CHECKED, never red: the CI case below is not red for a reason that holds everywhere.
  const local = run(
    cleanRegistry(),
    (() => {
      const f = fixtureFiles();
      delete f['private/renet'];
      return f;
    })()
  );
  cases.push({
    name: 'CONTROL: a missing scanned submodule outside CI is not a finding',
    ok: !local.some((f) => f.kind === 'submodule'),
    detail: local.map((f) => f.message).join('\n'),
  });

  for (const p of PLANTS) {
    const reg = cleanRegistry();
    const files = fixtureFiles();
    p.apply(reg, files);
    const hit = (fs2: Finding[]): boolean =>
      fs2.some(
        (f) => f.kind === p.kind && (f.where.includes(p.mark) || f.message.includes(p.mark))
      );
    const red = run(reg, files, [], p.ci);
    cases.push({
      name: `RED: ${p.name}`,
      ok: hit(red),
      detail: red.map((f) => `${f.kind} ${f.where}: ${f.message}`).join('\n') || 'no finding',
    });
    const reg2 = cleanRegistry();
    const files2 = fixtureFiles();
    p.apply(reg2, files2);
    const green = run(reg2, files2, [p.mutant], p.ci);
    cases.push({
      name: `MUTANT ${p.mutant}: the same plant is green without its check`,
      ok: !hit(green),
      detail: green.map((f) => `${f.kind} ${f.where}: ${f.message}`).join('\n'),
    });
  }

  // The real BLOCKER validator, once, so the wiring to the shared rule is proven and not only the fake.
  const real = validateBlockerQuality('fixture', 'tbd', '.ci/config/pins.json');
  cases.push({
    name: 'the shared BLOCKER validator refuses a hollow reason',
    ok: real !== null,
    detail: 'validateBlockerQuality accepted "tbd"',
  });
  const realOk = validateBlockerQuality(
    'fixture',
    'BUILD_VERSION is the build stamp injected at build time, not a pinned third-party version',
    '.ci/config/pins.json'
  );
  cases.push({
    name: 'CONTROL: the shared BLOCKER validator accepts a substantive reason',
    ok: realOk === null,
    detail: realOk?.message,
  });

  // Globs, both directions.
  const globs: [string, string, boolean][] = [
    ['.github/**', '.github/workflows/ci.yml', true],
    ['workers/*/package-lock.json', 'workers/a/package-lock.json', true],
    ['workers/*/package-lock.json', 'workers/a/b/package-lock.json', false],
    ['**/go.mod', 'go.mod', true],
    ['package-lock.json', 'x/package-lock.json', false],
  ];
  for (const [g, f, want] of globs)
    cases.push({
      name: `glob ${g} ${want ? 'matches' : 'does not match'} ${f}`,
      ok: globMatch(g, f) === want,
    });
  return cases;
}

// ---- main -------------------------------------------------------------------------------

function main(): number {
  const args = process.argv.slice(2);
  if (args.includes('--selftest')) {
    const failed = runControls([...loaderCases(), ...gateCases()]);
    return failed === 0 ? 0 : 1;
  }
  const root = envRoot('PINS_ROOT');
  let reg: PinRegistry;
  try {
    reg = loadRegistry(registryPath());
  } catch (err) {
    console.error(`${RED}✗ ${err instanceof RegistryError ? err.message : String(err)}${NC}`);
    return 1;
  }
  const notChecked: string[] = [];
  const tree = gitTree(root, reg, (sub) => notChecked.push(sub));
  const { findings, stats } = checkRegistry(reg, tree, {
    gateIds: new Set(GATES.map((g) => g.id)),
    reasonProblem: (id, reason) =>
      validateBlockerQuality(id, reason, '.ci/config/pins.json')?.message ?? null,
    ci: inCi(),
    exists: (rel) => fs.existsSync(path.join(root, rel)),
  });

  if (args.includes('--json')) {
    process.stdout.write(`${JSON.stringify({ findings, stats }, null, 2)}\n`);
    return findings.length === 0 && stats.hits >= MIN_HITS ? 0 : 1;
  }

  console.log('Pin registry coverage');
  console.log('='.repeat(60));
  for (const sub of notChecked)
    console.log(
      `${YELLOW}⊘ NOT CHECKED: ${sub} is not checked out, so its pins were not scanned. Under CI this is a hard failure.${NC}`
    );
  if (stats.files === 0 || stats.hits < MIN_HITS) {
    console.error(
      `${RED}✗ VACUOUS: the scan saw ${stats.files} file(s) and ${stats.hits} pin hit(s), under the floor of ${MIN_HITS}; the gate is not seeing the tree, so a green would mean nothing${NC}`
    );
    return 1;
  }
  if (findings.length > 0) {
    const order: FindingKind[] = [
      'submodule',
      'unclaimed',
      'count',
      'disagree',
      'literal',
      'dead-ignore',
      'dead-scope',
      'dead-exclude',
      'reason',
      'gate-id',
      'missing-file',
    ];
    findings.sort(
      (a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || a.where.localeCompare(b.where)
    );
    for (const f of findings)
      console.error(`${RED}✗ [${f.kind}] ${f.where}${NC}\n    ${f.message}`);
    console.error(
      `\n${RED}✗ ${findings.length} finding(s).${NC} The registry is .ci/config/pins.json; its shape is documented in scripts/lib/pins/registry.ts.`
    );
    return 1;
  }
  const fam = reg.entries.filter((e) => e.kind === 'family').length;
  console.log(
    `${GREEN}✓ ${stats.hits} pin hit(s) across ${stats.files} tracked file(s) in ${tree.repos.length} repo(s) are all claimed by ${reg.entries.length} entries (${fam} families, ${reg.entries.length - fam} leaves); ${stats.sites} site(s) match their expected counts and agree; ${stats.literalOccurrences} literal occurrence(s) over ${stats.literalFiles} file(s) are claimed; ${reg.ignores.length} ignore(s) all live.${NC}`
  );
  return 0;
}

process.exit(main());
