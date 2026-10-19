/**
 * The pin registry: `.ci/config/pins.json`, the one list of every pinned version in the
 * console and its scanned submodules, and where each one is written.
 *
 * WHY ONE FILE. Before it, a pin's sites were restated by each tool that touched it: the
 * embed inventory in embed-asset-sources.ts, the devcontainer inventory in
 * devcontainer-pin-sources.ts, the Go constants in embed-pin-upgrade.ts SOURCE_CONSTS and
 * the Leap pin's three files in renet_pkg_matrix.py PIN_SITES. Each list was complete only
 * by the care of whoever last edited it, and nothing could ask whether a pin existed that no
 * list named. Those four are readers of this file now, and `check:ci-pin-registry` asks the
 * reverse question over the whole tree (agent/plans/PLAN-pins-command.md Design 1 and 2).
 *
 * THE SHAPE. An entry is a `family` (a scope of scanner hits whose members its driver
 * enumerates: every package-lock.json, every `uses:` line) or a `leaf` (one pin, written at
 * the `sites` listed). A site is `{repo, file}` plus exactly one locator:
 *   arg    a Dockerfile `ARG <NAME>=<value>` line
 *   env    a `<NAME>=<value>` line (toolchain.env)
 *   json   a JSON pointer into the file (a *.lock.json pin record)
 *   match  an anchored regex with a named `value` group
 * and an `expect` count: the number of times the locator must match, so a site that moved
 * (zero) or was duplicated (two) is a finding rather than a silent partial bump. `role`
 * groups the sites whose captured values must agree (`version`, `sha256:<arch>`, `commit`).
 *
 * THIS MODULE IS PURE apart from `loadRegistry`'s one read. Validation reports EVERY
 * problem by field path (`entries[3] (embed:k3s).sites[0].expect: ...`), so a malformed
 * edit names the field to fix rather than failing on the first one. The completeness checks
 * that need the tree live in scripts/gates/check-pin-registry.ts.
 *
 * Usage:
 *   npx tsx scripts/lib/pins/registry.ts             # load, validate, print the shape
 *   npx tsx scripts/lib/pins/registry.ts --selftest  # the loader's controls
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { type ControlCase, runControls } from '../controls.js';
import { envRoot } from '../repo-root.js';

/** The scanners of check:ci-pin-registry. An ignore names one of these, or `literal`. */
export const SCANNERS = [
  'dockerfile-arg',
  'toolchain-env',
  'shell-const',
  'from-image',
  'action-uses',
  'npm-lockfile',
  'go-mod',
  'pin-lock-json',
  'ceph-pin',
] as const;
export type ScannerId = (typeof SCANNERS)[number];

/** Where a driver reads the newest release. `none` must carry a BLOCKER reason. */
export const SOURCE_TYPES = [
  'npm-registry',
  'go-list',
  'go-dl',
  'github-release',
  'github-tags',
  'pypi',
  'obs-repomd',
  'quay-tags',
  'dockerhub',
  'rsync-index',
  'none',
] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];

export const DRIVERS = [
  'npm',
  'go-mod',
  'actions',
  'docker',
  'embed',
  'devcontainer',
  'toolchain',
  'os-ceph-host',
  'ceph-image',
  'real-provider',
  'breakpoint',
] as const;
export type Driver = (typeof DRIVERS)[number];

export const SAFETY_MODES = ['release-age', 'mirror-tag', 'same-host-version', 'assisted'] as const;
export const MAJOR_MODES = ['refuse', 'allow-file', 'assisted'] as const;

export interface PinSource {
  type: SourceType;
  /** owner/repo, for github-release and github-tags. */
  repo?: string;
  /** Release-tag prefix stripped to yield the pinned value (`cli-v`, `gopls/v`). */
  tagPrefix?: string;
  /** Package name, for npm-registry and pypi. */
  package?: string;
  /** Module path, for go-list. */
  module?: string;
  /** Image repository, for dockerhub and quay-tags. */
  image?: string;
  /** Required for `none`: why no source is read, as a `BLOCKER:` line. */
  reason?: string;
}

