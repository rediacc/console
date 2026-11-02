import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

const mocks = vi.hoisted(() => ({
  print: vi.fn(),
  warn: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
  format: { value: 'json' },
}));

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: mocks.info,
    success: vi.fn(),
    warn: mocks.warn,
    error: mocks.error,
    print: mocks.print,
  },
}));
vi.mock('../../utils/errors.js', async () => ({
  ...(await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js')),
  getOutputFormat: () => mocks.format.value,
}));

const SNAP = '20261101T030000Z-0011223344556677';
const restoreRecord = (over: Record<string, unknown> = {}) =>
  JSON.stringify({
    guid: 'x',
    status: 'restored',
    snapshotId: SNAP,
    cellsTotal: 4,
    chunksFetched: 4,
    passphraseCheck: 'opened',
    ...over,
  });
const printed = (): Record<string, unknown> => mocks.print.mock.calls.at(-1)?.[0];

beforeEach(() => {
  vi.clearAllMocks();
});

describe('restore records: the passphrase check is rendered in every format', () => {
  async function report(output: string, format: string): Promise<void> {
    mocks.format.value = format;
    await import('../backup-restore-chunk.js');
    const { resolveStepHandler } = await import('../../services/jobs/steps.js');
    const handler = await resolveStepHandler('reportRestoreStats');
    await handler({
      jobId: 'j',
      machine: 'm1',
      params: {},
      state: 'succeeded',
      output,
    });
  }

  it.each(['json', 'yaml'])('%s prints the whole record, passphraseCheck included', async (format) => {
    await report(restoreRecord({ passphraseCheck: 'not-available' }), format);
    expect(printed()).toMatchObject({ passphraseCheck: 'not-available' });
  });

  it('table says plainly that an image with no passphrase was not test-opened', async () => {
    await report(restoreRecord({ passphraseCheck: 'not-available' }), 'table');
    const said = [...mocks.warn.mock.calls, ...mocks.info.mock.calls].map((c) => String(c[0])).join('\n');
    expect(said).toContain('commands.backup.restore.passphraseNotChecked');
  });

  it('table reports an opened image', async () => {
    await report(restoreRecord({ passphraseCheck: 'opened' }), 'table');
    expect(mocks.info.mock.calls.map((c) => String(c[0])).join('\n')).toContain(
      'commands.backup.restore.passphraseOpened'
    );
  });

  it('a refused passphrase on a placed image is a warning that carries the reason', async () => {
    await report(restoreRecord({ passphraseCheck: 'refused', reason: 'no key slot matched' }), 'table');
    expect(mocks.warn.mock.calls.map((c) => String(c[0])).join('\n')).toContain('no key slot matched');
  });
});
