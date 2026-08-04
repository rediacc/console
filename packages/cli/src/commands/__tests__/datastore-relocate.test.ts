/**
 * `rdc datastore attach <ref> --to <other machine>` — the single-mounter relocation.
 *
 * renet's datastore registry is PER-MACHINE, and the record is the only place a
 * datastore's ceph pool and image are written down. The relocation branch used to
 * detach from the old holder and then attach on the new one, which cannot work on a
 * machine that has never seen the datastore: the attach failed with `datastore
 * "<ref>" is not registered on this machine` AFTER the detach had already happened,
 * so the datastore ended up attached NOWHERE. Found live by
 * `./run.sh drill license --legs b` on 2026-08-04.
 *
 * These assertions read the dispatch ORDER, because that is what was wrong. A check
 * on the final state would pass against the broken build too, on the one machine
 * that already had the record.
 */
import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockGetDatastore = vi.hoisted(() => vi.fn());
const mockListDatastoreState = vi.hoisted(() => vi.fn());
const mockSetDatastoreState = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-datastores.js', () => ({
  assertCreatableName: vi.fn(),
  at: (state: Record<string, unknown>, ref: string) => state[ref],
  forgetDatastore: vi.fn(),
  getDatastore: mockGetDatastore,
  listDatastoreState: mockListDatastoreState,
  listDatastores: vi.fn().mockResolvedValue([]),
  parseDatastoreRef: (ref: string) => {
    const [name, tag] = ref.split(':');
    return { name, tag };
  },
  recordDatastore: vi.fn(),
  reposInDatastore: vi.fn().mockResolvedValue([]),
  requireDatastoreHost: vi.fn(),
  setDatastoreState: mockSetDatastoreState,
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: vi.fn().mockResolvedValue({}) },
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

vi.mock('../../services/executor/local-executor.js', () => ({
  parseCapturedJson: (raw: string) => JSON.parse(raw),
}));

vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn().mockResolvedValue(undefined),
  CMD: { DATASTORE_ATTACH: 'datastore attach', DATASTORE_DETACH: 'datastore detach' },
}));

vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));
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

const CEPH_RECORD = {
  name: 'tier1',
  backend: 'ceph',
  ceph: { pool: 'rediacc_rbd_pool', image: 'ds-tier1' },
  state: 'attached',
};

async function runAttach(ref: string, to: string): Promise<void> {
  const program = new Command();
  program.exitOverride();
  registerDatastoreCommands(program);
  await program.parseAsync(['node', 'rdc', 'datastore', 'attach', ref, '--to', to]);
}

/** The bridge verbs dispatched, in call order, with the machine each ran on. */
function dispatched(): { fn: string; machine: string; params: Record<string, unknown> }[] {
  return mockExecute.mock.calls.map((c) => ({
    fn: c[0].functionName,
    machine: c[0].machineName,
    params: c[0].params,
  }));
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetDatastore.mockResolvedValue({ name: 'tier1' });
  mockListDatastoreState.mockResolvedValue({ tier1: { attachedTo: 'machine-a' } });
  mockSetDatastoreState.mockResolvedValue(undefined);
  mockExecute.mockImplementation(({ functionName }: { functionName: string }) =>
    Promise.resolve({
      success: true,
      stdout: functionName === 'datastore_list' ? JSON.stringify([CEPH_RECORD]) : '',
    })
  );
});

describe('datastore attach — cross-machine relocation', () => {
  // The adopt comes before the DETACH, not merely before the attach. It writes one
  // registry row, does no disk work, and is idempotent, so putting it first means
  // nothing destructive has happened yet when a malformed record or an unreachable
  // target fails the move — renet's own Adopt doc states this ordering rule for
  // exactly this case (private/renet/pkg/datastore/adopt.go:22-28).
  it('adopts the record on the target before detaching the source', async () => {
    await runAttach('tier1', 'machine-b');

    expect(dispatched().map((d) => `${d.fn}@${d.machine}`)).toEqual([
      'datastore_list@machine-a',
      'datastore_adopt@machine-b',
      'datastore_detach@machine-a',
      'datastore_attach@machine-b',
    ]);
  });

  it('leaves the source attached when the target refuses the record', async () => {
    mockExecute.mockImplementation(({ functionName }: { functionName: string }) =>
      functionName === 'datastore_adopt'
        ? Promise.resolve({ success: false, error: 'unmarshal adopt record: unexpected end' })
        : Promise.resolve({
            success: true,
            stdout: functionName === 'datastore_list' ? JSON.stringify([CEPH_RECORD]) : '',
          })
    );

    await expect(runAttach('tier1', 'machine-b')).rejects.toThrow(/datastore_adopt/);

    expect(dispatched().map((d) => d.fn)).not.toContain('datastore_detach');
  });

  it('adopts a non-fork record as plain, carrying the whole record across', async () => {
    await runAttach('tier1', 'machine-b');

    const adopt = dispatched().find((d) => d.fn === 'datastore_adopt');
    expect(adopt?.params.name).toBe('tier1');
    expect(adopt?.params.plain).toBe(true);
    const ferried = JSON.parse(
      Buffer.from(String(adopt?.params.record_b64), 'base64').toString('utf8')
    );
    expect(ferried).toEqual(CEPH_RECORD);
  });

  it('refuses a local-backend datastore WITHOUT detaching it first', async () => {
    mockExecute.mockImplementation(({ functionName }: { functionName: string }) =>
      Promise.resolve({
        success: true,
        stdout:
          functionName === 'datastore_list'
            ? JSON.stringify([{ name: 'tier1', backend: 'local', state: 'attached' }])
            : '',
      })
    );

    await expect(runAttach('tier1', 'machine-b')).rejects.toThrow(/cannot reach them/);

    // The whole point: a refusal that arrives after the detach would have taken the
    // datastore offline to tell the operator it could not be moved.
    expect(dispatched().map((d) => d.fn)).toEqual(['datastore_list']);
  });

  it('does not ferry anything when the datastore is not attached anywhere yet', async () => {
    mockListDatastoreState.mockResolvedValue({});

    await runAttach('tier1', 'machine-b');

    expect(dispatched().map((d) => d.fn)).toEqual(['datastore_attach']);
  });
});
