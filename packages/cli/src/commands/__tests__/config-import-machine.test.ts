/**
 * `rdc config import-machine <machine> --from <config>` (PLAN-hostinger-to-bench Design 5), driven
 * end to end against real config files in a throwaway XDG_CONFIG_HOME: absent entries are added,
 * equal ones are no-ops, a same-name repository with another GUID and a differing strategy are
 * refused with nothing written, the output never carries a credential, key or GUID value, and the
 * write goes through `updateSyncedConfig`.
 */

import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { Command } from 'commander';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const configHome = mkdtempSync(join(tmpdir(), 'rdc-import-machine-'));
process.env.XDG_CONFIG_HOME = configHome;
delete process.env.REDIACC_CONFIG;

const SRC = 'imsrc';
const DST = 'imdst';

const GUID_MAIL = '11111111-1111-4111-8111-111111111111';
const GUID_MAIL_PRE = '22222222-2222-4222-8222-222222222222';
const GUID_OPS = '33333333-3333-4333-8333-333333333333';
const GUID_OTHER = '44444444-4444-4444-8444-444444444444';
const GUID_ELSEWHERE = '55555555-5555-4555-8555-555555555555';
const CRED_MAIL = 'cred-mail-0f9e8d7c6b5a';
const CRED_PRE = 'cred-pre-a1b2c3d4e5f6';
const CRED_OPS = 'cred-ops-99887766';
// Built from parts so the source carries no private-key header the secret-shape scans would flag.
const KEY_KIND = ['OPENSSH', 'PRIVATE', 'KEY'].join(' ');
const SSH_PRIV = `-----BEGIN ${KEY_KIND}-----\nsecretbody\n-----END ${KEY_KIND}-----`;
const SECRET_VALUE = 'repo-secret-value-xyz';
const SECRET_STRINGS = [
  GUID_MAIL,
  GUID_MAIL_PRE,
  GUID_OPS,
  GUID_OTHER,
  CRED_MAIL,
  CRED_PRE,
  CRED_OPS,
  'secretbody',
  SECRET_VALUE,
];

const out = vi.hoisted(() => ({
  print: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({ outputService: out }));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: (error: unknown) => {
    throw error;
  },
}));

const sync = vi.hoisted(() => ({ passThrough: true, calls: [] as string[] }));
vi.mock('../../services/config/synced-write.js', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../services/config/synced-write.js')>();
  return {
    ...real,
    updateSyncedConfig: (...args: Parameters<typeof real.updateSyncedConfig>) => {
      sync.calls.push(args[0]);
      return sync.passThrough ? real.updateSyncedConfig(...args) : Promise.resolve();
    },
  };
});

const { getConfigDir } = await import('@rediacc/shared/paths');
const { configFileStorage } = await import('../../adapters/config-file-storage.js');
const { configService } = await import('../../services/config/config-resources.js');
const { registerImportMachineCommand } = await import('../config-import-machine.js');
const { CliExitError } = await import('../../utils/cli-exit-error.js');
const { ValidationError } = await import('../../utils/errors.js');

type Cfg = Awaited<ReturnType<typeof configFileStorage.load>>;
type Res = NonNullable<Cfg['resources']>;

const nightly = {
  destinations: [{ kind: 'hosted-service' as const, name: 'hosted' }],
  schedule: '0 2 * * *',
  mode: 'hot' as const,
  bandwidthLimit: '12M',
};

function sourceResources(): Res {
  return {
    machines: {
      hostinger: {
        ip: '192.0.2.10',
        user: 'deploy',
        datastore: WK_DATASTORE_PATH,
        backupStrategies: ['nightly'],
      },
      elsewhere: { ip: '192.0.2.99', user: 'deploy' },
    },
    backupStrategies: { nightly },
    repositories: {
      mail: {
        placement: { machine: 'hostinger' },
        grand: 'latest',
        tags: {
          latest: {
            repositoryGuid: GUID_MAIL,
            credential: CRED_MAIL,
            sshPrivateKey: SSH_PRIV,
            secrets: { API_TOKEN: { mode: 'env', value: SECRET_VALUE } },
          },
          'pre-dms17': {
            repositoryGuid: GUID_MAIL_PRE,
            credential: CRED_PRE,
            grandGuid: GUID_MAIL,
          },
        },
      },
      ops: {
        placement: { machine: 'hostinger' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: GUID_OPS, credential: CRED_OPS } },
      },
      faraway: {
        placement: { machine: 'elsewhere' },
        grand: 'latest',
        tags: { latest: { repositoryGuid: GUID_ELSEWHERE, credential: 'cred-far' } },
      },
    },
  };
}

