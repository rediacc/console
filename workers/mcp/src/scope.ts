/**
 * The part of a grant's scope that shapes `tools/list` (agent/plans/PLAN-rmcp-remote-worker.md Design 2, the `scope_json` column of PLAN-rmcp-agent-grants.md).
 *
 * The read-only flag and the tool allowlist shape the listing and refuse a `tools/call` outside it (`scopeAdmitsTool`). The machine and repo globs do neither here: this Worker sees only a call's raw arguments, not the machine and repository it resolves to, so the globs travel with the grant to the executor's grant session (PLAN-rmcp-agent-grants.md Design 4 hands it the scope) and are applied where the call resolves.
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

/** The grant a request runs under, once its credential has been resolved (the account Worker's `resolveGrant` answer, Design 4). */
export interface GrantContext {
  grantId: string;
  scope: GrantScope;
  /** The grant's org and its executor placement: where a `tools/call` runs. */
  orgId: string;
  placement: number;
  /** The org's executor tier; a missing tier is `standard`. */
  tier?: string;
}

interface ScopedTool {
  name: string;
  annotations: { readOnlyHint: boolean };
}

/** Does `scope` admit `tool`: into the listing, and as the target of a `tools/call`? */
export function scopeAdmitsTool(scope: GrantScope, tool: ScopedTool): boolean {
  if (scope.readOnly && !tool.annotations.readOnlyHint) return false;
  return scope.tools === null || scope.tools.includes(tool.name);
}
