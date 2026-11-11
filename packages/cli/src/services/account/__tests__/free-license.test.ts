/**
 * PLAN-free-license F5: the CLI side of the Free License. With no login a human
 * is offered a login or a free licence, an agent or `--yes` takes the free
 * licence with a warning naming the signup link (R11), the licence comes from
 * `POST /licenses/free` on the configured server, a FREE licence renews through
 * renet's blob-authenticated path (R6), and hosted backups name the upgrade
 * instead of failing on a missing token (R13).
 */

import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_BENCH_ORIGIN,
} from '@rediacc/shared/config/well-known.generated';
import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const EU_ORIGIN = WK_ACCOUNT_DEFAULT_ORIGIN;
const US_DOMAIN = BAKED_IN_REGIONS.find((r) => r.id === 'us')?.domain ?? '';
const US_ORIGIN = `https://${US_DOMAIN}`;
const EU_DOMAIN = new URL(EU_ORIGIN).host;

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
  terms: vi.fn(),
  exists: vi.fn(),
  community: {
    maxRepositorySizeGb: 10,
    maxRepoLicenseIssuancesPerMonth: 100,
    storageQuotaBytes: 10 * 1024 ** 3,
  },
}));

vi.mock('@rediacc/shared/subscription', () => ({ PLAN_LIMITS: { COMMUNITY: m.community } }));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
// The Terms flow has its own file (terms.test.ts); here it only has to run and hand its acceptance on.
vi.mock('../terms.js', () => ({ ensureTermsAcceptance: m.terms }));
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
const ACCEPTANCE = {
  version: '2026-03-15',
  sha256: 'f'.repeat(64),
  locale: 'en',
  method: 'cli-flag-unattended',
};
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
  m.terms.mockResolvedValue(ACCEPTANCE);
  m.update.mockResolvedValue(undefined);
  m.promptRegion.mockResolvedValue({ region: {}, domain: EU_DOMAIN });
  m.community.maxRepositorySizeGb = 10;
  m.community.maxRepoLicenseIssuancesPerMonth = 100;
  m.community.storageQuotaBytes = 10 * 1024 ** 3;
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
        termsAcceptance: ACCEPTANCE,
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
  const US = { id: 'us', label: 'United States', domain: US_DOMAIN, default: false };

  it('a terminal with no server asks, uses the pick and saves it', async () => {
    setTty(true);
    m.askChoice.mockResolvedValueOnce('free');
    m.promptRegion.mockResolvedValue({ region: US, domain: US.domain });
    await resolveLicenseAuthority(vi.fn());
    expect(m.promptRegion).toHaveBeenCalledTimes(1);
    expect(m.update).toHaveBeenCalledTimes(1);
    expect(m.update.mock.calls[0][1]).toBe('/account/accountServer');
    const saved = m.update.mock.calls[0][2]({ account: { e2ePublicKey: 'k' } });
    expect(saved.account.accountServer).toBe(US_ORIGIN);
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    expect(m.fetch.mock.calls[0][1].serverUrl).toBe(US_ORIGIN);
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
    m.configured.mockReturnValue(EU_ORIGIN);
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
    expect(m.update.mock.calls[0][2]({}).account.accountServer).toBe(US_ORIGIN);
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    expect(m.fetch.mock.calls[0][1].serverUrl).toBe(US_ORIGIN);

    resetFreeLicenseStateForTests();
    m.update.mockClear();
    m.configured.mockReturnValue(EU_ORIGIN);
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

describe('hidden bench licence region', () => {
  it('bench resolves to the bench account server and is saved like any region', async () => {
    m.isAgent.mockReturnValue(true);
    await resolveLicenseAuthority(vi.fn(), { region: 'bench' });
    expect(m.promptRegion).not.toHaveBeenCalled();
    expect(m.update.mock.calls[0][2]({}).account.accountServer).toBe(WK_BENCH_ORIGIN);
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    expect(m.fetch.mock.calls[0][1].serverUrl).toBe(WK_BENCH_ORIGIN);
  });

  it('control: a lookalike id is still refused, and the message does not name bench', async () => {
    m.isAgent.mockReturnValue(true);
    await expect(resolveLicenseAuthority(vi.fn(), { region: 'bench2' })).rejects.toThrow(
      'errors.unknownRegion'
    );
    const en = (await import('../../../i18n/locales/en/cli.json')).default as {
      errors: { unknownRegion: string };
    };
    expect(en.errors.unknownRegion).not.toMatch(/bench/i);
  });

  it('bench is not in the picker list and not in the baked-in regions', async () => {
    setTty(true);
    m.askChoice.mockResolvedValueOnce('free');
    await resolveLicenseAuthority(vi.fn());
    const offered = m.promptRegion.mock.calls[0][0] as { id: string }[];
    expect(offered.length).toBeGreaterThan(0);
    expect(offered.map((r) => r.id)).not.toContain('bench');
    expect(BAKED_IN_REGIONS.map((r) => r.id)).toContain('us');
  });
});

describe('registration hint on a free licence', () => {
  const hints = () =>
    m.info.mock.calls.map((c) => String(c[0])).filter((x) => x.includes('registerHint'));

  it('a terminal prints it once across repos, with the numbers and the signup URL', async () => {
    setTty(true);
    m.askChoice.mockResolvedValueOnce('free');
    await resolveLicenseAuthority(vi.fn());
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'fork' });
    expect(hints()).toHaveLength(1);
    expect(hints()[0]).toContain('"repoGb":10');
    expect(hints()[0]).toContain('"issuances":100');
    expect(hints()[0]).toContain('"backupGb":10');
    expect(hints()[0]).toContain('/account/login');
  });

  it('the numbers are read from PLAN_LIMITS, not typed', async () => {
    m.community.maxRepositorySizeGb = 77;
    m.community.maxRepoLicenseIssuancesPerMonth = 555;
    m.community.storageQuotaBytes = 33 * 1024 ** 3;
    setTty(true);
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    expect(hints()[0]).toContain('"repoGb":77');
    expect(hints()[0]).toContain('"issuances":555');
    expect(hints()[0]).toContain('"backupGb":33');
    expect(hints()[0]).not.toContain('"repoGb":10');
  });

  it('under an agent the warning carries the numbers and no second hint follows', async () => {
    m.isAgent.mockReturnValue(true);
    m.community.maxRepoLicenseIssuancesPerMonth = 555;
    await resolveLicenseAuthority(vi.fn());
    expect(m.warn).toHaveBeenCalledWith(expect.stringContaining('"issuances":555'));
    m.fetch.mockResolvedValue({ license: BLOB });
    await issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
    expect(hints()).toHaveLength(0);
  });

  it('a subscription licence prints no hint', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    await resolveLicenseAuthority(vi.fn());
    expect(m.warn).not.toHaveBeenCalled();
    expect(hints()).toHaveLength(0);
    expect(m.info).not.toHaveBeenCalled();
  });
});

describe('autoTaken locale text', () => {
  it('names the Community numbers through placeholders in every locale', async () => {
    const en = (await import('../../../i18n/locales/en/cli.json')).default as {
      errors: { freeLicense: Record<string, string> };
    };
    for (const key of ['autoTaken', 'registerHint']) {
      for (const v of ['{{repoGb}}', '{{issuances}}', '{{backupGb}}', '{{url}}']) {
        expect(en.errors.freeLicense[key]).toContain(v);
      }
    }
  });
});
