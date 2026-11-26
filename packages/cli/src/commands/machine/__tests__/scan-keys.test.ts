/**
 * `machine scan-keys` exit status: a failed scan is the command's whole purpose failing, so the
 * single form throws a NETWORK_ERROR and the all-machines form sets the exit code after trying
 * every machine and printing a per-machine ok/error row.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EXIT_CODES } from '../../../types/index.js';

const h = vi.hoisted(() => ({
  machines: {} as Record<string, { ip: string; port?: number; knownHosts?: string }>,
  scan: (_ip: string): Promise<string> => Promise.resolve(''),
  updated: [] as string[],
  printed: [] as unknown[],
  exitCode: undefined as number | undefined,
}));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));
vi.mock('../../../services/config/config-resources.js', () => ({
  configService: {
    getLocalMachine: (name: string) => Promise.resolve(h.machines[name]),
    listMachines: () =>
      Promise.resolve(Object.entries(h.machines).map(([name, config]) => ({ name, config }))),
    updateMachine: (name: string) => {
      h.updated.push(name);
      return Promise.resolve();
    },
  },
}));
vi.mock('../../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    warn: vi.fn(),
    success: vi.fn(),
    print: (data: unknown) => h.printed.push(data),
    fail: (code: number) => {
      h.exitCode = code;
    },
  },
}));
vi.mock('../../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../services/core/request-context.js')>()),
  setExitCode: (code: number) => {
    h.exitCode = code;
  },
}));
vi.mock('../../../utils/host-keys.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/host-keys.js')>()),
  scanHostKeys: (ip: string) => h.scan(ip),
}));
vi.mock('../../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/errors.js')>()),
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { registerMachineRegistrationCommands } = await import('../register.js');
const { HostKeyScanError } = await import('../../../utils/host-keys.js');

function run(args: string[], output = 'table'): Promise<unknown> {
  const program = new Command().option('-o, --output <f>', 'format', output);
  program.exitOverride();
  const machine = program.command('machine');
  registerMachineRegistrationCommands(machine, program);
  return program.parseAsync(['node', 'rdc', 'machine', ...args]);
}

beforeEach(() => {
  h.machines = { good: { ip: '10.0.0.1' }, bad: { ip: '10.0.0.2' } };
  h.updated = [];
  h.printed = [];
  h.exitCode = undefined;
  h.scan = (ip) =>
    ip === '10.0.0.2'
      ? Promise.reject(new HostKeyScanError(ip, 22, 'unreachable', 'connect ECONNREFUSED'))
      : Promise.resolve(`${ip} ssh-ed25519 AAAA`);
});

describe('machine scan-keys exit status', () => {
  it('single machine: a failed scan throws a NETWORK_ERROR carrying the reason', async () => {
    const err = await run(['scan-keys', 'bad']).catch((e) => e);
    expect(err).toMatchObject({ code: 'NETWORK_ERROR', exitCode: EXIT_CODES.NETWORK_ERROR });
    expect(String(err.message)).toContain('unreachable');
    expect(h.updated).toEqual([]);
  });

  it('single machine: a successful scan pins and does not throw', async () => {
    await run(['scan-keys', 'good']);
    expect(h.updated).toEqual(['good']);
    expect(h.exitCode).toBeUndefined();
  });

  it('all machines: any failure sets the exit code, after every machine was tried', async () => {
    await run(['scan-keys']);
    expect(h.updated).toEqual(['good']);
    expect(h.exitCode).toBe(EXIT_CODES.NETWORK_ERROR);
  });

  it('all machines: every success leaves the exit code alone', async () => {
    h.machines = { good: { ip: '10.0.0.1' } };
    await run(['scan-keys']);
    expect(h.exitCode).toBeUndefined();
  });

  it('all machines -o json: prints per-machine ok/error rows and still fails', async () => {
    await run(['scan-keys'], 'json');
    expect(h.printed).toEqual([
      [
        { name: 'good', ok: true },
        { name: 'bad', ok: false, error: expect.stringContaining('unreachable') },
      ],
    ]);
    expect(h.exitCode).toBe(EXIT_CODES.NETWORK_ERROR);
  });
});
