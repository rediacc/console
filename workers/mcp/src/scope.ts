/**
 * The part of a grant's scope that shapes `tools/list` (agent/plans/PLAN-rmcp-remote-worker.md Design 2, the `scope_json` column of PLAN-rmcp-agent-grants.md).
 *
 * The machine and repo globs bound `tools/call` arguments, not the listing, so the listing reads only the read-only flag and the tool allowlist.
 */

export interface GrantScope {
  /** Only tools whose annotations declare `readOnlyHint` are served. */
  readOnly: boolean;
  /** Tool names the grant admits; null admits every proxy-surface tool. */
  tools: readonly string[] | null;
  /** Machine name globs a call may name; null admits every machine. */
  machines: readonly string[] | null;
  /** Repository name globs a call may name; null admits every repository. */
  repos: readonly string[] | null;
}

/** The grant a request runs under, once its credential has been resolved. */
export interface GrantContext {
  grantId: string;
  scope: GrantScope;
}

interface ScopedTool {
  name: string;
  annotations: { readOnlyHint: boolean };
}

/** Does `scope` admit `tool` into the listing? */
export function scopeAdmitsTool(scope: GrantScope, tool: ScopedTool): boolean {
  if (scope.readOnly && !tool.annotations.readOnlyHint) return false;
  return scope.tools === null || scope.tools.includes(tool.name);
}
