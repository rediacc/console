import { Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import type { OpsBackend } from '../../services/executor/ops-executor.js';
import { opsExecutorService } from '../../services/executor/ops-executor.js';
import { handleError } from '../../utils/errors.js';
import { OPS_BACKEND_CHOICES } from './backends.js';

export const WINDOWS_CLIENT_ROLE = 'windows-client';

interface OpsVm {
  name: string;
  ip: string;
  role?: string;
}

/** Best effort: a status failure never blocks the teardown. */
async function listWindowsClients(backend: OpsBackend | undefined): Promise<OpsVm[]> {
  try {
    const status = await opsExecutorService.runOpsJSON<{ vms?: OpsVm[] }>('status', [], {
      backend,
    });
    return (status.vms ?? []).filter((vm) => vm.role === WINDOWS_CLIENT_ROLE);
  } catch {
    return [];
  }
}

export function registerOpsDownCommand(ops: Command, _program: Command): void {
  ops
    .command('down')
    .summary(t('commands.ops.down.descriptionShort'))
    .description(t('commands.ops.down.description'))
    .addOption(
      new Option('--backend <backend>', t('options.opsBackend')).choices(OPS_BACKEND_CHOICES)
    )
    .option('--debug', t('options.debug'))
    .action(async (options: { backend?: string; debug?: boolean }) => {
      try {
        const backend = options.backend ? (options.backend as OpsBackend) : undefined;
        const windowsClients = await listWindowsClients(backend);
        if (windowsClients.length > 0) {
          outputService.info(
            t('commands.ops.down.windowsClients', {
              vms: windowsClients.map((vm) => `${vm.name} (${vm.ip})`).join(', '),
            })
          );
        }
        outputService.info(t('commands.ops.down.starting'));

        const exitCode = await opsExecutorService.runOpsStreaming('down', [], {
          backend,
          debug: options.debug,
        });

        if (exitCode === 0) {
          outputService.success(t('commands.ops.down.completed'));
        } else {
          outputService.error(t('commands.ops.down.failed'));
          setExitCode(exitCode);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
