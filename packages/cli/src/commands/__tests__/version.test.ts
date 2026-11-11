/**
 * PLAN-terms-acceptance C3: `rdc version`. Offline it reports "unknown (offline)" and still exits
 * 0, anonymously it names FREE per repository, and logged in it shows the plan.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  tokenState: vi.fn(),
  fetch: vi.fn(),
  print: vi.fn(),
  handleError: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: m.fetch }));
vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: m.tokenState,
}));
vi.mock('../../services/core/output.js', () => ({ outputService: { print: m.print } }));
vi.mock('../../services/update/updater.js', () => ({ resolveChannel: () => 'edge' }));
vi.mock('../../utils/errors.js', () => ({ handleError: m.handleError }));

import { collectVersionInfo, registerVersionCommand } from '../version.js';

async function run(args: string[]): Promise<void> {
  const program = new Command().option('-o, --output <format>', 'format', 'table');
  registerVersionCommand(program);
  await program.parseAsync(['node', 'rdc', 'version', ...args]);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('rdc version', () => {
  it('offline with a login reports unknown (offline) and does not fail', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockRejectedValue(new Error('getaddrinfo ENOTFOUND'));
    await run([]);
    expect(m.handleError).not.toHaveBeenCalled();
    const out = m.print.mock.calls[0][0] as string;
    expect(out).toContain('commands.version.license.label');
    expect(out).toContain('commands.version.license.unknown');
  });

  it('without a login the licence is anonymous and nothing is fetched', async () => {
    m.tokenState.mockReturnValue({ kind: 'missing' });
    const info = await collectVersionInfo();
    expect(info.license).toEqual({ kind: 'anonymous' });
    expect(info.channel).toBe('edge');
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('logged in shows the plan from the account server', async () => {
    m.tokenState.mockReturnValue({ kind: 'ready', token: {}, serverUrl: 'x' });
    m.fetch.mockResolvedValue({ planCode: 'BUSINESS' });
    expect((await collectVersionInfo()).license).toEqual({ kind: 'account', tier: 'BUSINESS' });
  });

  it('--json prints the info object, platform and channel included', async () => {
    m.tokenState.mockReturnValue({ kind: 'missing' });
    await run(['--json']);
    const parsed = JSON.parse(m.print.mock.calls[0][0] as string);
    expect(parsed).toMatchObject({
      platform: process.platform,
      arch: process.arch,
      channel: 'edge',
      license: { kind: 'anonymous' },
    });
    expect(typeof parsed.version).toBe('string');
  });
});
