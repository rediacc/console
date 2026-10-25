/**
 * `rdc machine restart-services <name> [--include-docker]`: a rolling restart of the renet daemons
 * that still run a replaced binary. renet confirms each unit healthy before it restarts the next.
 */

import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { machineConnections } from '../../services/machine/machine-connection.js';
import { reportDaemonUpgrade, restartDaemons } from '../../services/renet/renet-daemons.js';
import { REMOTE_RENET_PATH } from '../../services/renet/renet-provisioner.js';
import type { OutputFormat } from '../../types/index.js';
import { getOutputFormat, handleError } from '../../utils/errors.js';
import { assertMachineExists } from '../_validate.js';

interface RestartServicesOptions {
  includeDocker?: boolean;
  json?: boolean;
}

async function runRestartServices(
  machineName: string,
  options: RestartServicesOptions
): Promise<void> {
  await assertMachineExists(machineName);
  const format: OutputFormat = options.json ? 'json' : getOutputFormat();
  const table = format === 'table';
  if (table)
    outputService.info(t('commands.machine.restartServices.starting', { machine: machineName }));

  const lease = await machineConnections.acquire(machineName);
  let report: Awaited<ReturnType<typeof restartDaemons>>;
  try {
    report = await restartDaemons(
      lease.sftp,
      machineName,
      REMOTE_RENET_PATH,
      options.includeDocker === true
    );
  } finally {
    lease.release();
  }

  if (table) {
    reportDaemonUpgrade(report);
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
