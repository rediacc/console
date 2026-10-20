/**
 * What `npm run pins -- status` answers for one pin, as a module that only READS: the driver
 * context over the tree, the hold a pin's first `holds` file records, and the view the soak
 * rule and the major rule make of the releases a driver found (agent/plans/PLAN-pins-command.md
 * Design 3).
 *
 * WHY IT IS ITS OWN MODULE. scripts/pins/pins.ts is the CLI, and its bump path journals and
 * writes the tree (scripts/lib/pins/txn.ts). check:ci-pin-freshness asks the same question
 * `status` asks and writes nothing, so it imports this module rather than the CLI, and its
 * import closure holds no writer (check:ci-gate-tree-writes reads that closure).
 *
 * THE NEWER MAJORS. Every view also carries the major lines above the pin (`majors`), each
 * with the first instant of the line the source dates, whatever the view's state, so a held
 * pin still says which major its hold is holding back. check:ci-pin-freshness turns a line
 * whose first release is MAJOR_GRACE_DAYS old red (operator ruling 2026-10-14T20:56Z); the
 * grace lives in .ci/config/pin-major-grace.json and is read by getMajorGraceMs below.
 */
import fs from 'node:fs';
import path from 'node:path';
import {
  type DriverContext,
  driverFor,
  type Fixture,
  type Inspection,
  keyOf,
  leafCurrent,
  type Mutant,
  type Release,
} from './driver.js';
import type { PinEntry, PinRegistry } from './registry.js';
import { inRange, judge, majorOf, type Verdict } from './soak.js';

/** The grace config, beside .ci/config/release-age.json. */
export const MAJOR_GRACE_CONFIG = '.ci/config/pin-major-grace.json';

/**
 * `major_grace_days` of .ci/config/pin-major-grace.json, in milliseconds. A missing file, a
 * missing key or a value that is not a positive integer THROWS: the release-age window reads
 * an absent config as "off", and an absent grace read the same way would wave every newer
 * major through, so this one fails closed.
 */
export function getMajorGraceMs(configFile: string): number {
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(configFile, 'utf8'));
  } catch (err) {
    throw new Error(`${configFile} is unreadable (${(err as Error).message})`);
  }
  const days =
    parsed !== null && typeof parsed === 'object'
      ? (parsed as Record<string, unknown>).major_grace_days
      : undefined;
  if (typeof days !== 'number' || !Number.isInteger(days) || days <= 0)
    throw new Error(`${configFile} carries no positive integer major_grace_days`);
  return days * 86_400_000;
}

/**
 * A release a driver dates by its major line as well as by itself. A docker tag is the case:
 * Docker Hub stamps a tag with its last push, so a floating `26-bookworm-slim` rebuilt last
 * week says nothing about when node 26 first shipped, and the docker driver supplies the
 * line's first instant from the other tags of the line (scripts/lib/pins/drivers/docker.ts).
 * Absent, the line is dated by the earliest `publishedMs` among its releases.
 */
export type LineDatedRelease = Release & { lineFirstMs?: number | null };

/** One major line above the pin. */
export interface NewerMajor {
  /** The line's leading number; null when a version on it carries none (it is its own line). */
  major: number | null;
  /** The breaking line a driver named (Release.breaking.line, e.g. Go `1.27`); absent for a line of a new leading number. */
  line?: string;
  /** The newest release on the line. */
  newest: string;
  /** The earliest instant the source dates on the line; null when it dates none. */
  firstMs: number | null;
  /** Some release on the line carries no date, so the line may be older than firstMs says. */
  partial: boolean;
}

/** The leading number of a version, after a docker `<image>:` prefix and a `v`; null when there is none. */
export function majorLineOf(v: string): number | null {
  const tag = v.includes(':') ? v.slice(v.lastIndexOf(':') + 1) : v;
  const m = /^v?(\d+)(?!\d)/.exec(tag);
  return m ? Number(m[1]) : null;
}

/**
 * The major lines above `insp.current`, newest first: each new leading number, and each line a
 * driver marks breaking (Release.breaking), keyed by the line it names. Pure; `ignoreBreaking`
 * is the selftest's breaking-unlisted mutant.
 */
