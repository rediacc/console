/**
 * The npm driver of `npm run pins` (agent/plans/PLAN-pins-command.md T4 and T6): the one
 * driver for every npm project the registry's `npm` family scopes (the console root and its
 * workspaces, the four workers/ projects, private/account and its web and e2e sub-projects).
 *
 * IT IS check-deps' PLANNER, NOT A COPY. `check-deps.ts --plan-json` judges the trees (the
 * blocklist, the release-age window, the major rule, the held-major clock) and plans the npm
 * invocations with scripts/lib/deps/plan.ts; this driver turns that plan into transaction
 * steps. What the old `check:deps --upgrade` did in one process now runs inside the pins
 * transaction (scripts/lib/pins/txn.ts), so it is journaled, restored on failure and followed
 * by the canonical lockfile pass and the gates:
 *
 *   - every npm invocation is `npx -y npm@<NPM_VERSION> ...` (.devcontainer/toolchain.env),
 *     never the ambient npm, which would write a lockfile `check:ci-lockfile` rejects;
 *   - an exact-pin `overrides` entry that holds a package is moved by a planned write;
 *   - each `npm update` is followed by the freshness-window guard (npm-steps.ts guard);
 *   - the syncpack pin groups follow the moved packages (npm-steps.ts sync);
 *   - the canonical `install --package-lock-only` pass per touched lockfile and the root
 *     `npm ci && install:natives` are the transaction's own, not repeated here.
 *
 * ONE SYNTHETIC RELEASE stands for "every non-breaking package the window has cleared" (a
 * family answers `inspect` that way, see driver.ts); each held or blocklisted MAJOR is its own
 * release, named by its allow key (`vite@8`, `private/account/web:vite@8`), taken only by
 * `bump npm --to <key> --major --reason "<why>"`. A major plan runs the planner with the
 * allow entry TRANSIENT (check-deps `--allow`, never written) and removes the package's
 * blocklist line and held-major exception in the same transaction, so the net diff of a major
 * is the manifest, the lockfile and those two removals.
 *
 * `remove <pkg>` and `lockfiles [<dir>]` are the other two plans this module builds.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { globSync } from 'glob';
import { planOverrideBump } from '../../deps/execute.js';
import type { InstallStep } from '../../deps/plan.js';
import { FIXTURE_ROOT, MUTANT, type PackageInfo } from '../../deps/shared.js';
import { isWithinFreshnessWindow } from '../../release-age.js';
import { REPO_ROOT } from '../../repo-root.js';
import {
  type DriverContext,
  type FileWrite,
  type Inspection,
  keyOf,
  type PinDriver,
  type PinPlan,
  PlanRefused,
  type PlanStep,
  type Release,
} from '../driver.js';
import type { PinEntry, RepoPath } from '../registry.js';

// ---- the plan check-deps answers ------------------------------------------------------------

interface MajorCandidate {
  /** The allow key that takes it, and the version name `--to` matches. */
  key: string;
  /** The blocklist line that holds it (bare or `<dir>:<package>`), null for an unblocked held major. */
  blockKey: string | null;
  pkg: PackageInfo;
  /** '' for the root. */
  manifest: string;
  /** Publish instant when check-deps had to date it (blocklisted majors skip its window partition). */
  publishedMs: number | null;
}

interface NpmPlanJson {
  nowMs: number;
  minReleaseAgeMs: number;
  steps: InstallStep[];
  majors: MajorCandidate[];
  tooNew: Array<{ pkg: PackageInfo; manifest: string }>;
  manifests: string[];
}

const CHECK_DEPS = path.join(REPO_ROOT, 'scripts/gates/check-deps.ts');
const HELPER = path.join(REPO_ROOT, 'scripts/lib/pins/drivers/npm-steps.ts');

const cache = new WeakMap<DriverContext, Map<string, NpmPlanJson>>();

