/**
 * The daemon-backed executor, driven against a REAL daemon server on a temp
 * socket with a fake executor injected — so the client, the server, and the wire
 * protocol are exercised together without touching SSH or a machine.
 *
 * The invariant under test is "never make a command worse": every trouble the
 * daemon can hit (wrong token, stale build, no daemon, a non-serializable option,
 * the kill switch) must transparently fall back to the direct executor, and a
 * genuine daemon run must relay the events and hand back the same result.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createDaemonExecutor,
  type DaemonClientDeps,
  sendDaemonControl,
} from '../daemon/client.js';
import { isDaemonPlatform, tokenPathFor } from '../daemon/lifecycle.js';
import { type DaemonHandle, startExecutorDaemon } from '../daemon/server.js';
import type { ExecuteOptions, ExecuteResult, Executor, RenetEvent } from '../types.js';

const SERVER_IDENTITY = 'daemon-test-identity';

/** A fake executor that records its calls, emits one event, and returns a marker. */
function fakeExecutor(stdout = 'FROM_DAEMON'): { executor: Executor; calls: ExecuteOptions[] } {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options: ExecuteOptions): Promise<ExecuteResult> {
        calls.push(options);
        options.onEvent?.({ type: 'log', msg: 'from the daemon executor' });
        return Promise.resolve({ success: true, exitCode: 0, durationMs: 7, stdout });
      },
    },
  };
}

/** A fake executor that returns CLI-side provision steps in its result. */
function fakeExecutorWithSteps(cliSteps: { name: string; duration_ms: number }[]): {
  executor: Executor;
  calls: ExecuteOptions[];
} {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options: ExecuteOptions): Promise<ExecuteResult> {
        calls.push(options);
        return Promise.resolve({
          success: true,
          exitCode: 0,
          durationMs: 9,
          stdout: 'DATA',
          cliSteps,
        });
      },
    },
  };
}

/** A stand-in direct executor, so a fallback is observable. */
function fallbackExecutor(): { executor: Executor; calls: ExecuteOptions[] } {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options: ExecuteOptions): Promise<ExecuteResult> {
        calls.push(options);
        return Promise.resolve({
          success: true,
          exitCode: 0,
          durationMs: 1,
          stdout: 'FROM_FALLBACK',
        });
      },
    },
  };
}

const handles: DaemonHandle[] = [];
const tmpDirs: string[] = [];

function tmpSocket(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rdc-daemon-'));
  tmpDirs.push(dir);
  return path.join(dir, 'd.sock');
}

/**
 * The daemon executor as these tests use it: allowUnderTest opts the wrapper back
 * in under vitest, which production keeps it OUT of (daemonEligible disables it
 * when process.env.VITEST is set). Every test here injects a fake server, so the
 * daemon path is the point.
 */
function daemonClient(fallback: Executor, deps: DaemonClientDeps): Executor {
  return createDaemonExecutor(fallback, { allowUnderTest: true, ...deps });
}

async function startServer(
  socketPath: string,
  executor: Executor,
  identity = SERVER_IDENTITY
): Promise<DaemonHandle> {
  const handle = await startExecutorDaemon({
    executor,
    socketPath,
    identity,
    watchConfig: false,
    onExit: () => {}, // never kill the test runner
  });
  handles.push(handle);
  return handle;
}

afterEach(async () => {
  await Promise.all(handles.map((h) => h.close()));
  handles.length = 0;
  for (const dir of tmpDirs) fs.rmSync(dir, { recursive: true, force: true });
  tmpDirs.length = 0;
  delete process.env.REDIACC_NO_DAEMON;
  delete process.env.REDIACC_VIA_DAEMON;
});

// The daemon is a unix-socket feature: skip the whole suite where it never runs.
const suite = isDaemonPlatform() ? describe : describe.skip;

const OPTIONS: ExecuteOptions = { functionName: 'repository_status', machineName: 'm1' };

