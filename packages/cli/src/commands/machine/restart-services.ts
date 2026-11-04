/**
 * `rdc machine restart-services <name> [--include-docker]`: a rolling restart of the renet daemons
 * that still run a replaced binary. renet confirms each unit healthy before it restarts the next.
 * With --include-docker a `rediacc-docker-N` supervisor restart also restarts that repo's dockerd:
 * renet records the containers running before it, starts them again, waits until each is running
 * (and healthy where it has a healthcheck), reports the repo under `repos`, and stops the rolling
 * restart at the first repo that does not come back (its supervisor is `failed`, so the exit is 1).
 */

import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { pendingExitCode, runCommandJob } from '../../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../../services/jobs/steps.js';
import { parseDaemonUpgradeJson, reportDaemonUpgrade } from '../../services/renet/renet-daemons.js';
import type { OutputFormat } from '../../types/index.js';
import { getOutputFormat, handleError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { assertMachineExists } from '../_validate.js';

interface RestartServicesOptions {
  includeDocker?: boolean;
  json?: boolean;
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
        args: options.includeDocker ? { 'include-docker': true } : {},
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
  if (!outcome.result.success) renderRestartFailure(machineName, outcome.result, format);
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
    .option('--json', t('commands.machine.restartServices.jsonOption'))
    .action(async (name: string, options: RestartServicesOptions) => {
      try {
        await runRestartServices(name, options);
      } catch (error) {
        handleError(error);
      }
    });
}
