/**
 * PLAN-terms-acceptance C1: the CLI's Terms acceptance for the anonymous Free License.
 * An unattended run needs `--accept-terms` or `RDC_ACCEPT_TERMS=1` and refuses before any fetch,
 * `--yes` alone never accepts, a terminal asks y/N (default N), the acceptance is cached in
 * `state.terms` and asked again only when a newer version is declared, and a ready token never asks.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  fetch: vi.fn(),
  tokenState: vi.fn(),
  isAgent: vi.fn(),
  askChoice: vi.fn(),
  askConfirm: vi.fn(),
  getCurrent: vi.fn(),
  updateState: vi.fn(),
  exists: vi.fn(),
  latest: { version: '2026-11-11', sha256: 'a'.repeat(64) },
  warn: vi.fn(),
  info: vi.fn(),
}));

vi.mock('@rediacc/shared/subscription', () => ({
  PLAN_LIMITS: {
    COMMUNITY: {
      maxRepositorySizeGb: 10,
      maxRepoLicenseIssuancesPerMonth: 100,
      storageQuotaBytes: 1,
    },
  },
}));
vi.mock('@rediacc/shared/legal', () => ({
  CONSENT_NOTICES: { en: {} },
  LEGAL_ENTITY: { legalName: 'Example Ltd' },
  LEGAL_URLS: {
    terms: 'https://example.test/en/terms',
    privacy: 'https://example.test/en/privacy',
  },
  termsAt: () => ({ latest: m.latest }),
  satisfies: (accepted: string, required: string) => accepted >= required,
  consentNotice: (method: string) =>
    method === 'cli-prompt'
      ? 'Terms of {{legalName}} at {{termsUrl}} and {{privacyUrl}}. Accept the Terms?'
      : 'Unattended. Pass --accept-terms or set RDC_ACCEPT_TERMS=1. See {{termsUrl}}.',
}));
vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../account-client.js', () => ({ accountServerFetch: m.fetch }));
vi.mock('../subscription-auth.js', () => ({
  getSubscriptionTokenState: m.tokenState,
  getSubscriptionServerUrl: (preferred?: string) => preferred ?? 'https://acct.example',
  getConfiguredServerUrl: () => 'https://acct.example',
}));
vi.mock('../../../utils/region-prompt.js', () => ({ promptRegionSelection: vi.fn() }));
vi.mock('../../config/synced-write.js', () => ({ updateConfigAtPointer: vi.fn() }));
vi.mock('../../config/config-name.js', () => ({ getEffectiveConfigName: () => 'cfg' }));
vi.mock('../../config/config-resources.js', () => ({
  configService: { getCurrent: m.getCurrent },
}));
vi.mock('../../../adapters/config-file-storage.js', () => ({
  configFileStorage: { exists: m.exists, updateState: m.updateState },
}));
vi.mock('../../../utils/agent-guard.js', () => ({ isAgentEnvironment: m.isAgent }));
vi.mock('../../../utils/prompt.js', () => ({ askChoice: m.askChoice, askConfirm: m.askConfirm }));
vi.mock('../../core/output.js', () => ({ outputService: { warn: m.warn, info: m.info } }));
vi.mock('../license-machine.js', () => ({
  readRemoteMachineId: vi.fn().mockResolvedValue('a'.repeat(64)),
  readLocalMachineId: vi.fn().mockResolvedValue('b'.repeat(64)),
  writeRepoLicense: vi.fn(),
}));
vi.mock('../../machine/machine-connection.js', () => ({
  sftpConfigForMachine: () => ({}),
  withSharedOrPooledSftp: (sftp: unknown, _cfg: unknown, fn: (s: unknown) => unknown) => fn(sftp),
}));

import {
  issueFreeRepoLicense,
  resetFreeLicenseStateForTests,
  resolveLicenseAuthority,
} from '../free-license.js';
import { resetTermsStateForTests, setAcceptTermsFlag } from '../terms.js';

const MACHINE = { ip: '10.0.0.1', user: 'root' } as never;
const GUID = '11111111-2222-4333-8444-555555555555';

const stdinTty = Object.getOwnPropertyDescriptor(process.stdin, 'isTTY');
const stdoutTty = Object.getOwnPropertyDescriptor(process.stdout, 'isTTY');

function setTty(value: boolean): void {
  Object.defineProperty(process.stdin, 'isTTY', { value, configurable: true });
  Object.defineProperty(process.stdout, 'isTTY', { value, configurable: true });
}

function issue(): Promise<void> {
  return issueFreeRepoLicense('m', MACHINE, 'key', { repositoryGuid: GUID, kind: 'grand' });
}

beforeEach(() => {
  resetFreeLicenseStateForTests();
  resetTermsStateForTests();
  vi.clearAllMocks();
  m.latest = { version: '2026-11-11', sha256: 'a'.repeat(64) };
  m.tokenState.mockReturnValue({ kind: 'missing' });
  m.isAgent.mockReturnValue(false);
  m.getCurrent.mockResolvedValue({ state: {} });
  m.exists.mockResolvedValue(true);
  m.updateState.mockResolvedValue(undefined);
  m.fetch.mockResolvedValue({ license: {} });
  delete process.env.REDIACC_YES;
  delete process.env.RDC_ACCEPT_TERMS;
  setTty(false);
});

afterEach(() => {
  delete process.env.REDIACC_YES;
  delete process.env.RDC_ACCEPT_TERMS;
  if (stdinTty) Object.defineProperty(process.stdin, 'isTTY', stdinTty);
  if (stdoutTty) Object.defineProperty(process.stdout, 'isTTY', stdoutTty);
});

describe('unattended runs', () => {
  it('an agent with no flag throws before any fetch, naming the flag, the env var and the URL', async () => {
    m.isAgent.mockReturnValue(true);
    const error = await resolveLicenseAuthority(vi.fn()).catch((e: Error) => e);
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toContain('--accept-terms');
    expect((error as Error).message).toContain('RDC_ACCEPT_TERMS=1');
    expect((error as Error).message).toContain('https://example.test/en/terms');
    expect(m.fetch).not.toHaveBeenCalled();
    expect(m.updateState).not.toHaveBeenCalled();
  });

  it('--yes alone refuses, on a terminal too', async () => {
    process.env.REDIACC_YES = '1';
    setTty(true);
    await expect(resolveLicenseAuthority(vi.fn())).rejects.toThrow('--accept-terms');
    expect(m.askConfirm).not.toHaveBeenCalled();
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('no terminal, no agent and no flag refuses a direct issue before any fetch', async () => {
    await expect(issue()).rejects.toThrow('RDC_ACCEPT_TERMS=1');
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('the --accept-terms flag sends cli-flag-unattended and caches the acceptance', async () => {
    m.isAgent.mockReturnValue(true);
    setAcceptTermsFlag(true);
    await expect(resolveLicenseAuthority(vi.fn())).resolves.toBe('free');
    await issue();
    expect(m.askConfirm).not.toHaveBeenCalled();
    expect(m.fetch.mock.calls[0][1].body.termsAcceptance).toEqual({
      version: '2026-11-11',
      sha256: 'a'.repeat(64),
      locale: 'en',
      method: 'cli-flag-unattended',
    });
    const saved = m.updateState.mock.calls[0][1]({ state: { networkIds: { next: 3 } } });
    expect(saved.state.networkIds).toEqual({ next: 3 });
    expect(saved.state.terms).toMatchObject({
      version: '2026-11-11',
      method: 'cli-flag-unattended',
    });
  });

  it('RDC_ACCEPT_TERMS=1 accepts like the flag', async () => {
    m.isAgent.mockReturnValue(true);
    process.env.RDC_ACCEPT_TERMS = '1';
    await resolveLicenseAuthority(vi.fn());
    await issue();
    expect(m.fetch.mock.calls[0][1].body.termsAcceptance.method).toBe('cli-flag-unattended');
  });
});

describe('a terminal', () => {
  beforeEach(() => {
    setTty(true);
    m.askChoice.mockResolvedValue('free');
  });

  it('answering N fetches nothing and stores nothing', async () => {
    m.askConfirm.mockResolvedValue(false);
    await expect(resolveLicenseAuthority(vi.fn())).rejects.toThrow('errors.terms.declined');
    expect(m.askConfirm).toHaveBeenCalledWith(expect.stringContaining('Accept the Terms?'), false);
    expect(m.fetch).not.toHaveBeenCalled();
    expect(m.updateState).not.toHaveBeenCalled();
  });

  it('answering y sends cli-prompt, with the notice tokens filled', async () => {
    m.askConfirm.mockResolvedValue(true);
    await resolveLicenseAuthority(vi.fn());
    const shown = m.askConfirm.mock.calls[0][0] as string;
    expect(shown).toContain('Example Ltd');
    expect(shown).toContain('https://example.test/en/terms');
    expect(shown).not.toContain('{{');
    await issue();
    expect(m.fetch.mock.calls[0][1].body.termsAcceptance.method).toBe('cli-prompt');
  });

  it('a cached current acceptance skips the prompt, and a newer latest asks again', async () => {
    m.getCurrent.mockResolvedValue({
      state: {
        terms: {
          version: '2026-11-11',
          sha256: 'a'.repeat(64),
          acceptedAt: 'x',
          method: 'cli-prompt',
        },
      },
    });
    await resolveLicenseAuthority(vi.fn());
    expect(m.askConfirm).not.toHaveBeenCalled();
    await issue();
    expect(m.fetch.mock.calls[0][1].body.termsAcceptance.version).toBe('2026-11-11');

    resetFreeLicenseStateForTests();
    resetTermsStateForTests();
    m.latest = { version: '2027-01-01', sha256: 'c'.repeat(64) };
    m.askConfirm.mockResolvedValue(true);
    await resolveLicenseAuthority(vi.fn());
    expect(m.askConfirm).toHaveBeenCalledTimes(1);
  });
});

describe('a ready token', () => {
  it('never prompts and never refuses', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.isAgent.mockReturnValue(true);
    setTty(true);
    await expect(resolveLicenseAuthority(vi.fn())).resolves.toBe('token');
    expect(m.askConfirm).not.toHaveBeenCalled();
    expect(m.fetch).not.toHaveBeenCalled();
  });
});
