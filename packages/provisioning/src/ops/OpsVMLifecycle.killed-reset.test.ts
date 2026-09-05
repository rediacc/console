import { EventEmitter } from 'node:events';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpsCommandRunner } from './OpsCommandRunner';
import { OpsVMLifecycle } from './OpsVMLifecycle';
import type { OpsVMExecutor } from './OpsVMExecutor';

// WHY THIS FILE EXISTS. Console CI run 33937342780: `renet ops up` blew its
// budget, we SIGTERM'd it, and `resetVMs` reported SUCCESS at 1800.8s anyway.
// `ops up` treats Ceph provisioning as non-fatal, so a kill mid-provision still
// leaves SSH-reachable VMs and still prints "Cluster started successfully" --
// the readiness probe passed on a half-built fleet. The suite then died a
// second later on a Ceph error that named Ceph rather than the budget, which is
// what made it expensive: every hypothesis pointed at storage, and the cause
// was that the caller had been told a killed operation succeeded.
//
// Neither OpsVMLifecycle.ts nor OpsCommandRunner.ts had any test file before
// this one (only OpsManager.group-env.test.ts existed here), which is how the
// fix landed uncovered. Raised as a medium finding by the automated review of
// a032863c7 and tracked as worklist #a5d9f490.
//
// Each assertion is paired with a CONTROL that reproduces the ORIGINAL bug, so
// a green run means the test can actually distinguish the two -- not that the
// code path was never reached.

const fakeChild = () => {
  const child = new EventEmitter() as EventEmitter & {
    stdout: EventEmitter;
    stderr: EventEmitter;
    kill: ReturnType<typeof vi.fn>;
  };
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = vi.fn();
  return child;
};

const { spawned } = vi.hoisted(() => ({ spawned: [] as ReturnType<typeof fakeChild>[] }));

vi.mock('node:child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:child_process')>();
  return {
    ...actual,
    spawn: () => {
      const child = fakeChild();
      spawned.push(child);
      return child;
    },
  };
});

/** The wreckage a killed `ops up` leaves: it still claims the cluster is up. */
const HALF_PROVISIONED_OUTPUT = 'Cluster started successfully\n';

beforeEach(() => {
  spawned.length = 0;
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('OpsCommandRunner reports a kill distinctly from a non-zero exit', () => {
  it('sets timedOut when the budget expires, and kills the child', async () => {
    const runner = new OpsCommandRunner('/usr/bin/renet', '/tmp');
    const promise = runner.runWithEnv(['up'], [], {}, 1000);

    await vi.advanceTimersByTimeAsync(1001);
    const result = await promise;

    expect(result.timedOut).toBe(true);
    expect(result.code).toBe(-1);
    expect(result.stderr).toContain('Timeout exceeded');
    expect(spawned[0].kill).toHaveBeenCalledWith('SIGTERM');
  });

  it('CONTROL: a command that exits non-zero on its own is NOT flagged timedOut', async () => {
    const runner = new OpsCommandRunner('/usr/bin/renet', '/tmp');
    const promise = runner.runWithEnv(['up'], [], {}, 60_000);

    spawned[0].emit('close', 1);
    const result = await promise;

    // Both shapes carry a failing code; only the kill carries timedOut. If this
    // control ever goes true, `timedOut` has stopped meaning "we killed it" and
    // every assertion below is testing nothing.
    expect(result.code).toBe(1);
    expect(result.timedOut).toBeUndefined();
  });
});

describe('resetVMs must FAIL when we killed the reset', () => {
  const build = (result: Awaited<ReturnType<OpsCommandRunner['runWithEnv']>>) => {
    const commandRunner = { runWithEnv: vi.fn().mockResolvedValue(result) };
    // The readiness probe is what used to rescue a killed reset: it answers
    // "reachable" for a half-built fleet. Stubbing it to SUCCEED is deliberate
    // -- it recreates the exact conditions of run 33937342780, so the only
    // thing that can fail the reset is the timedOut guard itself.
    const vmExecutor = {
      waitForVM: vi.fn().mockResolvedValue(true),
      executeOnVM: vi.fn().mockResolvedValue({ code: 0, stdout: '', stderr: '' }),
    };
    return new OpsVMLifecycle(
      commandRunner as unknown as OpsCommandRunner,
      vmExecutor as unknown as OpsVMExecutor,
      () => ['192.168.111.11'],
      () => ['192.168.111.11'],
      () => []
    );
  };

  it('a SIGKILLed `ops up` fails the reset even though the fleet looks reachable', async () => {
    const lifecycle = build({
      stdout: HALF_PROVISIONED_OUTPUT,
      stderr: '\nTimeout exceeded: killed after 1800s',
      code: -1,
      timedOut: true,
    });

    const { success } = await lifecycle.resetVMs();

    // THE REGRESSION. Before the fix this returned true: code !== 0 fell
    // through to the readiness probe, the probe passed on the half-built fleet,
    // and the caller was told the reset succeeded.
    expect(success).toBe(false);
  });

  it('CONTROL: the same output WITHOUT timedOut still reaches the readiness probe', async () => {
    const lifecycle = build({
      stdout: HALF_PROVISIONED_OUTPUT,
      stderr: '',
      code: 0,
      timedOut: false,
    });

    const { success } = await lifecycle.resetVMs();

    // This is the pre-fix behaviour, and it must stay reachable: a clean `ops
    // up` still succeeds. If this ever went false the guard would be failing
    // every reset, and the assertion above would pass for the wrong reason.
    expect(success).toBe(true);
  });
});
