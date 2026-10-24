#!/usr/bin/env tsx
/**
 * check:ci-override-ranges -- every lockfile edge onto an OVERRIDDEN package must resolve
 * to a version the dependent itself declares.
 *
 * WHY. npm puts an `overrides` value in place of the dependent's own range and then judges
 * the tree against the override, not against the range the dependent wrote. So an override
 * floor below a dependent's range installs a version that dependent never accepted, and
 * neither `npm ls` nor check:ci-lockfile can see it: body-parser 2.4.0 declares
 * qs ^6.16.1 and ran on qs 6.16.0 under the `>=6.16.0` override (review 83dfdb27.1,
 * 2026-10-24; c9d5c7d1b fixed that edge and four more of the class in the root lockfile).
 *
 * WHAT IS JUDGED. For every npm project the pins registry's `npm-lockfile` scope names (the
 * same list `npm run pins -- lockfiles` walks, read from .ci/config/pins.json, never a list
 * typed here), every `packages` entry of its lockfile, and each name in that entry's
 * dependencies, devDependencies, optionalDependencies and peerDependencies that is an
 * override key of the project's own package.json (at any nesting depth, `name@range`
 * selectors reduced to `name`). The installed copy is found the way Node finds it: the
 * nearest `node_modules/<name>` walking up from the dependent's own path, a `link` entry
 * followed to its target.
 *
 * OPTIONAL EDGES. An optional dependency or optional peer that is NOT installed is no edge
 * and is counted as absent. One that IS installed counts in full: the dependent loads it
 * when present, so a version outside its range is as live as any other.
 *
 * WHAT IS NOT JUDGED, and printed as a count so it cannot hide: specs that are not semver
 * ranges (`npm:`, `file:`, `link:`, `workspace:`, git and URL specs, anything with a `:` or
 * a `/`).
 *
 * UNKNOWN IS A FAILURE. A range the parser cannot read, a prerelease or unparseable
 * installed version, a required edge with no installed copy, a scoped repo whose checkout
 * is absent, a lockfile with no package.json beside it, and a corpus of zero lockfiles all
 * exit 1 as UNCHECKED rather than folding into a pass.
 *
 * Usage: npx tsx scripts/gates/check-override-ranges.ts [--selftest] [--root <dir>]
 *   --root  judge another tree (its .ci/config/pins.json and lockfiles); the selftest
 *           and the control fixtures use it.
 * Exit 0 clean, 1 a finding or an unchecked edge.
 *
 * ---- gate ----
 * step: Override ranges
 * needs: node, submodules
 * lane: quality-security
 * selftest: true
 * ---- end gate ----
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

import { parseRange, parseVersion, rangeAdmits } from '../lib/deps/shared.js';
import { parseRegistry } from '../lib/pins/registry.js';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const REGISTRY_REL = '.ci/config/pins.json';
const DEP_FIELDS = [
  'dependencies',
  'devDependencies',
  'optionalDependencies',
  'peerDependencies',
] as const;

export interface LockNode {
  version?: string;
  link?: boolean;
  resolved?: string;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  optionalDependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
  peerDependenciesMeta?: Record<string, { optional?: boolean }>;
}

export interface Project {
  /** Repo-relative project directory, '.' for the root. */
  dir: string;
  abs: string;
}

export interface Verdicts {
  findings: string[];
  unchecked: string[];
  edges: number;
  skippedSpecs: number;
  absentOptional: number;
}

/** The package name an override key names: `name`, `@scope/name`, `name@range`, `@scope/name@range`. */
export function overrideKeyName(key: string): string {
  const at = key.indexOf('@', key.startsWith('@') ? 1 : 0);
  return at < 0 ? key : key.slice(0, at);
}

/** Every package name an `overrides` object overrides, at any nesting depth. `.` (the parent itself) is not a name. */
export function overrideNames(overrides: unknown): Set<string> {
  const out = new Set<string>();
  const walk = (obj: unknown): void => {
    if (obj === null || typeof obj !== 'object') return;
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      if (k !== '.') out.add(overrideKeyName(k));
      walk(v);
    }
  };
  walk(overrides);
  return out;
}

/** True for a spec that is not a semver range: an alias, a path, a workspace, a git or URL spec, a `user/repo` shorthand. */
export function isNonRegistrySpec(spec: string): boolean {
  return spec.includes(':') || spec.includes('/');
}

/**
 * The lockfile key of the copy of `name` that `dependent` loads, or null. Node walks from the
 * dependent's directory up through every ancestor's `node_modules`, never looking inside a
 * directory that is itself named node_modules.
 */
