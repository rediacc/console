import { WK_INFRA_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import { createJobOutputCollector } from '../job-client.js';
import { mergeEventsStderr, settleRenetRun } from '../local-executor.js';

const errorEvent = {
  type: 'log',
  level: 'error',
  msg: `device ${WK_INFRA_DOMAIN}/fake=x is not defined by any CDI spec`,
} as never;

describe('events-mode failure reason', () => {
  it('carries an error-level log event into the exit error and the combined output', () => {
    const collector = createJobOutputCollector();
    collector.consume(errorEvent);
    const settled = settleRenetRun({ exitCode: 1, stdout: '', stderr: '', collector });
    expect(settled.error).toContain(
      `device ${WK_INFRA_DOMAIN}/fake=x is not defined by any CDI spec`
    );
    expect(settled.combined).toContain('not defined by any CDI spec');
  });

  it('does not fold collector lines into a successful run', () => {
    const collector = createJobOutputCollector();
    collector.consume({ type: 'log', level: 'warning', msg: 'skipped csi' } as never);
    const settled = settleRenetRun({ exitCode: 0, stdout: '', stderr: '', collector });
    expect(settled.error).toBeUndefined();
    expect(settled.combined).not.toContain('skipped csi');
  });

  it('leaves a non-events run unchanged', () => {
    const settled = settleRenetRun({ exitCode: 1, stdout: 'out', stderr: 'Error: boom\n' });
    expect(settled.error).toBe('renet exited with code 1: boom');
    expect(settled.combined).toBe('outError: boom\n');
  });

  it('keeps raw stderr and joins on a newline', () => {
    expect(mergeEventsStderr('raw', 'evt\n')).toBe('raw\nevt\n');
    expect(mergeEventsStderr('raw', '')).toBe('raw');
  });
});
