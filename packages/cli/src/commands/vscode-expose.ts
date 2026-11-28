/**
 * `rdc vscode expose|unexpose <ref>`: start or stop the repository's browser
 * VS Code at its public hostname, behind the route server's portal-token gate
 * (agent/plans/PLAN-vscode-browser-exposure.md V3). Each verb is one renet
 * job, `repository_vscode_expose` or `repository_vscode_unexpose`; the editor
 * is a pinned code-server container on the repository's own daemon, so no SSH
 * tunnel is held and the editor is opened from the web console, which mints
 * the token. A cluster-placed repo is refused: the container runs on a docker
 * repository daemon.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { ensureRepositoryNetworkId } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { parseVSCodeExposeResult } from '../services/core/vscode-server-remote.js';
import { runCommandJob } from '../services/jobs/command-job.js';
import { requireStepOutput } from '../services/jobs/step-output.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { settleRepoJob } from './repo-job-outcome.js';

interface VSCodeExposeOptions {
  debug?: boolean;
  skipRouterRestart?: boolean;
}

type ExposeVerb = 'expose' | 'unexpose';

/** The `printVscodeExpose` step: print the editor's URL the expose job produced. */
bindStepHandler('printVscodeExpose', ({ output }) => {
  const text = requireStepOutput(output, 'vscode expose');
  if (text === undefined) return Promise.resolve();
  const result = parseVSCodeExposeResult(text);
  if (!result) {
    outputService.error(t('commands.vscode.expose.noResult'));
    setExitCode(1);
    return Promise.resolve();
  }
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(result, format);
    return Promise.resolve();
  }
  outputService.success(t('commands.vscode.expose.exposed', { url: result.url }));
  outputService.info(t('commands.vscode.expose.openHint'));
  return Promise.resolve();
});

async function runExposeVerb(
  verb: ExposeVerb,
  ref: string,
  options: VSCodeExposeOptions
): Promise<void> {
  // Mutating verb: the machine comes from the ref's placement (spec/03 §2.3).
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
  if (kubeCluster) {
    throw new ValidationError(
      t('errors.cluster.featureUnsupportedV1', {
        feature: `vscode ${verb}`,
        hint: t('errors.vscode.exposeNeedsDocker'),
      })
    );
  }
  if (!(await configService.getRepository(repoKey))) {
    throw new ValidationError(t('errors.vscode.exposeRepoNotFound', { name }));
  }
  await ensureRepositoryNetworkId(repoKey);

  const label = `vscode ${verb}`;
  const outcome = await runCommandJob(
    label,
    {
      functionName: verb === 'expose' ? 'repository_vscode_expose' : 'repository_vscode_unexpose',
      machineName,
      // #74: the repository mount lives on the datastore the repo is RECORDED on.
      datastore: await recordedDatastoreMount(repoKey),
      params: { repository: repoKey },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
      ...(verb === 'expose' && { captureOutput: true }),
    },
    verb === 'expose' ? [planStep('printVscodeExpose')] : []
  );
  const failed =
    verb === 'expose' ? t('commands.vscode.expose.failed') : t('commands.vscode.unexpose.failed');
  if (!settleRepoJob(label, outcome, failed)) return;
  if (verb === 'unexpose') {
    outputService.success(t('commands.vscode.unexpose.stopped', { name }));
  }
}

function addExposeVerb(
  vscode: Command,
  verb: ExposeVerb,
  summary: string,
  description: string
): void {
  vscode
    .command(verb)
    .summary(summary)
    .description(description)
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (ref: string, options: VSCodeExposeOptions) => {
      try {
        await runExposeVerb(verb, ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}

export function registerVSCodeExposeCommands(vscode: Command): void {
  addExposeVerb(
    vscode,
    'expose',
    t('commands.vscode.expose.descriptionShort'),
    t('commands.vscode.expose.description')
  );
  addExposeVerb(
    vscode,
    'unexpose',
    t('commands.vscode.unexpose.descriptionShort'),
    t('commands.vscode.unexpose.description')
  );
}
