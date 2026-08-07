/**
 * Thrown when a version string cannot be read as a dotted numeric version.
 *
 * WHY THIS TYPE EXISTS. `compareVersions` used to answer `0` -- "these are the
 * same version" -- for any input whose segments were not numbers, because
 * `Number('x')` is `NaN` and `NaN` is neither `<` nor `>` anything, so the loop
 * fell through to the equal case. Measured before the fix:
 * `('1.2.16', '1.2.x') === 0`, `('x.y.z', '1.2.16') === 0`,
 * `('garbage', 'garbage') === 0`.
 *
 * Every caller reads `0` as "same version": the CLI updater treats it as
 * "already current", the background updater skips staging, and the account
 * server's minimum-version gate lets the client through. So one malformed
 * version in a release manifest told every client it was up to date, forever,
 * and a malformed client version bypassed the minimum-version gate -- both
 * silently, both indistinguishable from the healthy answer.
 *
 * "I cannot tell" is not "equal". It is an error, and it is now raised as one.
 */
export class InvalidVersionError extends Error {
  constructor(public readonly version: string) {
    super(`Invalid version string: ${JSON.stringify(version)}`);
    this.name = 'InvalidVersionError';
  }
}

/** Version core after stripping a leading `v`, build metadata, and any pre-release suffix. */
function versionCore(v: string): string {
  return v.replace(/^v/, '').replace(/\+.*$/, '').replace(/-.*$/, '');
}

/**
 * True when `v` is a version this module can compare: one or more dot-separated
 * runs of digits, optionally prefixed with `v` and/or carrying a pre-release or
 * build suffix (both of which are ignored by the comparison).
 *
 * Use this to branch on untrusted input instead of catching InvalidVersionError.
 */
export function isValidVersion(v: string): boolean {
  return /^\d+(\.\d+)*$/.test(versionCore(v));
}

/**
 * Compare two semantic versions.
 * Returns -1 if a < b, 0 if equal, 1 if a > b.
 * Strips 'v' prefix. Ignores pre-release suffixes (e.g., -dev) and build metadata.
 *
 * @throws {InvalidVersionError} if either side is not a dotted numeric version.
 * A version that cannot be parsed is never reported as equal -- see the note on
 * InvalidVersionError for what that silence used to cost.
 */
export function compareVersions(a: string, b: string): number {
  if (!isValidVersion(a)) throw new InvalidVersionError(a);
  if (!isValidVersion(b)) throw new InvalidVersionError(b);

  const clean = (v: string) => versionCore(v).split('.').map(Number);

  const pa = clean(a);
  const pb = clean(b);

  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] ?? 0;
    const nb = pb[i] ?? 0;
    if (na < nb) return -1;
    if (na > nb) return 1;
  }
  return 0;
}