export function resolveKey(
  pkgs: Record<string, LockNode>,
  dependent: string,
  name: string
): string | null {
  const segs = dependent === '' ? [] : dependent.split('/');
  for (let n = segs.length; n >= 0; n--) {
    if (n > 0 && segs[n - 1] === 'node_modules') continue;
    const base = segs.slice(0, n).join('/');
    const key = base === '' ? `node_modules/${name}` : `${base}/node_modules/${name}`;
    if (Object.hasOwn(pkgs, key)) return key;
  }
  return null;
}

/** The version a resolved key installs, following a workspace or file `link` to its target. */
export function versionOf(pkgs: Record<string, LockNode>, key: string): string | undefined {
  const node = pkgs[key];
  if (node?.link && node.resolved !== undefined) return pkgs[node.resolved]?.version;
  return node?.version;
}

/** Judge one lockfile's edges onto `names`. `label` prefixes every message. */
export function judge(label: string, pkgs: Record<string, LockNode>, names: Set<string>): Verdicts {
  const v: Verdicts = { findings: [], unchecked: [], edges: 0, skippedSpecs: 0, absentOptional: 0 };
  if (names.size === 0) return v;
  for (const [dependent, node] of Object.entries(pkgs)) {
    if (node.link) continue; // the target entry carries the declarations
    const who = `${dependent || '(project root)'}${node.version ? `@${node.version}` : ''}`;
    for (const field of DEP_FIELDS) {
      for (const [name, spec] of Object.entries(node[field] ?? {})) {
        if (!names.has(name)) continue;
        if (isNonRegistrySpec(spec)) {
          v.skippedSpecs++;
          continue;
        }
        const optional =
          field === 'optionalDependencies' ||
          (field === 'peerDependencies' && node.peerDependenciesMeta?.[name]?.optional === true);
        const key = resolveKey(pkgs, dependent, name);
        if (key === null) {
          if (optional) v.absentOptional++;
          else
            v.unchecked.push(
              `${label}: ${who} declares ${name} ${spec} (${field}) and no installed copy resolves from ${dependent || 'the root'}`
            );
          continue;
        }
        v.edges++;
        const version = versionOf(pkgs, key);
        const sets = parseRange(spec);
        const pv = version === undefined ? null : parseVersion(version);
        if (sets === null || pv === null || pv.prerelease) {
          v.unchecked.push(
            `${label}: ${who} declares ${name} ${spec} (${field}) onto ${key}@${version ?? '(no version)'}: ${sets === null ? 'range not understood' : 'installed version not a stable semver'}, so it was not judged`
          );
          continue;
        }
        if (!rangeAdmits(sets, version as string)) {
          v.findings.push(
            `${label}: ${who} declares ${name} ${spec} (${field}), but ${key} is ${version}`
          );
        }
      }
    }
  }
  return v;
}

/** The npm projects the pins registry's npm-lockfile scope names under `root`, plus every scoped repo whose checkout is absent. */
export function projects(root: string): { projects: Project[]; absentRepos: string[] } {
  const reg = parseRegistry(
    fs.readFileSync(path.join(root, REGISTRY_REL), 'utf8'),
    path.join(root, REGISTRY_REL)
  );
  const out: Project[] = [];
  const absentRepos: string[] = [];
  for (const entry of reg.entries) {
    if (entry.driver !== 'npm') continue;
    for (const sc of entry.scope ?? []) {
      if (sc.scanner !== 'npm-lockfile') continue;
      const base = path.join(root, sc.repo);
      if (!fs.existsSync(base)) {
        absentRepos.push(sc.repo);
        continue;
      }
      for (const pat of sc.files)
        for (const f of globSync(pat, { cwd: base, posix: true }).sort(
          (a, b) => Number(a > b) - Number(a < b)
        )) {
          const abs = path.join(base, path.posix.dirname(f));
          out.push({ dir: path.relative(root, abs).split(path.sep).join('/') || '.', abs });
        }
    }
  }
  return { projects: out, absentRepos };
}

