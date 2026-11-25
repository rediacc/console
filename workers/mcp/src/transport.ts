/**
 * The MCP transport of the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 1).
 *
 * One SDK v2 `createMcpHandler` per isolate, stateless, JSON responses, with the stateless legacy leg so 2025-revision clients still connect. In front of it, in this order: the route (`/g/<grantId>`, anything else 404), GET and DELETE answered 405 (there is no session to stream or end), the Origin allowlist (403 on a browser origin outside it; native clients send none and pass), a credential in the query string (400), and the credential itself (src/credential.ts, Design 3 and 5): none, or an OAuth access token that is expired or not valid for this grant, gets 401 with `WWW-Authenticate: Bearer resource_metadata=...` so an OAuth client refreshes or signs in; an agent bearer naming another grant, an unknown grant and a wrong tag all get one bare 401 with no detail. The SDK's own ladder then checks the protocol headers against the body (`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`; a mismatch is 400 with -32020) and the content type.
 *
 * The resolved grant reaches the per-request server through `authInfo.extra`, which the SDK passes through untouched, so the server instance is built for exactly one grant's scope. `initialize`, `server/discover` and `tools/list` are answered from the shared registry and wake no container; `tools/call` is forwarded to the grant's org executor (src/call.ts).
 */
import {
  type AuthInfo,
  createMcpHandler,
  type McpRequestContext,
  originValidationResponse,
  Server,
} from '@modelcontextprotocol/server';
import { deriveAuthTag } from '../../../packages/shared/src/config-crypto/agent-grant.js';
import { type CallDeps, callTool, type GrantCaller } from './call.js';
import {
  type AccessTokenCheck,
  credentialOf,
  type OpenedBearer,
  openBearer,
  type VerifyAccessToken,
} from './credential.js';
import type { ExecutorBinding } from './executor.js';
import type { GrantContext } from './scope.js';
import { listGrantTools } from './tools.js';

/** The hosted clients whose browser origin may call the Worker; the Worker's own host joins them per region. */
export const HOSTED_CLIENT_ORIGINS: readonly string[] = ['claude.ai', 'chatgpt.com'];

/** How long a client may cache `tools/list` and `server/discover`: the listing changes only with a deploy or a scope edit. */
const LIST_TTL_MS = 60_000;

/** A grant id as it appears in the path. It names the grant; the bearer or the OAuth token authenticates it, and a request with neither is answered 401. */
const GRANT_PATH = /^\/g\/([A-Za-z0-9_-]{1,64})$/;

/** The account Worker's page where a grant that stopped serving is authorized again; the URL carries the grant id and nothing else. */
export const REAUTH_PATH = '/account/mcp/authorize';

/**
 * Resolve a grant from its id and the auth tag derived from the presented `S` (the account Worker's `resolveGrant`, Design 4). Null for an unknown grant and for a tag that does not match: the two must stay indistinguishable.
 */
export type ResolveGrant = (grantId: string, authTag: string) => Promise<GrantContext | null>;

export interface McpTransportOptions {
  /** The Worker's public host, e.g. mcp.eu.rediacc.cloud. */
  host: string;
  /** The version `server/discover` and `initialize` report. */
  serverVersion: string;
  /** The region's account origin, e.g. https://eu.rediacc.cloud: the host of every `reauthUrl`. */
  accountUrl: string;
  resolveGrant: ResolveGrant;
  /** The OAuth access-token check (RW-A1); without it every non-agent bearer is answered as an invalid token. */
  verifyAccessToken?: VerifyAccessToken;
  /** The `EXECUTOR` service binding a `tools/call` is forwarded over; a Worker deployed without it answers each call with SERVER_ERROR. */
  executor: ExecutorBinding | undefined;
  /** A fresh id per call; tests pin it. */
  newRequestId?: () => string;
}

export interface McpTransport {
  fetch: (request: Request) => Promise<Response>;
}

const GRANT_KEY = 'rediaccGrant';

function callerFrom(ctx: McpRequestContext): GrantCaller {
  const caller = ctx.authInfo?.extra?.[GRANT_KEY] as GrantCaller | undefined;
  if (!caller) throw new Error('the MCP server was built for a request with no resolved grant');
  return caller;
}

function buildServer(caller: GrantCaller, serverVersion: string, deps: CallDeps): Server {
  const server = new Server(
    { name: 'rdc', version: serverVersion },
    {
      capabilities: { tools: {} },
      cacheHints: {
        'tools/list': { ttlMs: LIST_TTL_MS, cacheScope: 'private' },
        'server/discover': { ttlMs: LIST_TTL_MS, cacheScope: 'private' },
      },
    }
  );
  const tools = listGrantTools(caller.grant.scope);
  server.setRequestHandler('tools/list', () => ({ tools }));
  server.setRequestHandler('tools/call', (request) =>
    callTool(deps, caller, request.params.name, request.params.arguments ?? {})
  );
  return server;
}

