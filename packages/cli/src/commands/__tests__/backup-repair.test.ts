import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  execute: vi.fn(),
  print: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  setExitCode: vi.fn(),
  removeRepository: vi.fn(),
  format: { value: 'json' },
}));

vi.mock('../../services/account/subscription-auth.js', () => ({
  getSubscriptionTokenState: () => ({
    kind: 'ready',
    token: { token: 't' },
    serverUrl: 'https://acct.example',
  }),
  getSubscriptionServerUrl: () => 'https://acct.example',
}));
vi.mock('../../services/account/account-client.js', () => ({ accountServerFetch: mocks.fetch }));
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
  getOutputFormat: () => mocks.format.value,
  handleError: (e: unknown) => {
    throw e;
  },
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mocks.execute }),
}));
vi.mock('../../utils/repo-executor.js', () => ({
  executeRepoFunction: vi.fn(),
  recordedDatastoreMount: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: vi.fn().mockResolvedValue({ repoKey: 'shop', machineName: 'm1' }),
  resolveRepoRefLocal: vi.fn().mockResolvedValue({ repoKey: 'shop' }),
}));
vi.mock('../backup-storage-browse.js', () => ({
  RENET_NO_LISTING_EXIT: 18,
  resolveLineage: vi.fn().mockResolvedValue('lineage-1'),
  runBrowseAt: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { removeRepository: mocks.removeRepository },
}));

import { registerBackupRepair } from '../backup-repair.js';

const H = (c: string) => c.repeat(64);
const byText = (a: string, b: string) => a.localeCompare(b);

/** The server's chunk-verify pages: one page carrying `missing` and `corrupt`. */
function verifyPage(missing: string[], corrupt: string[]) {
  return {
    subscriptionId: 's1',
    chunks: { lineageGuid: 'lineage-1', checked: 10, missing, corrupt, nextAfter: null },
  };
}

const repairCalls = () =>
  mocks.fetch.mock.calls.filter((c) => String(c[0]).endsWith('/backups/chunks/repair'));
const repairBodies = () =>
  repairCalls().map((c) => c[1].body as { hashes: string[]; dryRun: boolean });
const machineCalls = () =>
  mocks.execute.mock.calls.map(
    (c) => c[0] as { functionName: string; params: Record<string, string> }
  );

async function run(args: string[]): Promise<void> {
  const program = new Command().exitOverride();
  const backup = program.command('backup');
  registerBackupRepair(backup);
  await program.parseAsync(['node', 'rdc', 'backup', ...args]);
}

const printed = (): Record<string, unknown> => mocks.print.mock.calls.at(-1)?.[0];

