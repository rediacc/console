/**
 * The driver seam of `npm run pins`: what a driver answers, and the leaf planner every leaf
 * driver shares (agent/plans/PLAN-pins-command.md Design 3).
 *
 * A DRIVER KNOWS ONE KIND OF PIN, and only two things about it: where the newest releases
 * are read (`inspect`), and what a bump to one of them writes (`plan`). Everything around
 * those two is the core's, so no driver can skip it: the release-age judgement, the hold
 * check, the dirty-site refusal, the journal, the derive steps, the canonical lockfile pass,
 * the gate run and the compare-and-restore (scripts/lib/pins/txn.ts). A driver PLANS and
 * never writes: its plan is file contents in memory plus commands with declared writes, and
 * the transaction is the only code that touches the tree.
 *
 * THE DRIVERS. `npm` (T4, T6), `embed`, `devcontainer` and `toolchain` (T7), `actions`,
 * `go-mod`, `os-ceph-host`, `ceph-image`, `real-provider` and `docker` (T8) register here
 * through DRIVER_TABLE as they land. Until a driver lands, every entry it serves answers
 * "not compared" and its bump is refused, which is the fail-closed reading of a pin nobody
 * can judge. The fixture driver below is the one implementation this file carries: it reads
 * releases from a fixture file and plans through the shared leaf planner, so the selftest
 * drives the whole transaction without a network or a real driver.
 *
 * A FAMILY DRIVER (npm, go-mod, actions) answers `inspect` with one synthetic release that
 * stands for "every member's newest eligible version", and its `plan` returns the commands
 * that move them (an npm update under the pinned npm, a `go get`). The core treats it the
 * same way: it judges the synthetic release's publish time, journals the declared writes and
 * runs the canonical lockfile pass over every lockfile the commands touched.
 */
import fs from 'node:fs';
import path from 'node:path';
import type { Driver, PinEntry, PinRegistry, PinSite, RepoPath } from './registry.js';
import { jsonPointer, siteRegex } from './registry.js';

/** One release a source answered, newest first in an Inspection. */
export interface Release {
  version: string;
  /** Publish instant in epoch ms; null when the source carries no date (judged per the entry's safety mode). */
  publishedMs: number | null;
  /**
   * A driver whose safety is not `release-age` (mirror-tag, same-host-version) judges the
   * release itself and says so here; the core reads the release-age window only when this is
   * absent. `why` is printed beside a refusal.
   */
  verdict?: { eligible: boolean; why: string };
  /**
   * The driver's own rule says this release opens a BREAKING line though its leading number is
   * the pinned one's (a Go minor line, 1.26 -> 1.27, changes the `go` directive of every go.mod).
   * scripts/lib/pins/status.ts treats it exactly as a major: a plain bump, `bump --all` and
   * `apply-soaked` never take it, `bump <id> --major --reason "<why>"` does, and the newer-majors
   * report ages it as the line `line`. `why` is printed beside the refusal.
   */
  breaking?: { line: string; why: string };
}

export interface Inspection {
  /** The value the tree pins today (the first `version` site for a leaf). */
  current: string | null;
  /** Releases newer than `current`, newest first. Empty: the pin is current. */
  releases: Release[];
}

/** A file's planned contents. `after` is the whole file, text. */
export interface FileWrite extends RepoPath {
  after: string;
}

/** A command the transaction runs after the writes, and the files it may write. */
export interface PlanStep {
  label: string;
  /** A shell command line, run by bash from `cwd`. */
  run: string;
  /** Directory relative to the console root. */
  cwd: string;
  writes: RepoPath[];
}

export interface PinPlan {
  entry: PinEntry;
  from: string | null;
  to: Release;
  writes: FileWrite[];
  steps: PlanStep[];
  /** One line per rewritten site, for `plan` and the message drafts. */
  changes: string[];
}

/** What a driver reads through: the console root, the registry and an overlay of planned writes. */
export interface DriverContext {
  root: string;
  reg: PinRegistry;
  /** A file's text as the plan so far would leave it; null when absent. */
  read(p: RepoPath): string | null;
  /** The fixture, when PINS_ROOT and PINS_FIXTURE are both set (the selftest's seam). */
  fixture: Fixture | null;
  /** Set only under a fixture: the selftest's mutants. */
  mutant: Mutant | null;
}

