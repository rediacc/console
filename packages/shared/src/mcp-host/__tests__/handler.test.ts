/**
 * The production wiring of mcp-host/handler.ts (item 67f888f1.1): `EXECUTOR_RELOCATED` is answered through the real resolver and transport over the `GRANTS` and `EXECUTOR` bindings, with no refreshGrant injected, so a mismatch between the resolver's `fresh` and the call path's refresh hook shows here.
 */
import './helpers/workers-shim.js';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WK_MCP_EU_HOST } from '../../config/well-known.generated.js';
import { deriveAuthTag } from '../../config-crypto/agent-grant.js';
import type { McpCallRouting } from '../executor.js';
import type { HostExecutionContext } from '../host-types.js';
import type { ResolvedGrantWire } from '../resolve.js';
import { bearerFor, SECRET_BYTES } from './helpers/grant.js';

const HOST = WK_MCP_EU_HOST;
const GRANT_ID = 'eu_grant_wiring';

function wire(placement: number): ResolvedGrantWire {
  return {
    grantId: GRANT_ID,
    state: 'active',
    orgId: 'org-test',
    placement,
    tier: 'standard',
    userId: 'user-1',
    teamId: null,
    configId: 'cfg-1',
    region: 'eu',
    scope: { readOnly: false },
    expiresAt: '2099-01-01T00:00:00.000Z',
  };
}

beforeEach(() => {
  // index.ts keeps its resolver and transport per isolate, so each test loads a fresh module.
  vi.resetModules();
});

describe('mcp-host/handler.ts wiring', () => {
  it('re-resolves the grant with its id and auth tag and forwards to the new placement', async () => {
    const { default: worker } = await import('../handler.js');
    const lookups: { grantId: string; authTag: string }[] = [];
    const routings: McpCallRouting[] = [];
    const tag = await deriveAuthTag(SECRET_BYTES);
    const env = {
      REGION: 'eu',
      ENVIRONMENT: 'test',
      MCP_HOST: HOST,
      ACCOUNT_URL: 'https://account.test',
      GRANTS: {
        resolveGrant: (grantId: string, authTag: string) => {
          lookups.push({ grantId, authTag });
          // The first lookup opens the request at placement 1; the one after the relocation names placement 2.
          return Promise.resolve(authTag === tag ? wire(lookups.length === 1 ? 1 : 2) : null);
        },
      },
      EXECUTOR: {
        call: (routing: McpCallRouting) => {
          routings.push(routing);
          return Promise.resolve(
            routing.placement === 1
              ? { ok: false as const, code: 'EXECUTOR_RELOCATED', status: 503 }
              : {
                  ok: true as const,
                  answer: { result: { content: [{ type: 'text', text: 'ran' }], isError: false } },
                }
          );
        },
      },
    };
    const viaWorker = (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
      const request = new Request(input, init);
      request.headers.set('authorization', `Bearer ${bearerFor(GRANT_ID)}`);
      return Promise.resolve(worker.fetch(request, env as never, {} as HostExecutionContext));
    };
    const client = new Client(
      { name: 'rw-wiring', version: '0.0.0' },
      { versionNegotiation: { mode: 'legacy' } }
    );
    await client.connect(
      new StreamableHTTPClientTransport(new URL(`https://${HOST}/g/${GRANT_ID}`), {
        fetch: viaWorker,
      })
    );
    const result = await client.callTool({ name: 'repo_list', arguments: {} });
    await client.close();

    expect(result.isError).toBeFalsy();
    expect(routings.map((r) => r.placement)).toEqual([1, 2]);
    expect(lookups.at(-1)).toEqual({ grantId: GRANT_ID, authTag: tag });
  });
});