suite('daemon-backed executor', () => {
  it('runs an execute through the daemon and relays its events', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutor('RESULT_MARKER');
    await startServer(socketPath, daemon.executor);
    const fallback = fallbackExecutor();

    const client = daemonClient(fallback.executor, {
      socketPath,
      identity: SERVER_IDENTITY,
      spawnDaemon: () => {},
    });

    const events: RenetEvent[] = [];
    const result = await client.execute({ ...OPTIONS, onEvent: (e) => events.push(e) });

    expect(result.stdout).toBe('RESULT_MARKER');
    expect(result.durationMs).toBe(7);
    expect(daemon.calls).toHaveLength(1);
    // The daemon forces events mode so output travels as frames.
    expect(daemon.calls[0].eventsMode).toBe(true);
    expect(fallback.calls).toHaveLength(0);
    expect(events.map((e) => e.msg)).toEqual(['from the daemon executor']);
  });

  it('falls back to direct when the token does not match', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutor();
    await startServer(socketPath, daemon.executor);
    // Corrupt the token file the client will read, forcing a hello rejection.
    fs.writeFileSync(tokenPathFor(socketPath), 'the-wrong-token');
    const fallback = fallbackExecutor();

    const client = daemonClient(fallback.executor, {
      socketPath,
      identity: SERVER_IDENTITY,
      spawnDaemon: () => {},
    });

    const result = await client.execute(OPTIONS);

    expect(result.stdout).toBe('FROM_FALLBACK');
    expect(fallback.calls).toHaveLength(1);
    expect(daemon.calls).toHaveLength(0);
  });

  it('falls back and respawns a fresh daemon when the running one is stale', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutor();
    await startServer(socketPath, daemon.executor, 'server-build-A');
    const fallback = fallbackExecutor();
    const spawn = vi.fn();

    const client = daemonClient(fallback.executor, {
      socketPath,
      identity: 'client-build-B', // mismatch → server answers `stale`
      spawnDaemon: spawn,
    });

    const result = await client.execute(OPTIONS);

    expect(result.stdout).toBe('FROM_FALLBACK');
    expect(fallback.calls).toHaveLength(1);
    expect(daemon.calls).toHaveLength(0);
    // A stale daemon triggers a respawn so the NEXT invocation is warm again.
    expect(spawn).toHaveBeenCalled();
  });

  it('falls back when no daemon is listening', async () => {
    const socketPath = tmpSocket(); // dir exists, socket does not
    const fallback = fallbackExecutor();
    const spawn = vi.fn();

    const client = daemonClient(fallback.executor, {
      socketPath,
      identity: SERVER_IDENTITY,
      spawnDaemon: spawn, // no-op: the "spawned" daemon never comes up
      spawnWaitMs: 120,
    });

    const result = await client.execute(OPTIONS);

    expect(result.stdout).toBe('FROM_FALLBACK');
    expect(fallback.calls).toHaveLength(1);
    // It tried to auto-spawn before giving up.
    expect(spawn).toHaveBeenCalled();
  });

  it('routes a non-serializable option direct, never touching the daemon', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutor();
    await startServer(socketPath, daemon.executor);
    const fallback = fallbackExecutor();

    const client = daemonClient(fallback.executor, {
      socketPath,
      identity: SERVER_IDENTITY,
      spawnDaemon: () => {},
    });

    // A stray callback the protocol does not transport makes the options
    // unserializable, so the seam must keep this on the direct path.
    const options = { ...OPTIONS, weirdCallback: () => {} } as unknown as ExecuteOptions;
    const result = await client.execute(options);

    expect(result.stdout).toBe('FROM_FALLBACK');
    expect(fallback.calls).toHaveLength(1);
    expect(daemon.calls).toHaveLength(0);
  });

  it('redraws the CLI-side provision timeline from result.cliSteps', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutorWithSteps([
      { name: 'config', duration_ms: 2 },
      { name: 'ssh_connect', duration_ms: 0 },
      { name: 'renet_provision', duration_ms: 0 },
      { name: 'machine_verify', duration_ms: 0 },
    ]);
    await startServer(socketPath, daemon.executor);
    const fallback = fallbackExecutor();

    // Capture what the client draws to stdout (renderJobEvent → process.stdout).
    const written: string[] = [];
    const spy = vi
      .spyOn(process.stdout, 'write')
      .mockImplementation((chunk: string | Uint8Array) => {
        written.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString());
        return true;
      });

    try {
      // No onEvent, not captureOutput, not quiet: the direct path would show the
      // four provision lines, so the daemon path must too.
      await daemonClient(fallback.executor, {
        socketPath,
        identity: SERVER_IDENTITY,
        spawnDaemon: () => {},
      }).execute(OPTIONS);
    } finally {
      spy.mockRestore();
    }

    const out = written.join('');
    // The exact labels the direct timedStep path prints, via getDoneLabel.
    expect(out).toContain('Config loaded');
    expect(out).toContain('Connected');
    expect(out).toContain('Renet provisioned');
    expect(out).toContain('Machine verified');
    expect(daemon.calls).toHaveLength(1);
    expect(fallback.calls).toHaveLength(0);
  });

  it('does not redraw the timeline when the caller renders its own (onEvent set)', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutorWithSteps([{ name: 'config', duration_ms: 2 }]);
    await startServer(socketPath, daemon.executor);
    const fallback = fallbackExecutor();

    const written: string[] = [];
    const spy = vi
      .spyOn(process.stdout, 'write')
      .mockImplementation((chunk: string | Uint8Array) => {
        written.push(typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString());
        return true;
      });

    try {
      await daemonClient(fallback.executor, {
        socketPath,
        identity: SERVER_IDENTITY,
        spawnDaemon: () => {},
      }).execute({ ...OPTIONS, onEvent: () => {} });
    } finally {
      spy.mockRestore();
    }

    // The caller owns rendering (it set onEvent); the client must not double-draw.
    expect(written.join('')).not.toContain('Config loaded');
  });

  it('routes direct when REDIACC_NO_DAEMON=1', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutor();
    await startServer(socketPath, daemon.executor);
    const fallback = fallbackExecutor();
    process.env.REDIACC_NO_DAEMON = '1';

    const client = daemonClient(fallback.executor, {
      socketPath,
      identity: SERVER_IDENTITY,
      spawnDaemon: () => {},
    });

    const result = await client.execute(OPTIONS);

    expect(result.stdout).toBe('FROM_FALLBACK');
    expect(fallback.calls).toHaveLength(1);
    expect(daemon.calls).toHaveLength(0);
  });

  it('stays inert under vitest: routes direct with zero socket activity', async () => {
    const socketPath = tmpSocket();
    const daemon = fakeExecutor();
    await startServer(socketPath, daemon.executor);
    const fallback = fallbackExecutor();
    const spawn = vi.fn();

    // NOT the daemonClient helper: this is the production factory wiring, which
    // must stay OUT of the daemon path while the unit-test suite is running.
    expect(process.env.VITEST).toBeTruthy();
    const client = createDaemonExecutor(fallback.executor, {
      socketPath,
      identity: SERVER_IDENTITY,
      spawnDaemon: spawn,
    });

    const result = await client.execute(OPTIONS);

    expect(result.stdout).toBe('FROM_FALLBACK');
    expect(fallback.calls).toHaveLength(1);
    expect(daemon.calls).toHaveLength(0); // never touched the socket
    expect(spawn).not.toHaveBeenCalled(); // never auto-spawned
  });
});

suite('daemon control frames', () => {
  it('status reports the running daemon', async () => {
    const socketPath = tmpSocket();
    await startServer(socketPath, fakeExecutor().executor);

    const reply = await sendDaemonControl(
      { type: 'status' },
      { socketPath, identity: SERVER_IDENTITY }
    );

    expect(reply?.type).toBe('statusInfo');
    if (reply?.type === 'statusInfo') {
      expect(reply.pid).toBe(process.pid);
      expect(reply.identity).toBe(SERVER_IDENTITY);
    }
  });

  it('stop asks the daemon to shut down', async () => {
    const socketPath = tmpSocket();
    await startServer(socketPath, fakeExecutor().executor);

    const reply = await sendDaemonControl(
      { type: 'stop' },
      { socketPath, identity: SERVER_IDENTITY }
    );

    expect(reply?.type).toBe('stopping');
  });

  it('returns null when no daemon is listening', async () => {
    const socketPath = tmpSocket(); // no server bound
    const reply = await sendDaemonControl(
      { type: 'status' },
      { socketPath, identity: SERVER_IDENTITY }
    );
    expect(reply).toBeNull();
  });
});
