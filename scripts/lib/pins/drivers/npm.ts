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
 * `bump npm --to <key> --major --reason "<why>"`, and that run carries the in-range release
 * too, since check:deps judges the whole tree. A HELD major (no blocklist line, what check:deps
 * reds on as "awaiting a decision") cannot be left behind: a run that does not name every one
 * is refused before it writes, with the one `--to ... --major` line that takes them all
 * (driver.ts splitFamilySet). A blocklisted major is held on purpose and never forces that.
 *
 * THE INSTALLED TREE MUST BE THE LOCKED ONE. check-deps judges what `npm outdated` reports,
 * which is the installed tree; a node_modules that disagrees with its package-lock.json (a
 * failed run's npm steps, before txn.ts learned to reinstall after a restore) makes the plan
 * describe a tree nobody committed. inspect refuses such a project as not compared, naming the
 * package and the `npm ci` that resyncs it. A major plan runs the planner with the
 * allow entry TRANSIENT (check-deps `--allow`, never written) and removes the package's
 * blocklist line and held-major exception in the same transaction, so the net diff of a major
 * is the manifest, the lockfile and those two removals.
 *
 * AN OVERRIDE RANGE THE LOCKFILE DOES NOT MEET IS PART OF THE IN-RANGE RELEASE (worklist
 * #c97a62d9). A hand-raised `overrides` floor on a transitive package (vite >=8.3.1 -> >=8.3.5
 * on 2026-10-31, commit 2c8452ba) is invisible to check-deps, which judges `npm outdated`'s
 * direct dependencies only, so the run refused on eleven unrelated deferrals and the lock was
 * moved by hand. Each project's direct overrides are read against its own lockfile; a copy
 * outside the range is dated against the registry (the target is the release npm itself would
 * pick under `--before=<release-age cutoff>`), planned as `npm update <name> --before=<cutoff>`
 * with its freshness guard, and folded into the in-range release, so unrelated deferred
 * packages stay deferred and are named in the run's label rather than refusing it. A target
 * still inside the window refuses every plan of the family (the lock cannot meet its own
 * manifest until it clears), and a range no published release admits is not compared.
 *
 * `remove <pkg>` and `lockfiles [<dir>]` are the other two plans this module builds.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { globSync } from 'glob';
import { planOverrideBump } from '../../deps/execute.js';
import { freshnessCutoffMs, type InstallStep } from '../../deps/plan.js';
import {
  compareVersions,
  FIXTURE_ROOT,
  MUTANT,
  type PackageInfo,
  parseRange,
  parseVersion,
  rangeAdmits,
} from '../../deps/shared.js';
import { isWithinFreshnessWindow } from '../../release-age.js';
import { REPO_ROOT } from '../../repo-root.js';
import { askUpstream } from '../../upstream.js';
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
  splitFamilySet,
} from '../driver.js';
import type { PinEntry, RepoPath } from '../registry.js';
import {
  BIOME_CONFIG,
  BIOME_PACKAGE,
  lockfileOf,
  planBiomeSchema,
  predictManifests,
  sourceManifests,
} from './pin-manifests.js';

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

