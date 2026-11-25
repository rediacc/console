import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `ExecutorIssuer.resolveGrant` is the method the MCP Worker's `GRANTS` binding calls
 * (workers/mcp/src/resolve.ts). It hands the grant id and tag to the account app's
 * `resolveAgentGrant` over the fenced env and returns its answer unchanged, null included.
 */

const resolveAgentGrant = vi.fn();

vi.mock('cloudflare:workers', () => ({
  WorkerEntrypoint: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
  DurableObject: class {
    constructor(
      protected ctx: unknown,
      protected env: unknown
    ) {}
  },
}));
vi.mock('../../../../private/account/src/entry/cloudflare.js', () => ({
  default: { resolveAgentGrant },
}));

const { ExecutorIssuer } = await import('../index.js');

describe('ExecutorIssuer.resolveGrant', () => {
  beforeEach(() => resolveAgentGrant.mockReset());

  it('passes the grant id and tag through and returns the account answer', async () => {
    const answer = { active: true, orgId: 'org1' };
    resolveAgentGrant.mockResolvedValue(answer);
    const issuer = new ExecutorIssuer({} as never, { DB: {} } as never);
    expect(await issuer.resolveGrant('eu_g1', 'tag')).toBe(answer);
    const [, grantId, tag] = resolveAgentGrant.mock.calls[0] as [unknown, string, string];
    expect([grantId, tag]).toEqual(['eu_g1', 'tag']);
  });

  it('returns null for a grant the account does not know', async () => {
    resolveAgentGrant.mockResolvedValue(null);
    const issuer = new ExecutorIssuer({} as never, { DB: {} } as never);
    expect(await issuer.resolveGrant('eu_nope', 'tag')).toBeNull();
  });
});