export interface PinSite {
  /** `.` for the console, or a scanned submodule path such as `private/renet`. */
  repo: string;
  /** Path relative to `repo`. */
  file: string;
  role: string;
  expect: number;
  /** How a human names this site in a message (renet_pkg_matrix's OBS REBUILT line). */
  label?: string;
  /** Release-asset filename for a `sha256:<arch>` site, `{version}` substituted when present. */
  asset?: string;
  arg?: string;
  env?: string;
  json?: string;
  match?: string;
}

export interface PinScope {
  scanner: ScannerId;
  repo: string;
  /** Globs relative to `repo`: `*` within a segment, `**` across segments. */
  files: string[];
}

export interface RepoPath {
  repo: string;
  file: string;
}

export interface PinDerive {
  run: string;
  cwd: string;
  writes: RepoPath[];
}

export interface PinLiteral {
  /** A context regex with a named `value` group; an occurrence equal to the pin's current version must sit at a site, a derive output or an ignore. */
  re: string;
}

export interface PinEntry {
  id: string;
  kind: 'family' | 'leaf';
  name: string;
  driver: Driver;
  source: PinSource;
  safety: {
    mode: (typeof SAFETY_MODES)[number];
    major: (typeof MAJOR_MODES)[number];
  };
  /** Hold files (blocklists, baselines) relative to the console root. */
  holds: string[];
  /** Manifest gate ids that judge this pin. */
  gates: string[];
  scope?: PinScope[];
  sites: PinSite[];
  derive: PinDerive[];
  literals: PinLiteral[];
  /**
   * The Go module whose go.mod a devcontainer pin installed with `go install` is built from
   * (`golang.org/x/tools/gopls`). A release whose `go` directive is newer than the image's
   * GO_VERSION (.devcontainer/toolchain.env, built with GOTOOLCHAIN=local) cannot build there, so
   * the devcontainer driver and the freshness gate do not offer it (worklist #e023eb0d).
   */
  goModule?: string;
}

export interface PinIgnore {
  scanner: ScannerId | 'literal';
  repo: string;
  file: string;
  /** Regex over the hit's line; absent means every hit of that scanner in the file. */
  match?: string;
  reason: string;
}

export interface PinExclude {
  repo: string;
  glob: string;
  reason: string;
}

export interface PinRegistry {
  version: 1;
  submodules: {
    scanned: string[];
    unscanned: Array<{ path: string; reason: string }>;
  };
  literalExclude: PinExclude[];
  entries: PinEntry[];
  ignores: PinIgnore[];
}

/** The registry the readers load: the console's own, unless PINS_ROOT (a selftest fixture) moves the root. */
export const registryPath = (): string => path.join(envRoot('PINS_ROOT'), '.ci/config/pins.json');

export class RegistryError extends Error {
  constructor(
    readonly file: string,
    readonly problems: string[]
  ) {
    super(`${file}: ${problems.length} problem(s)\n${problems.map((p) => `  - ${p}`).join('\n')}`);
    this.name = 'RegistryError';
  }
}

const ID = /^[a-z0-9][a-z0-9-]*(:[a-z0-9][a-z0-9.+-]*)?$/;
const ROLE = /^[a-z][a-z0-9-]*(:[a-z0-9-]+)?$/;
const NAME = /^[A-Z][A-Z0-9_]*$/;
const GH_REPO = /^[\w.-]+\/[\w.-]+$/;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Compile a registry regex the way every reader does: multi-line, so `^` and `$` anchor lines. */
export function compile(source: string, flags = 'gm'): RegExp {
  return new RegExp(source, flags);
}

function regexProblem(source: unknown, needValue: boolean): string | null {
  if (typeof source !== 'string' || source === '') return 'must be a non-empty regex string';
  try {
    compile(source);
  } catch (err) {
    return `does not compile (${(err as Error).message})`;
  }
  if (needValue && !source.includes('(?<value>')) return 'must capture a named `value` group';
  return null;
}

