/** `rdc config remote enable --master-password-stdin`: the master password is read from stdin and handed on, never argv. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockReadStdinValue, mockEnableMasterPassword, mockHandleError, mockLoad } = vi.hoisted(
  () => ({
    mockReadStdinValue: vi.fn(),
    mockEnableMasterPassword: vi.fn(),
    mockHandleError: vi.fn(),
    mockLoad: vi.fn(),
  })
);

vi.mock('../../utils/stdin.js', () => ({ readStdinValue: mockReadStdinValue }));
vi.mock('../config-remote-master-password.js', () => ({
  enableMasterPassword: mockEnableMasterPassword,
}));
vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: { load: mockLoad },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getEffectiveConfigName: () => 'rediacc' },
}));
vi.mock('../../utils/secure-storage.js', () => ({ getSecureStorage: () => ({}) }));
vi.mock('../../services/account/subscription-auth.js', async (orig) => ({
  ...(await orig<typeof import('../../services/account/subscription-auth.js')>()),
  getSubscriptionServerUrl: () => 'https://account.example.com',
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<typeof import('../../utils/errors.js')>()),
  handleError: mockHandleError,
}));

const { registerRemoteCommands } = await import('../config-remote.js');
const { Command } = await import('commander');

const SECRET = 'master-SECRET-pw';

async function run(args: string[]): Promise<void> {
  const config = new Command('config');
  registerRemoteCommands(config);
  await config.parseAsync(['node', 'rdc', 'remote', 'enable', ...args], { from: 'node' });
}

const takesPasswordValue = (o: { long?: string; required: boolean; optional: boolean }) =>
  /password/.test(o.long ?? '') && (o.required || o.optional);

describe('password option predicate', () => {
  it('catches required and optional value forms but not a bare flag', () => {
    const cmd = new Command('x')
      .option('--a-password <v>')
      .option('--b-password [v]')
      .option('--c-password-stdin');
    expect(cmd.options.filter(takesPasswordValue).map((o) => o.long)).toEqual([
      '--a-password',
      '--b-password',
    ]);
  });
});

describe('config remote enable --master-password-stdin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoad.mockResolvedValue({ schemaVersion: 3, id: 'x', version: 1 });
  });

  it('passes the stdin master password to the enroll without --master-password', async () => {
    mockReadStdinValue.mockResolvedValue(SECRET);
    await run(['--master-password-stdin']);
    expect(mockEnableMasterPassword).toHaveBeenCalledWith(
      'https://account.example.com',
      expect.any(String),
      expect.objectContaining({ masterPassword: SECRET })
    );
    expect(mockHandleError).not.toHaveBeenCalled();
  });

  it('refuses an empty stdin without echoing anything', async () => {
    mockReadStdinValue.mockResolvedValue('');
    await run(['--master-password-stdin']);
    expect(mockEnableMasterPassword).not.toHaveBeenCalled();
    const err = mockHandleError.mock.calls[0][0] as Error;
    expect(err.message).toContain('--master-password-stdin');
  });

  it('has no option that takes the password as a value', () => {
    const config = new Command('config');
    registerRemoteCommands(config);
    const enable = config.commands
      .find((c) => c.name() === 'remote')
      ?.commands.find((c) => c.name() === 'enable');
    const valued = enable?.options.filter(takesPasswordValue);
    expect(valued).toEqual([]);
  });
});
