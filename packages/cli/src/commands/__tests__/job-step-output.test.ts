import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    print: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
    format: vi.fn(),
  },
}));
vi.mock('../../utils/guid-resolver.js', () => ({
  createGuidResolver: () => (name: string) => name,
  loadGuidMap: vi.fn(async () => ({})),
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  getOutputFormat: () => 'json',
}));

import { outputService } from '../../services/core/output.js';
import { resolveStepHandler, type StepContext } from '../../services/jobs/steps.js';

function ctx(output: string | undefined, params: StepContext['params'] = {}): StepContext {
  return { jobId: 'job-1', machine: 'm1', params, state: 'succeeded', output };
}

const error = vi.mocked(outputService.error);

beforeEach(() => {
  process.exitCode = undefined;
  vi.clearAllMocks();
});
afterEach(() => {
  process.exitCode = undefined;
});

// Each case: the step, its params, a real empty answer renet prints for "nothing", and the label in the error.
const sites: [string, StepContext['params'], string, string][] = [
  ['renderBackupList', { machine: 'm1' }, '{"entries":[]}', 'backup list'],
  ['renderRepoLog', {}, '{"success":true,"entries":[]}', 'repo log'],
  [
    'renderAutostartList',
    { machine: 'm1' },
    '{"service_installed":false,"service_enabled":false,"repositories":[]}',
    'repo admin autostart list',
  ],
  ['renderRepoPrune', { label: 'shop' }, '{}', 'repo prune'],
  ['renderRepoTrim', { reportOnly: false }, '{"repos":[]}', 'repo trim'],
  ['renderPolicyResult', {}, '{}', 'repo policy'],
  [
    'renderPruneOutcome',
    { dryRun: false },
    '{"prune_phase":"datastore"}\n{}\n{"prune_phase":"units"}\n',
    'machine prune',
  ],
];

describe.each(sites)('%s step on blank output', (step, params, realEmpty, label) => {
  it.each([
    ['undefined', undefined],
    ['an empty string', ''],
    ['whitespace', ' \n'],
  ])('says the result could not be read and exits 1 for %s', async (_name, output) => {
    const handler = await resolveStepHandler(step);
    await handler(ctx(output, params));

    expect(error).toHaveBeenCalledWith(
      expect.stringContaining(`${label}: the result could not be read`)
    );
    expect(process.exitCode).toBe(1);
  });

  it('keeps a real empty answer quiet with exit 0', async () => {
    const handler = await resolveStepHandler(step);
    await handler(ctx(realEmpty, params));

    expect(error).not.toHaveBeenCalled();
    expect(process.exitCode).toBeUndefined();
  });
});

describe('renderPruneOutcome with a blank datastore phase', () => {
  it('reports the lost datastore read even when the markers arrived', async () => {
    const handler = await resolveStepHandler('renderPruneOutcome');
    await handler(ctx('{"prune_phase":"datastore"}\n{"prune_phase":"units"}\n', { dryRun: false }));

    expect(error).toHaveBeenCalledWith(
      expect.stringContaining('machine prune datastore phase: the result could not be read')
    );
    expect(process.exitCode).toBe(1);
  });
});