const relPathProblem = (v: unknown): string | null =>
  typeof v !== 'string' || v === ''
    ? 'must be a non-empty path'
    : path.isAbsolute(v) || v.split('/').includes('..')
      ? `must be relative and stay inside its repo, got ${JSON.stringify(v)}`
      : null;

const blockerProblem = (v: unknown): string | null =>
  typeof v !== 'string' || !/^BLOCKER: \S/.test(v)
    ? 'must be a reason line starting `BLOCKER: `'
    : null;

/**
 * Validate a parsed pins.json. Returns every problem, each prefixed with its field path;
 * an empty list means `raw` is a PinRegistry.
 */
export function registryProblems(raw: unknown): string[] {
  const out: string[] = [];
  const bad = (field: string, why: string): void => {
    out.push(`${field}: ${why}`);
  };
  if (!isObj(raw)) return ['(root): must be a JSON object'];
  if (raw.version !== 1) bad('version', `must be 1, got ${JSON.stringify(raw.version)}`);

  const repos = new Set<string>(['.']);
  const subs = raw.submodules;
  if (!isObj(subs)) bad('submodules', 'must be an object with `scanned` and `unscanned`');
  else {
    if (!Array.isArray(subs.scanned)) bad('submodules.scanned', 'must be an array of paths');
    else
      subs.scanned.forEach((s, i) => {
        if (typeof s !== 'string' || !/^private\/[\w.-]+$/.test(s))
          bad(`submodules.scanned[${i}]`, 'must be a `private/<name>` path');
        else repos.add(s);
      });
    if (!Array.isArray(subs.unscanned)) bad('submodules.unscanned', 'must be an array');
    else
      subs.unscanned.forEach((s, i) => {
        if (!isObj(s) || typeof s.path !== 'string')
          bad(`submodules.unscanned[${i}].path`, 'must be a submodule path');
        else {
          const why = blockerProblem(s.reason);
          if (why) bad(`submodules.unscanned[${i}].reason`, why);
        }
      });
  }
  const repoProblem = (v: unknown): string | null =>
    typeof v === 'string' && repos.has(v)
      ? null
      : `must be "." or a submodules.scanned path, got ${JSON.stringify(v)}`;

  if (!Array.isArray(raw.literalExclude)) bad('literalExclude', 'must be an array');
  else
    raw.literalExclude.forEach((x, i) => {
      const f = `literalExclude[${i}]`;
      if (!isObj(x)) return bad(f, 'must be an object');
      const r = repoProblem(x.repo);
      if (r) bad(`${f}.repo`, r);
      if (typeof x.glob !== 'string' || x.glob === '') bad(`${f}.glob`, 'must be a glob');
      const why = blockerProblem(x.reason);
      if (why) bad(`${f}.reason`, why);
    });

  if (!Array.isArray(raw.entries) || raw.entries.length === 0) {
    bad('entries', 'must be a non-empty array');
  } else {
    const seen = new Set<string>();
    raw.entries.forEach((e, i) => {
      const at = isObj(e) && typeof e.id === 'string' ? `entries[${i}] (${e.id})` : `entries[${i}]`;
      if (!isObj(e)) return bad(at, 'must be an object');
      if (typeof e.id !== 'string' || !ID.test(e.id))
        bad(`${at}.id`, 'must match <kind>[:<name>] in lowercase, e.g. embed:k3s');
      else if (seen.has(e.id)) bad(`${at}.id`, 'is a duplicate');
      else seen.add(e.id);
      if (e.kind !== 'family' && e.kind !== 'leaf') bad(`${at}.kind`, 'must be family or leaf');
      if (typeof e.name !== 'string' || e.name === '') bad(`${at}.name`, 'must be a display name');
      if (!(DRIVERS as readonly unknown[]).includes(e.driver))
        bad(`${at}.driver`, `must be one of ${DRIVERS.join(', ')}`);

      const src = e.source;
      if (!isObj(src)) bad(`${at}.source`, 'must be an object with a `type`');
      else {
        if (!(SOURCE_TYPES as readonly unknown[]).includes(src.type))
          bad(`${at}.source.type`, `must be one of ${SOURCE_TYPES.join(', ')}`);
        if (src.type === 'none') {
          const why = blockerProblem(src.reason);
          if (why) bad(`${at}.source.reason`, `source none ${why}`);
        }
        if (
          (src.type === 'github-release' || src.type === 'github-tags') &&
          (typeof src.repo !== 'string' || !GH_REPO.test(src.repo))
        )
          bad(`${at}.source.repo`, `${String(src.type)} needs an owner/repo`);
        if (
          (src.type === 'npm-registry' || src.type === 'pypi') &&
          (typeof src.package !== 'string' || src.package === '')
        )
          bad(`${at}.source.package`, `${String(src.type)} needs a package name`);
        if (src.type === 'go-list' && (typeof src.module !== 'string' || src.module === ''))
          bad(`${at}.source.module`, 'go-list needs a module path');
        for (const k of ['repo', 'tagPrefix', 'package', 'module', 'image', 'reason'])
          if (src[k] !== undefined && typeof src[k] !== 'string')
            bad(`${at}.source.${k}`, 'must be a string');
      }

      const safety = e.safety;
      if (!isObj(safety)) bad(`${at}.safety`, 'must be an object with `mode` and `major`');
      else {
        if (!(SAFETY_MODES as readonly unknown[]).includes(safety.mode))
          bad(`${at}.safety.mode`, `must be one of ${SAFETY_MODES.join(', ')}`);
        if (!(MAJOR_MODES as readonly unknown[]).includes(safety.major))
          bad(`${at}.safety.major`, `must be one of ${MAJOR_MODES.join(', ')}`);
      }
      if (e.goModule !== undefined) {
        if (
          typeof e.goModule !== 'string' ||
          !/^[a-z0-9.-]+\.[a-z]+(?:\/[A-Za-z0-9._~-]+)+$/.test(e.goModule)
        )
          bad(`${at}.goModule`, 'must be a Go module path, e.g. golang.org/x/tools/gopls');
        else if (e.driver !== 'devcontainer')
          bad(
            `${at}.goModule`,
            'only a devcontainer pin installed with `go install` names a goModule'
          );
      }
      for (const k of ['holds', 'gates'] as const) {
        const v = e[k];
        if (!Array.isArray(v) || v.some((x) => typeof x !== 'string' || x === ''))
          bad(`${at}.${k}`, 'must be an array of non-empty strings');
      }

      if (e.kind === 'family') {
        if (!Array.isArray(e.scope) || e.scope.length === 0)
          bad(`${at}.scope`, 'a family needs a non-empty scope');
        else
          e.scope.forEach((s, j) => {
            const f = `${at}.scope[${j}]`;
            if (!isObj(s)) return bad(f, 'must be an object');
            if (!(SCANNERS as readonly unknown[]).includes(s.scanner))
              bad(`${f}.scanner`, `must be one of ${SCANNERS.join(', ')}`);
            const r = repoProblem(s.repo);
            if (r) bad(`${f}.repo`, r);
            if (
              !Array.isArray(s.files) ||
              s.files.length === 0 ||
              s.files.some((g) => typeof g !== 'string' || g === '')
            )
              bad(`${f}.files`, 'must be a non-empty array of globs');
          });
      } else if (e.scope !== undefined) bad(`${at}.scope`, 'only a family has a scope');

      if (!Array.isArray(e.sites)) bad(`${at}.sites`, 'must be an array');
      else {
        if (e.kind === 'leaf' && e.sites.length === 0) bad(`${at}.sites`, 'a leaf needs a site');
        e.sites.forEach((s, j) => {
          const f = `${at}.sites[${j}]`;
          if (!isObj(s)) return bad(f, 'must be an object');
          const r = repoProblem(s.repo);
          if (r) bad(`${f}.repo`, r);
          const p = relPathProblem(s.file);
          if (p) bad(`${f}.file`, p);
          if (typeof s.role !== 'string' || !ROLE.test(s.role))
            bad(`${f}.role`, 'must be a role such as version, commit or sha256:amd64');
          if (typeof s.expect !== 'number' || !Number.isInteger(s.expect) || s.expect < 1)
            bad(`${f}.expect`, `must be a positive integer, got ${JSON.stringify(s.expect)}`);
          const locators = ['arg', 'env', 'json', 'match'].filter((k) => s[k] !== undefined);
          if (locators.length !== 1)
            bad(
              f,
              `needs exactly one of arg, env, json, match (has ${locators.join(', ') || 'none'})`
            );
          for (const k of ['arg', 'env'])
            if (s[k] !== undefined && (typeof s[k] !== 'string' || !NAME.test(s[k] as string)))
              bad(`${f}.${k}`, 'must be an UPPER_SNAKE variable name');
          if (s.json !== undefined && (typeof s.json !== 'string' || !s.json.startsWith('/')))
            bad(`${f}.json`, 'must be a JSON pointer starting with /');
          if (s.match !== undefined) {
            const why = regexProblem(s.match, true);
            if (why) bad(`${f}.match`, why);
          }
          if (s.label !== undefined && (typeof s.label !== 'string' || s.label === ''))
            bad(`${f}.label`, 'must be a non-empty string');
          if (s.asset !== undefined && (typeof s.asset !== 'string' || s.asset === ''))
            bad(`${f}.asset`, 'must be a release-asset filename template');
        });
      }

      if (!Array.isArray(e.derive)) bad(`${at}.derive`, 'must be an array');
      else
        e.derive.forEach((d, j) => {
          const f = `${at}.derive[${j}]`;
          if (!isObj(d)) return bad(f, 'must be an object');
          if (typeof d.run !== 'string' || d.run === '') bad(`${f}.run`, 'must be a command');
          if (typeof d.cwd !== 'string' || d.cwd === '') bad(`${f}.cwd`, 'must be a directory');
          if (!Array.isArray(d.writes) || d.writes.length === 0)
            bad(`${f}.writes`, 'must list the files the step writes');
          else
            d.writes.forEach((w, k) => {
              if (!isObj(w)) return bad(`${f}.writes[${k}]`, 'must be {repo, file}');
              const r = repoProblem(w.repo);
              if (r) bad(`${f}.writes[${k}].repo`, r);
              const p = relPathProblem(w.file);
              if (p) bad(`${f}.writes[${k}].file`, p);
            });
        });

      if (!Array.isArray(e.literals)) bad(`${at}.literals`, 'must be an array');
      else
        e.literals.forEach((l, j) => {
          const why = isObj(l) ? regexProblem(l.re, true) : 'must be {re}';
          if (why) bad(`${at}.literals[${j}].re`, why);
        });
    });
  }

  if (!Array.isArray(raw.ignores)) bad('ignores', 'must be an array');
  else
    raw.ignores.forEach((g, i) => {
      const f = `ignores[${i}]`;
      if (!isObj(g)) return bad(f, 'must be an object');
      if (g.scanner !== 'literal' && !(SCANNERS as readonly unknown[]).includes(g.scanner))
        bad(`${f}.scanner`, `must be literal or one of ${SCANNERS.join(', ')}`);
      const r = repoProblem(g.repo);
      if (r) bad(`${f}.repo`, r);
      const p = relPathProblem(g.file);
      if (p) bad(`${f}.file`, p);
      if (g.match !== undefined) {
        const why = regexProblem(g.match, false);
        if (why) bad(`${f}.match`, why);
      }
      const why = blockerProblem(g.reason);
      if (why) bad(`${f}.reason`, why);
    });
  return out;
}

