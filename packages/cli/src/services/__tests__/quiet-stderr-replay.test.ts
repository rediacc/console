import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createQuietStderrPump } from '../executor/output-lines.js';

/**
 * A withheld logrus line is 115-358 columns wide. When the command fails it is
 * REPLAYED, and at that moment a human is reading it, so it must be wrapped by
 * us rather than by the terminal - terminal wrapping interleaves it with the row
 * below and shreds the layout. The tutorials hit this through
 * `run_cmd_expect_fail`, where the failure IS the demo and the diagnostic is on
 * camera.
 */
describe('createQuietStderrPump replay width', () => {
  // Shaped like the line that actually shipped on camera at 115 columns:
  // structured, with spaces, so it CAN be broken at a space.
  const LONG =
    'time="2026-08-19T17:54:21Z" level=info ' +
    'msg="Starting repository 3d8be679-59f1-4047-8b39-006c60108380 on machine-11 ' +
    'with docker daemon socket and loopback range already provisioned"';
  /** One unbroken token: wrapProse leaves these INTACT on purpose. */
  const UNBREAKABLE = `time="2026-08-19T17:54:21Z" level=info msg="${'x'.repeat(200)}"`;
  let written: string[];

  beforeEach(() => {
    written = [];
    vi.spyOn(process.stderr, 'write').mockImplementation((chunk: unknown) => {
      written.push(String(chunk));
      return true;
    });
    process.stdout.columns = 107;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('withholds a quiet logrus line while the command is still running', () => {
    const pump = createQuietStderrPump();
    pump.write(`${LONG}\n`);
    expect(written).toEqual([]);
  });

  it('replays it on failure with every row inside the terminal width', () => {
    const pump = createQuietStderrPump();
    pump.write(`${LONG}\n`);
    pump.flush(true);
    const rows = written
      .join('')
      .split('\n')
      .filter((r) => r !== '');
    expect(rows.length).toBeGreaterThan(1);
    for (const row of rows) expect(row.length).toBeLessThanOrEqual(107);
  });

  it('leaves an unbreakable token intact rather than making it uncopyable', () => {
    const pump = createQuietStderrPump();
    pump.write(`${UNBREAKABLE}\n`);
    pump.flush(true);
    const rows = written
      .join('')
      .split('\n')
      .filter((r) => r !== '');
    // DELIBERATE: a 200-character token with no spaces cannot be broken without
    // making it uncopyable, so it stays over-width. Recorded here so a future
    // reader knows this is a decision, not an oversight.
    expect(rows.some((r) => r.length > 107)).toBe(true);
  });

  it('echoes info lines LIVE when echoAll is set, which is what --debug relies on', () => {
    // The concurrent-fork-isolation suite greps a `--debug` log for renet's
    // "restored from checkpoint", emitted with log.Infof. If echoAll does not
    // pass info-level lines through immediately, that evidence never reaches the
    // log and the test blames console#440 for a regression that did not happen.
    const pump = createQuietStderrPump({ echoAll: true });
    pump.write(`${LONG}\n`);
    expect(written.join('')).toContain('level=info');
  });

  it('stays silent on success', () => {
    const pump = createQuietStderrPump();
    pump.write(`${LONG}\n`);
    pump.flush(false);
    expect(written).toEqual([]);
  });
});