/** The whole gate over `root`. Returns the exit code; writes to `log`/`err`. */
export function run(
  root: string,
  log: (s: string) => void = console.log,
  err: (s: string) => void = console.error
): number {
  let scoped: ReturnType<typeof projects>;
  try {
    scoped = projects(root);
  } catch (e) {
    err(
      `✗ override ranges: could not read the npm project list from ${REGISTRY_REL}: ${(e as Error).message}`
    );
    return 1;
  }
  const { projects: list, absentRepos } = scoped;
  const findings: string[] = [];
  const unchecked: string[] = [];
  let edges = 0;
  let skipped = 0;
  let absentOpt = 0;
  let entries = 0;
  let overridden = 0;
  for (const repo of absentRepos)
    unchecked.push(
      `${repo}: the pins registry scopes npm lockfiles here and the checkout is absent. Fix: git submodule update --init ${repo}`
    );
  for (const p of list) {
    const pj = path.join(p.abs, 'package.json');
    if (!fs.existsSync(pj)) {
      unchecked.push(`${p.dir}: package-lock.json has no package.json beside it`);
      continue;
    }
    const names = overrideNames(
      (JSON.parse(fs.readFileSync(pj, 'utf8')) as { overrides?: unknown }).overrides
    );
    const lock = JSON.parse(fs.readFileSync(path.join(p.abs, 'package-lock.json'), 'utf8')) as {
      packages?: Record<string, LockNode>;
    };
    if (!lock.packages || Object.keys(lock.packages).length === 0) {
      unchecked.push(
        `${p.dir}/package-lock.json: no \`packages\` map (lockfileVersion 1?), nothing to judge`
      );
      continue;
    }
    entries += Object.keys(lock.packages).length;
    overridden += names.size;
    const v = judge(
      p.dir === '.' ? 'package-lock.json' : `${p.dir}/package-lock.json`,
      lock.packages,
      names
    );
    findings.push(...v.findings);
    unchecked.push(...v.unchecked);
    edges += v.edges;
    skipped += v.skippedSpecs;
    absentOpt += v.absentOptional;
  }
  const shape =
    `${list.length} lockfile(s), ${entries} entries, ${overridden} override name(s), ` +
    `${edges} edge(s) judged, ${skipped} non-registry spec(s) skipped, ${absentOpt} absent optional edge(s)`;
  if (list.length === 0) {
    err(
      `✗ override ranges: the pins registry's npm-lockfile scope matched no lockfile under ${root}; the gate is not seeing the tree and its green would mean nothing`
    );
    for (const u of unchecked) err(`  UNCHECKED ${u}`);
    return 1;
  }
  if (findings.length > 0) {
    err(
      `✗ override ranges: ${findings.length} edge(s) resolve outside the range the dependent declares:`
    );
    for (const f of findings) err(`  ${f}`);
    err(
      '  npm accepted the override in place of that range, so npm ls stays green. Fix: raise the override floor in package.json `overrides` (and its _overridesReasons entry) to the highest range a dependent declares, then move the lock with `npm run pins -- bump <id>` or `npm run pins -- lockfiles`. Do not widen the gate.'
    );
  }
  if (unchecked.length > 0) {
    err(
      `✗ override ranges: ${unchecked.length} edge(s) or project(s) UNCHECKED, which is not a pass:`
    );
    for (const u of unchecked) err(`  UNCHECKED ${u}`);
  }
  if (findings.length > 0 || unchecked.length > 0) {
    err(`  (${shape})`);
    return 1;
  }
  log(
    `✓ override ranges: every edge onto an overridden package resolves inside its declared range (${shape})`
  );
  return 0;
}

// ---- selftest ---------------------------------------------------------------------------

