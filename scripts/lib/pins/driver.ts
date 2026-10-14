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
 */
export const MUTANTS = [
  'skip-site',
  'ignore-soak',
  'no-canonical',
  'partial-write',
  'no-dirty-check',
  'no-restore',
  'blind-restore',
] as const;
export type Mutant = (typeof MUTANTS)[number];

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
    Array<{ version: string; published: string | null; values?: Record<string, string> }>
  >;
  /** Commands the stub runner answers: the first whose regex matches the command line wins. */
  commands: Array<{ match: string; rc: number; writes?: Record<string, string> }>;
  /** Extra plan steps per entry id, for the lockfile and undeclared-write cases. */
  steps?: Record<string, PlanStep[]>;
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
  if (ctx.fixture !== null) return entry.kind === 'leaf' ? fixtureDriver(entry.driver) : null;
  return DRIVER_TABLE[entry.driver] ?? null;
}