/** The plan refuses this pin; nothing has been written. */
export class PlanRefused extends Error {}

export interface PinDriver {
  name: Driver;
  inspect(entry: PinEntry, ctx: DriverContext): Promise<Inspection>;
  /** `also` carries the further releases of a multi-`--to` selection; only a driver whose releases converge as a set (npm majors) accepts any. */
  plan(entry: PinEntry, to: Release, ctx: DriverContext, also?: Release[]): Promise<PinPlan>;
  /** The key a hold of this entry writes into its first `holds` file; null when the driver has no hold. */
  holdKey(entry: PinEntry): string | null;
}

/**
 * The selftest's mutants. Each disables one safety property, and the selftest proves the
 * case that relies on it goes red:
 *   skip-site      the leaf planner drops the last site of an entry
 *   ignore-soak    the core takes the newest release whatever its age
 *   no-canonical   the canonical lockfile pass is skipped
 *   partial-write  the leaf planner writes each site to disk as it plans it
 *   no-dirty-check the refusal of a site file holding another session's changes is off
 *   no-restore     a failed run keeps what it wrote
 *   blind-restore  a failed run restores every journaled file without comparing bytes
 *   first-eligible a run may leave a pending held major behind, and `--major` may take no major
 *                  (the selection before 2026-10-15, which planned only the in-range batch)
 *   no-resync      a failed run that restored a lockfile leaves the installed tree as the run
 *                  left it, so the next plan reads versions the lockfile no longer names
 *   all-gates      a red gate run names every gate it ran as failed, not the ones that failed
 *   silent-ungated a run over a pin whose entry names no gate prints and journals nothing about it
 *                  (the output before 2026-10-15, when `bump --all` showed no gate line at all)
 *   tree-diff-attribution  the generated-docs pass attributes to the run every file the tree
 *                  diff shows, not only the files the generator reports writing
 *   shared-message every repository's draft carries the whole run's subject, release lines,
 *                  sites and commands, not only its own
 *   no-manifest-pin a moved syncpack pin group leaves the manifests it covers on the old range
 *                  (the sync before 2026-10-19, 394935a1f)
 *   no-version-gate a plan that writes a manifest or .syncpackrc.json runs only its entry's own
 *                  gates, without check:version (the gate list before 2026-10-19)
 *   breaking-is-minor a release a driver marks breaking (a Go minor line) is judged by its
 *                  leading number alone, so a plain bump and apply-soaked take it
 *   breaking-unlisted the newer-majors report leaves out a line a driver marks breaking, so
 *                  status and check:ci-pin-freshness never age it
 */
export const MUTANTS = [
  'skip-site',
  'ignore-soak',
  'no-canonical',
  'partial-write',
  'no-dirty-check',
  'no-restore',
  'blind-restore',
  'first-eligible',
  'no-resync',
  'all-gates',
  'silent-ungated',
  'tree-diff-attribution',
  'shared-message',
  'no-manifest-pin',
  'no-version-gate',
  'breaking-is-minor',
  'breaking-unlisted',
] as const;
export type Mutant = (typeof MUTANTS)[number];

/** True for a path syncpack judges: a package.json or the .syncpackrc.json itself. */
const syncpackJudged = (p: RepoPath): boolean =>
  path.posix.basename(p.file) === 'package.json' ||
  (p.repo === '.' && p.file === '.syncpackrc.json');

/**
 * A plan that writes a manifest or .syncpackrc.json, by a planned write or a step's declared
 * write, runs `check:version` beside its entry's gates (worklist #3fc8b8cb): on 2026-10-19 a
 * `bump npm` moved a syncpack pin and its gates (check:deps, check:ci-lockfile) passed, and the
 * DiffersToPin it left surfaced only in the next ci:quick. `no-version-gate` is the mutant that
 * leaves the gate list alone.
 */
