/** `datastore delete` refuses while child datastores (parent.datastore === ref) exist; --force does not cover it. */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CliExitError } from '../../utils/cli-exit-error.js';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const m = vi.hoisted(() => ({
  getDatastore: vi.fn(),
  listDatastoreState: vi.fn(),
  setDatastoreState: vi.fn(),
  forgetDatastore: vi.fn(),
  childDatastores: vi.fn(),
  reposInDatastore: vi.fn(),
  execute: vi.fn(),
}));

vi.mock('../../services/config/config-datastores.js', () => ({
  assertCreatableName: vi.fn(),
  at: (state: Record<string, unknown>, ref: string) => state[ref],
  childDatastores: m.childDatastores,
  forgetDatastore: m.forgetDatastore,
  getDatastore: m.getDatastore,
  listDatastoreState: m.listDatastoreState,
  listDatastores: vi.fn().mockResolvedValue({}),
  parseDatastoreRef: (ref: string) => ({ name: ref }),
  recordDatastore: vi.fn(),
  reposInDatastore: m.reposInDatastore,
  requireDatastoreHost: vi.fn(),
  setDatastoreState: m.setDatastoreState,
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: vi.fn().mockResolvedValue({}) },
}));
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: m.execute }),
}));
vi.mock('../../services/executor/local-executor.js', () => ({ parseCapturedJson: JSON.parse }));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: { DATASTORE_DELETE: 'datastore delete' },
}));
vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn() }));
vi.mock('../../utils/prompt.js', () => ({ askConfirm: vi.fn().mockResolvedValue(true) }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), print: vi.fn() },
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    getOutputFormat: () => 'table',
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { registerDatastoreCommands } = await import('../datastore.js');

async function runDelete(...extra: string[]): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerDatastoreCommands(program);
  await program.parseAsync(['node', 'rdc', 'datastore', 'delete', 'tier1', '-y', ...extra]);
}

beforeEach(() => {
  vi.clearAllMocks();
  m.getDatastore.mockResolvedValue({ name: 'tier1' });
  m.listDatastoreState.mockResolvedValue({});
  m.reposInDatastore.mockResolvedValue([]);
  m.childDatastores.mockResolvedValue([]);
  m.execute.mockResolvedValue({ success: true, stdout: '' });
});

describe('datastore delete references', () => {
  it('refuses with exit 12 naming the children, and deletes nothing', async () => {
    m.childDatastores.mockResolvedValue(['fork-a', 'fork-b']);
    const err = (await runDelete().catch((e: unknown) => e)) as CliExitError;
    expect(err).toBeInstanceOf(CliExitError);
    expect(err.exitCode).toBe(12);
    expect(err.message).toContain('fork-a, fork-b');
    expect(m.forgetDatastore).not.toHaveBeenCalled();
  });

  it('--force does not cover children', async () => {
    m.childDatastores.mockResolvedValue(['fork-a']);
    const err = (await runDelete('--force').catch((e: unknown) => e)) as CliExitError;
    expect(err.exitCode).toBe(12);
    expect(m.forgetDatastore).not.toHaveBeenCalled();
  });

  it('deletes the record when there are no children', async () => {
    await runDelete();
    expect(m.forgetDatastore).toHaveBeenCalledWith('tier1');
  });
});
