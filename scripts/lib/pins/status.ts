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

/** The major lines above `insp.current`, newest first. Pure. */
export function newerMajors(insp: Inspection): NewerMajor[] {
  const cur = insp.current === null ? null : majorLineOf(insp.current);
  const lines = new Map<string, NewerMajor>();
  for (const r of insp.releases as LineDatedRelease[]) {
    const m = majorLineOf(r.version);
    if (cur !== null && m !== null && m <= cur) continue;
    const key = m === null ? `v:${r.version}` : `m:${m}`;
    const at = r.lineFirstMs !== undefined ? r.lineFirstMs : r.publishedMs;
    const line = lines.get(key) ?? { major: m, newest: r.version, firstMs: null, partial: false };
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

export interface PinView {
  id: string;
  name: string;
  driver: string;
  state: 'current' | 'bumpable' | 'deferred' | 'held' | 'major-only' | 'not-compared';
  current: string | null;
  target: Release | null;
  /** The further releases of a multi-`--to` selection, planned in the same transaction as `target`. */
  also: Release[];
  /** The newest release inside the window, when one is. */
  deferred: (Release & { clearsAt: number | null }) | null;
  verdict: Verdict | null;
  hold: Hold | null;
  /** The major lines above the pin, newest first, read whatever the state (empty when not compared). */
  majors: NewerMajor[];
  detail: string;
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
    deferred: null,
    verdict: null,
    hold: null,
    majors: [],
    detail: '',
  };
  const drv = driverFor(entry, ctx);
  if (!drv) {
    base.detail = `not compared: the ${entry.driver} driver has not landed (agent/plans/PLAN-pins-command.md T4-T8)`;
    return base;
  }
  let insp: Inspection;
  try {
    insp = await drv.inspect(entry, ctx);
  } catch (err) {
    base.detail = `not compared: ${(err as Error).message}`;
    return base;
  }
  base.current = insp.current;
  base.majors = newerMajors(insp);
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
  const isMajor = (r: Release): boolean => {
    const a = insp.current === null ? null : majorOf(insp.current);
    const b = majorOf(r.version);
    return a === null || b === null || a !== b;
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
      if (!(sel.onlyInRange ? inRange(insp.current, r.version) : sel.allowMajor || !isMajor(r)))
        return {
          ...base,
          state: 'major-only',
          detail: `${r.version} is a major or out-of-range release; \`bump ${entry.id} --major --reason "<why>"\``,
        };
      const j = judge(entry, r, w.nowMs, w.windowMs, w.mutant === 'ignore-soak');
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
    return {
      ...base,
      state: 'bumpable',
      target: taken[0],
      also: taken.slice(1),
      verdict: judge(entry, taken[0], w.nowMs, w.windowMs, w.mutant === 'ignore-soak'),
      detail: `${insp.current} -> ${taken.map((r) => r.version).join(' + ')}`,
    };
  }
  const admitted = pool.filter((r) =>
    sel.onlyInRange ? inRange(insp.current, r.version) : sel.allowMajor || !isMajor(r)
  );
  for (const r of admitted) {
    const v = judge(entry, r, w.nowMs, w.windowMs, w.mutant === 'ignore-soak');
    if (v.eligible)
      return {
        ...base,
        state: 'bumpable',
        target: r,
        verdict: v,
        detail: `${insp.current} -> ${r.version} (${v.why})`,
      };
    if (!base.deferred) base.deferred = { ...r, clearsAt: v.clearsAt };
    base.verdict ??= v;
  }
  if (base.deferred)
    return {
      ...base,
      state: 'deferred',
      detail: `${insp.current} -> ${base.deferred.version} deferred: ${base.verdict?.why}`,
    };
  return {
    ...base,
    state: 'major-only',
    detail:
      entry.safety.major === 'refuse'
        ? `only a major or out-of-range release is newer (${pool[0].version}); this pin refuses a major bump by its registry safety, so it moves by hand in its own change`
        : `only a major or out-of-range release is newer (${pool[0].version}); \`bump ${entry.id} --major --reason "<why>"\``,
  };
}
