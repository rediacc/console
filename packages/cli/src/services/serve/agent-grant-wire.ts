/**
 * The wire half of agent-grant-session.ts: the account's `agent-session` answer and policy-key shapes, and the pure readers over them (the grant secret, the overrides, the principal, the cache keys). Moved out so the session class stays under the line budget.
 */
import { AGENT_GRANT_SECRET_BYTES } from '@rediacc/shared/config-crypto';
import type { AgentGrantScopeAnswer } from './agent-grant-session.js';
import type { AgentGrantOverrides } from './policy.js';
import type { SessionPrincipal } from './sessions.js';

/** The 401 reasons a fresh open cures: the chain's token was spent, expired, or is unknown to the store. */
const REMINT_REASONS = new Set(['token_exhausted', 'token_expired', 'invalid_token']);

/** An override axis in the account's shape: exact names, every one, or nothing. */
type OverrideAxis = '*' | string[] | null;

/** One policy key wrapped for the grant: it opens the records of `policyConfigId` (team `policyTeamId`). */
export interface WrappedPolicyKey {
  policyConfigId: string;
  policyTeamId: string | null;
  wrapped: string;
}

/** The `agent-session` answer (private/account/src/dto/agent-grant.dto.ts `agentSessionResponse`). */
export interface AgentSessionAnswer {
  wrappedConfigKey: string;
  configKeyVersion: number;
  serverSecret: string;
  cekGeneration: number;
  storeId: string;
  configId: string;
  teamId: string | null;
  configToken: string;
  expiresAt: string;
  overrides: { grandRepos: OverrideAxis; clusterOps: OverrideAxis };
  scope: AgentGrantScopeAnswer;
  /** The policy keys wrapped for the grant: its own config's and the org-level config's. */
  policyKeys: WrappedPolicyKey[];
  /** The grant user's org role, email and team slug, read live by the account. */
  orgRole: SessionPrincipal['orgRole'];
  userEmail: string;
  teamSlug: string | null;
}

/** Strict base64url (no padding) of exactly 32 bytes, or null. Never echoes the input. */
export function parseSecret(text: string): Uint8Array | null {
  if (!/^[A-Za-z0-9_-]+$/.test(text) || text.length % 4 === 1) return null;
  const b64 = text.replaceAll('-', '+').replaceAll('_', '/');
  const bytes = Uint8Array.from(
    Buffer.from(b64 + '='.repeat((4 - (b64.length % 4)) % 4), 'base64')
  );
  if (bytes.byteLength !== AGENT_GRANT_SECRET_BYTES) return null;
  const canonical = Buffer.from(bytes)
    .toString('base64')
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '');
  return canonical === text ? bytes : null;
}

/** The overrides in the shape `authorize` reads (`AgentGrantOverrides`). */
export function overridesOf(answer: AgentSessionAnswer['overrides']): AgentGrantOverrides {
  const grand = answer.grandRepos;
  return {
    allowGrandRepos: grand === '*' ? true : (grand ?? false),
    allowClusterOps: answer.clusterOps === '*',
  };
}

/** Whether a store answer says the chain's token was spent, expired or unknown, which a fresh open cures. */
export function tokenLapsed(answer: { status: number; body: Record<string, unknown> }): boolean {
  const reason = typeof answer.body.code === 'string' ? answer.body.code : '';
  return answer.status === 401 && REMINT_REASONS.has(reason);
}

/** `${grantId}\0${version}`: the cache key of one decrypted document. */
export const documentKey = (grantId: string, version: number): string =>
  `${grantId}\u0000${version}`;

/** `${configId}\0${teamId}`: the lookup key of one pointer's policy key within a session. */
export const pointerKey = (configId: string, teamId: string | null): string =>
  `${configId}\u0000${teamId ?? ''}`;

/**
 * The principal an agent grant runs as: the grant user's org role, email and team slug, as the account
 * read them for this open. The user id stays the grant's, so the audit names the grant that acted.
 */
export function principalOf(
  orgId: string,
  grantId: string,
  answer: AgentSessionAnswer
): SessionPrincipal {
  return {
    orgId,
    teamId: answer.teamId,
    ...(answer.teamSlug ? { teamSlug: answer.teamSlug } : {}),
    userId: `agent-grant:${grantId}`,
    userEmail: answer.userEmail,
    orgRole: answer.orgRole,
    agentGrantId: grantId,
  };
}

export function isWrappedPolicyKey(entry: unknown): entry is WrappedPolicyKey {
  const item = entry as Partial<WrappedPolicyKey> | null;
  return (
    item !== null &&
    typeof item === 'object' &&
    typeof item.policyConfigId === 'string' &&
    (item.policyTeamId === null || typeof item.policyTeamId === 'string') &&
    typeof item.wrapped === 'string'
  );
}
