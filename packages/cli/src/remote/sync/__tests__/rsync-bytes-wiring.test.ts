/**
 * executeRsync's bytesTransferred wiring: the total of every finished file, falling back to the last
 * progress size when no file reached its 100% xfr# line. rsync is a fake child process here.
 */

import { EventEmitter } from 'node:events';
import { afterEach, describe, expect, it, vi } from 'vitest';

const fake = vi.hoisted(() => ({ chunks: [] as string[], code: 0 }));

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  spawn: () => {
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter;
      stderr: EventEmitter;
    };
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    setImmediate(() => {
      for (const chunk of fake.chunks) child.stdout.emit('data', Buffer.from(chunk));
      child.emit('close', fake.code);
    });
    return child;
  },
}));
vi.mock('../../utils/platform.js', () => ({
  commandExists: async () => true,
  getPlatform: () => 'linux',
}));

import { executeRsync } from '../rsync.js';

const run = (onProgress?: () => void) =>
  executeRsync({
    sshOptions: '',
    source: '/src/',
    destination: 'h:/dst/',
    onProgress,
  });

afterEach(() => {
  fake.chunks = [];
  fake.code = 0;
});

describe('executeRsync bytesTransferred', () => {
  it('sums the finished files across chunks, with or without a progress callback', async () => {
    fake.chunks = [
      '2,000 100%    1.00MB/s    0:00:00 (xfr#1, to-chk=1/3)\n',
      '500 100%    1.00MB/s    0:00:00 (xfr#2, to-chk=0/3)\n',
    ];
    expect((await run()).bytesTransferred).toBe(2500);
    expect((await run(() => undefined)).bytesTransferred).toBe(2500);
  });

  it('keeps the totals right when a chunk ends inside the xfr# number', async () => {
    fake.chunks = [
      '100 100%    1.00MB/s    0:00:00 (xfr#1, to-chk=11/12)\n',
      '700 100%    1.00MB/s    0:00:00 (xfr#1',
      '2, to-chk=0/12)\n',
    ];
    expect((await run()).bytesTransferred).toBe(800);
  });

  it('reports the last progress size when no file reached its final line', async () => {
    fake.code = 30;
    fake.chunks = ['   900  40%  1.00MB/s  0:00:01 \n', '1,800  80%  1.00MB/s  0:00:02 \n'];
    expect((await run()).bytesTransferred).toBe(1800);
  });

  it('control: nothing printed means zero bytes', async () => {
    fake.chunks = ['sending incremental file list\n'];
    expect((await run()).bytesTransferred).toBe(0);
  });
});