async function seed(name: string, resources: Res): Promise<void> {
  await configFileStorage.delete(name).catch(() => undefined);
  await configFileStorage.init(name);
  await configFileStorage.update(name, (cfg) => ({ ...cfg, resources }));
}

function raw(name: string): string {
  return readFileSync(join(getConfigDir(), `${name}.json`), 'utf-8');
}

async function load(name: string): Promise<Res> {
  return (await configFileStorage.loadDecrypted(name)).resources ?? {};
}

async function run(args: string[], format = 'json'): Promise<void> {
  const program = new Command();
  program.exitOverride();
  program.option('-o, --output <format>', 'format', format);
  const config = program.command('config');
  registerImportMachineCommand(config, program);
  await program.parseAsync(['config', 'import-machine', ...args], { from: 'user' });
}

/** The JSON payload of the last `print` call. */
function report(): {
  changes: number;
  refusals: number;
  rows: { kind: string; name: string; status: string; reason?: string }[];
} {
  return out.print.mock.calls.at(-1)?.[0];
}

function status(name: string, kind?: string): string | undefined {
  return report().rows.find((r) => r.name === name && (!kind || r.kind === kind))?.status;
}

async function refusal(args: string[]): Promise<InstanceType<typeof CliExitError>> {
  const err = await run(args).catch((e: unknown) => e);
  expect(err).toBeInstanceOf(CliExitError);
  return err as InstanceType<typeof CliExitError>;
}

beforeEach(async () => {
  vi.clearAllMocks();
  sync.passThrough = true;
  sync.calls = [];
  await seed(SRC, sourceResources());
  await seed(DST, {});
  configService.setRuntimeConfig(DST);
  configService.resetResourceView();
});

afterAll(() => {
  rmSync(configHome, { recursive: true, force: true });
});

