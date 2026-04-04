/**
 * Compare two semantic versions.
 * Returns -1 if a < b, 0 if equal, 1 if a > b.
 * Strips 'v' prefix. Ignores pre-release suffixes (e.g., -dev).
 */
export function compareVersions(a: string, b: string): number {
  const clean = (v: string) => v.replace(/^v/, '').replace(/-.*$/, '').split('.').map(Number);

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