function plain(status: number, body: string, headers: Record<string, string> = {}): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/plain', ...headers } });
}

/** The answer for an unknown grant, a wrong tag, and a bearer for another grant: one body, no detail. */
function unauthorized(): Response {
  return plain(401, 'Unauthorized');
}

/** Where `reauthUrl` sends the user for `grantId`. */
export function reauthUrlFor(accountUrl: string, grantId: string): string {
  const url = new URL(REAUTH_PATH, accountUrl);
  url.searchParams.set('grant', grantId);
  return url.toString();
}

/** The 401 an OAuth client acts on: it names the grant's protected-resource metadata, where the authorization server is found. */
function challenge(host: string, grantId: string, error?: 'invalid_token'): Response {
  const metadata = `https://${host}/.well-known/oauth-protected-resource/g/${grantId}`;
  const detail = error ? `, error="${error}"` : '';
  return plain(401, 'Unauthorized', {
    'www-authenticate': `Bearer resource_metadata="${metadata}"${detail}`,
  });
}

/** The agent bearer an OAuth access token stands for, or the challenge that sends the client to refresh or sign in. */
function oauthBearer(
  options: McpTransportOptions,
  token: string,
  grantId: string
): Promise<OpenedBearer | Response> | Response {
  if (!options.verifyAccessToken) return challenge(options.host, grantId, 'invalid_token');
  const resource = `https://${options.host}/g/${grantId}`;
  return options.verifyAccessToken(token, resource).then((check: AccessTokenCheck) => {
    if (check.status !== 'valid' || check.grantId !== grantId) {
      return challenge(options.host, grantId, 'invalid_token');
    }
    return openBearer(`rmcp_${check.grantId}.${check.secret}`) ?? unauthorized();
  });
}

/** The agent bearer a request's credential stands for, or the response that refuses it. */
function bearerOf(
  options: McpTransportOptions,
  request: Request,
  grantId: string
): Promise<OpenedBearer | Response> | OpenedBearer | Response {
  const credential = credentialOf(request);
  switch (credential.kind) {
    case 'in-query':
      return plain(400, 'A credential in the query string is refused; send it in a header.');
    case 'none':
      return challenge(options.host, grantId);
    case 'malformed':
      return unauthorized();
    case 'agent': {
      const opened = openBearer(credential.bearer);
      return opened?.grantId === grantId ? opened : unauthorized();
    }
    case 'oauth':
      return oauthBearer(options, credential.token, grantId);
  }
}

/** The caller a request authenticates as, or the response that refuses it. */
async function callerOf(
  options: McpTransportOptions,
  request: Request,
  grantId: string
): Promise<GrantCaller | Response> {
  const bearer = await bearerOf(options, request, grantId);
  if (bearer instanceof Response) return bearer;
  const grant = await options.resolveGrant(bearer.grantId, await deriveAuthTag(bearer.secret));
  if (grant?.grantId !== bearer.grantId) return unauthorized();
  return { grant, secret: bearer.secretText };
}

/** The transport for one Worker: routing, method, Origin and credential checks in front of the SDK handler. */
export function createMcpTransport(options: McpTransportOptions): McpTransport {
  const allowedOrigins = [...HOSTED_CLIENT_ORIGINS, options.host];
  const deps: CallDeps = {
    executor: options.executor,
    newRequestId: options.newRequestId,
    reauthUrl: (grantId) => reauthUrlFor(options.accountUrl, grantId),
  };
  const handler = createMcpHandler(
    (ctx) => buildServer(callerFrom(ctx), options.serverVersion, deps),
    {
      legacy: 'stateless',
      responseMode: 'json',
    }
  );

  return {
    fetch: async (request) => {
      const match = GRANT_PATH.exec(new URL(request.url).pathname);
      if (!match) return plain(404, 'Not found');
      if (request.method === 'GET' || request.method === 'DELETE') {
        return plain(405, 'Method not allowed', { allow: 'POST' });
      }
      const rejected = originValidationResponse(request, allowedOrigins);
      if (rejected) return rejected;
      const caller = await callerOf(options, request, match[1]);
      if (caller instanceof Response) return caller;
      // The secret rides `extra` for this request's server only; `token` stays empty, so nothing the SDK logs or echoes holds it.
      const authInfo: AuthInfo = {
        token: '',
        clientId: caller.grant.grantId,
        scopes: [],
        extra: { [GRANT_KEY]: caller },
      };
      return handler.fetch(request, { authInfo });
    },
  };
}
