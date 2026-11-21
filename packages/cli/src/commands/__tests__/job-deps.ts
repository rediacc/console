/**
 * Test seam for a command that runs its main call through `runCommandJob`: the executor is the caller's fake, the
 * ticket store is real in a temp directory, and the step claim grants every claim so the command's own plan runs.
 */
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { ExecuteOptions, ExecuteResult } from '../../services/executor/types.js';
import { setCommandJobDeps } from '../../services/jobs/command-job.js';
import { TicketStore } from '../../services/jobs/ticket-store.js';

/** Route `runCommandJob` through `execute`; call the returned function to restore the live dependencies. `warn` receives what a failed step reports. */
export function installJobDeps(
  execute: (options: ExecuteOptions) => Promise<ExecuteResult>,
  warn: (line: string) => void = () => undefined
): () => void {
  const dir = mkdtempSync(join(tmpdir(), 'job-deps-'));
  const store = new TicketStore('test', dir);
  setCommandJobDeps({
    executor: () => ({ execute }),
    store: () => store,
    stepDeps: () =>
      Promise.resolve({
        observer: { configName: 'test' },
        warn,
        claim: ({ steps }) =>
          Promise.resolve(steps.map((name) => ({ name, result: 'claimed' as const }))),
      }),
  });
  return () => {
    setCommandJobDeps();
    rmSync(dir, { recursive: true, force: true });
  };
}
