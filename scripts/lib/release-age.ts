/**
 * Release-age freshness window — the shared TS soak used by every freshness gate
 * (npm deps in check-deps.ts, embedded-asset pins in check-embed-asset-freshness.ts).
 *
 * This is the TypeScript twin of the bash `is_release_deferred` in
 * .ci/scripts/lib/release-age.sh (which the audit + Go-dep gates use). Both read
 * the SAME source of truth — `minimum-release-age` in .npmrc — and both round the
 * window up to the next UTC day, so a version that ages past the base window on a
 * given UTC day becomes eligible together with every other such version at the
 * following midnight. That batches a day's upgrades into one surfacing instead of
 * trickling in one-at-a-time. Keep the two in sync.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_NPMRC = path.resolve(__dirname, '..', '..', '.npmrc');

/**
 * Read `minimum-release-age` (minutes) from .npmrc and return it in milliseconds.
 * NOTE: this is our CI-gate knob, NOT npm's native install guard (npm's real key
 * is `min-release-age`, in days); see the .npmrc comment. Returns 0 when the
 * setting is absent — the feature is then disabled (no deferral).
 */
export function getMinReleaseAgeMs(npmrcFile: string = DEFAULT_NPMRC): number {
  try {
    const content = fs.readFileSync(npmrcFile, 'utf-8');
    const m = content.match(/^\s*minimum-release-age\s*=\s*(\d+)/m);
    if (m) return Number(m[1]) * 60 * 1000;
  } catch {
    // No .npmrc — feature disabled.
  }
  return 0;
}

/** Epoch ms of 00:00:00 UTC on the day AFTER the day that contains `ms`.
 *  Module-private: only isWithinFreshnessWindow needs it. */
function startOfNextUtcDay(ms: number): number {
  const d = new Date(ms);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1);
}

/**
 * True when a release published at `publishedMs` is still within the freshness
 * window as of `nowMs` (i.e. too new to act on yet). Null-handling is the
 * CALLER's policy — this takes a concrete timestamp:
 *   - check-deps treats a null publish time as deferred (fail-closed: don't pull
 *     a version whose age is unknown);
 *   - the embed-asset freshness gate treats null as NOT deferred (fail-open: a
 *     stale pin from a dateless source, e.g. a plain git tag, must still surface).
 */
export function isWithinFreshnessWindow(
  publishedMs: number,
  nowMs: number,
  minReleaseAgeMs: number
): boolean {
  if (minReleaseAgeMs <= 0) return false;
  return nowMs < startOfNextUtcDay(publishedMs + minReleaseAgeMs);
}
