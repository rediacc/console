import { afterEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  throughProxy: vi.fn(),
  proxyToken: vi.fn(),
}));

vi.mock('../services/executor/proxy-command.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/executor/proxy-command.js')>()),
  runCommandThroughProxy: m.throughProxy,
}));
vi.mock('../commands/subscription-proxy-token.js', () => ({
  executeProxyToken: m.proxyToken,
}));

const { createCli } = await import('../cli.js');

afterEach(() => {
  delete process.env.REDIACC_PROXY_URL;
  vi.clearAllMocks();
});

// `subscription proxy-token` mints the token `--proxy` needs, so the root hook runs it here even when the environment names a proxy.
describe('the root hook and `subscription proxy-token`', () => {
  it('runs the command locally when REDIACC_PROXY_URL is set, instead of sending it through the proxy', async () => {
    process.env.REDIACC_PROXY_URL = 'https://executor.test';
    m.proxyToken.mockResolvedValue(undefined);

    await createCli().parseAsync(['node', 'rdc', 'subscription', 'proxy-token']);

    expect(m.throughProxy).not.toHaveBeenCalled();
    expect(m.proxyToken).toHaveBeenCalledOnce();
  });
});
