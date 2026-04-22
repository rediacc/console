/**
 * Curated 301/410 redirect table — source of truth is ./redirects.json.
 *
 * This wrapper imports the JSON, compiles pattern regex once at module load,
 * and exports a typed resolver for the Worker fetch handler.
 *
 * Edit ./redirects.json (not this file) to add/remove entries. The CI check
 * `npm run check:ci-redirects` verifies every non-null `to` points to a live
 * page in packages/www/dist/route-manifest.json.
 */
import redirectsJson from './redirects.json';

export type RedirectTarget =
  | { to: string; status: 301; rationale: string }
  | { to: null; status: 410; rationale: string };

interface PatternRuleRaw {
  from: string;
  to: string | null;
  status: 301 | 410;
  rationale: string;
}

export interface PatternRule {
  re: RegExp;
  to: string | null;
  status: 301 | 410;
  rationale: string;
}

export interface RedirectsFile {
  exact: Record<string, RedirectTarget>;
  patterns: PatternRuleRaw[];
  /**
   * Paths that are live but NOT present in route-manifest.json — the Worker
   * serves them directly (SPA routes, file endpoints) or they're section
   * indexes the manifest generator skips. Used by the CI integrity check so
   * 301 targets pointing here don't fail validation.
   */
  allowed_non_manifest_targets: string[];
}

const typed = redirectsJson as RedirectsFile;

export const EXACT: Record<string, RedirectTarget> = typed.exact;

export const PATTERNS: PatternRule[] = typed.patterns.map((p) => ({
  re: new RegExp(p.from),
  to: p.to,
  status: p.status,
  rationale: p.rationale,
}));

export const ALLOWED_NON_MANIFEST_TARGETS: ReadonlySet<string> = new Set(
  typed.allowed_non_manifest_targets
);

/**
 * Resolve a path against the curated redirect table.
 *
 * Input path MUST be language-stripped and trailing-slash-stripped (caller
 * handles normalization). Returns the target + status, or null if no rule
 * matched (caller falls through to ASSETS).
 *
 * Exact lookup wins over pattern match — order is load-bearing. For example:
 *   /terms-of-service/acceptable-use-policy
 * matches BOTH the legal-concat pattern (→ $2 = dead /acceptable-use-policy)
 * AND an explicit 410 override in exact. Exact wins, so we correctly 410.
 */
export function applyRedirect(pathWithoutLang: string): {
  to: string | null;
  status: 301 | 410;
  via: 'exact' | 'pattern';
  rationale: string;
} | null {
  const exact = EXACT[pathWithoutLang];
  if (exact) {
    return { to: exact.to, status: exact.status, via: 'exact', rationale: exact.rationale };
  }

  for (const p of PATTERNS) {
    const m = pathWithoutLang.match(p.re);
    if (m) {
      const to = p.to === null ? null : p.to.replace(/\$(\d+)/g, (_, n) => m[Number(n)] ?? '');
      return { to, status: p.status, via: 'pattern', rationale: p.rationale };
    }
  }

  return null;
}