export function withManifestGates(plan: PinPlan, mutant: Mutant | null = null): PinPlan {
  if (mutant === 'no-version-gate' || plan.entry.gates.includes('check:version')) return plan;
  const touched = [...plan.writes, ...plan.steps.flatMap((s) => s.writes)];
  if (!touched.some(syncpackJudged)) return plan;
  return { ...plan, entry: { ...plan.entry, gates: [...plan.entry.gates, 'check:version'] } };
}

// ---- the shared leaf planner ----------------------------------------------------------------

const absOf = (root: string, p: RepoPath): string => path.join(root, p.repo, p.file);
export const keyOf = (p: RepoPath): string => (p.repo === '.' ? p.file : `${p.repo}/${p.file}`);

/** Set a JSON pointer's string value, refusing a file whose formatting would not survive. */
function setJson(text: string, pointer: string, value: string, where: string): string {
  const doc = JSON.parse(text) as unknown;
  if (`${JSON.stringify(doc, null, 2)}\n` !== text)
    throw new PlanRefused(
      `${where}: the file is not 2-space JSON with a trailing newline, so a rewrite would reformat it`
    );
  const parts = pointer.split('/').slice(1);
  const last = parts.pop() as string;
  const parent = jsonPointer(doc, parts.length ? `/${parts.join('/')}` : '');
  if (
    parent === null ||
    typeof parent !== 'object' ||
    typeof jsonPointer(doc, pointer) !== 'string'
  )
    throw new PlanRefused(`${where}: ${pointer} is not a string value`);
  (parent as Record<string, unknown>)[last.replace(/~1/g, '/').replace(/~0/g, '~')] = value;
  return `${JSON.stringify(doc, null, 2)}\n`;
}

/** Replace every `value` group of a line-based site; the match count is checked by the caller. */
function rewriteRegexSite(text: string, site: PinSite, value: string): string {
  const re = siteRegex(site, 'gmd') as RegExp;
  let out = '';
  let at = 0;
  for (const m of text.matchAll(re)) {
    const span = m.indices?.groups?.value;
    if (!span) continue;
    out += text.slice(at, span[0]) + value;
    at = span[1];
  }
  return out + text.slice(at);
}

/** Count a site's matches in `text`, the same way check:ci-pin-registry counts them. */
function countSite(text: string, site: PinSite): { n: number; values: string[] } {
  if (site.json !== undefined) {
    try {
      const v = jsonPointer(JSON.parse(text), site.json);
      return typeof v === 'string' ? { n: 1, values: [v] } : { n: 0, values: [] };
    } catch {
      return { n: 0, values: [] };
    }
  }
  const values = [...text.matchAll(siteRegex(site) as RegExp)].map((m) => m.groups?.value ?? '');
  return { n: values.length, values };
}

/** The value a leaf pins today: its first `version` site's match. */
export function leafCurrent(entry: PinEntry, ctx: DriverContext): string | null {
  const site = entry.sites.find((s) => s.role === 'version') ?? entry.sites[0];
  if (!site) return null;
  const text = ctx.read(site);
  return text === null ? null : (countSite(text, site).values[0] ?? null);
}

/**
 * Plan a leaf's site rewrites for `values` (role -> new value). Every site is checked
 * before any is planned: a site that does not match exactly `expect` times refuses the
 * WHOLE pin, so no bump ever leaves one site of three behind. Pure, apart from the
 * partial-write mutant, which writes as it goes to prove the selftest catches it.
 */
export function planLeafSites(
  entry: PinEntry,
  values: Record<string, string>,
  ctx: DriverContext
): { writes: FileWrite[]; changes: string[] } {
  let sites = entry.sites;
  if (ctx.mutant === 'skip-site') sites = sites.slice(0, -1);
  const texts = new Map<string, { p: RepoPath; text: string }>();
  const changes: string[] = [];
  for (const [i, site] of sites.entries()) {
    const k = keyOf(site);
    const where = `${entry.id} site ${i} (${k}, ${site.role})`;
    const cur = texts.get(k)?.text ?? ctx.read(site);
    if (cur === null) throw new PlanRefused(`${where}: the file does not exist`);
    const value = values[site.role];
    if (value === undefined)
      throw new PlanRefused(`${where}: the ${entry.driver} driver supplied no value for this role`);
    const { n, values: was } = countSite(cur, site);
    if (n !== site.expect)
      throw new PlanRefused(
        `${where}: matches ${n} time(s), the registry expects ${site.expect}; nothing is written for ${entry.id}`
      );
    const next =
      site.json !== undefined
        ? setJson(cur, site.json, value, where)
        : rewriteRegexSite(cur, site, value);
    texts.set(k, { p: { repo: site.repo, file: site.file }, text: next });
    changes.push(`${k}: ${site.role} ${was[0]} -> ${value}${n > 1 ? ` (${n} lines)` : ''}`);
    // tree-write: safe the partial-write mutant, set only under a PINS_ROOT and PINS_FIXTURE fixture tree (pins.ts makeWorld refuses it otherwise), so ctx.root is that fixture
    if (ctx.mutant === 'partial-write') fs.writeFileSync(absOf(ctx.root, site), next);
  }
  return {
    writes: [...texts.values()].map(({ p, text }) => ({ ...p, after: text })),
    changes,
  };
}