describe('config import-machine', () => {
  it('adds the machine, its bound strategy, every repository placed on it and every tag', async () => {
    await run(['hostinger', '--from', SRC]);

    const dst = await load(DST);
    const src = sourceResources();
    expect(dst.machines?.hostinger).toEqual(src.machines?.hostinger);
    expect(dst.backupStrategies?.nightly).toEqual(nightly);
    expect(dst.repositories?.mail).toEqual(src.repositories?.mail);
    expect(dst.repositories?.ops).toEqual(src.repositories?.ops);
    expect(report().changes).toBe(8);
    expect(status('mail:pre-dms17')).toBe('added');
    expect(status('hostinger/nightly', 'binding')).toBe('added');
  });

  it('control: leaves other machines and the repositories placed on them alone', async () => {
    await run(['hostinger', '--from', SRC]);
    const dst = await load(DST);
    expect(dst.machines?.elsewhere).toBeUndefined();
    expect(dst.repositories?.faraway).toBeUndefined();
  });

  it('a second run reports 0 changes and writes nothing', async () => {
    await run(['hostinger', '--from', SRC]);
    const before = raw(DST);
    sync.calls = [];
    await run(['hostinger', '--from', SRC]);
    expect(report().changes).toBe(0);
    expect(report().refusals).toBe(0);
    expect(report().rows.every((r) => r.status === 'equal')).toBe(true);
    expect(raw(DST)).toBe(before);
    expect(sync.calls).toEqual([]);
  });

  it('adds only the missing tags and bindings to an existing machine and family, keeping target-owned fields', async () => {
    const src = sourceResources();
    await seed(DST, {
      machines: {
        hostinger: {
          ...src.machines!.hostinger,
          backupStrategies: undefined,
          maintenanceWindow: '00:00-01:00',
        },
      },
      repositories: {
        mail: { ...src.repositories!.mail, tags: { latest: src.repositories!.mail.tags.latest } },
      },
    });
    await run(['hostinger', '--from', SRC]);

    const dst = await load(DST);
    expect(dst.machines?.hostinger.maintenanceWindow).toBe('00:00-01:00');
    expect(dst.machines?.hostinger.backupStrategies).toEqual(['nightly']);
    expect(dst.repositories?.mail.tags['pre-dms17']).toEqual(
      src.repositories!.mail.tags['pre-dms17']
    );
    expect(status('hostinger', 'machine')).toBe('equal');
    expect(status('mail:latest')).toBe('equal');
    expect(status('mail:pre-dms17')).toBe('added');
    expect(status('ops', 'repository')).toBe('added');
  });

  it('refuses a same-name repository with a different GUID and writes nothing', async () => {
    const src = sourceResources();
    await seed(DST, {
      repositories: {
        ops: {
          ...src.repositories!.ops,
          tags: { latest: { repositoryGuid: GUID_OTHER, credential: 'x' } },
        },
      },
    });
    const before = raw(DST);
    const err = await refusal(['hostinger', '--from', SRC]);
    expect(err.exitCode).toBe(12);
    expect(err.details).toContain('tag ops:latest: guid-differs');
    expect(raw(DST)).toBe(before);
    expect(sync.calls).toEqual([]);
  });

  it('refuses a differing strategy without --strategy-from-source, and replaces it with the flag', async () => {
    await seed(DST, { backupStrategies: { nightly: { ...nightly, schedule: '0 4 * * *' } } });
    const before = raw(DST);
    const err = await refusal(['hostinger', '--from', SRC]);
    expect(err.details).toContain('strategy nightly: strategy-differs');
    expect(raw(DST)).toBe(before);

    await run(['hostinger', '--from', SRC, '--strategy-from-source']);
    expect((await load(DST)).backupStrategies?.nightly).toEqual(nightly);
    expect(status('nightly', 'strategy')).toBe('replaced');
  });

  it('refuses the same machine name at another address', async () => {
    await seed(DST, { machines: { hostinger: { ip: '198.51.100.7', user: 'deploy' } } });
    const err = await refusal(['hostinger', '--from', SRC]);
    expect(err.details).toContain('machine hostinger: machine-differs');
  });

  it('--dry-run reports the changes and writes nothing', async () => {
    const before = raw(DST);
    await run(['hostinger', '--from', SRC, '--dry-run']);
    expect(report().changes).toBe(8);
    expect(raw(DST)).toBe(before);
    expect(sync.calls).toEqual([]);
  });

  it('never prints a credential, key or GUID value, in JSON or table output, on success or refusal', async () => {
    await run(['hostinger', '--from', SRC], 'json');
    await run(['hostinger', '--from', SRC], 'table');
    await seed(DST, {
      repositories: {
        ops: {
          ...sourceResources().repositories!.ops,
          tags: { latest: { repositoryGuid: GUID_OTHER } },
        },
      },
    });
    const err = await refusal(['hostinger', '--from', SRC]);
    await run(['hostinger', '--from', SRC, '--dry-run'], 'table');

    const emitted = JSON.stringify([
      out.print.mock.calls,
      out.info.mock.calls,
      out.success.mock.calls,
      out.warn.mock.calls,
      err.message,
      err.details,
    ]);
    expect(emitted).toContain('mail:pre-dms17');
    for (const s of SECRET_STRINGS) expect(emitted).not.toContain(s);
  });

  it('writes through updateSyncedConfig and nowhere else', async () => {
    sync.passThrough = false;
    const before = raw(DST);
    await run(['hostinger', '--from', SRC]);
    expect(sync.calls).toEqual([DST]);
    // With the synced writer stubbed out, the file is untouched: no direct write path exists.
    expect(raw(DST)).toBe(before);
  });

  it('refuses the active config as the source and a machine the source lacks', async () => {
    await expect(run(['hostinger', '--from', DST])).rejects.toThrow(ValidationError);
    await expect(run(['hostinger', '--from', DST])).rejects.toThrow(/is the active config/);
    await expect(run(['nosuch', '--from', SRC])).rejects.toThrow(/"nosuch" is not in the source/);
    await expect(run(['hostinger', '--from', 'absentcfg'])).rejects.toThrow(/does not exist/);
    expect(sync.calls).toEqual([]);
  });
});
