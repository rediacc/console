/**
 * A failed remote `renet job` call carries renet's own stderr into the thrown message, and a flag the remote renet does not know answers with the version-skew message instead of cobra's usage text.
 */

import { describe, expect, it, vi } from 'vitest';
import { isRenetFlagUnsupported, JobLogCursor, renetOlderThanCliMessage } from '../job-client.js';
import { followJobLogs, readJobStatus } from '../job-remote.js';

const JOB_ID = 'j18c1994eaa33d30d-3d9813b2';

function fakeSftp(exitCode: number, stderr: string) {
  return {
    execStreaming: vi.fn(
      (_cmd: string, handlers: { onStderr?: (data: Buffer) => void }): Promise<number> => {
        handlers.onStderr?.(Buffer.from(stderr));
        return Promise.resolve(exitCode);
      }
    ),
  };
}

describe('isRenetFlagUnsupported', () => {
  it.each(['Error: unknown flag: --since-line', "Error: unknown shorthand flag: 'x' in -x"])(
    'matches %s',
    (output) => {
      expect(isRenetFlagUnsupported(output)).toBe(true);
    }
  );

  it.each(['Error: repository "flag-runner" not found', 'job j1 failed: device busy', ''])(
    'does not match %s',
    (output) => {
      expect(isRenetFlagUnsupported(output)).toBe(false);
    }
  );
});

describe('readJobStatus failures', () => {
  it("carries renet's own stderr line", async () => {
    const sftp = fakeSftp(1, 'Error: unknown job "j9"\nRun renet --help\n');
    await expect(readJobStatus(sftp as never, '/usr/bin/renet', JOB_ID, 'm1')).rejects.toThrow(
      'Failed to read the status of job j18c1994eaa33d30d-3d9813b2: Error: unknown job "j9"'
    );
  });

  it('names the version skew for an unknown flag', async () => {
    const sftp = fakeSftp(1, 'Error: unknown flag: --since-line\nUsage: ...\n');
    await expect(readJobStatus(sftp as never, '/usr/bin/renet', JOB_ID, 'm1')).rejects.toThrow(
      renetOlderThanCliMessage('m1')
    );
  });
});

describe('followJobLogs failures', () => {
  it("carries renet's stderr instead of a bare exit code", async () => {
    const sftp = fakeSftp(1, 'Error: job spool unreadable\n');
    const lease = { sftp, ensure: () => Promise.resolve(sftp), release: () => {} };
    const error = await followJobLogs(
      lease as never,
      '/usr/bin/renet',
      JOB_ID,
      { onEvent: () => {} },
      new JobLogCursor(),
      'm1'
    ).catch((e: Error) => e);
    expect((error as Error).message).toContain('Error: job spool unreadable');
  });

  it('names the version skew when --since-line is unknown to the remote renet', async () => {
    const sftp = fakeSftp(1, 'Error: unknown flag: --since-line\n');
    const lease = { sftp, ensure: () => Promise.resolve(sftp), release: () => {} };
    const error = await followJobLogs(
      lease as never,
      '/usr/bin/renet',
      JOB_ID,
      { onEvent: () => {} },
      new JobLogCursor(),
      'm1'
    ).catch((e: Error) => e);
    expect((error as Error).message).toContain(
      'renet on m1 is older than this CLI; run machine setup'
    );
  });
});