// ---- the fixture driver ---------------------------------------------------------------------

/**
 * The selftest's fixture (PINS_FIXTURE, honoured only with PINS_ROOT): the releases each
 * entry's source would answer, the commands the stub runner answers, and the clock.
 */
export interface Fixture {
  /** ISO instant the run treats as now. */
  now: string;
  releases: Record<
    string,
    Array<{
      version: string;
      published: string | null;
      values?: Record<string, string>;
      breaking?: { line: string; why: string };
    }>
  >;
  /** Commands the stub runner answers: the first whose regex matches the command line wins; `out` is what it prints, and `events` the lines it writes to the file the command's `--events <file>` names. */
  commands: Array<{
    match: string;
    rc: number;
    writes?: Record<string, string>;
    out?: string;
    events?: string[];
  }>;
  /** Extra plan steps per entry id, for the lockfile and undeclared-write cases. */
  steps?: Record<string, PlanStep[]>;
  /**
   * Family entries the fixture answers, by id: the synthetic current, the in-range release (null when none is pending) and the releases; `held` marks a held major (the npm driver's blockKey null), which no run may leave behind. A plan writes `families/<id>.txt` listing the releases it took, one per line.
   */
  families?: Record<
    string,
    {
      current: string;
      inRange: string | null;
      releases: Array<{
        version: string;
        published: string | null;
        held?: boolean;
      }>;
    }
  >;
}

/**
 * Split the releases a family run takes into its in-range release and its majors, refusing any other, and refusing a run that leaves a held major behind: a held major (npm: no blocklist line) is what check:deps reds on as "awaiting a decision", and check:deps judges the whole tree, so such a run could only fail its gate (2026-10-15). The refusal names the one line that takes every held major with the rest. The npm driver plans through it, and so does the fixture family driver, so the selftest exercises the same acceptance. `lenient` is the first-eligible mutant.
 */
export function splitFamilySet(
  entryId: string,
  inRange: string | null,
  majorKeys: readonly string[],
  heldKeys: readonly string[],
  taken: readonly Release[],
  lenient = false
): { inRange: boolean; majors: string[] } {
  const bad = taken.filter((r) => r.version !== inRange && !majorKeys.includes(r.version));
  if (bad.length > 0)
    throw new PlanRefused(
      `${entryId}: ${bad.map((r) => r.version).join(', ')} ${bad.length > 1 ? 'are' : 'is'} neither the in-range release (${inRange ?? 'none pending'}) nor a pending major (${majorKeys.join(', ') || 'none'})`
    );
  const majors = [...new Set(taken.filter((r) => r.version !== inRange).map((r) => r.version))];
  const left = heldKeys.filter((k) => !majors.includes(k));
  if (left.length > 0 && !lenient)
    throw new PlanRefused(
      `${entryId}: ${left.length} held major(s) awaiting a decision (${left.join(', ')}) would stay behind, and the entry's gates judge the whole tree, so this run could only fail them; nothing is written. Take every held major with the in-range set: npm run pins -- bump ${entryId} ${heldKeys.map((k) => `--to ${k}`).join(' ')} --major --reason "<why now>" (or hold one with a BLOCKER line in its hold file)`
    );
  return { inRange: taken.some((r) => r.version === inRange), majors };
}

