/**
 * The access verbs (PLAN-ssh-key-source-ranges C1): `rdc config access` edits the
 * config's `access` bucket, `rdc machine access` binds keys to machines and
 * pushes them, `machine setup` re-applies them, and the contract keeps the push
 * off the proxy.
 */
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { AccessSchema } from '@rediacc/shared/config-schema';
import { Command } from 'commander';
import ssh2 from 'ssh2';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const h = vi.hoisted(() => ({
  state: {
    access: undefined as Record<string, unknown> | undefined,
    machines: {} as Record<string, { ip: string; user: string }>,
    writes: 0,
  },
  printed: [] as { data: unknown; format: unknown }[],
  warnings: [] as string[],
  stdout: [] as string[],
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getAccess: vi.fn(() => Promise.resolve(structuredClone(h.state.access))),
    updateAccess: vi.fn((edit: (access: Record<string, unknown>) => unknown) => {
      try {
        h.state.access = edit(structuredClone(h.state.access ?? {})) as Record<string, unknown>;
      } catch (error) {
        return Promise.reject(error);
      }
      h.state.writes += 1;
      return Promise.resolve();
    }),
    getLocalMachine: vi.fn((name: string) => {
      const machine = h.state.machines[name];
      if (!machine) return Promise.reject(new Error(`Machine "${name}" not found`));
      return Promise.resolve(machine);
    }),
    getLocalConfig: vi.fn(async () => ({ machines: h.state.machines })),
  },
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    warn: vi.fn((message: string) => h.warnings.push(message)),
    print: vi.fn((data: unknown, format?: unknown) => h.printed.push({ data, format })),
    format: vi.fn((data: unknown) => JSON.stringify(data)),
    getCommandName: vi.fn(() => 'machine access push'),
    getWarnings: vi.fn(() => []),
    getDurationMs: vi.fn(() => 0),
  },
}));

vi.mock('../../services/machine/access-push.js', () => ({ pushAccess: vi.fn() }));
vi.mock('../../services/repo/repo-key-deployment.js', () => ({ deployAllRepoKeys: vi.fn() }));
vi.mock('../../services/provision/infra-provision.js', () => ({ pushInfraConfig: vi.fn() }));
vi.mock('../../services/machine/machine-remove-guard.js', () => ({ guardMachineRemoval: vi.fn() }));
vi.mock('../../services/machine/machine-connection.js', () => ({ machineConnections: {} }));
vi.mock('../../services/renet/renet-execution.js', () => ({
  acquireRemoteRenet: vi.fn(),
  readSSHKey: vi.fn(),
}));
vi.mock('../../services/telemetry/telemetry.js', () => ({
  telemetryService: { trackError: vi.fn(), shutdown: vi.fn().mockResolvedValue(undefined) },
}));
vi.mock('../../services/core/request-context.js', () => ({
  setExitCode: vi.fn(),
  writeStdout: vi.fn((chunk: string) => h.stdout.push(chunk)),
  currentRequestContext: vi.fn(() => undefined),
  DispatchExit: class extends Error {},
  exitProcess: vi.fn((code: number) => {
    throw new Error(`exit ${code}`);
  }),
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (e: unknown) => {
    throw e;
  },
}));

const { registerAccessCommands: registerConfigAccess } = await import('../config-access.js');
const { registerAccessCommands: registerMachineAccess } = await import('../machine/access.js');
const { postSetupMachineTasks } = await import('../machine/register.js');
const { pushAccess } = await import('../../services/machine/access-push.js');
const { deployAllRepoKeys } = await import('../../services/repo/repo-key-deployment.js');

const PROBE = ssh2.utils.generateKeyPairSync('ed25519', { comment: 'console-probe' }).public;

function cli(): Command {
  const program = new Command();
  program.option('-o, --output <format>', 'output format', 'table');
  program.exitOverride();
  registerConfigAccess(program.command('config'), program);
  registerMachineAccess(program.command('machine'), program);
  return program;
}

async function run(...argv: string[]): Promise<void> {
  await cli().parseAsync(argv, { from: 'user' });
}

beforeEach(() => {
  h.state.access = undefined;
  h.state.machines = { hostinger: { ip: '72.61.137.225', user: 'muhammed' } };
  h.state.writes = 0;
  h.printed.length = 0;
  h.warnings.length = 0;
  h.stdout.length = 0;
  vi.clearAllMocks();
});

