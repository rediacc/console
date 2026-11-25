/**
 * The MCP transport of the hosted Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 1).
 *
 * One SDK v2 `createMcpHandler` per isolate, stateless, JSON responses, with the stateless legacy leg so 2025-revision clients still connect. In front of it, in this order: the route (`/g/<grantId>`, anything else 404), GET and DELETE answered 405 (there is no session to stream or end), the Origin allowlist (403 on a browser origin outside it; native clients send none and pass), and grant resolution (a bare 401 when the grant is unknown). The SDK's own ladder then checks the protocol headers against the body (`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`; a mismatch is 400 with -32020) and the content type.
 *
 * The resolved grant reaches the per-request server through `authInfo.extra`, which the SDK passes through untouched, so the server instance is built for exactly one grant's scope. `initialize`, `server/discover` and `tools/list` are answered from the shared registry and wake no container.
 */
import {
  type AuthInfo,
  createMcpHandler,
  type McpRequestContext,
  originValidationResponse,
  Server,
} from '@modelcontextprotocol/server';
import type { GrantContext } from './scope.js';
import { listGrantTools } from './tools.js';

/** The hosted clients whose browser origin may call the Worker; the Worker's own host joins them per region. */
export const HOSTED_CLIENT_ORIGINS: readonly string[] = ['claude.ai', 'chatgpt.com'];

/** How long a client may cache `tools/list` and `server/discover`: the listing changes only with a deploy or a scope edit. */
const LIST_TTL_MS = 60_000;

/** A grant id as it appears in the path: the account Worker's ids, never a credential. */
const GRANT_PATH = /^\/g\/([A-Za-z0-9_-]{1,64})$/;

export type ResolveGrant = (grantId: string, request: Request) => Promise<GrantContext | null>;

export interface McpTransportOptions {
  /** The Worker's public host, e.g. mcp.eu.rediacc.cloud. */
  host: string;
  /** The version `server/discover` and `initialize` report. */
  serverVersion: string;
  resolveGrant: ResolveGrant;
}

export interface McpTransport {
  fetch: (request: Request) => Promise<Response>;
}

const GRANT_KEY = 'rediaccGrant';

function grantFrom(ctx: McpRequestContext): GrantContext {
  const grant = ctx.authInfo?.extra?.[GRANT_KEY] as GrantContext | undefined;
  if (!grant) throw new Error('the MCP server was built for a request with no resolved grant');
  return grant;
}

function buildServer(grant: GrantContext, serverVersion: string): Server {
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
  const tools = listGrantTools(grant.scope);
  server.setRequestHandler('tools/list', () => ({ tools }));
  return server;
}

function plain(status: number, body: string, headers: Record<string, string> = {}): Response {
  return new Response(body, { status, headers: { 'content-type': 'text/plain', ...headers } });
}

/** The transport for one Worker: routing, method, Origin and grant checks in front of the SDK handler. */
export function createMcpTransport(options: McpTransportOptions): McpTransport {
  const allowedOrigins = [...HOSTED_CLIENT_ORIGINS, options.host];
  const handler = createMcpHandler((ctx) => buildServer(grantFrom(ctx), options.serverVersion), {
    legacy: 'stateless',
    responseMode: 'json',
  });

  return {
    fetch: async (request) => {
      const match = GRANT_PATH.exec(new URL(request.url).pathname);
      if (!match) return plain(404, 'Not found');
      if (request.method === 'GET' || request.method === 'DELETE') {
        return plain(405, 'Method not allowed', { allow: 'POST' });
      }
      const rejected = originValidationResponse(request, allowedOrigins);
      if (rejected) return rejected;
      const grant = await options.resolveGrant(match[1], request);
      if (!grant) return plain(401, 'Unauthorized');
      const authInfo: AuthInfo = {
        token: '',
        clientId: grant.grantId,
        scopes: [],
        extra: { [GRANT_KEY]: grant },
      };
      return handler.fetch(request, { authInfo });
    },
  };
}
