/**
 * Executor-daemon wire protocol: the pure half.
 *
 * Frames must survive an NDJSON round trip across arbitrary chunk boundaries, and
 * the serializability gate must let the two transported callbacks through while
 * rejecting anything else that JSON cannot carry (so a command with a real
 * non-serializable option is routed to the direct executor, never the daemon).
 */

import { describe, expect, it } from 'vitest';
import type { ExecuteOptions } from '../types.js';
import {
  createFrameReader,
  encodeFrame,
  type Frame,
  isDaemonSerializable,
  toWireOptions,
} from '../daemon/protocol.js';

function collect(chunks: string[]): Frame[] {
  const frames: Frame[] = [];
  const read = createFrameReader<Frame>((f) => frames.push(f));
  for (const chunk of chunks) read(chunk);
  return frames;
}

describe('daemon protocol codec', () => {
  it('round-trips a frame through encode/decode', () => {
    const frame: Frame = {
      type: 'event',
      id: 'abc',
      event: { type: 'log', msg: 'hello', level: 'info' },
      line: 3,
    };
    expect(collect([encodeFrame(frame)])).toEqual([frame]);
  });

  it('reassembles a frame split across chunk boundaries', () => {
    const frame: Frame = {
      type: 'result',
      id: 'x',
      result: { success: true, exitCode: 0, durationMs: 5 },
    };
    const wire = encodeFrame(frame);
    const mid = Math.floor(wire.length / 2);
    // Feed the frame in two pieces; the partial first line must be buffered until
    // its newline arrives in the second.
    expect(collect([wire.slice(0, mid), wire.slice(mid)])).toEqual([frame]);
  });

  it('decodes several frames delivered in one chunk', () => {
    const a: Frame = { type: 'accepted', id: '1' };
    const b: Frame = { type: 'stale' };
    const c: Frame = { type: 'helloOk' };
    expect(collect([encodeFrame(a) + encodeFrame(b) + encodeFrame(c)])).toEqual([a, b, c]);
  });

  it('drops a malformed line but keeps the valid ones around it', () => {
    const good: Frame = { type: 'helloOk' };
    expect(collect([`${encodeFrame(good)}not json\n${encodeFrame(good)}`])).toEqual([good, good]);
  });
});

describe('daemon serializability gate', () => {
  const base: ExecuteOptions = { functionName: 'repository_status', machineName: 'm1' };

  it('accepts plain options', () => {
    expect(isDaemonSerializable(base)).toBe(true);
  });

  it('accepts nested serializable params', () => {
    expect(
      isDaemonSerializable({
        ...base,
        params: { repository: 'shop', tags: ['a', 'b'] },
        timeout: 1000,
      })
    ).toBe(true);
  });

  it('accepts the transported callbacks (they become frames)', () => {
    expect(isDaemonSerializable({ ...base, onEvent: () => {}, onJobStarted: () => {} })).toBe(true);
  });

  it('rejects a non-transported callback (routes direct)', () => {
    const withStrayCallback = { ...base, somethingCustom: () => {} } as unknown as ExecuteOptions;
    expect(isDaemonSerializable(withStrayCallback)).toBe(false);
  });

  it('rejects a bigint that JSON cannot carry', () => {
    const withBigint = { ...base, params: { size: 10n } } as unknown as ExecuteOptions;
    expect(isDaemonSerializable(withBigint)).toBe(false);
  });

  it('toWireOptions strips only the transported callbacks', () => {
    const wire = toWireOptions({ ...base, timeout: 42, onEvent: () => {}, onJobStarted: () => {} });
    expect(wire).toEqual({ functionName: 'repository_status', machineName: 'm1', timeout: 42 });
    expect('onEvent' in wire).toBe(false);
    expect('onJobStarted' in wire).toBe(false);
  });
});