function selftest(): number {
  let failed = 0;
  const check = (name: string, ok: boolean): void => {
    console.log(`${ok ? '  PASS' : '  FAIL'} ${name}`);
    if (!ok) failed++;
  };

  check('overrideKeyName: plain', overrideKeyName('qs') === 'qs');
  check(
    'overrideKeyName: name@range',
    overrideKeyName('brace-expansion@^5.0.5') === 'brace-expansion'
  );
  check('overrideKeyName: scoped', overrideKeyName('@hono/node-server') === '@hono/node-server');
  check('overrideKeyName: scoped@range', overrideKeyName('@s/x@>=1') === '@s/x');
  const names = overrideNames({
    qs: '>=6',
    'gray-matter': { '.': '4', 'js-yaml': '^3' },
    'b@^5': '5',
  });
  check(
    'overrideNames: nested keys count, `.` does not',
    [...names].sort((a, b) => Number(a > b) - Number(a < b)).join(',') ===
      'b,gray-matter,js-yaml,qs'
  );
  check('isNonRegistrySpec: npm alias', isNonRegistrySpec('npm:qs@^6'));
  check('isNonRegistrySpec: user/repo', isNonRegistrySpec('user/repo'));
  check('isNonRegistrySpec: a range is a range', !isNonRegistrySpec('^6.16.1 || >=7'));

  const N = new Set(['qs', 'p']);
  // MUST FIRE: the body-parser case.
  const red = judge(
    'L',
    {
      '': { dependencies: { 'body-parser': '^2' } },
      'node_modules/body-parser': { version: '2.4.0', dependencies: { qs: '^6.16.1' } },
      'node_modules/qs': { version: '6.16.0' },
    },
    N
  );
  check(
    'judge: a dependent range the override undercuts fires',
    red.findings.length === 1 && red.edges === 1
  );
  // MUST NOT FIRE: satisfied.
  const green = judge(
    'L',
    {
      'node_modules/body-parser': { version: '2.4.0', dependencies: { qs: '^6.16.1' } },
      'node_modules/qs': { version: '6.16.1' },
    },
    N
  );
  check(
    'judge: a satisfied edge does not fire',
    green.findings.length === 0 && green.unchecked.length === 0 && green.edges === 1
  );
  // MUST NOT FIRE: a name that is not overridden, even when unsatisfied.
  const other = judge(
    'L',
    {
      'node_modules/a': { version: '1.0.0', dependencies: { z: '^9' } },
      'node_modules/z': { version: '1.0.0' },
    },
    N
  );
  check(
    'judge: an edge onto a name nobody overrides is out of scope',
    other.findings.length === 0 && other.edges === 0
  );
  // Nearest copy wins, both directions.
  const nestedOk = judge(
    'L',
    {
      'node_modules/a': { version: '1.0.0', dependencies: { qs: '^6.16.1' } },
      'node_modules/a/node_modules/qs': { version: '6.16.2' },
      'node_modules/qs': { version: '6.0.0' },
    },
    N
  );
  check(
    'judge: a nested satisfying copy shadows a hoisted bad one',
    nestedOk.findings.length === 0 && nestedOk.edges === 1
  );
  const nestedBad = judge(
    'L',
    {
      'node_modules/a': { version: '1.0.0', dependencies: { qs: '^6.16.1' } },
      'node_modules/a/node_modules/qs': { version: '6.0.0' },
      'node_modules/qs': { version: '6.16.2' },
    },
    N
  );
  check(
    'judge: a nested bad copy fires even with a good hoisted one',
    nestedBad.findings.length === 1
  );
  const deep = judge(
    'L',
    {
      'node_modules/a/node_modules/b': { version: '1.0.0', dependencies: { qs: '^6.16.1' } },
      'node_modules/a/node_modules/qs': { version: '6.0.0' },
    },
    N
  );
  check('judge: resolution walks up past the dependent to its parent', deep.findings.length === 1);
  const ws = judge(
    'L',
    {
      'packages/cli': { version: '0.0.0', dependencies: { qs: '^6.16.1' } },
      'node_modules/qs': { version: '6.0.0' },
    },
    N
  );
  check('judge: a workspace path resolves to the root node_modules', ws.findings.length === 1);
  // Optional peers.
  const absentPeer = judge(
    'L',
    {
      'node_modules/a': {
        version: '1.0.0',
        peerDependencies: { p: '^2' },
        peerDependenciesMeta: { p: { optional: true } },
      },
    },
    N
  );
  check(
    'judge: an absent optional peer is no edge',
    absentPeer.findings.length === 0 &&
      absentPeer.unchecked.length === 0 &&
      absentPeer.absentOptional === 1
  );
  const presentPeer = judge(
    'L',
    {
      'node_modules/a': {
        version: '1.0.0',
        peerDependencies: { p: '^2' },
        peerDependenciesMeta: { p: { optional: true } },
      },
      'node_modules/p': { version: '1.9.0' },
    },
    N
  );
  check(
    'judge: an INSTALLED optional peer outside its range fires',
    presentPeer.findings.length === 1
  );
  const missingReq = judge(
    'L',
    { 'node_modules/a': { version: '1.0.0', dependencies: { qs: '^6' } } },
    N
  );
  check(
    'judge: a required edge with no installed copy is UNCHECKED, not a pass',
    missingReq.unchecked.length === 1
  );
  // Links, skipped specs, unknowns.
  const linked = judge(
    'L',
    {
      'node_modules/a': { version: '1.0.0', dependencies: { p: '^2.1.0' } },
      'node_modules/p': { link: true, resolved: 'packages/p' },
      'packages/p': { version: '2.0.0' },
    },
    N
  );
  check('judge: a link is followed to its target version', linked.findings.length === 1);
  const alias = judge(
    'L',
    {
      'node_modules/a': { version: '1.0.0', dependencies: { qs: 'npm:other@^1' } },
      'node_modules/qs': { version: '6.0.0' },
    },
    N
  );
  check(
    'judge: an npm: alias is skipped and counted',
    alias.findings.length === 0 && alias.skippedSpecs === 1
  );
  const weird = judge(
    'L',
    {
      'node_modules/a': { version: '1.0.0', dependencies: { qs: '1.0.0 - 2.0.0' } },
      'node_modules/qs': { version: '6.0.0' },
    },
    N
  );
  check(
    'judge: a range the parser cannot read is UNCHECKED',
    weird.unchecked.length === 1 && weird.findings.length === 0
  );
  const pre = judge(
    'L',
    {
      'node_modules/a': { version: '1.0.0', dependencies: { qs: '^6' } },
      'node_modules/qs': { version: '6.1.0-rc.1' },
    },
    N
  );
  check(
    'judge: a prerelease installed version is UNCHECKED',
    pre.unchecked.length === 1 && pre.findings.length === 0
  );

  // END TO END through run(): the registry read, the scope glob, the project's own overrides.
  const real = JSON.parse(fs.readFileSync(path.join(REPO, REGISTRY_REL), 'utf8')) as {
    entries: Record<string, unknown>[];
  };
  const mk = (qs: string, extraScope: Record<string, unknown>[] = []): string => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'override-ranges-'));
    const reg = {
      ...real,
      entries: real.entries
        .filter((e) => e.driver === 'npm')
        .map((e) => ({
          ...e,
          scope: [
            {
              scanner: 'npm-lockfile',
              repo: '.',
              files: ['package-lock.json', 'workers/*/package-lock.json'],
            },
            ...extraScope,
          ],
        })),
    };
    fs.mkdirSync(path.join(dir, '.ci/config'), { recursive: true });
    fs.writeFileSync(path.join(dir, REGISTRY_REL), JSON.stringify(reg));
    fs.writeFileSync(
      path.join(dir, 'package.json'),
      JSON.stringify({ overrides: { qs: '>=6.16.0' } })
    );
    fs.writeFileSync(
      path.join(dir, 'package-lock.json'),
      JSON.stringify({
        lockfileVersion: 3,
        packages: {
          '': { dependencies: { 'body-parser': '^2' } },
          'node_modules/body-parser': { version: '2.4.0', dependencies: { qs: '^6.16.1' } },
          'node_modules/qs': { version: qs },
        },
      })
    );
    fs.mkdirSync(path.join(dir, 'workers/w'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'workers/w/package.json'), '{}');
    fs.writeFileSync(
      path.join(dir, 'workers/w/package-lock.json'),
      JSON.stringify({ packages: { '': {} } })
    );
    return dir;
  };
  const quiet = (): void => {};
  const out: string[] = [];
  const redRoot = mk('6.16.0');
  check(
    'run: the red fixture (qs 6.16.0 under body-parser ^6.16.1) exits 1',
    run(redRoot, quiet, (s) => out.push(s)) === 1
  );
  check(
    'run: and names the edge',
    out.some((s) => s.includes('body-parser@2.4.0 declares qs ^6.16.1'))
  );
  const greenLines: string[] = [];
  const greenRoot = mk('6.16.1');
  check('run: the green fixture exits 0', run(greenRoot, (s) => greenLines.push(s), quiet) === 0);
  check(
    'run: the green line prints the shape (2 lockfiles, 1 edge)',
    greenLines.some((s) => s.includes('2 lockfile(s)') && s.includes('1 edge(s) judged'))
  );
  const absentRoot = mk('6.16.1', [
    { scanner: 'npm-lockfile', repo: 'private/account', files: ['package-lock.json'] },
  ]);
  check('run: a scoped repo whose checkout is absent exits 1', run(absentRoot, quiet, quiet) === 1);
  const emptyRoot = mk('6.16.1');
  fs.rmSync(path.join(emptyRoot, 'package-lock.json'));
  fs.rmSync(path.join(emptyRoot, 'workers'), { recursive: true });
  check('run: zero lockfiles is a FAILURE, never a pass', run(emptyRoot, quiet, quiet) === 1);
  for (const d of [redRoot, greenRoot, absentRoot, emptyRoot])
    fs.rmSync(d, { recursive: true, force: true });

  console.log(
    failed === 0
      ? '✓ override ranges selftest: all cases pass'
      : `✗ override ranges selftest: ${failed} case(s) failed`
  );
  return failed === 0 ? 0 : 1;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return selftest();
  const at = argv.indexOf('--root');
  if (at >= 0 && argv[at + 1] === undefined) {
    console.error('✗ --root needs a directory');
    return 1;
  }
  return run(at >= 0 ? path.resolve(argv[at + 1] as string) : REPO);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main(process.argv.slice(2)));
}