/** Parse and validate registry text; throws RegistryError naming every problem. */
export function parseRegistry(text: string, file: string): PinRegistry {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (err) {
    throw new RegistryError(file, [`(root): not JSON (${(err as Error).message})`]);
  }
  const problems = registryProblems(raw);
  if (problems.length > 0) throw new RegistryError(file, problems);
  return raw as PinRegistry;
}

const memo = new Map<string, PinRegistry>();

/** Load the registry, validated, once per process per file. */
export function loadRegistry(file: string = registryPath()): PinRegistry {
  const hit = memo.get(file);
  if (hit) return hit;
  const reg = parseRegistry(fs.readFileSync(file, 'utf8'), file);
  memo.set(file, reg);
  return reg;
}

const esc = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * The regex a line-based site matches, with a `value` group; null for a `json` site.
 * `arg` and `env` are shorthands, so the common Dockerfile and toolchain.env sites carry
 * no hand-written regex to get wrong.
 */
export function siteRegex(site: PinSite, flags = 'gm'): RegExp | null {
  if (site.arg !== undefined) return compile(`^ARG\\s+${esc(site.arg)}=(?<value>\\S+)`, flags);
  if (site.env !== undefined) return compile(`^${esc(site.env)}=(?<value>\\S*)$`, flags);
  if (site.match !== undefined) return compile(site.match, flags);
  return null;
}

