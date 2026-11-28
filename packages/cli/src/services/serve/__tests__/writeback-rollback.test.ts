/**
 * WB6 (agent/plans/PLAN-rmcp-writeback.md Design 6): a registration is rolled back only on a definitive failure.
 * A timeout or lost connection on the dispatch keeps the entry (the job may be running on the host); a failed or
 * cancelled job removes it through the settle step; a refused start, which runs no job, removes it from the catch.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { jobStateUnknown, rollbackRefusedStart } from '../../../commands/repo-rollback.js';
import { ERROR_CODES } from '../../../types/errors.js';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import { configService } from '../../config/config-resources.js';
import { outputService } from '../../core/output.js';
import { asMayHaveReached, ProxyRequestError } from '../../executor/proxy-client-support.js';
import { resolveStepHandler, type StepContext } from '../../jobs/steps.js';

// Binds the rollbackCreate step handler.
import '../../../commands/repo-create-delete.js';

const timeout = () =>
  new CliExitError(ERROR_CODES.NETWORK_ERROR, 'proxy timed out', { retryable: true });

function ctx(state: StepContext['state']): StepContext {
  return {
    jobId: 'job-1',
    machine: 'm1',
    state,
    params: { repo: 'app', guid: 'g-1' },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('rollback only on a definitive failure', () => {
  it('a timeout keeps the entry', async () => {
    const rollback = vi.fn().mockResolvedValue(undefined);
    expect(jobStateUnknown(timeout())).toBe(true);
    await expect(rollbackRefusedStart(timeout(), rollback, 'app', 'g-1')).resolves.toBe(false);
    expect(rollback).not.toHaveBeenCalled();
  });

  it('a proxy request refused at connect is a refused start; one that may have reached the executor is unknown (9a8dc910.1)', () => {
    const never = new ProxyRequestError('refused', false, undefined);
    const maybe = new ProxyRequestError('reset', true, undefined);
    expect(jobStateUnknown(never)).toBe(false);
    expect(jobStateUnknown(maybe)).toBe(true);
    expect(jobStateUnknown(asMayHaveReached(never))).toBe(true);
    expect(jobStateUnknown(new CliExitError(ERROR_CODES.GENERAL_ERROR, 'x'))).toBe(false);
    expect(jobStateUnknown(new Error('refused'))).toBe(false);
  });

  it('a refused start with no job removes the entry', async () => {
    const rollback = vi.fn().mockResolvedValue(undefined);
    await expect(rollbackRefusedStart(new Error('refused'), rollback, 'app', 'g-1')).resolves.toBe(
      true
    );
    expect(rollback).toHaveBeenCalledWith('app', 'g-1');
  });

  it.each(['failed', 'cancelled'] as const)(
    'a %s job removes the entry through the settle step',
    async (state) => {
      vi.spyOn(configService, 'getRepository').mockResolvedValue({
        repositoryGuid: 'g-1',
      } as never);
      const remove = vi
        .spyOn(configService, 'removeRepository')
        .mockResolvedValue(undefined as never);
      vi.spyOn(outputService, 'warn').mockImplementation(() => undefined);

      const handler = await resolveStepHandler('rollbackCreate');
      await handler(ctx(state));

      expect(remove).toHaveBeenCalledWith('app');
    }
  );
});
