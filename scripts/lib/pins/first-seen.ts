/**
 * First-sight ledger for upstreams whose own date is a BUILD date, not the date the package
 * became installable (agent/plans/PLAN-ciquick-gate-contract.md K5).
 *
 * packages.msys2.org reports `build_date`, the instant the package was built; the package reached
 * the repository index days later (libzstd 1.6.0-1: built 2026-11-24, indexed 2026-11-28). Aging a
 * pin by the build date let a late-indexed package skip the release-age window. The window must run
 * from the first instant THIS repo saw the version in the index, so the read records that instant
 * here and ages the version from max(build date, first sight): a package built long ago that first
 * appears today is deferred; one whose recorded first sight is past the window is stale.
 *
 * The ledger is `.ci/cache/pins/first-seen.json` (gitignored scratch), so a gate run never writes the
 * tracked tree. A lost ledger (a fresh CI checkout) re-dates the version to today, which only defers
 * it further and so fails closed.
 */
import fs from 'node:fs';
import path from 'node:path';

export const FIRST_SEEN_REL = '.ci/cache/pins/first-seen.json';

export interface FirstSeenLedger {
  /** The recorded first sight of `key` in epoch ms, or null when the key was never seen. */
  get(key: string): number | null;
  /** Record the first sight of `key`; an existing record is never moved. */
  record(key: string, ms: number): void;
}

/** A ledger over the file under `root`; an unreadable or malformed file reads as empty. */
export function fileLedger(root: string): FirstSeenLedger {
  const file = path.join(root, FIRST_SEEN_REL);
  const load = (): Record<string, string> => {
    try {
      const doc: unknown = JSON.parse(fs.readFileSync(file, 'utf8'));
      return doc !== null && typeof doc === 'object' && !Array.isArray(doc)
        ? (doc as Record<string, string>)
        : {};
    } catch {
      return {};
    }
  };
  return {
    get(key) {
      const at = Date.parse(load()[key] ?? '');
      return Number.isNaN(at) ? null : at;
    },
    record(key, ms) {
      const doc = load();
      if (Date.parse(doc[key] ?? '') > 0) return;
      doc[key] = new Date(ms).toISOString();
      fs.mkdirSync(path.dirname(file), { recursive: true });
      // tree-write: safe the ledger is under .ci/cache, the gitignored scratch, never the tracked tree
      fs.writeFileSync(file, `${JSON.stringify(doc, null, 2)}\n`);
    },
  };
}

/**
 * The instant a version's release age runs from: the later of its build date and the first time the
 * index was seen to serve it. First sight is recorded now when the ledger has none. A null build
 * date stays null (an unknown age fails closed in the core).
 */
export function indexedAtMs(
  ledger: FirstSeenLedger,
  key: string,
  buildMs: number | null,
  nowMs: number
): number | null {
  if (buildMs === null) return null;
  let seen = ledger.get(key);
  if (seen === null) {
    ledger.record(key, nowMs);
    seen = nowMs;
  }
  return Math.max(buildMs, seen);
}
