/**
 * `repo admin autostart list`: the read job and the step that renders its payload. Split out of
 * repo-extended.ts to keep file size within limits.
 */
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { runCommandJob } from '../services/jobs/command-job.js';
import { requireStepOutput } from '../services/jobs/step-output.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { getOutputFormat } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { assertMachineExists } from './_validate.js';
import { parseDatastorePruneOutput } from './datastore-prune-parser.js';
import { settleRepoJob } from './repo-job-outcome.js';

interface AutostartListPayload {
  service_installed?: boolean;
  service_enabled?: boolean;
  repositories?: { name: string; enabled: boolean; on_disk: boolean }[] | null;
}

export interface AutostartListOptions {
  machine: string;
  cluster?: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
}

/** `repo autostart list`, fetch the renet payload and render it. */
export async function handleAutostartList(options: AutostartListOptions): Promise<void> {
  await assertMachineExists(options.machine);
  outputService.info(
    t('commands.repo.admin.autostart.list.starting', { machine: options.machine })
  );

  // One read job; the table is its success step, so a ticket handed back early prints nothing half-done.
  const outcome = await runCommandJob(
    'repo admin autostart list',
    {
      functionName: 'repository_autostart_list',
      machineName: options.machine,
      params: {},
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
      captureOutput: true,
    },
    [planStep('renderAutostartList', { machine: options.machine })]
  );
  settleRepoJob(
    'repo admin autostart list',
    outcome,
    outcome.result.error ?? t('commands.repo.admin.autostart.list.failed')
  );
}

/** The `renderAutostartList` step: print the payload the `repository_autostart_list` job produced. */
bindStepHandler('renderAutostartList', async ({ output, params }) => {
  // renet relays a single JSON object with `[repository_autostart_list]` line prefixes, same shape the prune parser extracts.
  const text = requireStepOutput(output, 'repo admin autostart list');
  if (text === undefined) return;
  const payload = parseDatastorePruneOutput(text) as AutostartListPayload;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(payload, format);
    return;
  }

  const resolve = createGuidResolver(await loadGuidMap());
  const rows = (payload.repositories ?? []).map((r) => ({
    repository: resolve(r.name),
    guid: r.name,
    enabled: r.enabled ? 'yes' : 'no',
    onDisk: r.on_disk ? 'yes' : 'no',
  }));

  if (rows.length === 0) {
    outputService.info(
      t('commands.repo.admin.autostart.list.empty', { machine: String(params.machine) })
    );
  } else {
    outputService.print(rows, 'table');
  }
  outputService.info(
    t('commands.repo.admin.autostart.list.service', {
      installed: payload.service_installed ? 'yes' : 'no',
      enabled: payload.service_enabled ? 'yes' : 'no',
    })
  );
});
