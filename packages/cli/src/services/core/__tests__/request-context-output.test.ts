/**
 * The request-scoped stand-ins for process.stdout, process.stderr and
 * process.exitCode: inside a dispatch they belong to the request, outside it
 * they are the process's, unchanged.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  type CommandRequestContext,
  commandOutcome,
  createOutputState,
  currentExitCode,
  joinStdout,
  runInRequestContext,
  setExitCode,
  writeStderr,
  writeStdout,
} from '../request-context.js';

function context(): CommandRequestContext {
  return { output: createOutputState(), stdout: [], stderr: [] };
}

describe('setExitCode', () => {
  const saved = process.exitCode;
  afterEach(() => {
    process.exitCode = saved;
  });

  it("sets the REQUEST's exit code inside a dispatch and leaves the process's alone", async () => {
    process.exitCode = undefined;
    const ctx = context();
    await runInRequestContext(ctx, () => {
      setExitCode(2);
      return Promise.resolve();
    });
    expect(ctx.exitCode).toBe(2);
    expect(process.exitCode).toBeUndefined();
  });

  it('sets process.exitCode outside a dispatch', () => {
    setExitCode(3);
    expect(process.exitCode).toBe(3);
  });
});

describe('writeStdout / writeStderr', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keep bytes as bytes in the request buffer, and never reach the process streams', async () => {
    const out = vi.spyOn(process.stdout, 'write');
    const ctx = context();
    const bytes = new Uint8Array([0xff, 0x00, 0x80]);
    await runInRequestContext(ctx, () => {
      writeStdout(bytes);
      writeStderr(new Uint8Array(Buffer.from('warn\n')));
      return Promise.resolve();
    });
    expect(ctx.stdout).toEqual([bytes]);
    expect(ctx.stderr).toEqual(['warn\n']);
    expect(out).not.toHaveBeenCalled();
  });

  it('decodes a multi-byte character split across two stderr byte chunks whole', async () => {
    const ctx = context();
    const euro = Buffer.from('€\n'); // e2 82 ac 0a
    await runInRequestContext(ctx, () => {
      writeStderr(new Uint8Array(euro.subarray(0, 2)));
      writeStderr(new Uint8Array(euro.subarray(2)));
      writeStderr('done\n');
      return Promise.resolve();
    });
    expect(ctx.stderr.join('')).toBe('€\ndone\n');
  });
});

describe('joinStdout', () => {
  it('keeps the historic line join for all-text output', () => {
    expect(joinStdout(['a', 'b'])).toEqual({ text: 'a\nb' });
  });

  it('concatenates bytes exactly once any chunk is binary', () => {
    const joined = joinStdout(['x', new Uint8Array([0xff, 0x0a])]);
    expect(joined.text).toBe('');
    expect(
      Buffer.from(joined.bytes ?? new Uint8Array()).equals(Buffer.from([0x78, 0xff, 0x0a]))
    ).toBe(true);
  });
});

describe('currentExitCode and commandOutcome', () => {
  const saved = process.exitCode;
  afterEach(() => {
    process.exitCode = saved;
  });

  it('inside a dispatch reads only the request code, never the executor process.exitCode', async () => {
    process.exitCode = 9;
    await runInRequestContext(context(), () => {
      expect(currentExitCode()).toBeUndefined();
      expect(commandOutcome(5)).toEqual({ success: true, exitCode: 0, duration: 5 });
      return Promise.resolve();
    });
  });

  it('outside a dispatch reads process.exitCode, and a nonzero code is a failed span', () => {
    process.exitCode = 3;
    expect(currentExitCode()).toBe(3);
    expect(commandOutcome(7)).toEqual({
      success: false,
      exitCode: 3,
      error: 'The command exited with code 3.',
      duration: 7,
    });
  });

  it('a nonzero code that is not an integer still fails, as exit 1', async () => {
    const ctx = context();
    ctx.exitCode = 1.5;
    await runInRequestContext(ctx, () => {
      expect(currentExitCode()).toBe(1);
      expect(commandOutcome(1).success).toBe(false);
      return Promise.resolve();
    });
    const nan = context();
    nan.exitCode = Number.NaN;
    await runInRequestContext(nan, () => {
      expect(currentExitCode()).toBe(1);
      return Promise.resolve();
    });
  });
});
