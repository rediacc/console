import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ format: 'json' as string }));

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
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  getOutputFormat: () => state.format,
}));

import { outputService } from '../../services/core/output.js';
import { planStep, resolveStepHandler, type StepContext } from '../../services/jobs/steps.js';
import '../repo-branching.js';
import '../repo-diff.js';

const print = vi.mocked(outputService.print);

function ctx(output: string, params: StepContext['params']): StepContext {
  return { jobId: 'job-1', machine: 'm1', params, state: 'succeeded', output };
}

const diffPayload = '{"success":true,"files":[{"status":"A","path":"a.txt","type":"file"}]}';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('repo diff honours the global output format', () => {
  it.each(['json', 'yaml'])('prints the diff object as %s, not a table', async (format) => {
    const handler = await resolveStepHandler('renderRepoDiff');
    await handler(ctx(diffPayload, { mode: 'name-status', format }));
    expect(print).toHaveBeenCalledTimes(1);
    const [data, fmt] = print.mock.calls[0];
    expect(fmt).toBe(format);
    expect(JSON.stringify(data)).toContain('a.txt');
  });
});

describe('the renderRepoDiff plan step', () => {
  it('carries the requested format through planStep, so the handler sees it', () => {
    const planned = planStep('renderRepoDiff', { mode: 'stat', format: 'yaml', path: '' });
    expect(JSON.stringify(planned)).toContain('"format":"yaml"');
  });
});

describe('repo log honours the global output format', () => {
  it.each(['json', 'yaml'])('prints the entries as %s', async (format) => {
    state.format = format;
    const handler = await resolveStepHandler('renderRepoLog');
    await handler(ctx('{"success":true,"entries":[{"id":"e1"}]}', {}));
    expect(print).toHaveBeenCalledTimes(1);
    const [data, fmt] = print.mock.calls[0];
    expect(fmt).toBe(format);
    expect(JSON.stringify(data)).toContain('e1');
  });
});
