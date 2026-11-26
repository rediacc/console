/**
 * `machine status --strict` exits 2 on health drift, and the exit code is recorded BEFORE the JSON
 * document prints: the envelope derives `success` from the code set when it is written, so a code
 * set after the print leaves a success:true envelope on a failed run.
 */

import type { ListResult } from '@rediacc/shared/renet-contract/data/list-types.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  handlers: new Map<string, (ctx: unknown) => Promise<void>>(),
  listResult: {} as unknown,
  setExitCode: vi.fn(),
  print: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (k: string) => k }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: m.print, warn: vi.fn(), print: m.print, report: vi.fn() },
}));
vi.mock('../../services/core/request-context.js', async (orig) => ({
  ...(await orig<typeof import('../../services/core/request-context.js')>()),
  setExitCode: m.setExitCode,
  writeStderr: vi.fn(),
  writeStdout: vi.fn(),
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getLocalMachine: async () => undefined,
    getCurrent: async () => null,
  },
}));
vi.mock('../../services/jobs/steps.js', () => ({
  bindStepHandler: (name: string, handler: (ctx: unknown) => Promise<void>) => {
    m.handlers.set(name, handler);
  },
  planStep: vi.fn(),
}));
vi.mock('../../services/machine/machine-status.js', () => ({
  parseMachineStatus: () => m.listResult,
}));
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<typeof import('../../utils/errors.js')>()),
  getOutputFormat: () => 'json',
  handleError: (error: unknown) => {
    throw error;
  },
}));
vi.mock('../../utils/guid-resolver.js', async (orig) => ({
  ...(await orig<typeof import('../../utils/guid-resolver.js')>()),
  loadGuidMap: async () => ({}),
  createGuidResolver: () => (guid: string) => guid,
  createRepoNameResolver: () => (guid: string) => ({ name: guid, source: 'guid' }),
}));
vi.mock('../../utils/spinner.js', () => ({ startSpinner: vi.fn(), stopSpinner: vi.fn() }));

await import('../machine/status.js');

function render(strict: boolean): Promise<void> {
  const handler = m.handlers.get('renderMachineStatus');
  if (!handler) throw new Error('renderMachineStatus handler was not bound');
  return handler({ machine: 'm1', output: '{}', params: { strict } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('machine status --strict', () => {
  it('sets exit 2 BEFORE the JSON document prints when a container has drifted', async () => {
    m.listResult = {
      health_drift: { entries: [{ container: 'web' }] },
    } as unknown as ListResult;
    await render(true);
    expect(m.setExitCode).toHaveBeenCalledWith(2);
    expect(m.print).toHaveBeenCalled();
    expect(m.setExitCode.mock.invocationCallOrder[0]).toBeLessThan(
      m.print.mock.invocationCallOrder[0] ?? 0
    );
  });

  it('leaves the exit code alone without --strict, or with nothing drifted', async () => {
    m.listResult = {
      health_drift: { entries: [{ container: 'web' }] },
    } as unknown as ListResult;
    await render(false);
    m.listResult = { health_drift: { entries: [] } } as unknown as ListResult;
    await render(true);
    expect(m.setExitCode).not.toHaveBeenCalled();
  });
});