/** Run `check-deps.ts --plan-json` against the context's root and parse its one PLAN-JSON line. */
function loadPlan(ctx: DriverContext, flags: string[]): NpmPlanJson {
  const memo = cache.get(ctx) ?? new Map<string, NpmPlanJson>();
  cache.set(ctx, memo);
  const k = flags.join('\0');
  const hit = memo.get(k);
  if (hit) return hit;
  const env: NodeJS.ProcessEnv = { ...process.env };
  if (path.resolve(ctx.root) !== path.resolve(REPO_ROOT)) env.CHECK_DEPS_ROOT = ctx.root;
  const r = spawnSync(
    process.execPath,
    [...process.execArgv, CHECK_DEPS, '--plan-json', ...flags],
    { cwd: ctx.root, env, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 }
  );
  const line = (r.stdout ?? '').split('\n').find((l) => l.startsWith('PLAN-JSON '));
  if (!line)
    throw new Error(
      `check-deps --plan-json answered no plan (rc=${r.status}): ${`${r.stdout ?? ''}${r.stderr ?? ''}`.trim().split('\n').slice(-8).join(' | ')}`
    );
  const plan = JSON.parse(line.slice('PLAN-JSON '.length)) as NpmPlanJson;
  memo.set(k, plan);
  return plan;
}

// ---- paths, commands ------------------------------------------------------------------------