export function newerMajors(insp: Inspection, ignoreBreaking = false): NewerMajor[] {
  const cur = insp.current === null ? null : majorLineOf(insp.current);
  const lines = new Map<string, NewerMajor>();
  for (const r of insp.releases as LineDatedRelease[]) {
    const m = majorLineOf(r.version);
    const brk = ignoreBreaking ? undefined : r.breaking;
    if (!brk && cur !== null && m !== null && m <= cur) continue;
    const key = brk ? `b:${brk.line}` : m === null ? `v:${r.version}` : `m:${m}`;
    const at = r.lineFirstMs !== undefined ? r.lineFirstMs : r.publishedMs;
    const line = lines.get(key) ?? {
      major: m,
      ...(brk ? { line: brk.line } : {}),
      newest: r.version,
      firstMs: null,
      partial: false,
    };
    if (at === null || Number.isNaN(at)) line.partial = true;
    else if (line.firstMs === null || at < line.firstMs) line.firstMs = at;
    lines.set(key, line);
  }
  return [...lines.values()].sort((a, b) => (b.major ?? -1) - (a.major ?? -1));
}

/** The part of a pins run a status needs: the root, the registry, the fixture seam and the clock. */
export interface StatusWorld {
  root: string;
  reg: PinRegistry;
  fixture: Fixture | null;
  mutant: Mutant | null;
  nowMs: number;
  windowMs: number;
}

export function contextOf(w: StatusWorld): DriverContext & { overlay: Map<string, string> } {
  const overlay = new Map<string, string>();
  return {
    root: w.root,
    reg: w.reg,
    fixture: w.fixture,
    mutant: w.mutant,
    overlay,
    read(p) {
      const hit = overlay.get(keyOf(p));
      if (hit !== undefined) return hit;
      const abs = path.join(w.root, p.repo, p.file);
      return fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
    },
  };
}

export interface Hold {
  file: string;
  key: string;
  reason: string;
  expires: string | null;
  expired: boolean;
  /** The 1-based line of the file that holds it, so a re-hold replaces it rather than adding a second. */
  line: number;
}

/**
 * The hold of an entry, read from its first `holds` file: a line whose first token is the
 * driver's key. When the key appears on more than one line, an unexpired line wins over an
 * expired one, so a hold renewed past its expiry is never shadowed by the line it replaced.
 */