export interface NpmPlanJson {
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
export function pinnedNpm(root: string): string {
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
export function stepsOf(
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
  const biomeP = repoPathOf(ctx, path.join(ctx.root, BIOME_CONFIG));
  const biomeText = ctx.read(biomeP);
  const biomeAfter = biomeText === null ? null : planBiomeSchema(biomeText, steps);
  if (biomeAfter !== null) {
    writes.push({ ...biomeP, after: biomeAfter });
    notes.push(`${keyOf(biomeP)}: $schema follows ${BIOME_PACKAGE}`);
  }
  const moved = steps.filter((s) => s.packages.length > 0);
  const rc = path.join(ctx.root, '.syncpackrc.json');
  if (moved.length > 0 && fs.existsSync(rc)) {
    // The manifests whose declared ranges a moved pin group may rewrite (worklist #3fc8b8cb), declared up front, then the lockfile pass over each one's project, so the lockfile's workspace entry carries the rewritten range even when no npm step touched that lockfile.
    const rcText = fs.readFileSync(rc, 'utf8');
    const manifests = predictManifests(
      rcText,
      new Set(names(moved)),
      sourceManifests(ctx.root, rcText).flatMap((file) => {
        const text = ctx.read(repoPathOf(ctx, path.join(ctx.root, file)));
        return text === null ? [] : [{ file, text }];
      })
    );
    out.push({
      label: 'syncpack pin groups',
      run: helperLine('sync', moved),
      cwd: '.',
      writes: [
        { repo: '.', file: '.syncpackrc.json' },
        ...manifests.map((f) => repoPathOf(ctx, path.join(ctx.root, f))),
      ],
    });
    const locks = [...new Set(manifests.flatMap((f) => lockfileOf(ctx.root, f) ?? []))].sort(
      (a, b) => Number(a > b) - Number(a < b)
    );
    for (const lock of locks)
      out.push({
        label: `lockfile pass after the pin-group ranges: ${lock}`,
        run: npmLine(version, ['install', '--package-lock-only', '--ignore-scripts']),
        cwd: path.posix.dirname(lock),
        writes: [repoPathOf(ctx, path.join(ctx.root, lock))],
      });
  }
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

// ---- override ranges the lockfile does not meet -------------------------------------------

/** One direct override whose range a locked copy falls outside. */
interface OverrideDrift {
  name: string;
  range: string;
  /** The distinct locked versions outside the range, ascending. */
  outside: string[];
  /** The hoisted copy's version (`node_modules/<name>`), the one the freshness guard reads; null when there is none. */
  hoisted: string | null;
}

/** The package name of a lockfile key (`node_modules/a/node_modules/@s/b` -> `@s/b`), and the chain of packages above it. */
function lockChain(key: string): string[] {
  return key
    .split(/(?:^|\/)node_modules\//)
    .filter((s) => s !== '')
    .map((s) => s.replace(/\/$/, ''));
}

/**
 * The direct overrides of a manifest (a string value, or the `"."` of an object value, keyed by
 * a bare name) that a locked copy falls outside of. Pure. A `$name` reference, a `name@range`
 * selector key and a range this module cannot parse are left out (they are check:ci-override-ranges'
 * to judge); a copy below a package whose override object scopes the same name (gray-matter's
 * js-yaml ^3) answers to that nested override, not the top-level one, so it is not judged here.
 */
export function overrideDrift(manifestText: string, lockText: string): OverrideDrift[] {
  const overrides =
    (JSON.parse(manifestText) as { overrides?: Record<string, unknown> }).overrides ?? {};
  const locked =
    (JSON.parse(lockText) as { packages?: Record<string, { version?: string; link?: boolean }> })
      .packages ?? {};
  const bare = (k: string): string => (k.lastIndexOf('@') > 0 ? k.slice(0, k.lastIndexOf('@')) : k);
  /** For each overridden name, the packages whose override object re-scopes it. */
  const scopedBy = new Map<string, Set<string>>();
  const walk = (parent: string, obj: Record<string, unknown>): void => {
    for (const [k, v] of Object.entries(obj)) {
      if (k === '.') continue;
      const set = scopedBy.get(bare(k)) ?? new Set<string>();
      set.add(parent);
      scopedBy.set(bare(k), set);
      if (typeof v === 'object' && v !== null) walk(bare(k), v as Record<string, unknown>);
    }
  };
  const direct: Array<{ name: string; range: string }> = [];
  for (const [k, v] of Object.entries(overrides)) {
    const value =
      typeof v === 'string'
        ? v
        : typeof v === 'object' && v !== null
          ? (v as Record<string, unknown>)['.']
          : undefined;
    if (typeof v === 'object' && v !== null) walk(bare(k), v as Record<string, unknown>);
    if (typeof value !== 'string' || value.startsWith('$') || bare(k) !== k) continue;
    direct.push({ name: k, range: value });
  }
  const out: OverrideDrift[] = [];
  for (const { name, range } of direct) {
    const sets = parseRange(range);
    if (!sets) continue;
    const scopes = scopedBy.get(name) ?? new Set<string>();
    const outside = new Set<string>();
    for (const [key, entry] of Object.entries(locked)) {
      const chain = lockChain(key);
      if (chain.at(-1) !== name || entry.link === true || entry.version === undefined) continue;
      if (chain.slice(0, -1).some((p) => scopes.has(p))) continue;
      if (!rangeAdmits(sets, entry.version)) outside.add(entry.version);
    }
    if (outside.size === 0) continue;
    out.push({
      name,
      range,
      outside: [...outside].sort(compareVersions),
      hoisted: locked[`node_modules/${name}`]?.version ?? null,
    });
  }
  return out;
}

/** The part of a registry document the target needs. */
export interface Packument {
  versions?: Record<string, unknown>;
  time?: Record<string, string>;
  'dist-tags'?: Record<string, string>;
}

type OverrideTarget =
  | { kind: 'target'; version: string; publishedMs: number }
  | { kind: 'deferred'; version: string; publishedMs: number | null }
  | { kind: 'none' };

/**
 * The release `npm update <name> --before=<cutoffMs>` resolves for an override range, as
 * npm-pick-manifest picks it: the `latest` dist-tag when the range admits it and it is old
 * enough, else the highest admitted stable release published at or before the cutoff. A release
 * with no publish time is never old enough (fail closed). `deferred` names the newest admitted
 * release when every one is inside the window; `none` means no published release is admitted.
 * Pure; a null cutoff is a window switched off.
 */
export function overrideTarget(
  range: string,
  doc: Packument,
  cutoffMs: number | null
): OverrideTarget {
  const sets = parseRange(range);
  if (!sets) return { kind: 'none' };
  const at = (v: string): number | null => {
    const t = doc.time?.[v];
    const ms = t === undefined ? Number.NaN : Date.parse(t);
    return Number.isFinite(ms) ? ms : null;
  };
  const admitted = Object.keys(doc.versions ?? {})
    .filter((v) => parseVersion(v)?.prerelease === null && rangeAdmits(sets, v))
    .sort((a, b) => compareVersions(b, a));
  if (admitted.length === 0) return { kind: 'none' };
  const cleared = admitted.filter((v) => {
    const ms = at(v);
    return cutoffMs === null ? true : ms !== null && ms <= cutoffMs;
  });
  if (cleared.length === 0)
    return { kind: 'deferred', version: admitted[0], publishedMs: at(admitted[0]) };
  const tag = doc['dist-tags']?.latest;
  const pick = tag !== undefined && cleared.includes(tag) ? tag : cleared[0];
  return { kind: 'target', version: pick, publishedMs: at(pick) ?? 0 };
}

/** The override moves of one plan: the npm steps that move them, and the targets the window still holds. */
export interface OverrideJudgement {
  moves: InstallStep[];
  /** One line per override whose every admitted release is inside the release-age window. */
  deferred: string[];
  /** One line per move, for the plan's changes. */
  notes: string[];
}

const isoMs = (ms: number): string => new Date(ms).toISOString();

/**
 * Every npm project of the family, its direct overrides against its own lockfile (overrideDrift),
 * each drifted one dated through `docs` (overrideTarget) and turned into an `npm update` step
 * that carries the release-age cutoff, so the window applies to the override target as to every
 * other planned package. `skip` holds `<abs cwd>\0<name>` pairs check-deps already plans. Throws
 * PlanRefused for a range no published release admits; `docs` throws when the registry did not
 * answer, which leaves the family not compared.
 */
export async function judgeOverrides(
  entry: PinEntry,
  ctx: DriverContext,
  nowMs: number,
  windowMs: number,
  docs: (name: string) => Promise<Packument>,
  skip: ReadonlySet<string> = new Set()
): Promise<OverrideJudgement> {
  const cutoff = freshnessCutoffMs(nowMs, windowMs);
  const out: OverrideJudgement = { moves: [], deferred: [], notes: [] };
  for (const d of projectDirs(entry, ctx)) {
    const manifestP = repoPathOf(ctx, path.join(d.abs, 'package.json'));
    const manifest = ctx.read(manifestP);
    const lock = ctx.read(repoPathOf(ctx, path.join(d.abs, 'package-lock.json')));
    if (manifest === null || lock === null) continue;
    const dir = relDir(ctx, d.abs);
    for (const drift of overrideDrift(manifest, lock)) {
      if (skip.has(`${d.abs}\0${drift.name}`)) continue;
      const where = `${keyOf(manifestP)}: overrides["${drift.name}"] ${drift.range}`;
      const t = overrideTarget(drift.range, await docs(drift.name), cutoff);
      if (t.kind === 'none')
        throw new PlanRefused(
          `${entry.id}: ${where} admits no published release, while the lock holds ${drift.outside.join(', ')}; correct the range`
        );
      if (t.kind === 'deferred') {
        out.deferred.push(
          `${where}: the lock holds ${drift.outside.join(', ')} and every admitted release is inside the release-age window (newest ${t.version}, ${t.publishedMs === null ? 'publish time unknown' : `published ${isoMs(t.publishedMs)}`})`
        );
        continue;
      }
      out.moves.push({
        cwd: d.abs,
        args: ['update', drift.name, ...(cutoff === null ? [] : [`--before=${isoMs(cutoff)}`])],
        label: `${dir === '.' ? 'root' : dir} (override range)`,
        packages: [
          { name: drift.name, current: drift.hoisted ?? drift.outside[0], latest: t.version },
        ],
      });
      out.notes.push(
        `${where}: the lock holds ${drift.outside.join(', ')}; npm update ${drift.name} moves every copy it governs to ${t.version} (published ${isoMs(t.publishedMs)})`
      );
    }
  }
  return out;
}

/** The registry document of a package: from `<root>/.fixture-registry/` under a fixture root (as check-deps reads it), else registry.npmjs.org; throws when neither answers. */
function registryDocs(ctx: DriverContext): (name: string) => Promise<Packument> {
  const fixture = path.resolve(ctx.root) !== path.resolve(REPO_ROOT);
  return async (name) => {
    if (fixture) {
      const p = path.join(ctx.root, '.fixture-registry', `${encodeURIComponent(name)}.json`);
      if (!fs.existsSync(p)) throw new Error(`no fixture registry document for ${name} (${p})`);
      return JSON.parse(fs.readFileSync(p, 'utf8')) as Packument;
    }
    const r = await askUpstream({
      url: `https://registry.npmjs.org/${name.replace('/', '%2F')}`,
      headers: { accept: 'application/json' },
      who: `pins npm override ${name}`,
    });
    return JSON.parse(r.body) as Packument;
  };
}

const overrideMemo = new WeakMap<DriverContext, Promise<OverrideJudgement>>();

/** judgeOverrides for the context's tree, once per context, skipping what the check-deps plan already moves. */
function overridesOf(
  entry: PinEntry,
  ctx: DriverContext,
  plan: NpmPlanJson
): Promise<OverrideJudgement> {
  const hit = overrideMemo.get(ctx);
  if (hit !== undefined) return hit;
  const skip = new Set(plan.steps.flatMap((s) => s.packages.map((p) => `${s.cwd}\0${p.name}`)));
  const p = judgeOverrides(entry, ctx, plan.nowMs, plan.minReleaseAgeMs, registryDocs(ctx), skip);
  overrideMemo.set(ctx, p);
  return p;
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

/** The synthetic in-range release a plan answers (its packages plus its override moves), or null when nothing in range is past the window. */
const inRangeVersion = (plan: NpmPlanJson, ov: OverrideJudgement): string | null => {
  const n = names(plan.steps).length + ov.moves.length;
  return n > 0 ? `1.${n}` : null;
};

/** The deferred packages a run leaves behind, for its label: they stay deferred, they never refuse the run. */
const leftDeferred = (plan: NpmPlanJson): string =>
  plan.tooNew.length > 0
    ? `; ${plan.tooNew.length} package(s) stay deferred inside the release-age window`
    : '';

/**
 * The in-range release of the family, from the check-deps plan and the override judgement. Pure.
 * An override target still inside the window makes it ineligible whatever else is pending (the
 * lock cannot meet its own manifest until it clears); deferred packages alone answer the same
 * `1.1` deferral as before overrides were judged.
 */
export function inRangeReleases(plan: NpmPlanJson, ov: OverrideJudgement): Release[] {
  const pkgs = names(plan.steps);
  const inRange = inRangeVersion(plan, ov);
  if (ov.deferred.length > 0)
    return [
      {
        version: inRange ?? '1.1',
        publishedMs: null,
        verdict: {
          eligible: false,
          why: `${ov.deferred.length} override target(s) inside the release-age window: ${ov.deferred.join('; ')}`,
        },
      },
    ];
  if (inRange !== null)
    return [
      {
        version: inRange,
        publishedMs: null,
        verdict: {
          eligible: true,
          why: `${pkgs.length} package(s) past the release-age window across ${plan.manifests.length} manifest(s)${ov.moves.length > 0 ? `, ${ov.moves.length} override range(s) the lockfile does not meet` : ''}${leftDeferred(plan)}`,
        },
      },
    ];
  if (plan.tooNew.length > 0)
    return [
      {
        version: '1.1',
        publishedMs: null,
        verdict: {
          eligible: false,
          why: `${plan.tooNew.length} package(s) newer than the lockfiles, all inside the release-age window`,
        },
      },
    ];
  return [];
}

/** The override moves a plan has not already planned, by (project, package). */
const newMoves = (steps: InstallStep[], ov: OverrideJudgement): InstallStep[] => {
  const planned = new Set(steps.flatMap((s) => s.packages.map((p) => `${s.cwd}\0${p.name}`)));
  return ov.moves.filter((m) => !planned.has(`${m.cwd}\0${m.packages[0].name}`));
};

/** Refuse any plan while an override target is still inside the window. */
function refuseDeferredOverrides(entry: PinEntry, ov: OverrideJudgement): void {
  if (ov.deferred.length > 0)
    throw new PlanRefused(
      `${entry.id}: ${ov.deferred.join('; ')}; nothing is written. Run it again once the target clears the window (npm run pins -- when ${entry.id}).`
    );
}

/**
 * The plan of the in-range release alone: check-deps' steps, then each override move (an
 * `npm update <name> --before=<cutoff>` with its freshness guard). Deferred packages are left
 * where they are and named in the label.
 */
export function inRangePlan(
  entry: PinEntry,
  ctx: DriverContext,
  base: NpmPlanJson,
  ov: OverrideJudgement
): PinPlan {
  refuseDeferredOverrides(entry, ov);
  const moves = newMoves(base.steps, ov);
  if (base.steps.length === 0 && moves.length === 0)
    throw new PlanRefused(`${entry.id}: nothing past the window to bump`);
  const pkgs = names(base.steps).length;
  const label = [
    ...(pkgs > 0 || moves.length === 0 ? [`${pkgs} package(s)`] : []),
    ...(moves.length > 0
      ? [
          `${moves.length} override move(s) (${moves.map((m) => `${m.packages[0].name} ${m.packages[0].latest}`).join(', ')})`,
        ]
      : []),
  ].join(' with ');
  return npmPlanOf(
    entry,
    ctx,
    `${base.manifests.length} manifests`,
    {
      version: `${label}${base.tooNew.length > 0 ? `; ${base.tooNew.length} deferred package(s) left` : ''}`,
      publishedMs: null,
    },
    { ...base, steps: [...base.steps, ...moves] },
    [],
    ov.notes
  );
}

export const npmDriver: PinDriver = {
  name: 'npm',
  holdKey: () => null,
  async inspect(entry, ctx): Promise<Inspection> {
    const drift = installedDrift(entry, ctx);
    if (drift.length > 0)
      throw new Error(
        `the installed tree disagrees with its lockfile, so npm outdated would judge versions nobody locked: ${drift.slice(0, 4).join('; ')}${drift.length > 4 ? `; and ${drift.length - 4} more` : ''}`
      );
    const plan = loadPlan(ctx, []);
    const releases = inRangeReleases(plan, await overridesOf(entry, ctx, plan));
    for (const m of plan.majors) releases.push(majorRelease(m, plan));
    return { current: IN_RANGE_BASE, releases };
  },
  async plan(entry, to, ctx, also = []): Promise<PinPlan> {
    const base = loadPlan(ctx, []);
    const ov = await overridesOf(entry, ctx, base);
    // The core hands a set run its in-range release and its majors together (scripts/lib/pins/status.ts); anything else is refused by name.
    const set = splitFamilySet(
      entry.id,
      inRangeVersion(base, ov),
      base.majors.map((m) => m.key),
      base.majors.filter((m) => m.blockKey === null).map((m) => m.key),
      [to, ...also]
    );
    const majors = set.majors.map((k) => base.majors.find((m) => m.key === k) as MajorCandidate);
    if (majors.length === 0) return inRangePlan(entry, ctx, base, ov);
    refuseDeferredOverrides(entry, ov);
    // Majors: the planner runs with every allow entry transient and every hold absent, so a family whose majors only converge as a set (check:deps stays red while any one is undecided) moves in one transaction.
    const plan = loadPlan(
      ctx,
      majors.flatMap((m) => ['--allow', m.key, ...(m.blockKey ? ['--unblock', m.blockKey] : [])])
    );
    if (plan.steps.length === 0)
      throw new PlanRefused(
        `${entry.id}: the planner found nothing to install for ${majors.map((m) => m.key).join(', ')}`
      );
    const writes: FileWrite[] = [];
    const changes: string[] = [];
    const blockKeys = new Set(majors.flatMap((m) => (m.blockKey ? [m.blockKey] : [])));
    if (blockKeys.size > 0) {
      const bl = holdFile(entry, 'deps-upgrade-blocklist');
      const text = needText(ctx, bl);
      const after = dropBlocklistLines(text, blockKeys);
      if (after !== text) {
        writes.push({ ...bl, after });
        for (const k of blockKeys) changes.push(`${keyOf(bl)}: drop the ${k} hold`);
      }
      const ex = holdFile(entry, 'deps-major-exceptions.json');
      const exText = ctx.read(ex);
      if (exText !== null) {
        const r = dropJsonKeys(exText, 'exceptions', (k) => blockKeys.has(k), keyOf(ex));
        if (r.dropped.length > 0) {
          writes.push({ ...ex, after: r.after });
          for (const k of r.dropped) changes.push(`${keyOf(ex)}: drop the ${k} exception`);
        }
      }
    }
    const [first] = majors;
    // The in-range packages that ride the same run are named in the release label, so the drafted subject does not read as the major alone.
    const riders = names(plan.steps).filter((n) => !majors.some((m) => m.pkg.name === n));
    const withRiders = riders.length > 0 ? ` with ${riders.length} in-range package(s)` : '';
    // The override moves ride a major run too: the entry's gates judge the whole tree, and a lock outside its own overrides fails them.
    const moves = newMoves(plan.steps, ov);
    const withMoves = moves.length > 0 ? ` and ${moves.length} override move(s)` : '';
    return npmPlanOf(
      entry,
      ctx,
      majors.length === 1
        ? `${first.pkg.name} ${first.pkg.current}`
        : `${majors.length} majors (${majors.map((m) => m.key).join(', ')})`,
      {
        version: `${majors.length === 1 ? `${first.pkg.name} ${first.pkg.latest}` : `${majors.length} majors`}${withRiders}${withMoves}`,
        publishedMs: to.publishedMs,
      },
      { ...plan, steps: [...plan.steps, ...moves] },
      writes,
      [...changes, ...(moves.length > 0 ? ov.notes : [])]
    );
  },
};

// ---- the installed tree against its lockfile ------------------------------------------------

/**
 * The packages whose installed tree disagrees with package-lock.json, one line each. Pure.
 *
 * VERSION DRIFT: an entry npm's hidden lockfile (node_modules/.package-lock.json) and package-lock.json both carry with a version, at different versions (`<pkg> installed <v>, locked <v>`). Only such entries are compared for version: npm leaves another platform's optional packages uninstalled, and a workspace link carries no version.
 *
 * EXTRANEOUS: an installed package package-lock.json does not name at all (`<pkg> installed <v>, not in the lockfile`), such as one a failed run installed and the restore took out of the lockfile again. It is read from two places, because neither alone is complete: the hidden lockfile lists what npm last installed, and a later `npm install --package-lock-only` rewrites the hidden lockfile without touching node_modules (measured 2026-10-15 under npm 11.21.0: is-number stayed in node_modules while the hidden lockfile went to `{}`), so `onDisk` carries the top-level package directories actually present, as `node_modules/<name>` keys. A workspace link (`link: true`) and npm's own root entry (`""`) are never extraneous.
 */
export function lockDrift(
  lockText: string,
  hiddenText: string,
  onDisk: readonly string[] = []
): string[] {
  type Pkgs = Record<string, { version?: string; link?: boolean } | undefined>;
  const lock = JSON.parse(lockText) as { packages?: Pkgs; lockfileVersion?: number };
  // A lockfile with no `packages` map (lockfileVersion 1) names no installed path, so every package would read as extraneous (review f56ddcde.1); it is one finding, not hundreds.
  if (lock.packages != null && (typeof lock.packages !== 'object' || Array.isArray(lock.packages)))
    return [
      `package-lock.json packages map is malformed (${Array.isArray(lock.packages) ? 'an array' : typeof lock.packages}, expected an object); rewrite it with the pinned npm before comparing`,
    ];
  if (lock.packages == null)
    return [
      `package-lock.json has no packages map (lockfileVersion ${lock.lockfileVersion ?? 'unknown'}); rewrite it with the pinned npm before comparing`,
    ];
  const locked = lock.packages;
  const installed = ((JSON.parse(hiddenText) as { packages?: Pkgs }).packages ?? {}) as Pkgs;
  const name = (k: string): string => k.replace(/^(?:.*\/)?node_modules\//, '');
  const out: string[] = [];
  const extraneous = new Set<string>();
  for (const [k, v] of Object.entries(installed)) {
    if (k === '' || v?.link === true) continue;
    if (!(k in locked)) {
      extraneous.add(k);
      out.push(`${name(k)} installed ${v?.version ?? '(no version)'}, not in the lockfile`);
      continue;
    }
    const want = locked[k]?.version;
    if (v?.version === undefined || want === undefined || v.version === want) continue;
    out.push(`${name(k)} installed ${v.version}, locked ${want}`);
  }
  for (const k of onDisk)
    if (!(k in locked) && !extraneous.has(k))
      out.push(`${name(k)} present in node_modules, not in the lockfile`);
  return out;
}

/** The top-level package directories under a node_modules directory, as `node_modules/<name>` and `node_modules/@scope/<name>` keys; npm's own dot entries (.bin, .package-lock.json, .cache) are not packages. */
export function installedDirs(nmAbs: string): string[] {
  if (!fs.existsSync(nmAbs)) return [];
  const out: string[] = [];
  for (const n of fs.readdirSync(nmAbs)) {
    if (n.startsWith('.')) continue;
    if (n.startsWith('@')) {
      const scope = path.join(nmAbs, n);
      if (!fs.statSync(scope).isDirectory()) continue;
      for (const s of fs.readdirSync(scope))
        if (!s.startsWith('.')) out.push(`node_modules/${n}/${s}`);
    } else out.push(`node_modules/${n}`);
  }
  return out;
}

/** lockDrift over every npm project of the family that has an installed tree, each finding prefixed with its project and the line that resyncs it. */
function installedDrift(entry: PinEntry, ctx: DriverContext): string[] {
  const out: string[] = [];
  for (const d of projectDirs(entry, ctx)) {
    const lock = path.join(d.abs, 'package-lock.json');
    const hidden = path.join(d.abs, 'node_modules/.package-lock.json');
    if (!fs.existsSync(lock) || !fs.existsSync(hidden)) continue;
    const found = lockDrift(
      fs.readFileSync(lock, 'utf8'),
      fs.readFileSync(hidden, 'utf8'),
      installedDirs(path.join(d.abs, 'node_modules'))
    );
    const dir = relDir(ctx, d.abs);
    if (found.length > 0)
      out.push(
        `${dir}: ${found.slice(0, 3).join(', ')}${found.length > 3 ? ` (+${found.length - 3})` : ''}; run (cd ${dir} && npx -y npm@${pinnedNpm(ctx.root)} ci${dir === '.' ? ' && npm run install:natives' : ''})`
      );
  }
  return out;
}

// ---- lockfiles ------------------------------------------------------------------------------

/** Every npm project directory the registry's family scopes, as (repo, dir within repo, absolute dir). */
function projectDirs(
  entry: PinEntry,
  ctx: DriverContext
): Array<{ repo: string; dir: string; abs: string }> {
  const out: Array<{ repo: string; dir: string; abs: string }> = [];
  const absent: string[] = [];
  for (const sc of entry.scope ?? []) {
    if (sc.scanner !== 'npm-lockfile') continue;
    const base = path.join(ctx.root, sc.repo);
    if (!fs.existsSync(base)) {
      absent.push(sc.repo);
      continue;
    }
    for (const pat of sc.files)
      for (const f of globSync(pat, { cwd: base, posix: true }).sort(
        (a, b) => Number(a > b) - Number(a < b)
      )) {
        const dir = path.posix.dirname(f) === '.' ? '' : path.posix.dirname(f);
        out.push({ repo: sc.repo, dir, abs: path.join(base, dir) });
      }
  }
  // VACUOUS guard: a family that scopes npm lockfiles yet enumerates none would let every plan and every removal report "nothing to do" over an empty corpus.
  if (out.length === 0 && (entry.scope ?? []).some((sc) => sc.scanner === 'npm-lockfile'))
    throw new PlanRefused(
      `${entry.id}: VACUOUS: the npm-lockfile scope matched no package-lock.json under ${ctx.root}${absent.length > 0 ? ` (repo checkout absent: ${absent.join(', ')})` : ''}, so nothing was judged`
    );
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
  const kept = lines.filter((_, i) => !drop.has(i));
  // An array whose last entry went leaves a dangling comma on the entry before it; any other array keeps its commas.
  if (/^\s*\]/.test(lines[idx + 1] ?? '')) {
    let p = commentStart - 1;
    while (p >= 0 && (lines[p].trim().startsWith('//') || lines[p].trim() === '')) p--;
    if (p >= 0) kept[p] = kept[p].replace(/,\s*$/, '');
  }
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
  for (const d of dirs) {
    const hasManifest = new Map<string, boolean>();
    // build/ and coverage/ are output only beside a package.json, the directory that builds them, at any depth (a workspace member's output is walked from the root scan too); a source folder that happens to be named build/ elsewhere still counts.
    const isOutput = (rel: string): boolean => {
      const parts = rel.split('/');
      for (let i = 0; i < parts.length - 1; i++) {
        if (parts[i] !== 'build' && parts[i] !== 'coverage') continue;
        const owner = parts.slice(0, i).join('/');
        let has = hasManifest.get(owner);
        if (has === undefined) {
          has = fs.existsSync(path.join(d, owner, 'package.json'));
          hasManifest.set(owner, has);
        }
        if (has) return true;
      }
      return false;
    };
    for (const f of globSync(['**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}'], {
      cwd: d,
      posix: true,
      // Dot directories (.ci/, .storybook/) hold sources too, except the generated ones named here.
      dot: true,
      // dist/ and the generated dot directories are skipped at any depth.
      ignore: [
        '**/node_modules/**',
        '**/dist/**',
        '**/.git/**',
        '**/.astro/**',
        '**/.wrangler/**',
        '**/.next/**',
        '**/.turbo/**',
        '**/.svelte-kit/**',
        '**/.vite/**',
        '**/.cache/**',
        '**/.build_cache/**',
        '**/.ci/cache/**',
      ],
    }).sort((a, b) => Number(a > b) - Number(a < b)))
      if (!isOutput(f) && re.test(fs.readFileSync(path.join(d, f), 'utf8')))
        out.push(path.join(d, f));
  }
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
      for (const d of globSync(g, { cwd: pr.abs, posix: true }).sort(
        (a, b) => Number(a > b) - Number(a < b)
      )) {
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
      const isKey = (k: string): boolean => k === pkg || k.startsWith(`${pkg}@`);
      if (`${JSON.stringify(doc, null, 2)}\n` !== text) {
        // A manifest that cannot be rewritten byte-faithfully must not leave its override behind in silence.
        if (['overrides', '_overridesReasons'].some((f) => Object.keys(doc[f] ?? {}).some(isKey)))
          throw new PlanRefused(
            `remove ${pkg}: ${keyOf(p)} holds an override for it but is not in npm's two-space form; reformat it first`
          );
        continue;
      }
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
