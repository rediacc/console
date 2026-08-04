/**
 * Regression test: `rdc config init <name> --server <url>` must seed the
 * server's E2E public key, not just the server URL.
 *
 * Writing `accountServer` alone leaves `account.e2ePublicKey` absent, so the
 * FIRST tunnelled request falls through to the baked-in production key
 * (getServerKeyMaterial tier 3 in services/account/account-client.ts) and dies
 * with a bare "Error: Decryption failed". Only a LATER command self-heals, via
 * discoverServerKey(). A drill hit exactly that: init against a non-production
 * server, then one failing command, then `rdc config current` silently repaired
 * it.
 *
 * The server being unreachable at init time must stay non-fatal, because
 * discovery still heals the config on a later run.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockFetchServerInfo = vi.fn();
const mockWarn = vi.fn();

vi.mock('../../services/account/account-client.js', () => ({
  fetchServerInfo: (...args: unknown[]) => mockFetchServerInfo(...args),
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    warn: (...args: unknown[]) => mockWarn(...args),
    info: vi.fn(),
    success: vi.fn(),
    print: vi.fn(),
  },
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string) => key,
}));

const SERVER_KEY = 'MCowBQYDK2VuAyEAdGVzdC1zZXJ2ZXIta2V5LWZvci11bml0LXRlc3Rz';

function serverInfo(publicKeySpki: string | undefined) {
  return {
    e2e: { keys: publicKeySpki ? [{ keyId: 'v1', publicKeySpki }] : [] },
    apiVersion: 1,
    minCliVersion: '0.0.0',
    warnCliVersion: null,
    environment: 'test',
  };
}

describe('buildInitAccountUpdate', () => {
  beforeEach(() => {
    mockFetchServerInfo.mockReset();
    mockWarn.mockReset();
  });

  it('returns undefined when --server was not passed', async () => {
    const { buildInitAccountUpdate } = await import('../config.js');

    expect(await buildInitAccountUpdate(undefined)).toBeUndefined();
    expect(mockFetchServerInfo).not.toHaveBeenCalled();
  });

  it('seeds e2ePublicKey from the server alongside accountServer', async () => {
    mockFetchServerInfo.mockResolvedValue(serverInfo(SERVER_KEY));
    const { buildInitAccountUpdate } = await import('../config.js');

    const update = await buildInitAccountUpdate('https://edge.example.com');

    expect(mockFetchServerInfo).toHaveBeenCalledWith('https://edge.example.com');
    expect(update).toEqual({
      accountServer: 'https://edge.example.com',
      e2ePublicKey: SERVER_KEY,
    });
    expect(mockWarn).not.toHaveBeenCalled();
  });

  it('strips trailing slashes before fetching and before storing', async () => {
    mockFetchServerInfo.mockResolvedValue(serverInfo(SERVER_KEY));
    const { buildInitAccountUpdate } = await import('../config.js');

    const update = await buildInitAccountUpdate('https://edge.example.com///');

    expect(mockFetchServerInfo).toHaveBeenCalledWith('https://edge.example.com');
    expect(update?.accountServer).toBe('https://edge.example.com');
  });

  it('still writes the server URL and warns when the server is unreachable', async () => {
    mockFetchServerInfo.mockRejectedValue(new Error('server-info returned 502'));
    const { buildInitAccountUpdate } = await import('../config.js');

    const update = await buildInitAccountUpdate('https://down.example.com');

    expect(update).toEqual({ accountServer: 'https://down.example.com' });
    expect(update).not.toHaveProperty('e2ePublicKey');
    expect(mockWarn).toHaveBeenCalledWith('commands.config.init.serverKeyUnreachable');
  });

  it('warns when the server advertises no key at all', async () => {
    mockFetchServerInfo.mockResolvedValue(serverInfo(undefined));
    const { buildInitAccountUpdate } = await import('../config.js');

    const update = await buildInitAccountUpdate('https://keyless.example.com');

    expect(update).toEqual({ accountServer: 'https://keyless.example.com' });
    expect(mockWarn).toHaveBeenCalledWith('commands.config.init.serverKeyMissing');
  });
});
