import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `GrantResolver.resolveGrant` is the method the MCP Worker's `GRANTS` binding calls
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

const { ExecutorIssuer, GrantResolver } = await import('../index.js');
const { fencedEnv } = await import('../d1-fence.js');

describe('GrantResolver.resolveGrant', () => {
  beforeEach(() => resolveAgentGrant.mockReset());

  it('passes the grant id and tag through and returns the account answer', async () => {
    const answer = { active: true, orgId: 'org1' };
    resolveAgentGrant.mockResolvedValue(answer);
    const issuer = new GrantResolver({} as never, { DB: {} } as never);
    expect(await issuer.resolveGrant('eu_g1', 'tag')).toBe(answer);
    const [, grantId, tag] = resolveAgentGrant.mock.calls[0] as [unknown, string, string];
    expect([grantId, tag]).toEqual(['eu_g1', 'tag']);
  });

  it('hands the account app the fenced env, never the raw one', async () => {
    resolveAgentGrant.mockResolvedValue(null);
    const rawDb = { prepare: vi.fn(), batch: vi.fn() };
    const env = { DB: rawDb };
    await new GrantResolver({} as never, env as never).resolveGrant('eu_g1', 'tag');
    const [passed] = resolveAgentGrant.mock.calls[0] as [{ DB: unknown }];
    expect(passed).not.toBe(env);
    expect(passed.DB).not.toBe(rawDb);
    // The same fenced object a later call receives, as for every other entrypoint.
    expect(passed).toBe(fencedEnv(env as never));
  });

  it('control: an env with no DB binding has nothing to fence and passes through as it is', async () => {
    resolveAgentGrant.mockResolvedValue(null);
    const env = {};
    await new GrantResolver({} as never, env as never).resolveGrant('eu_g1', 'tag');
    expect(resolveAgentGrant.mock.calls[0]?.[0]).toBe(env);
  });

  it('returns null for a grant the account does not know', async () => {
    resolveAgentGrant.mockResolvedValue(null);
    const issuer = new GrantResolver({} as never, { DB: {} } as never);
    expect(await issuer.resolveGrant('eu_nope', 'tag')).toBeNull();
  });
});

/**
 * Every function an entrypoint exposes over RPC: the prototype's methods and the function-valued own properties of an instance (an arrow-function class field is an own property, not a prototype method).
 */
const rpcMethods = (cls: new (ctx: never, env: never) => object) =>
  [
    ...Object.getOwnPropertyNames(cls.prototype),
    ...Object.entries(new cls({} as never, {} as never))
      .filter(([, value]) => typeof value === 'function')
      .map(([name]) => name),
  ]
    .filter((name) => name !== 'constructor')
    .sort((a, b) => a.localeCompare(b));

describe('rpcMethods', () => {
  it('lists an arrow-function class field as well as a prototype method', () => {
    class Probe {
      viaPrototype() {
        return 1;
      }
      viaField = () => 2;
      notAFunction = 3;
    }
    expect(rpcMethods(Probe)).toEqual(['viaField', 'viaPrototype']);
  });
});

describe('entrypoint surfaces', () => {
  it('ExecutorIssuer exposes no resolveGrant', () => {
    expect(rpcMethods(ExecutorIssuer)).not.toContain('resolveGrant');
    expect(rpcMethods(ExecutorIssuer)).toEqual([
      'issue',
      'probe',
      'relocate',
      'route',
      'verifyInternal',
    ]);
  });

  it('GrantResolver exposes only resolveGrant', () => {
    expect(rpcMethods(GrantResolver)).toEqual(['resolveGrant']);
  });
});