describe('config access', () => {
  it('add --hosted-executor writes both lists', async () => {
    await run(
      'config',
      'access',
      'add',
      'console-probe',
      '--public-key',
      PROBE,
      '--hosted-executor'
    );

    expect(h.state.access).toEqual({
      keys: {
        'console-probe': {
          publicKey: PROBE,
          sourceRanges: { ipv4: ['104.28.0.0/16'], ipv6: ['2a09:bac0::/29'] },
        },
      },
    });
    expect(AccessSchema.safeParse(h.state.access).success).toBe(true);
  });

  it('add --ipv6 alongside --hosted-executor adds to the seeded list; --no-restrict is stored', async () => {
    await run(
      'config',
      'access',
      'add',
      'team',
      '--public-key',
      PROBE,
      '--hosted-executor',
      '--ipv6',
      '2001:db8::/32',
      '--no-restrict'
    );
    expect(h.state.access).toMatchObject({
      keys: {
        team: {
          restrict: false,
          sourceRanges: { ipv4: ['104.28.0.0/16'], ipv6: ['2a09:bac0::/29', '2001:db8::/32'] },
        },
      },
    });
  });

  it('add without any range is refused by the schema and writes nothing', async () => {
    await expect(
      run('config', 'access', 'add', 'console-probe', '--public-key', PROBE)
    ).rejects.toThrow(/resolves to no source range/);
    expect(h.state.access).toBeUndefined();
  });

  it('add with a host-bit CIDR is refused naming the canonical form', async () => {
    await expect(
      run('config', 'access', 'add', 'p', '--public-key', PROBE, '--ipv4', '104.28.1.0/16')
    ).rejects.toThrow(/104\.28\.0\.0\/16/);
  });

  it('add on an existing key keeps its machine bindings', async () => {
    await run('config', 'access', 'add', 'p', '--public-key', PROBE, '--hosted-executor');
    await run('machine', 'access', 'set', 'hostinger', '--key', 'p');
    await run('config', 'access', 'add', 'p', '--public-key', PROBE, '--ipv4', '198.51.100.0/24');
    expect(h.state.access).toMatchObject({
      keys: { p: { sourceRanges: { ipv4: ['198.51.100.0/24'] }, machines: { hostinger: {} } } },
    });
  });

  it('ranges --clear with a range flag is refused', async () => {
    await expect(run('config', 'access', 'ranges', '--clear', '--hosted-executor')).rejects.toThrow(
      /clearConflict/
    );
    expect(h.state.writes).toBe(0);
  });

  it('list -o json prints one row per key', async () => {
    await run('config', 'access', 'add', 'p', '--public-key', PROBE, '--hosted-executor');
    await run('-o', 'json', 'config', 'access', 'list');
    expect(h.printed.at(-1)).toEqual({
      format: 'json',
      data: [
        {
          key: 'p',
          type: 'ssh-ed25519',
          comment: 'console-probe',
          restrict: true,
          sourceRanges: { ipv4: ['104.28.0.0/16'], ipv6: ['2a09:bac0::/29'] },
          machines: [],
        },
      ],
    });
  });

  it('remove of an unknown key is refused', async () => {
    await expect(run('config', 'access', 'remove', 'nope')).rejects.toThrow(/keyNotFound/);
  });
});

describe('machine access', () => {
  beforeEach(async () => {
    await run('config', 'access', 'add', 'p', '--public-key', PROBE, '--hosted-executor');
    h.state.writes = 0;
  });

  it('set on an unknown machine refuses and writes nothing', async () => {
    await expect(run('machine', 'access', 'set', 'ghost', '--key', 'p')).rejects.toThrow(
      /Machine "ghost" not found/
    );
    expect(h.state.writes).toBe(0);
  });

  it('set binds the key, with machine ranges replacing the key ranges there', async () => {
    await run('machine', 'access', 'set', 'hostinger', '--key', 'p', '--ipv6', '2a09:bac0::/29');
    expect(h.state.access).toMatchObject({
      keys: { p: { machines: { hostinger: { sourceRanges: { ipv6: ['2a09:bac0::/29'] } } } } },
    });
    await run('machine', 'access', 'set', 'hostinger', '--key', 'p', '--clear-ranges');
    expect(h.state.access).toMatchObject({ keys: { p: { machines: { hostinger: {} } } } });
  });

  it('remove drops a binding even when the machine no longer exists', async () => {
    await run('machine', 'access', 'set', 'hostinger', '--key', 'p');
    h.state.machines = {};
    await run('machine', 'access', 'remove', 'hostinger', '--key', 'p');
    expect(h.state.access).toMatchObject({ keys: { p: { machines: {} } } });
  });

  it('show -o json reports the ranges each bound key resolves to', async () => {
    await run('machine', 'access', 'set', 'hostinger', '--key', 'p');
    await run('-o', 'json', 'machine', 'access', 'show', 'hostinger');
    expect(h.printed.at(-1)?.data).toEqual([
      {
        key: 'p',
        restrict: true,
        sourceRanges: { ipv4: ['104.28.0.0/16'], ipv6: ['2a09:bac0::/29'] },
        rangesFrom: 'key',
      },
    ]);
  });

  it('push -o json prints the report', async () => {
    const report = {
      machine: 'hostinger',
      path: '/home/muhammed/.ssh/authorized_keys',
      written: true,
      changes: [{ key: 'p', action: 'adopt', line: 15, text: 'from="..." ssh-ed25519 AAAA' }],
    };
    vi.mocked(pushAccess).mockResolvedValueOnce(report as never);

    await run('-o', 'json', 'machine', 'access', 'push', 'hostinger', '--dry-run');

    expect(pushAccess).toHaveBeenCalledWith('hostinger', { dryRun: true });
    expect(h.printed).toEqual([{ data: report, format: 'json' }]);
  });

  it('push on an unknown machine refuses before connecting', async () => {
    await expect(run('machine', 'access', 'push', 'ghost')).rejects.toThrow(/not found/);
    expect(pushAccess).not.toHaveBeenCalled();
  });
});

