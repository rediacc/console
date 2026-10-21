import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../account/account-client.js', () => ({
  accountServerFetch: vi.fn(),
}));

const CONFIGURED = 'https://config.example.com';
const mockConfiguredServer = vi.hoisted(() => vi.fn<() => string | undefined>());
vi.mock('../account/subscription-auth.js', () => ({
  getConfiguredServerUrl: mockConfiguredServer,
  normalizeServerUrl: (url: string) => url.replace(/\/+$/, ''),
}));

import { Command } from 'commander';
import { accountServerFetch } from '../account/account-client.js';
import {
  credentialsToBasicAuthToken,
  fetchCommandOtlpCredentials,
  fetchOtlpCredentials,
  resetOtlpCredentialsCache,
  serverOptionOf,
} from '../telemetry/otlp-credentials.js';

const mockedFetch = vi.mocked(accountServerFetch);

describe('fetchOtlpCredentials', () => {
  beforeEach(() => {
    resetOtlpCredentialsCache();
    vi.resetAllMocks();
    mockConfiguredServer.mockReturnValue(CONFIGURED);
  });

  afterEach(() => {
    resetOtlpCredentialsCache();
  });

  it('calls GET /account/api/v1/telemetry/config with noAuth=true', async () => {
    mockedFetch.mockResolvedValue({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'u', pass: 'p' },
    });

    await fetchOtlpCredentials();

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(mockedFetch).toHaveBeenCalledWith('/account/api/v1/telemetry/config', {
      noAuth: true,
      serverUrl: CONFIGURED,
    });
  });

  it('fetches nothing, and never asks the production default, when no server is named and the config names none', async () => {
    mockConfiguredServer.mockReturnValue(undefined);

    expect(await fetchOtlpCredentials()).toBeNull();
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it('asks the server the command names (`config init --server <dev>`) over the configured one', async () => {
    mockedFetch.mockResolvedValue({ otlp: null });

    await fetchOtlpCredentials('http://192.168.111.254:4800/');

    expect(mockedFetch).toHaveBeenCalledWith('/account/api/v1/telemetry/config', {
      noAuth: true,
      serverUrl: 'http://192.168.111.254:4800',
    });
  });

  it('returns credentials when the server provides them', async () => {
    mockedFetch.mockResolvedValue({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'otlp-eu-abc', pass: 'pass-xyz' },
    });

    const result = await fetchOtlpCredentials();

    expect(result).toEqual({
      endpoint: 'otlp.rediacc.io',
      user: 'otlp-eu-abc',
      pass: 'pass-xyz',
    });
  });

  it('returns null when the server explicitly returns otlp:null', async () => {
    mockedFetch.mockResolvedValue({ otlp: null });

    const result = await fetchOtlpCredentials();

    expect(result).toBeNull();
  });

  it('never throws: treats fetch errors as "disabled"', async () => {
    mockedFetch.mockRejectedValue(new Error('network down'));

    const result = await fetchOtlpCredentials();

    expect(result).toBeNull();
  });

  it('never throws when resolving the server itself fails', async () => {
    mockConfiguredServer.mockImplementation(() => {
      throw new Error('config unreadable');
    });

    expect(await fetchOtlpCredentials()).toBeNull();
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it('caches the result across calls within one process', async () => {
    mockedFetch.mockResolvedValue({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'u', pass: 'p' },
    });

    await fetchOtlpCredentials();
    await fetchOtlpCredentials();
    await fetchOtlpCredentials();

    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("caches null results (doesn't retry failures)", async () => {
    mockedFetch.mockRejectedValue(new Error('network down'));

    await fetchOtlpCredentials();
    await fetchOtlpCredentials();
    await fetchOtlpCredentials();

    // Fetch should be attempted once, the null is cached
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it('resets the cache via resetOtlpCredentialsCache', async () => {
    mockedFetch.mockResolvedValueOnce({ otlp: null });
    await fetchOtlpCredentials();
    expect(mockedFetch).toHaveBeenCalledTimes(1);

    resetOtlpCredentialsCache();
    mockedFetch.mockResolvedValueOnce({
      otlp: { endpoint: 'otlp.rediacc.io', user: 'u', pass: 'p' },
    });

    const result = await fetchOtlpCredentials();
    expect(result?.user).toBe('u');
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it('returns null when the response is missing the otlp field', async () => {
    mockedFetch.mockResolvedValue({});

    const result = await fetchOtlpCredentials();

    expect(result).toBeNull();
  });
});

describe('credentialsToBasicAuthToken', () => {
  it('base64-encodes user:pass', () => {
    const encoded = credentialsToBasicAuthToken({
      endpoint: 'otlp.rediacc.io',
      user: 'alice',
      pass: 'secret',
    });
    expect(encoded).toBe(Buffer.from('alice:secret').toString('base64'));
  });

  it('handles passwords with special characters', () => {
    const encoded = credentialsToBasicAuthToken({
      endpoint: 'otlp.rediacc.io',
      user: 'u',
      pass: 'p@ss:word!',
    });
    expect(Buffer.from(encoded, 'base64').toString()).toBe('u:p@ss:word!');
  });
});

describe('serverOptionOf', () => {
  function parsed(argv: string[]): Command {
    const program = new Command().exitOverride();
    let action: Command | undefined;
    const config = program.command('config');
    config
      .command('init [name]')
      .option('--server <url>')
      .action((_name, _opts, cmd: Command) => {
        action = cmd;
      });
    config.command('current').action((_opts, cmd: Command) => {
      action = cmd;
    });
    program.parse(argv, { from: 'user' });
    if (!action) throw new Error('no action ran');
    return action;
  }

  it('returns the --server a command was given', () => {
    expect(
      serverOptionOf(parsed(['config', 'init', 'dev', '--server', 'http://dev.test:4800']))
    ).toBe('http://dev.test:4800');
  });

  it('returns nothing for a command without one', () => {
    expect(serverOptionOf(parsed(['config', 'init', 'dev']))).toBeUndefined();
    expect(serverOptionOf(parsed(['config', 'current']))).toBeUndefined();
  });
});

describe('fetchCommandOtlpCredentials, through a preAction hook as cli.ts runs it', () => {
  beforeEach(() => {
    resetOtlpCredentialsCache();
    vi.resetAllMocks();
    mockConfiguredServer.mockReturnValue(CONFIGURED);
    mockedFetch.mockResolvedValue({ otlp: null });
  });

  afterEach(() => {
    resetOtlpCredentialsCache();
  });

  async function runHook(argv: string[]): Promise<void> {
    const program = new Command().exitOverride();
    let fetched: Promise<unknown> | undefined;
    program.hook('preAction', (_thisCommand, actionCommand) => {
      fetched = fetchCommandOtlpCredentials(actionCommand);
    });
    const config = program.command('config');
    config
      .command('init [name]')
      .option('--server <url>')
      .action(() => undefined);
    config.command('current').action(() => undefined);
    await program.parseAsync(argv, { from: 'user' });
    await fetched;
  }

  const servers = () => mockedFetch.mock.calls.map(([, options]) => options?.serverUrl);

  it("asks the server a command's --server names, normalized", async () => {
    await runHook(['config', 'init', 'dev', '--server', 'http://dev.test:4800/']);
    expect(servers()).toEqual(['http://dev.test:4800']);
  });

  it('asks the configured server for a command given no --server', async () => {
    await runHook(['config', 'init', 'dev']);
    expect(servers()).toEqual([CONFIGURED]);
  });

  it('asks the configured server for a command that takes no --server', async () => {
    await runHook(['config', 'current']);
    expect(servers()).toEqual([CONFIGURED]);
  });

  it('asks nothing for a command with no --server on a config that names no server', async () => {
    mockConfiguredServer.mockReturnValue(undefined);
    await runHook(['config', 'current']);
    expect(mockedFetch).not.toHaveBeenCalled();
  });
});