/** Resolve an RFC 6901 pointer; undefined when any step is absent (own properties only). */
export function jsonPointer(doc: unknown, pointer: string): unknown {
  let cur: unknown = doc;
  for (const raw of pointer.split('/').slice(1)) {
    const key = raw.replace(/~1/g, '/').replace(/~0/g, '~');
    if (Array.isArray(cur) && /^\d+$/.test(key)) cur = cur[Number(key)];
    else if (isObj(cur) && Object.hasOwn(cur, key)) cur = cur[key];
    else return undefined;
  }
  return cur;
}

export interface SiteMatch {
  value: string;
  /** 1-based line of the match start; 0 for a json site. */
  line: number;
  /** Lines the match spans, inclusive. */
  lastLine: number;
}

/** Every match of a site in `text`. A json site yields one match when the pointer resolves to a string. */
export function siteMatches(site: PinSite, text: string): SiteMatch[] {
  if (site.json !== undefined) {
    let doc: unknown;
    try {
      doc = JSON.parse(text);
    } catch {
      return [];
    }
    const v = jsonPointer(doc, site.json);
    return typeof v === 'string' ? [{ value: v, line: 0, lastLine: 0 }] : [];
  }
  const re = siteRegex(site) as RegExp;
  const out: SiteMatch[] = [];
  for (const m of text.matchAll(re)) {
    const start = m.index ?? 0;
    const line = text.slice(0, start).split('\n').length;
    const lastLine = line + m[0].split('\n').length - 1;
    out.push({ value: m.groups?.value ?? '', line, lastLine });
  }
  return out;
}