export function holdOf(w: StatusWorld, entry: PinEntry, key: string | null): Hold | null {
  const file = entry.holds[0];
  if (!file || key === null) return null;
  const abs = path.join(w.root, file);
  if (!fs.existsSync(abs)) return null;
  const lines = fs.readFileSync(abs, 'utf8').split('\n');
  let found: Hold | null = null;
  for (const [i, line] of lines.entries()) {
    const t = line.trim();
    if (t === '' || t.startsWith('#') || t.split(/\s+/)[0] !== key) continue;
    const inline = /#\s*(.*)$/.exec(t)?.[1] ?? '';
    const reason =
      inline ||
      (lines[i - 1]?.trim().startsWith('#') ? lines[i - 1].trim().replace(/^#\s*/, '') : '');
    const expires = /expires (\d{4}-\d\d-\d\d)/.exec(reason)?.[1] ?? null;
    const hold: Hold = {
      file,
      key,
      reason,
      expires,
      expired: expires !== null && Date.parse(`${expires}T00:00:00Z`) <= w.nowMs,
      line: i + 1,
    };
    if (!hold.expired) return hold;
    found ??= hold;
  }
  return found;
}

/** Every repo (`.` or a submodule path) an entry reads or writes: its sites, family scopes and derive outputs. */
export function repoReach(entry: PinEntry): string[] {
  const repos = new Set<string>();
  for (const s of entry.sites) repos.add(s.repo);
  for (const sc of entry.scope ?? []) repos.add(sc.repo);
  for (const d of entry.derive) for (const wr of d.writes) repos.add(wr.repo);
  return [...repos].sort();
}

/** A submodule checkout is absent when its directory is missing or empty (what a CI checkout without `submodules:` leaves of a gitlink). */
function checkoutAbsent(root: string, repo: string): boolean {
  const dir = path.join(root, repo);
  if (!fs.existsSync(dir)) return true;
  return fs.statSync(dir).isDirectory() && fs.readdirSync(dir).length === 0;
}

/** The submodule paths `.gitmodules` declares; a registry repo outside this set is a typo or a plain directory, never an absent submodule. */
function declaredSubmodules(root: string): Set<string> {
  const f = path.join(root, '.gitmodules');
  if (!fs.existsSync(f)) return new Set();
  const paths = [...fs.readFileSync(f, 'utf8').matchAll(/^\s*path\s*=\s*(.+?)\s*$/gm)];
  return new Set(paths.map((m) => m[1]));
}

/** The declared submodules the entry reaches whose checkout is absent from `root`; empty for a pin whose every repo is present. */
export function absentSubmodules(root: string, entry: PinEntry): string[] {
  const declared = declaredSubmodules(root);
  return repoReach(entry).filter((r) => r !== '.' && declared.has(r) && checkoutAbsent(root, r));
}

export interface PinView {
  id: string;
  name: string;
  driver: string;
  state: 'current' | 'bumpable' | 'deferred' | 'held' | 'major-only' | 'not-compared';
  current: string | null;
  target: Release | null;
  /** The further releases of a multi-`--to` selection, planned in the same transaction as `target`. */
  also: Release[];
  /** The selection takes a major or out-of-range release (`--major` with a selection that takes none is refused by the CLI). */
  takesMajor: boolean;
  /** Every eligible major or out-of-range release the source answered, for the `--to` line of that refusal. */
  eligibleMajors: string[];
  /** The newest release inside the window, when one is. */
  deferred: (Release & { clearsAt: number | null }) | null;
  verdict: Verdict | null;
  hold: Hold | null;
  /** The major lines above the pin, newest first, read whatever the state (empty when not compared). */
  majors: NewerMajor[];
  detail: string;
  /** Set when the pin could not be compared AND it reaches a submodule absent from the checkout: the paths, so the run reports it NOT-CHECKED instead of refusing it. */
  notChecked: string[];
}

export interface SelectOpts {
  /** Release names to take; more than one is taken together (a family whose majors only converge as a set). */
  to?: string[];
  allowMajor?: boolean;
  onlyInRange?: boolean;
}

export async function viewOf(
  w: StatusWorld,
  ctx: DriverContext,
  entry: PinEntry,
  sel: SelectOpts = {}
): Promise<PinView> {
  const base: PinView = {
    id: entry.id,
    name: entry.name,
    driver: entry.driver,
    state: 'not-compared',
    current: entry.kind === 'leaf' ? leafCurrent(entry, ctx) : null,
    target: null,
    also: [],
    takesMajor: false,
    eligibleMajors: [],
    deferred: null,
    verdict: null,
    hold: null,
    majors: [],
    detail: '',
    notChecked: [],
  };
  const drv = driverFor(entry, ctx);
  if (!drv) {
    base.detail = `not compared: the ${entry.driver} driver has not landed (agent/plans/PLAN-pins-command.md T4-T8)`;
    base.notChecked = absentSubmodules(w.root, entry);
    return base;
  }
  let insp: Inspection;
  try {
    insp = await drv.inspect(entry, ctx);
  } catch (err) {
    const message = (err as Error).message;
    base.detail = `not compared: ${message}`;
    // Decided from the checkout, never from the message: drivers word a missing submodule differently (go_deps says "the scan lost private/", check-deps names every path), so a filter on the text refused go-mod in run 39392415656's case. A pin whose declared submodule is absent cannot be compared whatever the error says, and its message stays in `why`.
    base.notChecked = absentSubmodules(w.root, entry);
    return base;
  }
  base.current = insp.current;
  base.majors = newerMajors(insp, w.mutant === 'breaking-unlisted');
  base.hold = holdOf(w, entry, drv.holdKey(entry));
  if (insp.releases.length === 0) return { ...base, state: 'current', detail: 'current' };
  if (base.hold && !base.hold.expired)
    return { ...base, state: 'held', detail: `held in ${base.hold.file}: ${base.hold.reason}` };

  let pool = insp.releases;
  const wanted = sel.to !== undefined && sel.to.length > 0 ? sel.to : null;
  if (wanted) {
    pool = pool.filter((r) => wanted.includes(r.version));
    const missing = wanted.filter((v) => !pool.some((r) => r.version === v));
    if (missing.length > 0)
      return {
        ...base,
        detail: `not compared: ${missing.join(', ')} ${missing.length > 1 ? 'are' : 'is'} not among the releases newer than ${insp.current} the source answered`,
      };
  }
  // A release a driver marks breaking (a Go minor line) is a major whatever its leading number.
  const breaking = (r: Release): boolean =>
    r.breaking !== undefined && w.mutant !== 'breaking-is-minor';
  const isMajor = (r: Release): boolean => {
    if (breaking(r)) return true;
    const a = insp.current === null ? null : majorOf(insp.current);
    const b = majorOf(r.version);
    return a === null || b === null || a !== b;
  };
  const soak = (r: Release) => judge(entry, r, w.nowMs, w.windowMs, w.mutant === 'ignore-soak');
  base.eligibleMajors = insp.releases
    .filter((r) => isMajor(r) && soak(r).eligible)
    .map((r) => r.version);
  // A SET ENTRY (the npm family) converges only as a whole: its gate judges every member at once, so a run that takes a major takes the eligible in-range release with it (2026-10-15: oxc-parser 0.154 beside two in-range minors).
  const isSet = entry.driver === 'npm';
  const bumpable = (taken: Release[], why: string): PinView => {
    const withRange =
      isSet && taken.some(isMajor)
        ? insp.releases
            .filter((r) => !isMajor(r) && !taken.includes(r) && soak(r).eligible)
            .slice(0, 1)
        : [];
    const all = [...taken, ...withRange];
    return {
      ...base,
      state: 'bumpable',
      target: all[0],
      also: all.slice(1),
      takesMajor: all.some(isMajor),
      verdict: soak(all[0]),
      detail: `${insp.current} -> ${all.map((r) => r.version).join(' + ')}${why}`,
    };
  };
  if (wanted && wanted.length > 1) {
    if (entry.driver !== 'npm')
      return {
        ...base,
        detail: `not compared: several --to are taken together only by the npm driver, and ${entry.id} is ${entry.driver}`,
      };
    const taken: Release[] = [];
    for (const v of wanted) {
      const r = pool.find((x) => x.version === v) as Release;
      if (
        !(sel.onlyInRange
          ? !breaking(r) && inRange(insp.current, r.version)
          : sel.allowMajor || !isMajor(r))
      )
        return {
          ...base,
          state: 'major-only',
          detail: `${r.version} is a major or out-of-range release; \`bump ${entry.id} --major --reason "<why>"\``,
        };
      const j = soak(r);
      if (!j.eligible)
        return {
          ...base,
          state: 'deferred',
          deferred: { ...r, clearsAt: j.clearsAt },
          verdict: j,
          detail: `${insp.current} -> ${r.version} deferred: ${j.why}`,
        };
      taken.push(r);
    }
    return bumpable(taken, '');
  }
  const admitted = pool.filter((r) =>
    sel.onlyInRange
      ? !breaking(r) && inRange(insp.current, r.version)
      : sel.allowMajor || !isMajor(r)
  );
  for (const r of admitted) {
    const v = soak(r);
    if (v.eligible) return bumpable([r], ` (${v.why})`);
    if (!base.deferred) base.deferred = { ...r, clearsAt: v.clearsAt };
    base.verdict ??= v;
  }
  if (base.deferred)
    return {
      ...base,
      state: 'deferred',
      detail: `${insp.current} -> ${base.deferred.version} deferred: ${base.verdict?.why}`,
    };
  const why =
    pool[0].breaking && w.mutant !== 'breaking-is-minor' ? `: ${pool[0].breaking.why}` : '';
  return {
    ...base,
    state: 'major-only',
    detail:
      entry.safety.major === 'refuse'
        ? `only a major or out-of-range release is newer (${pool[0].version}${why}); this pin refuses a major bump by its registry safety, so it moves by hand in its own change`
        : `only a major or out-of-range release is newer (${pool[0].version}${why}); \`bump ${entry.id} --major --reason "<why>"\``,
  };
}
