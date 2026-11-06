/**
 * The event tap decides per call whether renet's raw `output` reaches a proxied caller.
 *
 * On bench (2026-11-05) `rdc --proxy ... repo up <fork> --debug` printed about 128 KB of machine-wide container JSON:
 * the --debug up call switched output forwarding on for the whole dispatch, and the later `list-all` read that
 * postRepoUpTasks makes to resolve service URLs streamed every repository's containers and labels (a `mail` repo's
 * roundcube labels among them) into the fork's output. A repo-scoped command's output carries only its own data.
 */

import { describe, expect, it } from 'vitest';
import { createOutputState, runInRequestContext } from '../../core/request-context.js';
import { tapExecutor } from '../event-tap.js';
import type { ExecuteOptions, ExecuteResult, Executor, RenetEvent } from '../types.js';

const OWN_LINE = 'compose up: privdrop web started\n';
const MACHINE_WIDE = `${JSON.stringify({
  containers: [
    { name: 'privdrop-web', labels: { 'rediacc.repo_name': 'demo-stackoverflow:privdrop' } },
    {
      name: 'mail-roundcube',
      labels: { 'rediacc.repo_name': 'mail', 'com.docker.compose.service': 'roundcube' },
    },
  ],
})}\n`;

/** An executor whose every call streams the scripted `output` line for its function. */
function scripted(lines: Record<string, string>): Executor {
  return {
    execute(options: ExecuteOptions): Promise<ExecuteResult> {
      const msg = lines[options.functionName] ?? '';
      options.onEvent?.({ type: 'output', msg });
      options.onEvent?.({ type: 'step_done', name: options.functionName, duration_ms: 1 });
      return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: msg });
    },
  };
}

async function served(run: (executor: Executor) => Promise<void>): Promise<RenetEvent[]> {
  const seen: RenetEvent[] = [];
  await runInRequestContext(
    {
      output: createOutputState(),
      stdout: [],
      stderr: [],
      onEvent: (event) => seen.push(event),
    },
    () => run(tapExecutor(scripted({ repository_up: OWN_LINE, list_all: MACHINE_WIDE })))
  );
  return seen;
}

function outputs(events: RenetEvent[]): string[] {
  return events.flatMap((e) => (e.type === 'output' && e.msg ? [e.msg] : []));
}

describe('tapExecutor output forwarding', () => {
  it('a --debug up forwards its own output, never the machine-wide read that follows it', async () => {
    const events = await served(async (executor) => {
      await executor.execute({ functionName: 'repository_up', machineName: 'm1', debug: true });
      await executor.execute({ functionName: 'list_all', machineName: 'm1', captureOutput: true });
    });

    expect(outputs(events)).toEqual([OWN_LINE]);
    const all = JSON.stringify(events);
    expect(all).not.toContain('mail-roundcube');
    expect(all).not.toContain('roundcube');
    // Step events of every call still stream: only raw output is per-call.
    expect(events.filter((e) => e.type === 'step_done')).toHaveLength(2);
  });

  it('forwards a passthroughOutput call, and drops the output of a plain call', async () => {
    const events = await served(async (executor) => {
      await executor.execute({ functionName: 'list_all', machineName: 'm1' });
      await executor.execute({
        functionName: 'repository_up',
        machineName: 'm1',
        passthroughOutput: true,
      });
    });
    expect(outputs(events)).toEqual([OWN_LINE]);
  });

  it("the command's own handler still sees every event", async () => {
    const own: RenetEvent[] = [];
    await served(async (executor) => {
      await executor.execute({
        functionName: 'list_all',
        machineName: 'm1',
        onEvent: (e) => own.push(e),
      });
    });
    expect(outputs(own)).toEqual([MACHINE_WIDE]);
  });
});
