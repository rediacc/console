/**
 * Debug logging, gated by the single `REDIACC_DEBUG` env var.
 *
 * Semantics:
 *   - unset / empty: everything off.
 *   - `1` or `*`: every scope and general (unscoped) logging on.
 *   - comma list (e.g. `daemon,timing`): the listed scopes are on; general
 *     (unscoped) logging is also on when the var is non-empty — any debug
 *     intent enables baseline logging.
 *
 * Known scopes: `daemon`, `renet`, `timing`, `otel`.
 */
export function debugEnabled(scope?: string): boolean {
  const raw = process.env.REDIACC_DEBUG;
  if (!raw) return false;

  const value = raw.trim();
  if (value === '') return false;

  // `1` or `*` enables everything (scoped and unscoped).
  if (value === '1' || value === '*') return true;

  // Non-empty value: unscoped (general) logging is always on.
  if (scope === undefined) return true;

  const scopes = value.split(',').map((s) => s.trim());
  return scopes.includes(scope) || scopes.includes('*');
}

/**
 * Debug logging helper — outputs when `REDIACC_DEBUG` enables the given scope
 * (or general logging when no scope is passed).
 */
export function debugLog(message: string, scope?: string): void {
  if (debugEnabled(scope)) {
    console.warn(`[DEBUG] ${message}`);
  }
}
