import { deriveTocPublicKeyLine } from '@rediacc/shared/backup/toc-key';
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mocks = vi.hoisted(() => ({
  print: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  setExitCode: vi.fn(),
  getRepository: vi.fn(),
  execStreaming: vi.fn(),
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mocks.info,
    success: vi.fn(),
    warn: mocks.warn,
    error: vi.fn(),
    print: mocks.print,
  },
}));
vi.mock('../../services/core/request-context.js', async () => ({
  ...(await vi.importActual<typeof import('../../services/core/request-context.js')>(
    '../../services/core/request-context.js'
  )),
  setExitCode: mocks.setExitCode,
}));
vi.mock('../../utils/errors.js', async () => ({
  ...(await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js')),
  getOutputFormat: () => 'json',
  handleError: (e: unknown) => {
    throw e;
  },
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn().mockResolvedValue({ repoKey: 'mail', machineName: 'm1' }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: mocks.getRepository },
}));
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn().mockResolvedValue({
      sftp: { execStreaming: mocks.execStreaming },
      machine: { datastore: '/mnt/rediacc' },
      release: vi.fn(),
    }),
  },
}));

import { registerBackupTocKey } from '../backup-toc-key.js';

const G = '10000000-0000-4000-8000-000000000001';
const GRAND = '10000000-0000-4000-8000-0000000000aa';
const SECRET = 'S3cretCredentialValue0123456789abcdef';
const line = deriveTocPublicKeyLine(SECRET, GRAND).trimEnd();

interface Call {
  command: string;
  stdin?: string;
}
const calls: Call[] = [];

/** A machine holding `stored` (or nothing), answering like renet's toc-key verb. */
function machine(stored: string | null) {
  let current = stored;
  mocks.execStreaming.mockImplementation(
    (command: string, opts: { stdin?: string; onStdout: (d: Buffer) => void }) => {
      calls.push({ command, stdin: opts.stdin });
      const emit = (code: number, record: object) => {
        opts.onStdout(Buffer.from(`${JSON.stringify({ guid: G, ...record })}\n`));
        return Promise.resolve(code);
      };
      if (command.includes('toc-key status')) {
        return emit(0, {
          action: 'status',
          outcome: current === null ? 'absent' : 'present',
          publicKey: current ?? undefined,
        });
      }
      const sent = /--public-key '([^']+)'/.exec(command)?.[1] ?? '';
      if (current === null) {
        current = sent;
        return emit(0, { action: 'install', outcome: 'installed' });
      }
      if (current === sent) return emit(0, { action: 'install', outcome: 'unchanged' });
      if (command.includes('--replace')) {
        current = sent;
        return emit(0, { action: 'install', outcome: 'replaced' });
      }
      return emit(1, { action: 'install', outcome: 'differs' });
    }
  );
}

async function run(args: string[]): Promise<void> {
  const program = new Command().exitOverride();
  const backup = program.command('backup');
  registerBackupTocKey(backup);
  await program.parseAsync(['node', 'rdc', 'backup', 'toc-key', ...args]);
}
const printed = (): { results: { outcome: string }[] } => mocks.print.mock.calls.at(-1)?.[0];

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  mocks.getRepository.mockResolvedValue({
    repositoryGuid: G,
    grandGuid: GRAND,
    credential: SECRET,
  });
});

describe('backup toc-key sync', () => {
  it('installs a missing key and exits 0, with only the public line leaving the CLI', async () => {
    machine(null);
    await run(['sync', 'mail']);
    expect(printed().results[0].outcome).toBe('installed');
    expect(mocks.setExitCode).not.toHaveBeenCalled();
    expect(calls.every((c) => c.stdin === undefined)).toBe(true);
    expect(calls.map((c) => c.command).join('\n')).not.toContain(SECRET);
    expect(calls.map((c) => c.command).join('\n')).toContain(line);
  });

  it('an equal key is a silent no-op', async () => {
    machine(line);
    await run(['sync', 'mail']);
    expect(printed().results[0].outcome).toBe('unchanged');
    expect(mocks.warn).not.toHaveBeenCalled();
    expect(mocks.setExitCode).not.toHaveBeenCalled();
  });

  it('a different key is never overwritten without --replace, warns, and exits 1', async () => {
    machine('rediacc-toc-x25519 OTHERKEY');
    await run(['sync', 'mail']);
    expect(printed().results[0].outcome).toBe('differs');
    expect(calls.some((c) => c.command.includes('--replace'))).toBe(false);
    expect(mocks.warn.mock.calls.join('\n')).toContain('--replace');
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('--replace carries the credential on stdin of that one call, and never on argv', async () => {
    machine('rediacc-toc-x25519 OTHERKEY');
    await run(['sync', 'mail', '--replace']);
    expect(printed().results[0].outcome).toBe('replaced');
    const withSecret = calls.filter((c) => c.stdin !== undefined);
    expect(withSecret).toHaveLength(1);
    expect(withSecret[0].stdin).toBe(SECRET);
    expect(withSecret[0].command).toContain('--password-stdin');
    expect(calls.map((c) => c.command).join('\n')).not.toContain(SECRET);
    expect(mocks.setExitCode).not.toHaveBeenCalled();
  });

  it('--dry-run reads and writes nothing on the machine', async () => {
    machine(null);
    await run(['sync', 'mail', '--dry-run']);
    expect(mocks.execStreaming).not.toHaveBeenCalled();
    expect(printed().results[0].outcome).toBe('dry-run');
  });

  it('a repository with no credential warns and exits 1, asking the machine nothing', async () => {
    mocks.getRepository.mockResolvedValue({ repositoryGuid: G, grandGuid: GRAND });
    machine(null);
    await run(['sync', 'mail']);
    expect(printed().results[0].outcome).toBe('no-credential');
    expect(mocks.execStreaming).not.toHaveBeenCalled();
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });
});