/** Entries a driver reads, in registry order. */
export const entriesFor = (reg: PinRegistry, driver: Driver): PinEntry[] =>
  reg.entries.filter((e) => e.driver === driver);

/** The part of an id after `<kind>:`. */
export const idName = (e: PinEntry): string => e.id.slice(e.id.indexOf(':') + 1);

// ---- selftest -----------------------------------------------------------------------------

/** A minimal valid registry; each control breaks exactly one field of a copy of it. */
function validFixture(): Obj {
  return {
    version: 1,
    submodules: { scanned: ['private/renet'], unscanned: [] },
    literalExclude: [],
    entries: [
      {
        id: 'embed:zot',
        kind: 'leaf',
        name: 'zot',
        driver: 'embed',
        source: { type: 'github-release', repo: 'project-zot/zot' },
        safety: { mode: 'release-age', major: 'assisted' },
        holds: [],
        gates: ['check:ci-embed-asset-freshness'],
        sites: [
          {
            repo: 'private/renet',
            file: 'Dockerfile',
            role: 'version',
            arg: 'ZOT_VERSION',
            expect: 2,
          },
        ],
        derive: [],
        literals: [],
      },
      {
        id: 'npm',
        kind: 'family',
        name: 'npm trees',
        driver: 'npm',
        source: { type: 'npm-registry', package: '*' },
        safety: { mode: 'release-age', major: 'allow-file' },
        holds: [],
        gates: ['check:deps'],
        scope: [{ scanner: 'npm-lockfile', repo: '.', files: ['package-lock.json'] }],
        sites: [],
        derive: [],
        literals: [],
      },
    ],
    ignores: [],
  };
}

