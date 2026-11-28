/**
 * `machine scan-keys -o json` over every machine: the envelope agrees with the exit code. One dead
 * machine exits NETWORK_ERROR, so the envelope says success:false with an error naming the machine,
 * and still carries every per-machine row; an all-good run stays success:true with no errors.
 * Runs the real outputService inside a request context, which captures stdout and the exit code.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createOutputState, runInRequestContext } from '../../../services/core/request-context.js';
import { EXIT_CODES } from '../../../types/index.js';

const h = vi.hoisted(() => ({
  machines: {} as Record<string, { ip: string; port?: number; knownHosts?: string }>,
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
    updateMachine: () => Promise.resolve(),
  },
}));
vi.mock('../../../utils/host-keys.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../utils/host-keys.js')>();
  return {
    ...actual,
    scanHostKeys: (ip: string) =>
      ip === '10.0.0.2'
        ? Promise.reject(new actual.HostKeyScanError(ip, 22, 'unreachable', 'connect ECONNREFUSED'))
        : Promise.resolve(`${ip} ssh-ed25519 AAAA`),
  };
});

const { registerMachineRegistrationCommands } = await import('../register.js');

interface Envelope {
  success: boolean;
  data: unknown;
  errors: { code: string; message: string; retryable: boolean; exitCode: number }[] | null;
}

async function scanAllJson(): Promise<{ envelope: Envelope; exitCode: number | undefined }> {
  const ctx = {
    output: createOutputState(),
    stdout: [] as (string | Uint8Array)[],
    stderr: [] as string[],
    exitCode: undefined as number | undefined,
  };
  await runInRequestContext(ctx, async () => {
    const program = new Command().option('-o, --output <f>', 'format', 'json');
    program.exitOverride();
    registerMachineRegistrationCommands(program.command('machine'), program);
    await program.parseAsync(['node', 'rdc', 'machine', 'scan-keys']);
  });
  return { envelope: JSON.parse(ctx.stdout.join('')) as Envelope, exitCode: ctx.exitCode };
}

beforeEach(() => {
  h.machines = { good: { ip: '10.0.0.1' }, dead: { ip: '10.0.0.2' } };
});

describe('machine scan-keys -o json envelope', () => {
  it('one dead machine: success:false, a NETWORK_ERROR naming it, and every row kept', async () => {
    const { envelope, exitCode } = await scanAllJson();
    expect(exitCode).toBe(EXIT_CODES.NETWORK_ERROR);
    expect(envelope.success).toBe(false);
    expect(envelope.errors).toEqual([
      {
        code: 'NETWORK_ERROR',
        message: expect.stringContaining('dead'),
        retryable: true,
        exitCode: EXIT_CODES.NETWORK_ERROR,
      },
    ]);
    expect(envelope.errors?.[0].message).toContain('unreachable');
    expect(envelope.errors?.[0].message).not.toContain('good');
    expect(envelope.data).toEqual([
      { name: 'good', ok: true },
      { name: 'dead', ok: false, error: expect.stringContaining('unreachable') },
    ]);
  });

  it('every machine scanned: success:true and no errors', async () => {
    h.machines = { good: { ip: '10.0.0.1' }, other: { ip: '10.0.0.3' } };
    const { envelope, exitCode } = await scanAllJson();
    expect(exitCode).toBeUndefined();
    expect(envelope.success).toBe(true);
    expect(envelope.errors).toBeNull();
    expect(envelope.data).toEqual([
      { name: 'good', ok: true },
      { name: 'other', ok: true },
    ]);
  });
});
