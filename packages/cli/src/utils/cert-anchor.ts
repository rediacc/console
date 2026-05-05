/**
 * Classify ACME certificate domain names by their *anchor* — the leftmost
 * meaningful label that ties the cert back to a resource in the operator's
 * config (a repository GUID, a repo name, or a machine name).
 *
 * Used by `rdc config prune` to decide which cached cert entries are dead
 * weight (anchor no longer in config) and which are still load-bearing.
 *
 * Naming conventions in this codebase:
 *
 *   *.<GUID>.<machine>.<baseDomain>          ← per-repo wildcard, GUID-form
 *   *.<repoName>.<machine>.<baseDomain>      ← per-repo wildcard, name-form
 *   *.<service>.<machine>.<baseDomain>       ← per-service subdomain
 *   *.<machine>.<baseDomain>                 ← machine-scoped wildcard
 *   *.<baseDomain>                           ← root wildcard
 *   <baseDomain>                             ← apex
 *   <singleLabel>.<baseDomain>               ← top-level service subdomain
 *
 * Anything that doesn't match a known shape is classified as `opaque` and
 * the caller treats it as load-bearing (we'd rather keep something we
 * don't understand than drop a live cert).
 */

const GUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export type CertAnchorKind =
  | 'guid' // *.<GUID>.<machine>.<baseDomain>
  | 'repo-name' // *.<repoName>.<machine>.<baseDomain>
  | 'machine' // *.<machine>.<baseDomain>
  | 'service' // *.<service>.<machine>.<baseDomain>
  | 'top-level' // <single>.<baseDomain>
  | 'root' // *.<baseDomain>
  | 'apex' // <baseDomain>
  | 'opaque'; // anything we don't recognize

export interface CertAnchor {
  kind: CertAnchorKind;
  /** The GUID, repo name, machine name, or service name — depending on `kind`. */
  anchor?: string;
  /** Machine label, when relevant (for `guid`, `repo-name`, `service`, `machine`). */
  machine?: string;
  /** Original input, for diagnostics and round-tripping. */
  raw: string;
}

/**
 * Parse a cert domain name relative to a known `baseDomain`. The base must
 * match the suffix or the result is `opaque`.
 *
 * Pure function — no I/O, no allocations beyond the return object.
 */
function classifyWildcard(labels: string[], raw: string): CertAnchor {
  if (labels.length === 1) {
    return { kind: 'machine', anchor: labels[0], raw };
  }
  if (labels.length === 2) {
    const [head, machine] = labels;
    if (GUID_RE.test(head)) {
      return { kind: 'guid', anchor: head, machine, raw };
    }
    return { kind: 'repo-name', anchor: head, machine, raw };
  }
  return { kind: 'opaque', raw };
}

function classifyConcrete(labels: string[], raw: string): CertAnchor {
  if (labels.length === 1) {
    return { kind: 'top-level', anchor: labels[0], raw };
  }
  if (labels.length === 2) {
    const [service, machine] = labels;
    return { kind: 'service', anchor: service, machine, raw };
  }
  return { kind: 'opaque', raw };
}

export function parseCertAnchor(name: string, baseDomain: string): CertAnchor {
  const raw = name;
  if (!baseDomain) return { kind: 'opaque', raw };
  if (name === baseDomain) return { kind: 'apex', raw };

  const isWildcard = name.startsWith('*.');
  const remainder = isWildcard ? name.slice(2) : name;

  if (!remainder.endsWith(`.${baseDomain}`) && remainder !== baseDomain) {
    return { kind: 'opaque', raw };
  }
  if (isWildcard && remainder === baseDomain) {
    return { kind: 'root', raw };
  }

  const prefix = remainder.slice(0, remainder.length - baseDomain.length - 1);
  const labels = prefix.split('.');
  return isWildcard ? classifyWildcard(labels, raw) : classifyConcrete(labels, raw);
}