const q = (s: string): string => (/^[\w@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`);

/** The pinned npm version (.devcontainer/toolchain.env NPM_VERSION) of the tree being bumped. */
function pinnedNpm(root: string): string {
  const tc = path.join(root, '.devcontainer/toolchain.env');
  const m = fs.existsSync(tc) ? /^NPM_VERSION=(\S+)$/m.exec(fs.readFileSync(tc, 'utf8')) : null;
  if (!m)
    throw new PlanRefused(
      'NPM_VERSION is missing from .devcontainer/toolchain.env; refusing to plan an ambient npm'
    );
  return m[1];
}

/**
 * One npm invocation as a shell line. The `ambient-npm` mutant (a fixture run only) plans the
 * ambient `npm` instead, which the selftest proves is red. `--loglevel=notice` rides every
 * invocation because `npm run -s` exports npm_config_loglevel=silent to its children, and a
 * silent child prints nothing when it fails (the 2026-09-30 bare "Some upgrades failed").
 */
function npmLine(version: string, args: string[]): string {
  const rest = [...args, '--loglevel=notice'].map(q).join(' ');
  return MUTANT === 'ambient-npm' && FIXTURE_ROOT ? `npm ${rest}` : `npx -y npm@${version} ${rest}`;
}

/** A command that runs one of this module's helper verbs under the interpreter this process uses. */
const helperLine = (verb: 'guard' | 'sync', steps: InstallStep[]): string =>
  [
    q(process.execPath),
    ...process.execArgv.map(q),
    q(HELPER),
    verb,
    Buffer.from(JSON.stringify(steps)).toString('base64'),
  ].join(' ');

/** An absolute path inside the context's root as the (repo, file) pair the transaction journals. */
function repoPathOf(ctx: DriverContext, abs: string): RepoPath {
  const rel = path.relative(ctx.root, abs).split(path.sep).join('/');
  const sub = ctx.reg.submodules.scanned.find((s) => rel === s || rel.startsWith(`${s}/`));
  return sub ? { repo: sub, file: rel.slice(sub.length + 1) } : { repo: '.', file: rel };
}

const relDir = (ctx: DriverContext, abs: string): string =>
  path.relative(ctx.root, abs).split(path.sep).join('/') || '.';

/** The files an npm step may change: the manifests it names and the project's lockfile. */
function stepWrites(ctx: DriverContext, step: InstallStep): RepoPath[] {
  const dirs = new Set<string>([step.cwd]);
  for (const a of step.args) {
    const m = /^-w=(.+)$/.exec(a);
    if (m) dirs.add(path.join(step.cwd, m[1]));
  }
  const files = [...dirs].map((d) => repoPathOf(ctx, path.join(d, 'package.json')));
  files.push(repoPathOf(ctx, path.join(step.cwd, 'package-lock.json')));
  return files;
}

// ---- policy-file edits ----------------------------------------------------------------------

/** Drop the blocklist lines whose key is in `keys`, with the comment block directly above each (never a file-header block). */
function dropBlocklistLines(text: string, keys: Set<string>): string {
  const lines = text.split('\n');
  const drop = new Set<number>();
  for (const [i, l] of lines.entries()) {
    const t = l.trim();
    if (t === '' || t.startsWith('#') || !keys.has(t.split(/\s+/)[0])) continue;
    drop.add(i);
    let j = i - 1;
    while (j >= 0 && lines[j].trim().startsWith('#')) j--;
    const above = i - 1 - j;
    // A comment block is the entry's own only when a blank line (not the file start) sits above it and it is short.
    if (above > 0 && above <= 3 && j >= 0 && lines[j].trim() === '')
      for (let k = j + 1; k < i; k++) drop.add(k);
  }
  return lines.filter((_, i) => !drop.has(i)).join('\n');
}

/** Delete keys from the object at `field` of a 2-space JSON file; refuses a file a rewrite would reformat. */
function dropJsonKeys(
  text: string,
  field: string,
  match: (key: string) => boolean,
  where: string
): { after: string; dropped: string[] } {
  const doc = JSON.parse(text) as Record<string, Record<string, unknown> | undefined>;
  if (`${JSON.stringify(doc, null, 2)}\n` !== text)
    throw new PlanRefused(
      `${where}: not 2-space JSON with a trailing newline, so a rewrite would reformat it`
    );
  const table = doc[field];
  if (!table || typeof table !== 'object') return { after: text, dropped: [] };
  const dropped = Object.keys(table).filter(match);
  for (const k of dropped) delete table[k];
  return { after: dropped.length ? `${JSON.stringify(doc, null, 2)}\n` : text, dropped };
}

const exceptionKeyMatches =
  (pkg: string) =>
  (key: string): boolean =>
    key === pkg || key.endsWith(`:${pkg}`);
const allowKeyMatches =
  (pkg: string) =>
  (key: string): boolean =>
    new RegExp(`^(?:[^:\\s]+:)?${pkg.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}@\\d`).test(key);

function holdFile(entry: PinEntry, suffix: string): RepoPath {
  const f = entry.holds.find((h) => h.endsWith(suffix));
  if (!f) throw new PlanRefused(`${entry.id}: the registry names no hold file ending ${suffix}`);
  return { repo: '.', file: f };
}

function needText(ctx: DriverContext, p: RepoPath): string {
  const t = ctx.read(p);
  if (t === null) throw new PlanRefused(`${keyOf(p)} does not exist`);
  return t;
}

// ---- plan assembly --------------------------------------------------------------------------

/** The npm steps of a plan as transaction steps, each `update` followed by its freshness guard, then the pin-group sync. */
function stepsOf(
  ctx: DriverContext,
  entry: PinEntry,
  steps: InstallStep[],
  version: string
): { writes: FileWrite[]; steps: PlanStep[]; notes: string[] } {
  const refused = steps.filter((s) => s.refused);
  if (refused.length > 0)
    throw new PlanRefused(
      `${entry.id}: ${refused.map((s) => `${s.label}: ${s.packages.map((p) => `${p.name} ${p.current} -> ${p.latest}`).join(', ')} not applied: ${s.refused}`).join('; ')}`
    );
  const writes: FileWrite[] = [];
  const out: PlanStep[] = [];
  const notes: string[] = [];
  const planned = new Map<string, string>();
  for (const st of steps) {
    if (st.overrideBump) {
      const b = st.overrideBump;
      const p = repoPathOf(ctx, b.file);
      const bumped = planOverrideBump(
        planned.get(keyOf(p)) ?? needText(ctx, p),
        b,
        path.relative(ctx.root, b.file) || 'package.json'
      );
      if (bumped.after === null) throw new PlanRefused(`${entry.id}: ${bumped.error}`);
      planned.set(keyOf(p), bumped.after);
      const dup = writes.find((w) => keyOf(w) === keyOf(p));
      if (dup) dup.after = bumped.after;
      else writes.push({ ...p, after: bumped.after });
      notes.push(`${keyOf(p)}: overrides["${b.name}"] ${b.from} -> ${b.to}`);
      if (bumped.advisory) notes.push(`advisory: ${bumped.advisory}`);
    }
    out.push({
      label: st.label,
      run: npmLine(version, st.args),
      cwd: relDir(ctx, st.cwd),
      writes: stepWrites(ctx, st),
    });
    if (st.args[0] === 'update')
      out.push({
        label: `freshness guard: ${st.label}`,
        run: helperLine('guard', [st]),
        cwd: '.',
        writes: [],
      });
  }
  const moved = steps.filter((s) => s.packages.length > 0);
  const rc = path.join(ctx.root, '.syncpackrc.json');
  if (moved.length > 0 && fs.existsSync(rc))
    out.push({
      label: 'syncpack pin groups',
      run: helperLine('sync', moved),
      cwd: '.',
      writes: [{ repo: '.', file: '.syncpackrc.json' }],
    });
  return { writes, steps: out, notes };
}

const packageLine = (manifest: string, p: PackageInfo): string =>
  `${manifest || 'root'}: ${p.name} ${p.current} -> ${p.latest}`;

function npmPlanOf(
  entry: PinEntry,
  ctx: DriverContext,
  from: string,
  to: Release,
  plan: NpmPlanJson,
  extraWrites: FileWrite[],
  extraChanges: string[]
): PinPlan {
  const built = stepsOf(ctx, entry, plan.steps, pinnedNpm(ctx.root));
  const changes = [
    ...plan.steps.flatMap((s) =>
      s.packages.map((p) => packageLine(relDir(ctx, s.cwd) === '.' ? '' : s.label, p))
    ),
    ...built.notes,
    ...extraChanges,
  ];
  const writes = [...built.writes];
  for (const w of extraWrites) {
    const dup = writes.find((x) => keyOf(x) === keyOf(w));
    if (dup) dup.after = w.after;
    else writes.push(w);
  }
  return { entry, from, to, writes, steps: built.steps, changes };
}

// ---- the driver -----------------------------------------------------------------------------

const names = (steps: InstallStep[]): string[] => [
  ...new Set(steps.flatMap((s) => s.packages.map((p) => p.name))),
];

function majorRelease(m: MajorCandidate, plan: NpmPlanJson): Release {
  const why = `major ${m.pkg.current} -> ${m.pkg.latest} in ${m.manifest || 'root'}`;
  // A held major was window-partitioned by check-deps already; a blocklisted one was not, so its age is judged here, and an unknown age is a refusal (fail closed).
  if (m.blockKey !== null && plan.minReleaseAgeMs > 0) {
    if (m.publishedMs === null)
      return {
        version: m.key,
        publishedMs: null,
        verdict: { eligible: false, why: `${why}, publish time unknown` },
      };
    if (isWithinFreshnessWindow(m.publishedMs, plan.nowMs, plan.minReleaseAgeMs))
      return {
        version: m.key,
        publishedMs: m.publishedMs,
        verdict: { eligible: false, why: `${why}, inside the release-age window` },
      };
  }
  return { version: m.key, publishedMs: m.publishedMs, verdict: { eligible: true, why } };
}

/** Synthetic version of the all-in-range release, `1.<n>` for n packages, so the core reads it as a same-major step from `1.0`. */
const IN_RANGE_BASE = '1.0';

export const npmDriver: PinDriver = {
  name: 'npm',
  holdKey: () => null,
  inspect(_entry, ctx): Promise<Inspection> {
    const plan = loadPlan(ctx, []);
    const releases: Release[] = [];
    const pkgs = names(plan.steps);
    if (plan.steps.length > 0)
      releases.push({
        version: `1.${pkgs.length}`,
        publishedMs: null,
        verdict: {
          eligible: true,
          why: `${pkgs.length} package(s) past the release-age window across ${plan.manifests.length} manifest(s)`,
        },
      });
    else if (plan.tooNew.length > 0)
      releases.push({
        version: '1.1',
        publishedMs: null,
        verdict: {
          eligible: false,
          why: `${plan.tooNew.length} package(s) newer than the lockfiles, all inside the release-age window`,
        },
      });
    for (const m of plan.majors) releases.push(majorRelease(m, plan));
    return Promise.resolve({ current: IN_RANGE_BASE, releases });
  },
  plan(entry, to, ctx): Promise<PinPlan> {
    const major = loadPlan(ctx, []).majors.find((m) => m.key === to.version);
    if (!major) {
      const plan = loadPlan(ctx, []);
      if (plan.steps.length === 0)
        throw new PlanRefused(`${entry.id}: nothing past the window to bump`);
      return Promise.resolve(
        npmPlanOf(
          entry,
          ctx,
          `${plan.manifests.length} manifests`,
          { version: `${names(plan.steps).length} package(s)`, publishedMs: null },
          plan,
          [],
          []
        )
      );
    }
    // A major: the planner runs with the allow entry transient and the hold absent, restricted to the packages that entry authorises.
    const plan = loadPlan(ctx, [
      '--allow',
      major.key,
      ...(major.blockKey ? ['--unblock', major.blockKey] : []),
    ]);
    if (plan.steps.length === 0)
      throw new PlanRefused(`${entry.id}: the planner found nothing to install for ${major.key}`);
    const writes: FileWrite[] = [];
    const changes: string[] = [];
    if (major.blockKey) {
      const bl = holdFile(entry, 'deps-upgrade-blocklist');
      const text = needText(ctx, bl);
      const after = dropBlocklistLines(text, new Set([major.blockKey]));
      if (after !== text) {
        writes.push({ ...bl, after });
        changes.push(`${keyOf(bl)}: drop the ${major.blockKey} hold`);
      }
      const ex = holdFile(entry, 'deps-major-exceptions.json');
      const exText = ctx.read(ex);
      if (exText !== null) {
        const r = dropJsonKeys(exText, 'exceptions', (k) => k === major.blockKey, keyOf(ex));
        if (r.dropped.length > 0) {
          writes.push({ ...ex, after: r.after });
          changes.push(`${keyOf(ex)}: drop the ${major.blockKey} exception`);
        }
      }
    }
    return Promise.resolve(
      npmPlanOf(
        entry,
        ctx,
        `${major.pkg.name} ${major.pkg.current}`,
        { version: `${major.pkg.name} ${major.pkg.latest}`, publishedMs: to.publishedMs },
        plan,
        writes,
        changes
      )
    );
  },
};

// ---- lockfiles ------------------------------------------------------------------------------

/** Every npm project directory the registry's family scopes, as (repo, dir within repo, absolute dir). */
function projectDirs(
  entry: PinEntry,
  ctx: DriverContext
): Array<{ repo: string; dir: string; abs: string }> {
  const out: Array<{ repo: string; dir: string; abs: string }> = [];
  for (const sc of entry.scope ?? []) {
    if (sc.scanner !== 'npm-lockfile') continue;
    const base = path.join(ctx.root, sc.repo);
    if (!fs.existsSync(base)) continue;
    for (const pat of sc.files)
      for (const f of globSync(pat, { cwd: base, posix: true }).sort()) {
        const dir = path.posix.dirname(f) === '.' ? '' : path.posix.dirname(f);
        out.push({ repo: sc.repo, dir, abs: path.join(base, dir) });
      }
  }
  return out;
}

/**
 * `pins lockfiles [<dir>]`: the canonical lockfile pass under the pinned npm over every npm
 * project (or one), gated by check:ci-lockfile. The transaction repeats the pass over any
 * lockfile this changed, which is idempotent.
 */
export function planLockfiles(
  entry: PinEntry,
  ctx: DriverContext,
  dir: string | undefined
): PinPlan {
  const version = pinnedNpm(ctx.root);
  let dirs = projectDirs(entry, ctx);
  if (dir !== undefined) {
    const want = dir.replace(/\/+$/, '') || '.';
    dirs = dirs.filter((d) => relDir(ctx, d.abs) === want);
    if (dirs.length === 0)
      throw new PlanRefused(
        `lockfiles: ${dir} is not an npm project of the registry (known: ${projectDirs(entry, ctx)
          .map((d) => relDir(ctx, d.abs))
          .join(', ')})`
      );
  }
  const steps: PlanStep[] = dirs.map((d) => ({
    label: `canonical lockfile pass: ${relDir(ctx, d.abs)}`,
    run: npmLine(version, ['install', '--package-lock-only', '--ignore-scripts']),
    cwd: relDir(ctx, d.abs),
    writes: [repoPathOf(ctx, path.join(d.abs, 'package-lock.json'))],
  }));
  return {
    entry: { ...entry, derive: [], gates: ['check:ci-lockfile'] },
    from: 'the current locks',
    to: { version: `${steps.length} lockfile(s) in canonical form`, publishedMs: null },
    writes: [],
    steps,
    changes: steps.map((s) => s.label),
  };
}

// ---- remove ---------------------------------------------------------------------------------

const DEP_FIELDS = [
  'dependencies',
  'devDependencies',
  'optionalDependencies',
  'peerDependencies',
] as const;

interface Manifest {
  abs: string;
  json: Record<string, unknown>;
}

function readManifest(abs: string): Manifest | null {
  const f = path.join(abs, 'package.json');
  if (!fs.existsSync(f)) return null;
  return { abs, json: JSON.parse(fs.readFileSync(f, 'utf8')) as Record<string, unknown> };
}

const declares = (m: Manifest, pkg: string): boolean =>
  DEP_FIELDS.some((f) => pkg in ((m.json[f] as Record<string, string> | undefined) ?? {}));

/** Remove `pkg` from the knip config's ignoreDependencies, with the BLOCKER comment that covered only it. */
function dropKnipEntry(text: string, pkg: string): string {
  const lines = text.split('\n');
  const idx = lines.findIndex((l) =>
    new RegExp(`^\\s*"${pkg.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}",?\\s*$`).test(l)
  );
  if (idx < 0) return text;
  const drop = new Set<number>([idx]);
  let j = idx - 1;
  while (j >= 0 && lines[j].trim().startsWith('//')) j--;
  const commentStart = j + 1;
  const next = lines[idx + 1]?.trim() ?? '';
  // The comment above is the entry's own when the next line is not another entry the same comment covers.
  const coversNext = /^"[^"]+",?$/.test(next);
  if (commentStart < idx && !coversNext) for (let k = commentStart; k < idx; k++) drop.add(k);
  let kept = lines.filter((_, i) => !drop.has(i));
  // An array whose last entry went leaves a dangling comma before its closing bracket.
  kept = kept.map((l, i) =>
    /,\s*$/.test(l) && /^\s*\]/.test(kept[i + 1] ?? '') ? l.replace(/,\s*$/, '') : l
  );
  return kept.join('\n');
}

/**
 * The source files under the declaring manifests that still import `pkg`. check:ci-runtime-imports-are-deps judges only a package filed under devDependencies that runtime code imports; a package removed outright is "unlisted entirely", which it names out of scope, so a removal that leaves an importer behind reaches no gate until tsc or knip. The plan refuses it instead (fail closed).
 */
function importersOf(pkg: string, dirs: string[]): string[] {
  const esc = pkg.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  const re = new RegExp(`(?:from|import|require\\()\\s*\\(?\\s*['"]${esc}(?:/[^'"]*)?['"]`);
  const out: string[] = [];
  // Every JS and TS source under the declaring directory, at any depth: an importer under scripts/, tests/ or e2e/ keeps the package in use as much as one under src/. Build output and dependency trees are not sources.
  for (const d of dirs)
    for (const f of globSync(['**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}'], {
      cwd: d,
      posix: true,
      ignore: [
        '**/node_modules/**',
        '**/dist/**',
        '**/build/**',
        '**/coverage/**',
        '**/.astro/**',
        '.ci/cache/**',
      ],
    }).sort())
      if (re.test(fs.readFileSync(path.join(d, f), 'utf8'))) out.push(path.join(d, f));
  return out;
}

/** `pins remove <pkg>`: uninstall from every declaring manifest and clean every line that named the package. */
export function planRemove(entry: PinEntry, ctx: DriverContext, pkg: string): PinPlan {
  const version = pinnedNpm(ctx.root);
  const projects = projectDirs(entry, ctx);
  const steps: PlanStep[] = [];
  const writes: FileWrite[] = [];
  const changes: string[] = [];
  const overlay = new Map<string, string>();
  const readOf = (p: RepoPath): string | null => overlay.get(keyOf(p)) ?? ctx.read(p);
  const put = (p: RepoPath, after: string, what: string): void => {
    const before = readOf(p);
    if (before === after) return;
    overlay.set(keyOf(p), after);
    const dup = writes.find((w) => keyOf(w) === keyOf(p));
    if (dup) dup.after = after;
    else writes.push({ ...p, after });
    changes.push(`${keyOf(p)}: ${what}`);
  };
  let declaring = 0;
  const declaringDirs: string[] = [];
  for (const pr of projects) {
    const root = readManifest(pr.abs);
    if (!root) continue;
    const members: Manifest[] = [];
    const wsGlobs = Array.isArray(root.json.workspaces) ? (root.json.workspaces as string[]) : [];
    for (const g of wsGlobs)
      for (const d of globSync(g, { cwd: pr.abs, posix: true }).sort()) {
        const m = readManifest(path.join(pr.abs, d));
        if (m) members.push(m);
      }
    const hits = [root, ...members].filter((m) => declares(m, pkg));
    // overrides and their reasons live in the project's own manifest, whether or not it declares the package.
    for (const m of [root]) {
      const p = repoPathOf(ctx, path.join(m.abs, 'package.json'));
      const text = readOf(p);
      if (text === null) continue;
      const doc = JSON.parse(text) as Record<string, Record<string, unknown> | undefined>;
      if (`${JSON.stringify(doc, null, 2)}\n` !== text) continue;
      const isKey = (k: string): boolean => k === pkg || k.startsWith(`${pkg}@`);
      let touched = false;
      for (const f of ['overrides', '_overridesReasons'])
        for (const k of Object.keys(doc[f] ?? {}))
          if (isKey(k)) {
            delete (doc[f] as Record<string, unknown>)[k];
            touched = true;
          }
      if (touched)
        put(p, `${JSON.stringify(doc, null, 2)}\n`, `drop the ${pkg} override and its reason`);
    }
    if (hits.length === 0) continue;
    declaring += hits.length;
    declaringDirs.push(...hits.map((m) => m.abs));
    const flags = hits
      .filter((m) => m !== root)
      .map((m) => `-w=${path.relative(pr.abs, m.abs).split(path.sep).join('/')}`);
    const withRoot = hits.includes(root);
    const args = [
      'uninstall',
      pkg,
      ...flags,
      ...(flags.length > 0 && withRoot ? ['--include-workspace-root'] : []),
    ];
    const stepLike: InstallStep = { cwd: pr.abs, args, label: relDir(ctx, pr.abs), packages: [] };
    steps.push({
      label: `uninstall ${pkg}: ${relDir(ctx, pr.abs)}`,
      run: npmLine(version, args),
      cwd: relDir(ctx, pr.abs),
      writes: stepWrites(ctx, stepLike),
    });
    changes.push(
      `${relDir(ctx, pr.abs)}: npm uninstall ${pkg} (${hits.map((m) => relDir(ctx, m.abs)).join(', ')})`
    );
  }
  if (declaring === 0)
    throw new PlanRefused(`remove ${pkg}: no npm manifest of the registry declares it`);
  const importers = importersOf(pkg, declaringDirs);
  if (importers.length > 0)
    throw new PlanRefused(
      `remove ${pkg}: still imported by ${importers
        .slice(0, 5)
        .map((f) => relDir(ctx, f))
        .join(
          ', '
        )}${importers.length > 5 ? ` and ${importers.length - 5} more` : ''}; nothing is written. Remove the imports first.`
    );

  const blocklist = holdFile(entry, 'deps-upgrade-blocklist');
  const blText = readOf(blocklist);
  if (blText !== null) {
    const keys = new Set<string>();
    for (const l of blText.split('\n')) {
      const k = l.trim().split(/\s+/)[0];
      if (k === pkg || (k.endsWith(`:${pkg}`) && !l.trim().startsWith('#'))) keys.add(k);
    }
    if (keys.size > 0) put(blocklist, dropBlocklistLines(blText, keys), `drop the ${pkg} hold`);
  }
  for (const [suffix, field, match] of [
    ['deps-major-exceptions.json', 'exceptions', exceptionKeyMatches(pkg)],
    ['deps-major-allow.json', 'allow', allowKeyMatches(pkg)],
  ] as const) {
    const f = holdFile(entry, suffix);
    const t = readOf(f);
    if (t === null) continue;
    const r = dropJsonKeys(t, field, match, keyOf(f));
    if (r.dropped.length > 0) put(f, r.after, `drop ${r.dropped.join(', ')}`);
  }
  const rcP: RepoPath = { repo: '.', file: '.syncpackrc.json' };
  const rcText = readOf(rcP);
  if (rcText !== null) {
    const rc = JSON.parse(rcText) as Record<string, unknown>;
    if (`${JSON.stringify(rc, null, 2)}\n` !== rcText)
      throw new PlanRefused(
        '.syncpackrc.json: not 2-space JSON with a trailing newline, so a rewrite would reformat it'
      );
    let touched = false;
    for (const field of ['versionGroups', 'semverGroups']) {
      const groups = rc[field];
      if (!Array.isArray(groups)) continue;
      rc[field] = (groups as Record<string, unknown>[]).filter((g) => {
        const deps = g.dependencies;
        if (!Array.isArray(deps) || !deps.includes(pkg)) return true;
        touched = true;
        g.dependencies = deps.filter((d) => d !== pkg);
        return (g.dependencies as unknown[]).length > 0;
      });
    }
    if (touched) put(rcP, `${JSON.stringify(rc, null, 2)}\n`, `drop ${pkg} from the pin groups`);
  }
  const knip: RepoPath = { repo: '.', file: 'knip.jsonc' };
  const knipText = readOf(knip);
  if (knipText !== null) {
    const after = dropKnipEntry(knipText, pkg);
    if (after !== knipText) put(knip, after, `drop the ${pkg} ignore`);
  }
  return {
    entry: {
      ...entry,
      derive: [],
      gates: [
        'check:ci-runtime-imports-are-deps',
        'check:deps',
        'check:version',
        'check:ci-overrides-reasons',
        'check:ci-knip-blockers',
        'check:ci-suppression-liveness',
        'check:ci-lockfile',
      ],
    },
    from: pkg,
    to: { version: 'removed', publishedMs: null },
    writes,
    steps,
    changes,
  };
}
