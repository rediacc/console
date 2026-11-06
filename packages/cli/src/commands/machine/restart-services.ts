/**
 * `rdc machine restart-services <name> [--include-docker [--repo <name>]]`: a rolling restart of the renet daemons
 * that still run a replaced binary. renet confirms each unit healthy before it restarts the next.
 * With --include-docker a `rediacc-docker-N` supervisor restart also restarts that repo's dockerd:
 * renet records the containers running before it, starts them again, waits until each is running
 * (and healthy where it has a healthcheck), reports the repo under `repos`, and stops the rolling
 * restart at the first repo that does not come back (its supervisor is `failed`, so the exit is 1).
 * `--repo <name>` (with --include-docker) scopes the restart to that repo's network id; a renet that predates the scope refuses it and nothing restarts.
 */

import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { isRenetFlagUnsupported } from '../../services/executor/job-client.js';
import { pendingExitCode, runCommandJob } from '../../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../../services/jobs/steps.js';
import { parseDaemonUpgradeJson, reportDaemonUpgrade } from '../../services/renet/renet-daemons.js';
import type { OutputFormat } from '../../types/index.js';
import { getOutputFormat, handleError, ValidationError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { assertMachineExists } from '../_validate.js';

interface RestartServicesOptions {
  includeDocker?: boolean;
  repo?: string;
  json?: boolean;
}

/** The refusal of a renet that predates `--network-id`: cobra's unknown flag naming it, or the job builder's closed argument list. */
function isScopeUnsupported(text: string): boolean {
  return (
    (isRenetFlagUnsupported(text) && /unknown (?:shorthand )?flag[^\n]*network-id/.test(text)) ||
    /argument "network-ids" is not allowed/.test(text)
  );
}

/** Whether the job's stdout is the restart report of a run that started, which no refusal ever prints. */
function isRestartReport(stdout: string | undefined): boolean {
  try {
    parseDaemonUpgradeJson(stdout ?? '');
    return true;
  } catch {
    return false;
  }
}

/** A refusal: the JSON error envelope under `--json`, the error text and exit 1 otherwise. */
function refuse(message: string, format: OutputFormat): void {
  if (format === 'json') handleError(new ValidationError(message));
  outputService.error(message);
  setExitCode(1);
}

/** The argument object of the daemons-restart job. */
function restartArgs(
  options: RestartServicesOptions,
  networkIds: number[] | undefined
): Record<string, unknown> {
  return {
    ...(options.includeDocker ? { 'include-docker': true } : {}),
    ...(networkIds ? { 'network-ids': networkIds } : {}),
  };
}

/** Whether a failed job's output is an older renet refusing the scope. */
function isScopeRefused(result: { stderr?: string; stdout?: string; error?: string }): boolean {
  // A report on stdout means units were handled, so its text is data, not a refusal.
  const stdout = isRestartReport(result.stdout) ? '' : (result.stdout ?? '');
  return isScopeUnsupported(`${result.stderr ?? ''}\n${stdout}\n${result.error ?? ''}`);
}

/** The network ids `--repo` selects, undefined without it, or 'refused' once the refusal is printed. */
async function resolveScope(
  options: RestartServicesOptions,
  format: OutputFormat
): Promise<number[] | undefined | 'refused'> {
  if (options.repo === undefined) return undefined;
  const resolved = await resolveRepoNetworkId(options);
  if ('error' in resolved) {
    refuse(resolved.error, format);
    return 'refused';
  }
  return [resolved.networkId];
}

/** Map `--repo` to its network id, or say why not: a refusal runs nothing. */
async function resolveRepoNetworkId(
  options: RestartServicesOptions
): Promise<{ networkId: number } | { error: string }> {
  const repo = options.repo as string;
  if (!options.includeDocker) {
    return { error: t('commands.machine.restartServices.repoNeedsDocker') };
  }
  const config = await configService.getRepository(repo);
  if (!config?.networkId || config.networkId <= 0) {
    return { error: t('commands.machine.restartServices.repoNoNetworkId', { repo }) };
  }
  return { networkId: config.networkId };
}

/** Print the report of the `daemons-restart` job, as tables or as data, and settle the exit code. */
function renderRestartReport(
  machineName: string,
  report: ReturnType<typeof parseDaemonUpgradeJson>,
  format: OutputFormat
): void {
  const table = format === 'table';
  if (table) {
    reportDaemonUpgrade({ ran: true, ...report });
    if (report.restarted.length === 0 && report.failed.length === 0 && report.stale.length === 0) {
      outputService.info(
        t('commands.machine.restartServices.nothingStale', { machine: machineName })
      );
    }
  } else {
    outputService.print(report, format);
  }

  if (report.failed.length > 0) {
    setExitCode(1);
  } else if (table) {
    outputService.success(
      t('commands.machine.restartServices.completed', { machine: machineName })
    );
  }
}

bindStepHandler('renderRestartServices', ({ machine, output, params }) => {
  const format: OutputFormat = params.json === true ? 'json' : getOutputFormat();
  renderRestartReport(machine, parseDaemonUpgradeJson(output ?? ''), format);
  return Promise.resolve();
});

async function runRestartServices(
  machineName: string,
  options: RestartServicesOptions
): Promise<void> {
  await assertMachineExists(machineName);
  const format: OutputFormat = options.json ? 'json' : getOutputFormat();
  const scope = await resolveScope(options, format);
  if (scope === 'refused') return;
  const networkIds = scope;
  if (format === 'table') {
    outputService.info(t('commands.machine.restartServices.starting', { machine: machineName }));
  }

  // One job; renet rolls the units inside it and the report is its step, so a ticket handed back early prints nothing half-done.
  const outcome = await runCommandJob(
    'machine restart-services',
    {
      functionName: 'daemons-restart',
      machineName,
      commandKind: {
        name: 'daemons-restart',
        args: restartArgs(options, networkIds),
      },
      captureOutput: true,
    },
    [planStep('renderRestartServices', { json: options.json === true })]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (outcome.result.success) return;
  if (networkIds && isScopeRefused(outcome.result)) {
    refuse(t('commands.machine.restartServices.repoRenetTooOld', { machine: machineName }), format);
    return;
  }
  renderRestartFailure(machineName, outcome.result, format);
}

/** A failed job still prints the report it left on stdout (the failed units), then exits non-zero. */
function renderRestartFailure(
  machineName: string,
  result: Parameters<typeof renderLocalExecutionFailure>[0],
  format: OutputFormat
): void {
  try {
    renderRestartReport(machineName, parseDaemonUpgradeJson(result.stdout ?? ''), format);
    setExitCode(result.exitCode && result.exitCode > 0 ? result.exitCode : 1);
  } catch {
    renderLocalExecutionFailure(result, `Restarting the renet daemons on '${machineName}' failed`);
  }
}

export function registerRestartServicesCommand(machine: Command): void {
  machine
    .command('restart-services')
    .argument('<name>', t('options.name'))
    .summary(t('commands.machine.restartServices.descriptionShort'))
    .description(t('commands.machine.restartServices.description'))
    .option('--include-docker', t('commands.machine.restartServices.includeDockerOption'))
    .option('--repo <name>', t('commands.machine.restartServices.repoOption'))
    .option('--json', t('commands.machine.restartServices.jsonOption'))
    .action(async (name: string, options: RestartServicesOptions) => {
      try {
        await runRestartServices(name, options);
      } catch (error) {
        handleError(error);
      }
    });
}