export function selftestCases(): ControlCase[] {
  const cases: ControlCase[] = [];
  const clone = (): Obj => JSON.parse(JSON.stringify(validFixture())) as Obj;
  const leaf = (r: Obj): Obj => (r.entries as Obj[])[0];
  const site = (r: Obj): Obj => (leaf(r).sites as Obj[])[0];

  const control = registryProblems(validFixture());
  cases.push({
    name: 'CONTROL: the valid fixture has no problems',
    ok: control.length === 0,
    detail: control.join('; '),
  });

  const breaks: [string, (r: Obj) => void, string][] = [
    ['version', (r) => (r.version = 2), 'version:'],
    ['entries empty', (r) => (r.entries = []), 'entries:'],
    ['id', (r) => (leaf(r).id = 'Embed:Zot'), '.id:'],
    ['duplicate id', (r) => ((r.entries as Obj[])[1].id = 'embed:zot'), 'is a duplicate'],
    ['kind', (r) => (leaf(r).kind = 'branch'), '.kind:'],
    ['driver', (r) => (leaf(r).driver = 'apt'), '.driver:'],
    ['source.type', (r) => ((leaf(r).source as Obj).type = 'ftp'), '.source.type:'],
    ['source none without reason', (r) => (leaf(r).source = { type: 'none' }), '.source.reason:'],
    ['github source without repo', (r) => delete (leaf(r).source as Obj).repo, '.source.repo:'],
    ['safety.mode', (r) => ((leaf(r).safety as Obj).mode = 'yolo'), '.safety.mode:'],
    ['safety.major', (r) => ((leaf(r).safety as Obj).major = 'yes'), '.safety.major:'],
    ['gates', (r) => (leaf(r).gates = [1]), '.gates:'],
    ['goModule not a module path', (r) => (leaf(r).goModule = 'gopls'), '.goModule:'],
    [
      'goModule on a non-devcontainer pin',
      (r) => (leaf(r).goModule = 'golang.org/x/tools/gopls'),
      'only a devcontainer pin',
    ],
    ['leaf with no site', (r) => (leaf(r).sites = []), 'a leaf needs a site'],
    ['leaf with a scope', (r) => (leaf(r).scope = []), 'only a family has a scope'],
    ['family with no scope', (r) => delete (r.entries as Obj[])[1].scope, 'a family needs'],
    ['site.repo', (r) => (site(r).repo = 'private/nope'), '.sites[0].repo:'],
    ['site.file escapes', (r) => (site(r).file = '../x'), '.sites[0].file:'],
    ['site.role', (r) => (site(r).role = 'Version'), '.sites[0].role:'],
    ['site.expect zero', (r) => (site(r).expect = 0), '.sites[0].expect:'],
    ['site two locators', (r) => (site(r).env = 'ZOT_VERSION'), 'needs exactly one of'],
    ['site no locator', (r) => delete site(r).arg, 'needs exactly one of'],
    [
      'site.match without value group',
      (r) => {
        delete site(r).arg;
        site(r).match = '^ARG ZOT_VERSION=(\\S+)';
      },
      '.sites[0].match:',
    ],
    [
      'site.match not a regex',
      (r) => {
        delete site(r).arg;
        site(r).match = '(?<value>[';
      },
      'does not compile',
    ],
    [
      'site.json not a pointer',
      (r) => {
        delete site(r).arg;
        site(r).json = 'components.zot';
      },
      '.sites[0].json:',
    ],
    ['site.asset empty', (r) => (site(r).asset = ''), '.sites[0].asset:'],
    [
      'derive without writes',
      (r) => (leaf(r).derive = [{ run: 'x', cwd: '.', writes: [] }]),
      '.derive[0].writes:',
    ],
    [
      'literal without value group',
      (r) => (leaf(r).literals = [{ re: 'zot v\\d' }]),
      '.literals[0].re:',
    ],
    [
      'ignore without BLOCKER',
      (r) => (r.ignores = [{ scanner: 'go-mod', repo: '.', file: 'go.mod', reason: 'later' }]),
      'ignores[0].reason:',
    ],
    [
      'ignore unknown scanner',
      (r) => (r.ignores = [{ scanner: 'rpm', repo: '.', file: 'x', reason: 'BLOCKER: x' }]),
      'ignores[0].scanner:',
    ],
    [
      'unscanned submodule without reason',
      (r) => ((r.submodules as Obj).unscanned = [{ path: 'private/elite' }]),
      'unscanned[0].reason:',
    ],
    [
      'literalExclude without reason',
      (r) => (r.literalExclude = [{ repo: '.', glob: 'notes/**' }]),
      'literalExclude[0].reason:',
    ],
  ];
  for (const [name, mutate, field] of breaks) {
    const r = clone();
    mutate(r);
    const problems = registryProblems(r);
    cases.push({
      name: `refuses a malformed ${name}, by field (${field})`,
      ok: problems.some((p) => p.includes(field)),
      detail: problems.length ? problems.join('; ') : 'no problem reported',
    });
  }

  // The loader throws with the field path; a caller that catches RegistryError sees them all.
  let thrown: unknown;
  try {
    parseRegistry(JSON.stringify({ ...validFixture(), version: 3 }), 'fixture.json');
  } catch (err) {
    thrown = err;
  }
  cases.push({
    name: 'parseRegistry throws RegistryError naming the file and the field',
    ok:
      thrown instanceof RegistryError &&
      thrown.message.includes('fixture.json') &&
      thrown.problems.some((p) => p.startsWith('version:')),
    detail: String(thrown),
  });

  // Locators: the shorthand regexes, the json pointer and the line arithmetic.
  const df = 'FROM x\nARG ZOT_VERSION=9.8.7\nRUN y\nARG ZOT_VERSION=9.8.7\n';
  const zm = siteMatches(
    { repo: '.', file: 'Dockerfile', role: 'version', arg: 'ZOT_VERSION', expect: 2 },
    df
  );
  cases.push({
    name: 'an arg site matches every ARG line, with its value and line',
    ok: zm.length === 2 && zm[0].value === '9.8.7' && zm[0].line === 2 && zm[1].line === 4,
    detail: JSON.stringify(zm),
  });
  const pm = siteMatches(
    { repo: '.', file: 'x.lock.json', role: 'version', json: '/components/k3s/version', expect: 1 },
    '{"components":{"k3s":{"version":"9.8.7+k3s1"}}}'
  );
  cases.push({
    name: 'a json site resolves its pointer to the string value',
    ok: pm.length === 1 && pm[0].value === '9.8.7+k3s1',
    detail: JSON.stringify(pm),
  });
  cases.push({
    name: 'CONTROL: a json pointer through a prototype key resolves to nothing',
    ok: jsonPointer({ a: {} }, '/a/constructor') === undefined,
  });
  return cases;
}

function main(): number {
  if (process.argv.includes('--selftest')) {
    const failed = runControls(selftestCases());
    return failed === 0 ? 0 : 1;
  }
  const file = registryPath();
  try {
    const reg = loadRegistry(file);
    const fam = reg.entries.filter((e) => e.kind === 'family').length;
    const sites = reg.entries.reduce((n, e) => n + e.sites.length, 0);
    console.log(
      `${path.relative(process.cwd(), file)}: ${reg.entries.length} entries (${fam} families, ${reg.entries.length - fam} leaves), ${sites} sites, ${reg.ignores.length} ignores`
    );
    return 0;
  } catch (err) {
    console.error(err instanceof RegistryError ? err.message : String(err));
    return 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  process.exit(main());
}
