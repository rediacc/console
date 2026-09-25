/**
 * `rdc config remote enable` states and checks the portal prerequisites
 * (signed in, two-factor authentication, a recently verified session) BEFORE it
 * prints or opens any portal URL. A missing 2FA used to surface only mid-flow in
 * the browser (operator report, 2026-09-24). With no login token for the server
 * it refuses outright: the relay binds the handoff to the token's user (D1).
 *
 * Driven through the real Commander registration; only the I/O seams (account
 * API, stored login token, output, config file, browser launch) are mocked.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const API = 'https://acct.example.com';

const { mockFetch, mockTokenState, lines, errors, mockExecFile } = vi.hoisted(() => ({
  mockFetch: vi.fn(),
  mockTokenState: vi.fn(),
  lines: [] as string[],
  errors: [] as unknown[],
  mockExecFile: vi.fn(),
}));

vi.mock('../../services/account/account-client.js', () => ({
  accountServerFetch: mockFetch,
}));

vi.mock('../../services/account/subscription-auth.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/account/subscription-auth.js')>()),
  getSubscriptionTokenState: mockTokenState,
  getSubscriptionServerUrl: () => API,
}));

vi.mock('../../services/core/output.js', () => {
  const push = (m: string) => {
    lines.push(m);
  };
  return { outputService: { info: push, success: push, warn: push, print: push, error: push } };
});

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { load: vi.fn(() => Promise.resolve({ schemaVersion: 3, id: 'cfg' })) },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getEffectiveConfigName: () => 'test' },
}));

vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (e: unknown) => {
    errors.push(e);
  },
}));

vi.mock('node:child_process', () => ({ execFile: mockExecFile }));

const { registerRemoteCommands } = await import('../config-remote.js');

async function runEnable(...flags: string[]) {
  const program = new Command();
  program.exitOverride();
  registerRemoteCommands(program.command('config'));
  await program.parseAsync(['node', 'rdc', 'config', 'remote', 'enable', ...flags]);
}

const REQS_PATH = '/account/api/v1/configs/enable-requirements';
const urlPrinted = () => lines.some((l) => l.includes('/account/config-remote'));
const errorText = () => errors.map((e) => (e instanceof Error ? e.message : String(e))).join('\n');

function loggedIn() {
  mockTokenState.mockReturnValue({
    kind: 'ready',
    serverUrl: `${API}/`,
    token: { token: 'rdt_login', serverUrl: `${API}/` },
  });
}

/** Relay met path: the created code is already past its expiresAt, so the run ends on `expired` without a claim. */
function routeFetch(reqs: unknown) {
  mockFetch.mockImplementation((path: string) => {
    if (path === REQS_PATH) {
      return reqs instanceof Error ? Promise.reject(reqs) : Promise.resolve(reqs);
    }
    if (path === '/account/api/v1/device-codes') {
      return Promise.resolve({
        deviceCode: 'dc-uuid',
        interval: 5,
        expiresIn: 600,
        expiresAt: new Date(Date.now() - 1000).toISOString(),
      });
    }
    return Promise.resolve({ status: 'expired' });
  });
}

beforeEach(() => {
  lines.length = 0;
  errors.length = 0;
  mockFetch.mockReset();
  mockTokenState.mockReset();
  mockExecFile.mockReset();
});

describe('config remote enable: prerequisites before the portal URL', () => {
  it('refuses without 2FA, naming the account and the settings page, before any URL', async () => {
    loggedIn();
    routeFetch({ email: 'op@example.com', totpEnabled: false, configServiceAvailable: true });

    await runEnable();

    expect(mockFetch).toHaveBeenCalledWith(REQS_PATH, {
      serverUrl: API,
      token: 'rdt_login',
    });
    expect(errors).toHaveLength(1);
    const msg = errorText();
    expect(msg).toContain('op@example.com');
    expect(msg).toContain('Two-factor authentication (TOTP)');
    expect(msg).toContain(`${API}/account/settings`);
    expect(msg).toContain('rdc config remote enable');
    expect(msg).not.toContain('not available');
    expect(urlPrinted()).toBe(false);
    expect(mockExecFile).not.toHaveBeenCalled();
    // No device code is requested either.
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('refuses when the server has no config storage, alongside the missing 2FA', async () => {
    loggedIn();
    routeFetch({ email: 'op@example.com', totpEnabled: false, configServiceAvailable: false });

    await runEnable();

    const msg = errorText();
    expect(msg).toContain(`Config storage is not available on ${API}`);
    expect(msg).toContain('Two-factor authentication (TOTP)');
    expect(urlPrinted()).toBe(false);
  });

  it('all met: confirms the account, names it on the link line, then prints the relay link', async () => {
    loggedIn();
    routeFetch({ email: 'op@example.com', totpEnabled: true, configServiceAvailable: true });

    await runEnable();

    const checked = lines.findIndex((l) => l.includes('op@example.com'));
    const approve = lines.findIndex((l) => l.includes('signed in as op@example.com'));
    const url = lines.findIndex((l) => l.includes('/account/config-remote#code=dc-uuid'));
    expect(checked).toBeGreaterThanOrEqual(0);
    expect(approve).toBeGreaterThan(checked);
    expect(url).toBeGreaterThan(approve);
    expect(lines.some((l) => l.includes('recently verified session'))).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith('/account/api/v1/device-codes', expect.anything());
    // The run ends on the (mocked) expired device code, not on a prerequisite.
    expect(errorText()).toContain('expired');
  });

  it('no login token: refuses with loginRequired before any request or URL', async () => {
    mockTokenState.mockReturnValue({ kind: 'missing' });
    routeFetch(new Error('unused'));

    await runEnable();

    expect(mockFetch).not.toHaveBeenCalled();
    expect(urlPrinted()).toBe(false);
    expect(mockExecFile).not.toHaveBeenCalled();
    const msg = errorText();
    expect(msg).toContain('rdc subscription login');
    expect(msg).toContain(API);
  });

  it('a server without the route (older deploy) falls back to stating the prerequisites', async () => {
    loggedIn();
    routeFetch(Object.assign(new Error('Not Found'), { status: 404 }));

    await runEnable();

    const totp = lines.findIndex((l) => l.includes(`${API}/account/settings`));
    const url = lines.findIndex((l) => l.includes('/account/config-remote#code='));
    expect(totp).toBeGreaterThanOrEqual(0);
    expect(url).toBeGreaterThan(totp);
    // No account email is known, so the link line names the portal instead.
    expect(lines.some((l) => l.includes('signed in to the portal'))).toBe(true);
  });

  it('a login token for a different server is not used: loginRequired', async () => {
    mockTokenState.mockReturnValue({
      kind: 'ready',
      serverUrl: 'https://other.example.com',
      token: { token: 'rdt_other', serverUrl: 'https://other.example.com' },
    });
    routeFetch(new Error('unused'));

    await runEnable();

    expect(mockFetch).not.toHaveBeenCalled();
    expect(errorText()).toContain('rdc subscription login');
    expect(urlPrinted()).toBe(false);
  });

  it('--headless is gone', async () => {
    loggedIn();
    routeFetch({ email: 'op@example.com', totpEnabled: true, configServiceAvailable: true });

    await expect(runEnable('--headless')).rejects.toThrow(/unknown option/);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
