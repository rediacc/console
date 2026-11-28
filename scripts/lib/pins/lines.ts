/**
 * The VERSION LINE of a pin: the part of a version a move inside of is routine, and a move out
 * of is a judgment call the grace clock of check:ci-pin-freshness ages (plan #ef324e18).
 *
 * WHY NOT THE FIRST NUMBER. A line keyed by the leading number alone made python 3.9 to 3.15,
 * golang 1.26 to 1.27 and otel-collector-contrib 0.111 to 0.166 one line each, so a pin sat
 * below six years of python lines without ever ageing. A line is the first `depth` parts of the
 * version, and the depth is a property of the upstream's numbering, not of the tag:
 *   - the top-level `lines` table of .ci/config/pins.json gives it per source, keyed
 *     `<source.type>:<image|package|repo|module>` with the `why` (python numbers its releases
 *     3.x, so depth 2; node numbers them 26, so depth 1). Every dockerhub leaf needs an entry,
 *     which scripts/lib/pins/registry.ts validates;
 *   - a source with no entry reads depth 1 (npm and PyPI semver);
 *   - a version whose first part is 0 reads at least depth 2 whatever the entry says, since a
 *     0.x minor is a breaking line (the same rule as scripts/lib/pins/soak.ts inRange);
 *   - a release a driver marks breaking (the Go toolchain) keeps the line it names
 *     (Release.breaking), which scripts/lib/pins/status.ts reads before this module.
 *
 * Pure. The mutants are check:ci-pin-freshness's: `first-number-only` keys every line by its
 * first number (the rule before this module), `zero-is-major` drops the 0.x rule.
 */
import type { PinEntry, PinRegistry, PinSource } from './registry.js';

/** One row of the `lines` table. */
export interface LineRule {
  /** How many leading parts of a version make its line, 1 to 3. */
  depth: number;
  /** Why this upstream's line is that deep. */
  why: string;
}

export const LINE_MUTANTS = ['first-number-only', 'zero-is-major'] as const;
export type LineMutant = (typeof LINE_MUTANTS)[number];

/** The `lines` key of a source: `<type>:<image|package|repo|module>`; null for a source that names none. */
export function lineSubject(src: PinSource): string | null {
  const name = src.image ?? src.package ?? src.repo ?? src.module;
  return typeof name === 'string' && name !== '' ? `${src.type}:${name}` : null;
}

/** The registry depth of an entry's source; undefined when the table has no row for it. */
export function lineDepthOf(reg: Pick<PinRegistry, 'lines'>, entry: PinEntry): number | undefined {
  const key = lineSubject(entry.source);
  return key === null ? undefined : reg.lines[key]?.depth;
}

/**
 * The leading version parts of a release label, as written (`04` stays `04`), after a docker
 * `<image>:` prefix (the text after the last colon), a re-digest `@<hex>` suffix and a `v`;
 * null when the label starts with no number (an npm family label such as `i18next@27`).
 */
export function versionParts(v: string): string[] | null {
  let tag = v.includes(':') ? v.slice(v.lastIndexOf(':') + 1) : v;
  const at = tag.indexOf('@');
  if (at > 0) tag = tag.slice(0, at);
  const m = /^v?(\d+(?:\.\d+)*)/.exec(tag);
  return m ? m[1].split('.') : null;
}

/** A version's line: its label (`3.10`) and the parts that make it. */
export interface Line {
  key: string;
  parts: string[];
}

/** The depth a version is read at: the rule's, at least 2 for a 0.x version, 1 under first-number-only. */
export function effectiveDepth(
  parts: string[],
  depth: number | undefined,
  mutant?: LineMutant
): number {
  if (mutant === 'first-number-only') return 1;
  const d = depth ?? 1;
  return Number(parts[0]) === 0 && mutant !== 'zero-is-major' ? Math.max(d, 2) : d;
}

/** The line of a release label at `depth` (the registry's, or undefined); null when the label carries no version. */
export function lineOf(v: string, depth: number | undefined, mutant?: LineMutant): Line | null {
  const parts = versionParts(v);
  if (parts === null) return null;
  const line = parts.slice(0, effectiveDepth(parts, depth, mutant));
  return { key: line.join('.'), parts: line };
}

/**
 * -1, 0 or 1 as line `a` sits below, on or above line `b`. Two lines whose shared leading parts
 * agree are ONE line: a floating `3` pin holds every 3.x, so 3.10 is no line above it.
 */
export function cmpLine(a: Line, b: Line): number {
  const n = Math.min(a.parts.length, b.parts.length);
  for (let i = 0; i < n; i++) {
    const d = Number(a.parts[i]) - Number(b.parts[i]);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  return 0;
}
