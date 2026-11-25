/**
 * The credential of an MCP request (agent/plans/PLAN-rmcp-remote-worker.md Design 3 and 5).
 *
 * Two forms authenticate a grant. A headless client sends the agent bearer `rmcp_<grantId>.<base64url(S)>` in `Authorization: Bearer` or, with the same value, in `x-api-key`. An OAuth client sends an access token minted by this Worker's authorization server (RW-A1), whose props carry the grant id and `S`. Either way the Worker ends with the grant id and `S`, derives the auth tag from `S`, and resolves the grant with it, so the grant id in the path names a grant and never authenticates one.
 *
 * A credential in the query string is refused outright (D14: a URL is logged in full), whatever else the request carries.
 */
import {
  AGENT_BEARER_PREFIX,
  type AgentBearer,
  parseAgentBearer,
} from '../../../packages/shared/src/config-crypto/agent-grant.js';

/** What a request presents. */
export type Credential =
  | { kind: 'none' }
  | { kind: 'in-query' }
  /** An `rmcp_` bearer, from either header. */
  | { kind: 'agent'; bearer: string }
  /** Any other bearer: an OAuth access token. */
  | { kind: 'oauth'; token: string }
  /** A header that carries something but no usable bearer. */
  | { kind: 'malformed' };

/** Query parameter names that carry a credential in common clients. */
const CREDENTIAL_PARAMS: ReadonlySet<string> = new Set([
  'access_token',
  'token',
  'api_key',
  'apikey',
  'key',
  'bearer',
  'auth',
  'authorization',
]);

function credentialInQuery(url: URL): boolean {
  for (const [name, value] of url.searchParams) {
    if (CREDENTIAL_PARAMS.has(name.toLowerCase())) return true;
    if (value.startsWith(AGENT_BEARER_PREFIX)) return true;
  }
  return false;
}

function fromBearer(token: string): Credential {
  if (token === '') return { kind: 'malformed' };
  return token.startsWith(AGENT_BEARER_PREFIX)
    ? { kind: 'agent', bearer: token }
    : { kind: 'oauth', token };
}

/** Read the credential a request presents. `Authorization` wins over `x-api-key` when both are set. */
export function credentialOf(request: Request): Credential {
  if (credentialInQuery(new URL(request.url))) return { kind: 'in-query' };
  const authorization = request.headers.get('authorization');
  if (authorization !== null) {
    const match = /^Bearer\s+(\S+)\s*$/i.exec(authorization.trim());
    return match ? fromBearer(match[1]) : { kind: 'malformed' };
  }
  const apiKey = request.headers.get('x-api-key');
  if (apiKey !== null) {
    const value = apiKey.trim();
    return value.startsWith(AGENT_BEARER_PREFIX)
      ? { kind: 'agent', bearer: value }
      : { kind: 'malformed' };
  }
  return { kind: 'none' };
}

/** A parsed agent bearer and its secret in the base64url form the executor forward carries. */
export interface OpenedBearer extends AgentBearer {
  secretText: string;
}

/** Parse `rmcp_<grantId>.<base64url(S)>`; null for anything that is not exactly that form. */
export function openBearer(bearer: string): OpenedBearer | null {
  const parsed = parseAgentBearer(bearer);
  if (!parsed) return null;
  // parseAgentBearer accepts only canonical base64url of 32 bytes, so the text after the dot is that encoding.
  return { ...parsed, secretText: bearer.slice(bearer.indexOf('.') + 1) };
}

/** What the OAuth layer answers for an access token (RW-A1 supplies the check). */
export type AccessTokenCheck =
  | { status: 'valid'; grantId: string; secret: string }
  | { status: 'expired' }
  | { status: 'invalid' };

/** Check an access token presented for `resource` (the grant's canonical URL, the audience the token must name). */
export type VerifyAccessToken = (token: string, resource: string) => Promise<AccessTokenCheck>;