export function readFixture(file: string): Fixture {
  return JSON.parse(fs.readFileSync(file, 'utf8')) as Fixture;
}

/** One driver for every leaf under a fixture: releases from the fixture, sites through planLeafSites. */
function fixtureDriver(name: Driver): PinDriver {
  const releasesOf = (entry: PinEntry, ctx: DriverContext) =>
    (ctx.fixture as Fixture).releases[entry.id] ?? [];
  return {
    name,
    inspect(entry, ctx) {
      const current = leafCurrent(entry, ctx);
      const all = releasesOf(entry, ctx);
      const at = all.findIndex((r) => r.version === current);
      const newer = at < 0 ? all : all.slice(0, at);
      return Promise.resolve({
        current,
        releases: newer.map((r) => ({
          version: r.version,
          publishedMs: r.published === null ? null : Date.parse(r.published),
          ...(r.breaking ? { breaking: r.breaking } : {}),
        })),
      });
    },
    plan(entry, to, ctx) {
      const rel = releasesOf(entry, ctx).find((r) => r.version === to.version);
      const values = { version: to.version, ...(rel?.values ?? {}) };
      const { writes, changes } = planLeafSites(entry, values, ctx);
      return Promise.resolve({
        entry,
        from: leafCurrent(entry, ctx),
        to,
        writes,
        steps: (ctx.fixture as Fixture).steps?.[entry.id] ?? [],
        changes,
      });
    },
    holdKey: (entry) => entry.id.slice(entry.id.indexOf(':') + 1),
  };
}

/** One driver for every family under a fixture: releases from `fixture.families`, a plan that lists what it took. */
function fixtureFamilyDriver(name: Driver): PinDriver {
  const famOf = (entry: PinEntry, ctx: DriverContext) => {
    const fam = (ctx.fixture as Fixture).families?.[entry.id];
    if (!fam) throw new Error(`the fixture carries no family ${entry.id}`);
    return fam;
  };
  return {
    name,
    inspect(entry, ctx) {
      const fam = famOf(entry, ctx);
      return Promise.resolve({
        current: fam.current,
        releases: fam.releases.map((r) => ({
          version: r.version,
          publishedMs: r.published === null ? null : Date.parse(r.published),
        })),
      });
    },
    plan(entry, to, ctx, also = []) {
      const fam = famOf(entry, ctx);
      const majorKeys = fam.releases.map((r) => r.version).filter((v) => v !== fam.inRange);
      const set = splitFamilySet(
        entry.id,
        fam.inRange,
        majorKeys,
        fam.releases.filter((r) => r.held === true).map((r) => r.version),
        [to, ...also],
        ctx.mutant === 'first-eligible'
      );
      const taken = [...(set.inRange && fam.inRange ? [fam.inRange] : []), ...set.majors];
      return Promise.resolve({
        entry,
        from: fam.current,
        to,
        writes: [{ repo: '.', file: `families/${entry.id}.txt`, after: `${taken.join('\n')}\n` }],
        steps: [],
        changes: taken.map((v) => `take ${v}`),
      });
    },
    holdKey: () => null,
  };
}

/**
 * The real drivers, keyed by registry driver name. This module never imports a driver: the
 * drivers import it, so a table built here would be a cycle that breaks whichever module a
 * caller loads first. scripts/lib/pins/drivers/table.ts builds the table and the CLI hands
 * it in through registerDrivers once at startup; an entry with no registered driver answers
 * "not compared".
 */
let DRIVER_TABLE: Partial<Record<Driver, PinDriver>> = {};

export function registerDrivers(table: Partial<Record<Driver, PinDriver>>): void {
  DRIVER_TABLE = { ...DRIVER_TABLE, ...table };
}

/** The driver for an entry; under a fixture, the fixture driver for every leaf. */
export function driverFor(entry: PinEntry, ctx: DriverContext): PinDriver | null {
  if (ctx.fixture !== null) {
    if (entry.kind === 'leaf') return fixtureDriver(entry.driver);
    return ctx.fixture.families?.[entry.id] ? fixtureFamilyDriver(entry.driver) : null;
  }
  return DRIVER_TABLE[entry.driver] ?? null;
}
