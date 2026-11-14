/**
 * PLAN-terms-acceptance C3: `rdc legal`. The Terms version comes from the shared manifest, the
 * acceptance from the account server when logged in and from the config state when anonymous.
 */

import { LEGAL_ENTITY, termsAt } from '@rediacc/shared/legal';
import { Command } from 'commander';
import {
  afterAll,
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  type MockInstance,
  vi,
} from 'vitest';

const m = vi.hoisted(() => ({
  tokenState: vi.fn(),
  fetch: vi.fn(),
  getCurrent: vi.fn(),
  print: vi.fn(),
  printError: vi.fn(),
  exit: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: m.fetch }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: m.tokenState,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: m.getCurrent },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    print: m.print,
    error: m.printError,
    getCommandName: () => 'legal',
    getWarnings: () => [],
    getDurationMs: () => 0,
  },
}));
vi.mock('../../services/telemetry/telemetry.js', () => ({
  telemetryService: { trackError: vi.fn(), shutdown: () => Promise.resolve() },
}));

import { collectLegalInfo, registerLegalCommand, renderLegal } from '../legal.js';

async function run(args: string[]): Promise<void> {
  const program = new Command().option('-o, --output <format>', 'format', 'table');
  registerLegalCommand(program);
  await program.parseAsync(['node', 'rdc', 'legal', ...args]);
}

const realExit = process.exit;
let exitSpy: MockInstance<typeof process.exit>;

beforeEach(() => {
  vi.clearAllMocks();
  exitSpy = vi.spyOn(process, 'exit').mockImplementation(((code?: number) => {
    m.exit(code);
    return undefined as never;
  }) as typeof process.exit);
  m.tokenState.mockReturnValue({ kind: 'missing' });
  m.getCurrent.mockResolvedValue({ state: {} });
});

afterEach(() => {
  exitSpy.mockRestore();
});

// The spy is per test: a process.exit left replaced would swallow every later exit in the worker.
afterAll(() => {
  expect(process.exit).toBe(realExit);
});

describe('rdc legal --json', () => {
  it('terms.version equals the manifest and accepted comes from state when anonymous', async () => {
    m.getCurrent.mockResolvedValue({
      state: {
        terms: {
          version: '2026-03-15',
          sha256: 'x',
          acceptedAt: '2026-11-11T10:00:00.000Z',
          method: 'cli-prompt',
        },
      },
    });
    await run(['--json']);
    const parsed = JSON.parse(m.print.mock.calls[0][0] as string);
    expect(parsed.terms.version).toBe(termsAt(new Date()).current.version);
    expect(parsed.terms.sha256).toBe(termsAt(new Date()).current.sha256);
    expect(parsed.accepted).toEqual({
      version: '2026-03-15',
      acceptedAt: '2026-11-11T10:00:00.000Z',
      method: 'cli-prompt',
      source: 'config',
    });
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('anonymous with nothing stored reports not accepted', async () => {
    expect((await collectLegalInfo()).accepted).toBeNull();
  });

  it('logged in reads the acceptance from the account server', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockResolvedValue({
      accepted: {
        version: '2026-03-15',
        acceptedAt: '2026-11-11T09:00:00Z',
        method: 'web-checkbox',
      },
    });
    const info = await collectLegalInfo();
    expect(m.fetch).toHaveBeenCalledWith('/account/api/v1/terms/status');
    expect(info.accepted).toMatchObject({
      version: '2026-03-15',
      method: 'web-checkbox',
      source: 'account',
    });
  });

  it('a server that cannot answer leaves the acceptance unknown, flagged unreachable', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockRejectedValue(new Error('offline'));
    const info = await collectLegalInfo();
    expect(info.accepted).toBeNull();
    expect(info.acceptedUnreachable).toBe(true);
    const out = renderLegal(info);
    expect(out).toContain('commands.legal.acceptedUnreachable');
    expect(out).not.toContain('commands.legal.notAccepted');
  });

  it('a server that answers 500 surfaces its error instead of being flagged unreachable', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockRejectedValue(Object.assign(new Error('boom'), { status: 500 }));
    await expect(collectLegalInfo()).rejects.toMatchObject({ status: 500 });
  });

  it.each([
    [401, 'unauthorized'],
    [500, 'boom'],
  ])(
    'the legal command given a %i prints the error and exits non-zero, with nothing on stdout',
    async (status, message) => {
      m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
      m.fetch.mockRejectedValue(Object.assign(new Error(message), { status }));
      await run([]);
      expect(m.printError).toHaveBeenCalledWith(expect.stringContaining(message));
      expect(m.exit).toHaveBeenCalledTimes(1);
      expect(m.exit.mock.calls[0][0]).not.toBe(0);
      expect(m.print).not.toHaveBeenCalled();
    }
  );

  it('control: the legal command given an unreachable server prints the document and exits cleanly', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockRejectedValue(new Error('offline'));
    await run([]);
    expect(m.print).toHaveBeenCalledTimes(1);
    expect(m.print.mock.calls[0][0]).toContain('commands.legal.acceptedUnreachable');
    expect(m.printError).not.toHaveBeenCalled();
    expect(m.exit).not.toHaveBeenCalled();
  });

  it('a reachable server with no acceptance on record is plainly not accepted', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockResolvedValue({ accepted: null });
    const info = await collectLegalInfo();
    expect(info.acceptedUnreachable).toBe(false);
    const out = renderLegal(info);
    expect(out).toContain('commands.legal.notAccepted');
    expect(out).not.toContain('commands.legal.acceptedUnreachable');
  });
});

describe('the legal command, human-readable output', () => {
  it('shows the contracting entity only, the binding links and the credits pointer', async () => {
    const out = renderLegal(await collectLegalInfo());
    expect(out).toContain(LEGAL_ENTITY.legalName);
    expect(out).toContain(LEGAL_ENTITY.registryCode);
    expect(out).toContain('rdc credits --licenses');
    expect(out).not.toMatch(/licensor/i);
    expect(out).toContain('commands.legal.notAccepted');
  });

  it('every document has a page URL and an English binding URL', async () => {
    const info = await collectLegalInfo();
    expect(info.documents.length).toBeGreaterThan(0);
    for (const doc of info.documents) {
      expect(doc.url).toMatch(/^https:\/\//);
      expect(doc.bindingUrl).toContain('/en/');
    }
  });
});
