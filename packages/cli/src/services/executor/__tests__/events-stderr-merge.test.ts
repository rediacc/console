import { describe, expect, it } from 'vitest';
import { createJobOutputCollector } from '../job-client.js';
import { mergeEventsStderr } from '../local-executor.js';
import { buildRenetExitError } from '../renet-output.js';

describe('events-mode failure reason', () => {
  it('carries an error-level log event into the exit error', () => {
    const collector = createJobOutputCollector();
    collector.consume({
      type: 'log',
      level: 'error',
      msg: 'device rediacc.io/fake=x is not defined by any CDI spec',
    } as never);
    const stderr = mergeEventsStderr('', collector.stderr);
    expect(buildRenetExitError(1, stderr, collector.stdout)).toContain(
      'device rediacc.io/fake=x is not defined by any CDI spec'
    );
  });

  it('keeps raw stderr and joins on a newline', () => {
    expect(mergeEventsStderr('raw', 'evt\n')).toBe('raw\nevt\n');
    expect(mergeEventsStderr('raw', '')).toBe('raw');
  });
});
