import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { routeLogEvent } from '../executor/daemon/client.js';
import { createQuietStderrPump, shouldEchoRelayLive } from '../executor/output-lines.js';

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

/**
 * The WIRING, not the pump. A peer proved the previous coverage gap by reverting the
 * flag half of this decision and re-running the pump tests: 5 passed either way. The
 * pump contract was pinned; the decision feeding it was not, so `--debug` could go
 * back to meaning nothing with no test going red.
 */
describe('shouldEchoRelayLive', () => {
  const saved = process.env.REDIACC_DEBUG;
  afterEach(() => {
    if (saved === undefined) delete process.env.REDIACC_DEBUG;
    else process.env.REDIACC_DEBUG = saved;
  });

  it('is TRUE for the --debug flag alone, with no env var', () => {
    delete process.env.REDIACC_DEBUG;
    expect(shouldEchoRelayLive({ debug: true })).toBe(true);
  });

  it('is TRUE for REDIACC_DEBUG alone, with no flag', () => {
    process.env.REDIACC_DEBUG = '1';
    expect(shouldEchoRelayLive({})).toBe(true);
  });

  it('is FALSE when neither is set, so the quiet default survives', () => {
    delete process.env.REDIACC_DEBUG;
    expect(shouldEchoRelayLive({})).toBe(false);
    expect(shouldEchoRelayLive({ debug: false })).toBe(false);
  });
});

/**
 * THE DAEMON PATH, which is the one `repo up` actually uses. The direct path was
 * fixed first and this one was missed, so `--debug` still withheld renet's
 * info-level lines and the concurrent-fork-isolation suite still could not find
 * "restored from checkpoint" in its own --debug log. Fixing the instance instead
 * of sweeping the class cost a second CI run.
 */
describe('routeLogEvent honours echoAll', () => {
  let out: string[];
  let held: string[];
  beforeEach(() => {
    out = [];
    held = [];
    vi.spyOn(process.stderr, 'write').mockImplementation((c: unknown) => {
      out.push(String(c));
      return true;
    });
  });
  afterEach(() => vi.restoreAllMocks());

  const info = { type: 'log', level: 'info', msg: 'Container x restored from checkpoint' };

  it('WITHHOLDS an info line when echoAll is false', () => {
    routeLogEvent(info as never, (l) => held.push(l), false);
    expect(out.join('')).toBe('');
    expect(held).toHaveLength(1);
  });

  it('ECHOES the same info line when echoAll is true, which is what --debug needs', () => {
    routeLogEvent(info as never, (l) => held.push(l), true);
    expect(out.join('')).toContain('restored from checkpoint');
    expect(held).toHaveLength(0);
  });

  it('always echoes error level, echoAll or not', () => {
    routeLogEvent({ type: 'log', level: 'error', msg: 'boom' } as never, (l) => held.push(l), false);
    expect(out.join('')).toContain('boom');
  });
});
