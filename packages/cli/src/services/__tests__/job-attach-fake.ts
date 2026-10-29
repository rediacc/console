/**
 * A test fake that answers a `renet job start --attach` exec the way renet does
 * (agent/plans/PLAN-detached-jobs.md section 15): one stream of a `job_handle`
 * line, the job's events, and a `job_status` trailer.
 *
 * Every renet call through the executor runs as a machine job, so a test that
 * scripts "what renet printed and how it exited" wraps its script with
 * `asJobAttach`: the script still answers with stdout, stderr and an exit code,
 * and the fake turns them into what the job's spool would hold (stdout lines as
 * `output` events, stderr lines as error `log` events) and the trailer's exit
 * code. Any other exec (a `renet execute` exemption, a probe) passes through
 * untouched. An unscripted mock answers `undefined`, which a `renet execute`
 * run read as a failure; the fake keeps that reading (exit 1) rather than
 * turning it into a dropped channel the executor would retry.
 */

/** The handlers `execStreaming` takes, loosely typed as each test's own fake is. */
export interface FakeHandlers {
  stdin?: string;
  onStdout?: (data: never) => void;
  onStderr?: (data: never) => void;
}

export type FakeExec = (command: string, handlers: FakeHandlers) => Promise<number | undefined>;

export const FAKE_JOB_ID = 'j18c1994eaa33d30d-3d9813b2';

const lines = (text: string): string[] => text.split('\n').filter((line) => line.length > 0);

/**
 * One stdout line of a run as the spool records it: `job run` forces events
 * mode, so a text-mode step line (`{"step_done":{...}}`) is a step event, and
 * every other line is an `output` event.
 */
function spoolEvent(msg: string): Record<string, unknown> {
  const jsonAt = msg.indexOf('{');
  if (jsonAt >= 0) {
    try {
      const parsed = JSON.parse(msg.slice(jsonAt)) as Record<string, unknown>;
      for (const type of ['step_start', 'step_done'] as const) {
        const step = parsed[type];
        if (step && typeof step === 'object') return { type, ...(step as Record<string, unknown>) };
      }
    } catch {
      // not JSON: an output line
    }
  }
  return { type: 'output', msg };
}

/** The attach stream renet prints for a job whose run produced this stdout, stderr and exit code. */
export function attachStream(
  stdout: string,
  stderr: string,
  exitCode: number,
  fn = 'unknown'
): string {
  const events = [
    ...lines(stdout).map(spoolEvent),
    ...lines(stderr).map((msg) => ({ type: 'log', level: 'error', msg })),
  ];
  const trailer = {
    type: 'job_status',
    job_id: FAKE_JOB_ID,
    function: fn,
    state: exitCode === 0 ? 'succeeded' : 'failed',
    exit_code: exitCode,
    started_at: '2026-10-29T10:00:00Z',
    finished_at: '2026-10-29T10:00:01Z',
  };
  return [{ type: 'job_handle', job_id: FAKE_JOB_ID, unit: 'u', log_path: 'p' }, ...events, trailer]
    .map((line) => `${JSON.stringify(line)}\n`)
    .join('');
}

/** Wrap a renet-run script so a `job start` exec answers as an attach stream. */
export function asJobAttach(run: FakeExec): FakeExec {
  return async (command, handlers) => {
    if (!command.includes(' job start ')) return run(command, handlers);
    let stdout = '';
    let stderr = '';
    const exitCode = await run(command, {
      ...handlers,
      onStdout: ((data: unknown) => {
        stdout += String(data);
      }) as (data: never) => void,
      onStderr: ((data: unknown) => {
        stderr += String(data);
      }) as (data: never) => void,
    });
    const code = typeof exitCode === 'number' ? exitCode : 1;
    const fn = /"function":"([a-z_]+)"/.exec(handlers.stdin ?? '')?.[1];
    (handlers.onStdout as ((data: string) => void) | undefined)?.(
      attachStream(stdout, stderr, code, fn)
    );
    return 0;
  };
}
