/**
 * PLAN-free-license F5: the CLI side of the Free License. With no login a human
 * is offered a login or a free licence, an agent or `--yes` takes the free
 * licence with a warning naming the signup link (R11), the licence comes from
 * `POST /licenses/free` on the configured server, a FREE licence renews through
 * renet's blob-authenticated path (R6), and hosted backups name the upgrade
 * instead of failing on a missing token (R13).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  fetch: vi.fn(),
  tokenState: vi.fn(),
  isAgent: vi.fn(),
  askChoice: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  writeRepoLicense: vi.fn(),
  configured: vi.fn(),
  promptRegion: vi.fn(),
  update: vi.fn(),
  exists: vi.fn(),
}));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../account-client.js', () => ({ accountServerFetch: m.fetch }));
vi.mock('../subscription-auth.js', () => ({
  getSubscriptionTokenState: m.tokenState,
  getSubscriptionServerUrl: (preferred?: string) => preferred ?? 'https://acct.example',
  getConfiguredServerUrl: m.configured,
}));
vi.mock('../../../utils/region-prompt.js', () => ({ promptRegionSelection: m.promptRegion }));
vi.mock('../../config/synced-write.js', () => ({ updateConfigAtPointer: m.update }));
vi.mock('../../config/config-name.js', () => ({ getEffectiveConfigName: () => 'cfg' }));
vi.mock('../../../adapters/config-file-storage.js', () => ({
  configFileStorage: { exists: m.exists },
}));
vi.mock('../../../utils/agent-guard.js', () => ({ isAgentEnvironment: m.isAgent }));
vi.mock('../../../utils/prompt.js', () => ({ askChoice: m.askChoice }));
vi.mock('../../core/output.js', () => ({ outputService: { warn: m.warn, info: m.info } }));
vi.mock('../license-machine.js', () => ({
  readRemoteMachineId: vi.fn().mockResolvedValue('a'.repeat(64)),
  readLocalMachineId: vi.fn().mockResolvedValue('b'.repeat(64)),
  writeRepoLicense: m.writeRepoLicense,
}));
vi.mock('../../machine/machine-connection.js', () => ({
  sftpConfigForMachine: () => ({}),
  withSharedOrPooledSftp: (sftp: unknown, _cfg: unknown, fn: (s: unknown) => unknown) => fn(sftp),
}));

import {
  assertHostedBackupAccount,
  FREE_LICENSE_MAX_SIZE_GB,
  FREE_LICENSE_PATH,
  freeLicenseNoBackupMessage,
  isFreeLicenseBackupRefusal,
  issueFreeRepoLicense,
  renewInstalledLicenses,
  resetFreeLicenseStateForTests,
  resolveLicenseAuthority,
} from '../free-license.js';

const MACHINE = { ip: '10.0.0.1', user: 'root' } as never;
const GUID = '11111111-2222-4333-8444-555555555555';
const BLOB = { payload: 'p', signature: 's', publicKeyId: '0123456789abcdef' };

const stdinTty = Object.getOwnPropertyDescriptor(process.stdin, 'isTTY');
const stdoutTty = Object.getOwnPropertyDescriptor(process.stdout, 'isTTY');

function setTty(value: boolean): void {
  Object.defineProperty(process.stdin, 'isTTY', { value, configurable: true });
  Object.defineProperty(process.stdout, 'isTTY', { value, configurable: true });
}

beforeEach(() => {
  resetFreeLicenseStateForTests();
  vi.clearAllMocks();
  m.tokenState.mockReturnValue({ kind: 'missing' });
  m.isAgent.mockReturnValue(false);
  delete process.env.REDIACC_YES;
  setTty(false);
  m.configured.mockReturnValue(undefined);
  m.exists.mockResolvedValue(true);
  m.update.mockResolvedValue(undefined);
  m.promptRegion.mockResolvedValue({ region: {}, domain: 'eu.rediacc.cloud' });
});

afterEach(() => {
  delete process.env.REDIACC_YES;
  if (stdinTty) Object.defineProperty(process.stdin, 'isTTY', stdinTty);
  if (stdoutTty) Object.defineProperty(process.stdout, 'isTTY', stdoutTty);
});

describe('resolveLicenseAuthority', () => {
  it('a ready token licenses the run and nothing is offered', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    const login = vi.fn();
    await expect(resolveLicenseAuthority(login)).resolves.toBe('token');
    expect(login).not.toHaveBeenCalled();
    expect(m.askChoice).not.toHaveBeenCalled();
    expect(m.warn).not.toHaveBeenCalled();
  });

  it('an agent takes the free licence automatically, warning with the signup link', async () => {
    m.isAgent.mockReturnValue(true);
    setTty(true);
    const login = vi.fn();
    await expect(resolveLicenseAuthority(login)).resolves.toBe('free');
    expect(login).not.toHaveBeenCalled();
    expect(m.askChoice).not.toHaveBeenCalled();
    expect(m.warn).toHaveBeenCalledWith(expect.stringContaining('errors.freeLicense.autoTaken'));
    expect(m.warn).toHaveBeenCalledWith(
      expect.stringContaining('https://acct.example/account/login')
    );
  });

  it('--yes takes the free licence automatically, warning with the signup link', async () => {
    process.env.REDIACC_YES = '1';
    setTty(true);
    const login = vi.fn();
    await expect(resolveLicenseAuthority(login)).resolves.toBe('free');
    expect(login).not.toHaveBeenCalled();
    expect(m.askChoice).not.toHaveBeenCalled();
    expect(m.warn).toHaveBeenCalledWith(expect.stringContaining('errors.freeLicense.autoTaken'));
    // The rendered text carries the cap: a dropped maxGb argument fails here.
    expect(m.warn).toHaveBeenCalledWith(
      expect.stringContaining(`"maxGb":${FREE_LICENSE_MAX_SIZE_GB}`)
    );
  });

  it('the offer names no duration and carries the free size cap in the locale text', async () => {
    const en = (await import('../../../i18n/locales/en/cli.json')).default as {
      errors: { freeLicense: Record<string, string> };
    };
    const strings = Object.values(en.errors.freeLicense).join(' ');
    expect(strings).not.toMatch(/48|hour/i);
    expect(en.errors.freeLicense.offerFree).toContain('{{maxGb}} GB');
    expect(FREE_LICENSE_MAX_SIZE_GB).toBe(3);
    // Interpolate the real locale text with the value the code passes: the rendered offer says "3 GB".
    const render = (text: string, vars: Record<string, unknown>) =>
      text.replace(/\{\{(\w+)\}\}/g, (_, k: string) => String(vars[k]));
    expect(render(en.errors.freeLicense.offerFree, { maxGb: FREE_LICENSE_MAX_SIZE_GB })).toContain(
      '3 GB'
    );
    expect(
      render(en.errors.freeLicense.autoTaken, { maxGb: FREE_LICENSE_MAX_SIZE_GB, url: 'u' })
    ).toContain('3 GB');
  });

  it('at a terminal, choosing the free licence asks once and skips the login', async () => {
    setTty(true);
    m.askChoice.mockResolvedValue('free');
    const login = vi.fn();
    await expect(resolveLicenseAuthority(login)).resolves.toBe('free');
    expect(m.askChoice).toHaveBeenCalledTimes(1);
    const [, choices] = m.askChoice.mock.calls[0] as [string, { name: string; value: string }[]];
    expect(choices.map((c) => c.value)).toEqual(['login', 'free']);
    expect(choices[1].name).toContain(`"maxGb":${FREE_LICENSE_MAX_SIZE_GB}`);
    expect(login).not.toHaveBeenCalled();
    // The recovery path re-runs the pre-flight: the choice holds, nothing is asked again.
    await expect(resolveLicenseAuthority(login)).resolves.toBe('free');
    expect(m.askChoice).toHaveBeenCalledTimes(1);
  });

  it('at a terminal, choosing login runs the login and licenses through the token', async () => {
    setTty(true);
    m.askChoice.mockResolvedValue('login');
    const login = vi.fn().mockResolvedValue(undefined);
    await expect(resolveLicenseAuthority(login)).resolves.toBe('token');
    expect(login).toHaveBeenCalledTimes(1);
    expect(m.warn).not.toHaveBeenCalled();
  });

  it('with no terminal, no agent and no --yes, the login runs as before', async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    await expect(resolveLicenseAuthority(login)).resolves.toBe('token');
    expect(login).toHaveBeenCalledTimes(1);
    expect(m.askChoice).not.toHaveBeenCalled();
  });
});

describe('issueFreeRepoLicense', () => {
  it('posts to /licenses/free unauthenticated on the configured server and installs the blob', async () => {
    m.fetch.mockResolvedValue({ license: BLOB, signupUrl: 'https://acct.example/account/signup' });
    const sftp = { exec: vi.fn() } as never;
    await issueFreeRepoLicense(
      'm1',
      MACHINE,
      'key',
      { repositoryGuid: GUID, kind: 'grand', requestedSizeGb: 2, datastoreId: 'ds-1' },
      '/usr/bin/renet',
      sftp
    );
    expect(m.fetch).toHaveBeenCalledTimes(1);
    const [path, opts] = m.fetch.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe(FREE_LICENSE_PATH);
    expect(path).toBe('/account/api/v1/licenses/free');
    expect(opts).toMatchObject({
      method: 'POST',
      noAuth: true,
      serverUrl: 'https://acct.example',
      body: {
        machineId: 'a'.repeat(64),
        clientMachineId: 'b'.repeat(64),
        repositoryGuid: GUID,
        kind: 'grand',
        requestedSizeGb: 2,
        datastoreId: 'ds-1',
      },
    });
    expect(m.writeRepoLicense).toHaveBeenCalledWith('m1', GUID, BLOB, 'ds-1');
    // The server's signup link replaces the fallback in every later message.
    expect(freeLicenseNoBackupMessage()).toContain('https://acct.example/account/signup');
  });

  it("propagates the server's refusal and installs nothing", async () => {
    m.fetch.mockRejectedValue(new Error('8 free licenses from this address in 72 hours'));
    await expect(
      issueFreeRepoLicense(
        'm1',
        MACHINE,
        'key',
        { repositoryGuid: GUID, kind: 'grand' },
        undefined,
        { exec: vi.fn() } as never
      )
    ).rejects.toThrow(/8 free licenses/);
    expect(m.writeRepoLicense).not.toHaveBeenCalled();
  });
});

describe('renewInstalledLicenses (FREE renewal through the existing renew path)', () => {
  it("runs renet's blob-authenticated renewal and counts a renewed FREE licence", async () => {
    const exec = vi.fn().mockResolvedValue(
      JSON.stringify({
        at: '2026-10-30T00:00:00Z',
        lockBusy: false,
        results: [
          { repositoryGuid: GUID, keyId: 'k', outcome: 'renewed', newSequence: 7 },
          { repositoryGuid: 'other', keyId: 'k', outcome: 'skipped_fresh' },
        ],
      })
    );
    const out = await renewInstalledLicenses(MACHINE, 'key', {
      force: true,
      remoteRenetPath: '/usr/bin/renet',
      sftp: { exec } as never,
    });
    expect(exec).toHaveBeenCalledWith(
      "sudo -n '/usr/bin/renet' license renew --force --output json"
    );
    expect(out.renewed).toBe(1);
    expect(out.results).toHaveLength(2);
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('sends only due blobs without --force, and a run with no results renews nothing', async () => {
    const exec = vi.fn().mockResolvedValue('{"lockBusy":false,"results":null}');
    const out = await renewInstalledLicenses(MACHINE, 'key', { sftp: { exec } as never });
    expect(exec.mock.calls[0]?.[0]).not.toContain('--force');
    expect(out.renewed).toBe(0);
  });
});

describe('hosted backups on a Free License', () => {
  it('assertHostedBackupAccount refuses with the upgrade message when not logged in', () => {
    expect(() => assertHostedBackupAccount()).toThrow(/errors\.freeLicense\.noHostedBackup/);
    expect(() => assertHostedBackupAccount()).toThrow(/account\/login/);
  });

  it('assertHostedBackupAccount passes with a login', () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    expect(() => assertHostedBackupAccount()).not.toThrow();
  });

  it("isFreeLicenseBackupRefusal finds the server's code wherever renet printed it", () => {
    const refusal = 'server refused (HTTP 403, FREE_LICENSE_NO_BACKUP): no hosted backup';
    expect(isFreeLicenseBackupRefusal({ stderr: refusal })).toBe(true);
    expect(isFreeLicenseBackupRefusal({ error: refusal })).toBe(true);
    expect(isFreeLicenseBackupRefusal({ stdout: refusal })).toBe(true);
    expect(isFreeLicenseBackupRefusal({ error: 'quota refused', stderr: '' })).toBe(false);
  });
});

describe('free licence region pick', () => {
  const US = { id: 'us', label: 'United States', domain: 'us.rediacc.cloud', default: false };

  it('a terminal with no server asks, uses the pick and saves it', async () => {
    setTty(true);
    m.askChoice.mockResolvedValueOnce('free');
    m.promptRegion.mockResolvedValue({ region: US, domain: US.domain });
    await resolveLicenseAuthority(vi.fn());
    expect(m.promptRegion).toHaveBeenCalledTimes(1);
    expect(m.update).toHaveBeenCalledTimes(1);
    expect(m.update.mock.calls[0][1]).toBe('/account/accountServer');
    const saved = m.update.mock.calls[0][2]({ account: { e2ePublicKey: 'k' } });
    expect(saved.account.accountServer).toBe('https://us.rediacc.cloud');
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    expect(m.fetch.mock.calls[0][1].serverUrl).toBe('https://us.rediacc.cloud');
  });

  it('no terminal keeps the default and prints one line naming it', async () => {
    m.isAgent.mockReturnValue(true);
    await resolveLicenseAuthority(vi.fn());
    expect(m.promptRegion).not.toHaveBeenCalled();
    expect(m.update).not.toHaveBeenCalled();
    expect(m.info).toHaveBeenCalledTimes(1);
    expect(m.info).toHaveBeenCalledWith(
      expect.stringContaining('errors.freeLicense.defaultRegion')
    );
    expect(m.info).toHaveBeenCalledWith(expect.stringContaining('https://acct.example'));
  });

  it('a configured server is never prompted or overwritten', async () => {
    setTty(true);
    m.configured.mockReturnValue('https://eu.rediacc.cloud');
    m.askChoice.mockResolvedValueOnce('free');
    await resolveLicenseAuthority(vi.fn());
    expect(m.promptRegion).not.toHaveBeenCalled();
    expect(m.update).not.toHaveBeenCalled();
    expect(m.info).not.toHaveBeenCalled();
  });

  it('--region us uses us without asking, and a configured server wins over it', async () => {
    m.isAgent.mockReturnValue(true);
    await resolveLicenseAuthority(vi.fn(), { region: 'us' });
    expect(m.promptRegion).not.toHaveBeenCalled();
    expect(m.update.mock.calls[0][2]({}).account.accountServer).toBe('https://us.rediacc.cloud');
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    expect(m.fetch.mock.calls[0][1].serverUrl).toBe('https://us.rediacc.cloud');

    resetFreeLicenseStateForTests();
    m.update.mockClear();
    m.configured.mockReturnValue('https://eu.rediacc.cloud');
    await resolveLicenseAuthority(vi.fn(), { region: 'us' });
    expect(m.update).not.toHaveBeenCalled();
    expect(m.warn).toHaveBeenCalledWith(
      expect.stringContaining('errors.freeLicense.regionIgnored')
    );
  });

  it('an unknown --region id is refused', async () => {
    m.isAgent.mockReturnValue(true);
    await expect(resolveLicenseAuthority(vi.fn(), { region: 'mars' })).rejects.toThrow(
      'errors.unknownRegion'
    );
  });
});
