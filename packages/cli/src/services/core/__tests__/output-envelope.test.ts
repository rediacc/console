/**
 * The JSON envelope agrees with the exit code. A command that set a nonzero exit code before it
 * printed (setExitCode, or outputService.fail with a message) gets success:false and one errors[]
 * entry, its data kept; one that set none stays success:true with errors:null.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { EXIT_CODES } from '../../../types/index.js';
import { outputService } from '../output.js';
import { createOutputState, runInRequestContext, setExitCode } from '../request-context.js';

interface Envelope {
  success: boolean;
  data: unknown;
  errors: { code: string; message: string; retryable: boolean; exitCode: number }[] | null;
}

/** Run `body` inside a request context, so the exit code it sets stays on the request. */
async function inRequest(body: () => void): Promise<Envelope> {
  const ctx = {
    output: createOutputState(),
    stdout: [] as (string | Uint8Array)[],
    stderr: [] as string[],
  };
  await runInRequestContext(ctx, () => {
    outputService.setCommandContext('test cmd', Date.now());
    body();
    outputService.print({ rows: [1, 2] }, 'json');
    return Promise.resolve();
  });
  return JSON.parse(ctx.stdout.join('')) as Envelope;
}

describe('JSON envelope success follows the exit code', () => {
  afterEach(() => {
    process.exitCode = undefined;
  });

  it('no exit code set: success:true, errors:null', async () => {
    const env = await inRequest(() => undefined);
    expect(env.success).toBe(true);
    expect(env.errors).toBeNull();
    expect(env.data).toEqual({ rows: [1, 2] });
  });

  it('a bare setExitCode: success:false, the code named, the data kept', async () => {
    const env = await inRequest(() => setExitCode(EXIT_CODES.GENERAL_ERROR));
    expect(env.success).toBe(false);
    expect(env.errors).toEqual([
      {
        code: 'GENERAL_ERROR',
        message: 'test cmd failed with exit code 1 (GENERAL_ERROR).',
        retryable: false,
        exitCode: 1,
      },
    ]);
    expect(env.data).toEqual({ rows: [1, 2] });
  });

  it('fail(): the recorded message, and a retryable code is marked retryable', async () => {
    const env = await inRequest(() =>
      outputService.fail(EXIT_CODES.NETWORK_ERROR, 'host "dead" is unreachable')
    );
    expect(env.errors).toEqual([
      {
        code: 'NETWORK_ERROR',
        message: 'host "dead" is unreachable',
        retryable: true,
        exitCode: EXIT_CODES.NETWORK_ERROR,
      },
    ]);
  });

  it('an unnamed code (renet 18) is EXIT_18', async () => {
    const env = await inRequest(() => setExitCode(18));
    expect(env.errors?.[0]).toMatchObject({ code: 'EXIT_18', exitCode: 18 });
  });

  it("inside a dispatch the executor's own process.exitCode is not the request's", async () => {
    process.exitCode = 1;
    const env = await inRequest(() => undefined);
    expect(env.success).toBe(true);
  });

  it('on a laptop (no request context) process.exitCode decides', () => {
    const writes: string[] = [];
    const original = process.stdout.write.bind(process.stdout);
    process.stdout.write = ((chunk: string) => {
      writes.push(chunk);
      return true;
    }) as typeof process.stdout.write;
    try {
      setExitCode(EXIT_CODES.NETWORK_ERROR);
      outputService.print([{ name: 'x' }], 'json');
    } finally {
      process.stdout.write = original;
    }
    const env = JSON.parse(writes.join('')) as Envelope;
    expect(env.success).toBe(false);
    expect(env.errors?.[0]).toMatchObject({ code: 'NETWORK_ERROR', retryable: true });
  });
});
