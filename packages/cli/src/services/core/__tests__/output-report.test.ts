/** `outputService.report` is a command's primary prose result: stdout. `info` and `warn` stay on stderr. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { outputService } from '../output.js';
import { createOutputState, runInRequestContext } from '../request-context.js';

describe('outputService.report', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    outputService.setQuiet(false);
  });

  it('writes to stdout and leaves stderr empty, while info and warn write to stderr only', () => {
    const out = vi.spyOn(process.stdout, 'write').mockReturnValue(true);
    const err = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    outputService.report('plan: PRO');
    expect(out.mock.calls.map((c) => String(c[0]))).toEqual(['plan: PRO\n']);
    expect(err).not.toHaveBeenCalled();

    outputService.info('progress note');
    outputService.warn('a warning');
    expect(out).toHaveBeenCalledTimes(1);
    expect(err).toHaveBeenCalledTimes(2);
  });

  it('is not silenced by --quiet, which only silences progress', () => {
    const out = vi.spyOn(process.stdout, 'write').mockReturnValue(true);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    outputService.setQuiet(true);
    outputService.report('plan: PRO');
    expect(out).toHaveBeenCalledTimes(1);
  });

  it('lands in the request stdout buffer inside a dispatch', async () => {
    const ctx = { output: createOutputState(), stdout: [] as string[], stderr: [] as string[] };
    await runInRequestContext(ctx, () => {
      outputService.report('plan: PRO');
      outputService.info('progress note');
      return Promise.resolve();
    });
    expect(ctx.stdout).toEqual(['plan: PRO']);
    expect(ctx.stderr).toEqual(['progress note']);
  });
});