describe('machine setup post tasks', () => {
  it('call pushAccess after the repo keys', async () => {
    vi.mocked(deployAllRepoKeys).mockResolvedValueOnce(0);
    vi.mocked(pushAccess).mockResolvedValueOnce({
      machine: 'hostinger',
      path: '/home/muhammed/.ssh/authorized_keys',
      written: false,
      changes: [],
    });

    await postSetupMachineTasks('hostinger');

    expect(pushAccess).toHaveBeenCalledWith('hostinger');
    expect(vi.mocked(deployAllRepoKeys).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(pushAccess).mock.invocationCallOrder[0]
    );
    expect(h.warnings).toEqual([]);
  });

  it('a push failure only warns', async () => {
    vi.mocked(deployAllRepoKeys).mockResolvedValueOnce(0);
    vi.mocked(pushAccess).mockRejectedValueOnce(new Error('ssh refused'));

    await expect(postSetupMachineTasks('hostinger')).resolves.toBeUndefined();

    expect(h.warnings).toHaveLength(1);
    expect(h.warnings[0]).toContain('commands.machine.access.push.setupFailed');
    expect(h.warnings[0]).toContain('ssh refused');
  });
});

describe('error envelope for the access refusals', () => {
  async function envelopeFor(error: Error): Promise<Record<string, unknown>> {
    const real =
      await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
    h.stdout.length = 0;
    real.setOutputFormat('json');
    try {
      expect(() => real.handleError(error)).toThrow(/^exit /);
    } finally {
      real.setOutputFormat('table');
    }
    return JSON.parse(h.stdout.join('')).errors[0];
  }

  function coded(code: string, message: string): Error {
    return Object.assign(new Error(message), { code });
  }

  it.each([
    ['ACCESS_LOCKOUT', 2, false],
    ['ACCESS_KEY_CONFLICT', 2, false],
    ['ACCESS_KEY_DUPLICATE_BLOB', 2, false],
    ['ACCESS_FILE_CHANGED', 1, true],
  ])('%s keeps its code, exits %i, retryable %s', async (code, exitCode, retryable) => {
    const { exitProcess } = await import('../../services/core/request-context.js');
    const got = await envelopeFor(coded(code, `${code} happened`));
    expect(got).toMatchObject({ code, retryable, guidance: `${code} happened` });
    expect(vi.mocked(exitProcess)).toHaveBeenLastCalledWith(exitCode);
  });
});

describe('cli contract', () => {
  it('marks machine access push proxyCapable: false', () => {
    const out = mkdtempSync(join(tmpdir(), 'access-contract-'));
    try {
      const script = fileURLToPath(
        new URL('../../../scripts/generate-cli-contract.ts', import.meta.url)
      );
      const result = spawnSync('npx', ['tsx', script, '--output', out], { encoding: 'utf8' });
      expect(result.status, result.stderr).toBe(0);
      const contract = JSON.parse(readFileSync(join(out, 'contract.json'), 'utf8')) as {
        commands: { path: string[]; proxyCapable: boolean; proxyBlockedReason?: string }[];
      };
      const push = contract.commands.find((c) => c.path.join(' ') === 'machine access push');
      expect(push?.proxyCapable).toBe(false);
      expect(push?.proxyBlockedReason).toMatch(/never rewrites the access it connects with/);
    } finally {
      rmSync(out, { recursive: true, force: true });
    }
  }, 120_000);
});
