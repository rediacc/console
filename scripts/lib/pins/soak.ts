/**
 * The soak judgement of `npm run pins`: which release a bump may take, and when a too-new
 * one clears. The rule itself lives once, in scripts/lib/release-age.ts; this module only
 * ASKS it, so `pins when` cannot name an instant the freshness gates would disagree with.
 */

import { isWithinFreshnessWindow } from '../release-age.js';
import type { Release } from './driver.js';
import type { PinEntry } from './registry.js';

const DAY_MS = 86_400_000;

/**
 * The first instant at which `isWithinFreshnessWindow` stops answering true for a release
 * published at `publishedMs`. The rule only ever clears at a UTC midnight, so the search
 * walks midnights from the publish day and asks the rule at each; it never computes the
 * instant itself. Null when the window is off (nothing is ever deferred).
 */
export function soakClearsAt(publishedMs: number, windowMs: number): number | null {
  if (!isWithinFreshnessWindow(publishedMs, publishedMs, windowMs)) return null;
  const first = Math.floor(publishedMs / DAY_MS) * DAY_MS + DAY_MS;
  for (let t = first; t <= publishedMs + windowMs + 2 * DAY_MS; t += DAY_MS)
    if (!isWithinFreshnessWindow(publishedMs, t, windowMs)) return t;
  throw new Error(
    `release-age answered deferred past every midnight after ${new Date(publishedMs).toISOString()}`
  );
}

export interface Verdict {
  eligible: boolean;
  why: string;
  /** When a deferred release clears; null when it is eligible or never will by age alone. */
  clearsAt: number | null;
}

/** An instant as ISO 8601 UTC, to the second (milliseconds too when nonzero), never rounded. */
export const iso = (ms: number): string => new Date(ms).toISOString().replace(/\.000Z$/, 'Z');

/**
 * Judge one release for one entry. A driver verdict (mirror-tag, same-host-version) wins;
 * otherwise the release-age window decides, and a release with no publish time is deferred
 * (fail closed: its age is unknown). `ignoreSoak` is the selftest's ignore-soak mutant.
 */
export function judge(
  entry: PinEntry,
  r: Release,
  nowMs: number,
  windowMs: number,
  ignoreSoak: boolean
): Verdict {
  if (ignoreSoak) return { eligible: true, why: 'MUTANT ignore-soak', clearsAt: null };
  if (r.verdict) return { eligible: r.verdict.eligible, why: r.verdict.why, clearsAt: null };
  if (entry.safety.mode !== 'release-age')
    return {
      eligible: false,
      why: `safety ${entry.safety.mode} needs the ${entry.driver} driver's own verdict, and it gave none`,
      clearsAt: null,
    };
  if (r.publishedMs === null)
    return { eligible: false, why: 'no publish time, so its age is unknown', clearsAt: null };
  if (!isWithinFreshnessWindow(r.publishedMs, nowMs, windowMs))
    return {
      eligible: true,
      why: `published ${iso(r.publishedMs)}, past the window`,
      clearsAt: null,
    };
  const clearsAt = soakClearsAt(r.publishedMs, windowMs);
  return {
    eligible: false,
    why: `published ${iso(r.publishedMs)}, inside the window until ${clearsAt === null ? '?' : iso(clearsAt)}`,
    clearsAt,
  };
}

/** The major component of a dotted version, ignoring a leading `v`; null when not numeric. */
export function majorOf(v: string): number | null {
  const m = /^v?(\d+)\./.exec(v) ?? /^v?(\d+)$/.exec(v);
  return m ? Number(m[1]) : null;
}

/**
 * True when `to` is a patch or an in-range minor of `from` (what `apply-soaked` takes): the
 * same major, or for a 0.x line the same minor too, since a 0.x minor is a breaking line.
 */
export function inRange(from: string | null, to: string): boolean {
  if (from === null) return false;
  const a = /^v?(\d+)\.(\d+)/.exec(from);
  const b = /^v?(\d+)\.(\d+)/.exec(to);
  if (!a || !b) return false;
  if (a[1] !== b[1]) return false;
  return a[1] !== '0' || a[2] === b[2];
}
