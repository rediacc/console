import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { fakeAccountServer, tokenState, configTeam, handleError } = vi.hoisted(() => ({
  fakeAccountServer: vi.fn(),
  tokenState: { current: undefined as unknown },
  configTeam: { current: undefined as string | undefined },
  handleError: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: fakeAccountServer,
}));
vi.mock('../../services/account/subscription-auth.js', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../services/account/subscription-auth.js')>();
  return {
    getSubscriptionScopeMismatch: real.getSubscriptionScopeMismatch,
    getSubscriptionTokenState: () => tokenState.current,
  };
});
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getTeam: async () => configTeam.current },
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError,
}));

import { executeProxyToken, PROXY_CLI_TOKEN_PATH } from '../subscription-proxy-token.js';

const LOGIN = 'rdt_login_token_value';
const MINTED = 'rdt_minted_proxy_token';
const EXPIRES = '2026-10-23T12:05:00.000Z';
const SERVER = 'https://eu.example.test';

/**
 * A fake account server at the client seam: it answers POST /proxy/cli-token only for the stored
 * login token, the way the route does, and refuses anything else.
 */
function serveMint(): void {
  fakeAccountServer.mockImplementation(
    (path: string, opts: { method?: string; token?: string; serverUrl?: string }) => {
      if (path !== PROXY_CLI_TOKEN_PATH || opts.method !== 'POST') {
        return Promise.reject(Object.assign(new Error('Not Found'), { status: 404 }));
      }
      if (opts.token !== LOGIN || opts.serverUrl !== SERVER) {
        return Promise.reject(
          Object.assign(new Error('Invalid or expired API token'), { status: 401 })
        );
      }
      return Promise.resolve({ token: MINTED, expiresAt: EXPIRES, scopes: ['proxy:exec'] });
    }
  );
}

let stdout: string[];
let stderr: string[];
let drivenArgv: string[];

beforeEach(() => {
  vi.clearAllMocks();
  stdout = [];
  stderr = [];
  vi.spyOn(process.stdout, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stdout.push(String(chunk));
    return true;
  });
  vi.spyOn(process.stderr, 'write').mockImplementation((chunk: string | Uint8Array) => {
    stderr.push(String(chunk));
    return true;
  });
  tokenState.current = {
    kind: 'ready',
    token: { token: LOGIN, serverUrl: SERVER, teamName: 'Default' },
    serverUrl: SERVER,
  };
  configTeam.current = 'Default';
  serveMint();
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Drive the real command tree, as `rdc subscription proxy-token ...` would. */
async function run(...args: string[]): Promise<void> {
  const { registerSubscriptionCommands } = await import('../subscription.js');
  const program = new Command().exitOverride();
  registerSubscriptionCommands(program);
  drivenArgv = ['node', 'rdc', 'subscription', 'proxy-token', ...args];
  await program.parseAsync(drivenArgv);
}

describe('rdc subscription proxy-token', () => {
  it('writes the minted token, and nothing else, to stdout', async () => {
    await run();
    expect(handleError).not.toHaveBeenCalled();
    expect(stdout.join('')).toBe(`${MINTED}\n`);
    expect(stderr.join('')).not.toContain(MINTED);
  });

  it('presents the stored login token to the mint route, never on argv', async () => {
    await run();
    expect(fakeAccountServer).toHaveBeenCalledTimes(1);
    const [path, opts] = fakeAccountServer.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe('/account/api/v1/proxy/cli-token');
    expect(opts).toMatchObject({ method: 'POST', token: LOGIN, serverUrl: SERVER });
    // The token reaches the mint route through `opts.token` (asserted above); the argv the command was driven with never carries it.
    expect(drivenArgv.join(' ')).not.toContain(LOGIN);
  });

  it('--json writes the token and its expiresAt as one JSON line', async () => {
    await run('--json');
    const out = stdout.join('');
    expect(out.endsWith('\n')).toBe(true);
    expect(JSON.parse(out)).toEqual({ token: MINTED, expiresAt: EXPIRES });
  });

  it('refuses without a login, and writes nothing to stdout', async () => {
    tokenState.current = { kind: 'missing' };
    await run();
    expect(fakeAccountServer).not.toHaveBeenCalled();
    expect(handleError).toHaveBeenCalledTimes(1);
    expect((handleError.mock.calls[0][0] as Error).message).toBe('errors.subscription.notLoggedIn');
    expect(stdout.join('')).toBe('');
  });

  it('refuses a login bound to another team than the config', async () => {
    configTeam.current = 'Other';
    await run();
    expect(fakeAccountServer).not.toHaveBeenCalled();
    expect((handleError.mock.calls[0][0] as Error).message).toContain('"Default"');
    expect(stdout.join('')).toBe('');
  });

  it('surfaces a server refusal and writes nothing to stdout', async () => {
    fakeAccountServer.mockRejectedValueOnce(
      Object.assign(new Error('A proxy token cannot mint another proxy token.'), { status: 403 })
    );
    await run();
    expect((handleError.mock.calls[0][0] as Error).message).toContain('cannot mint');
    expect(stdout.join('')).toBe('');
  });

  it('fails rather than printing an empty line when the server returns no token', async () => {
    fakeAccountServer.mockResolvedValueOnce({});
    await expect(executeProxyToken({})).rejects.toThrow('commands.subscription.proxyToken.noToken');
    expect(stdout.join('')).toBe('');
  });
});