/** Script the account: the store verify, then the repair route's answer. */
function account(
  verify: ReturnType<typeof verifyPage>,
  repair: (body: { hashes: string[]; dryRun: boolean }) => unknown
) {
  mocks.fetch.mockImplementation((url: string, init?: { body?: unknown }) => {
    if (url.endsWith('/backups/verify')) return Promise.resolve(verify);
    if (url.endsWith('/backups/chunks/repair'))
      return Promise.resolve(repair(init?.body as { hashes: string[]; dryRun: boolean }));
    return Promise.reject(new Error(`unexpected ${url}`));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.format.value = 'json';
});

describe('backup repair', () => {
  it('a clean store verify calls nothing else', async () => {
    account(verifyPage([], []), () => {
      throw new Error('must not be called');
    });
    await run(['repair', 'shop']);
    expect(repairCalls()).toHaveLength(0);
    expect(mocks.execute).not.toHaveBeenCalled();
    expect(printed()).toMatchObject({ status: 'clean' });
    expect(mocks.setExitCode).not.toHaveBeenCalled();
  });

  it('--dry-run asks the server with dryRun true, never deletes, never touches the machine', async () => {
    account(verifyPage([H('a')], [H('b')]), (body) => ({
      deleted: body.hashes.filter((h) => h === H('b')),
      stillGood: [],
      absent: body.hashes.filter((h) => h === H('a')),
      affectedSnapshots: ['20261101T030000Z-0011223344556677'],
    }));
    await run(['repair', 'shop', '--dry-run']);
    expect(repairBodies().length).toBeGreaterThan(0);
    expect(repairBodies().every((b) => b.dryRun === true)).toBe(true);
    expect(mocks.execute).not.toHaveBeenCalled();
    expect(printed()).toMatchObject({
      status: 'dry-run',
      affectedSnapshots: ['20261101T030000Z-0011223344556677'],
    });
    // Damage was found, so the dry run still reports it as a failing check.
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('deletes at the server first, then re-uploads exactly the deleted and absent hashes, and not stillGood', async () => {
    const order: string[] = [];
    account(verifyPage([H('a')], [H('b'), H('c')]), (body) => {
      order.push(`server:${body.dryRun}`);
      return { deleted: [H('b')], stillGood: [H('c')], absent: [H('a')], affectedSnapshots: [] };
    });
    mocks.execute.mockImplementation(() => {
      order.push('machine');
      return Promise.resolve({
        success: true,
        exitCode: 0,
        stdout: JSON.stringify({ guid: 'g', status: 'repaired', uploaded: [H('a'), H('b')] }),
      });
    });
    await run(['repair', 'shop']);
    expect(order).toEqual(['server:false', 'machine']);
    const call = machineCalls()[0];
    expect(call.functionName).toBe('backup_repair');
    expect(call.params.repository).toBe('shop');
    expect(call.params.hashes.split(/[\s,]+/).sort(byText)).toEqual([H('a'), H('b')].sort(byText));
    expect(printed()).toMatchObject({ status: 'repaired' });
    expect(mocks.setExitCode).not.toHaveBeenCalled();
  });

  it('batches the repair route at 200 hashes', async () => {
    const many = Array.from({ length: 450 }, (_, i) => i.toString(16).padStart(64, '0'));
    account(verifyPage([], many), (body) => ({
      deleted: body.hashes,
      stillGood: [],
      absent: [],
      affectedSnapshots: [],
    }));
    mocks.execute.mockResolvedValue({
      success: true,
      exitCode: 0,
      stdout: JSON.stringify({ guid: 'g', status: 'repaired' }),
    });
    await run(['repair', 'shop']);
    expect(repairBodies().map((b) => b.hashes.length)).toEqual([200, 200, 50]);
  });

  it('an unrepairable hash exits non-zero and is named with the affected snapshots', async () => {
    account(verifyPage([], [H('b')]), () => ({
      deleted: [H('b')],
      stillGood: [],
      absent: [],
      affectedSnapshots: ['20261101T030000Z-0011223344556677'],
    }));
    mocks.execute.mockResolvedValue({
      success: false,
      exitCode: 1,
      stdout: JSON.stringify({
        guid: 'g',
        status: 'partial',
        unrepairable: [{ hash: H('b'), reason: 'the anchor no longer holds it' }],
      }),
    });
    await run(['repair', 'shop']);
    expect(printed()).toMatchObject({
      status: 'partial',
      unrepairable: [{ hash: H('b') }],
      affectedSnapshots: ['20261101T030000Z-0011223344556677'],
    });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('an object the store still holds at the key (alreadyPresent) is not reported as repaired', async () => {
    account(verifyPage([], [H('b')]), () => ({
      deleted: [H('b')],
      stillGood: [],
      absent: [],
      affectedSnapshots: [],
    }));
    mocks.execute.mockResolvedValue({
      success: false,
      exitCode: 1,
      stdout: JSON.stringify({ guid: 'g', status: 'partial', alreadyPresent: [H('b')] }),
    });
    await run(['repair', 'shop']);
    expect(printed()).toMatchObject({ status: 'partial', alreadyPresent: [H('b')] });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('a machine with no readable record fails closed', async () => {
    account(verifyPage([], [H('b')]), () => ({
      deleted: [H('b')],
      stillGood: [],
      absent: [],
      affectedSnapshots: [],
    }));
    mocks.execute.mockResolvedValue({ success: false, exitCode: 1, stdout: 'boom' });
    await run(['repair', 'shop']);
    expect(printed()).toMatchObject({ status: 'failed' });
    expect(mocks.setExitCode).toHaveBeenCalledWith(1);
  });

  it('everything stillGood means the server deleted nothing and the machine is not asked', async () => {
    account(verifyPage([], [H('b')]), () => ({
      deleted: [],
      stillGood: [H('b')],
      absent: [],
      affectedSnapshots: [],
    }));
    await run(['repair', 'shop']);
    expect(mocks.execute).not.toHaveBeenCalled();
    expect(printed()).toMatchObject({ status: 'clean' });
  });
});

describe('restore --salvage', () => {
  it('is refused without --as, and refused for a single path', async () => {
    const { assertRestoreRepairFlags } = await import('../backup.js');
    expect(() => assertRestoreRepairFlags({ salvage: true })).toThrow(
      'commands.backup.restore.salvageNeedsAs'
    );
    expect(() => assertRestoreRepairFlags({ salvage: true, as: 'copy', path: '/etc' })).toThrow(
      'commands.backup.restore.salvageWholeImage'
    );
    expect(() => assertRestoreRepairFlags({ salvage: true, as: 'copy' })).not.toThrow();
    expect(() => assertRestoreRepairFlags({})).not.toThrow();
  });
});

describe('a salvage that placed a damaged image', () => {
  const damaged = JSON.stringify({
    guid: 'x',
    status: 'restored-damaged',
    cellsTotal: 4,
    chunksFetched: 3,
    badCells: [{ cell: 2, offset: 8, length: 4, reason: 'missing', inLuksHeader: true }],
  });

  it('keeps the target registration, where any other failure drops it', async () => {
    await import('../backup.js');
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    const rollback = await resolveStepHandler('rollbackRestoreRegistration');
    const base = { jobId: 'j', machine: 'm1', params: { repo: 'copy' }, state: 'failed' as const };
    await rollback({ ...base, output: damaged });
    expect(mocks.removeRepository).not.toHaveBeenCalled();
    await rollback({
      ...base,
      output: JSON.stringify({ cellsTotal: 1, chunksFetched: 0, status: 'failed' }),
    });
    expect(mocks.removeRepository).toHaveBeenCalledTimes(1);
    await rollback({ ...base, output: undefined });
    expect(mocks.removeRepository).toHaveBeenCalledTimes(2);
  });

  it('reports every hole by byte range and the LUKS header warning', async () => {
    await import('../backup.js');
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    mocks.format.value = 'table';
    const report = await resolveStepHandler('reportRestoreDamage');
    await report({ jobId: 'j', machine: 'm1', params: {}, state: 'failed', output: damaged });
    const said = mocks.warn.mock.calls.map((c) => String(c[0])).join('\n');
    expect(said).toContain('commands.backup.restore.salvageDamaged');
    expect(said).toContain('"offset":8,"end":12');
    expect(said).toContain('commands.backup.restore.salvageHeaderHit');
  });
});
