import { Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import type { OpsBackend } from '../../services/executor/ops-executor.js';
import { opsExecutorService } from '../../services/executor/ops-executor.js';
import { handleError } from '../../utils/errors.js';

export function registerOpsDownCommand(ops: Command, _program: Command): void {
  ops
    .command('down')
    .description(t('commands.ops.down.description'))
    .addOption(new Option('--backend <backend>', t('options.opsBackend')).choices(['kvm', 'qemu']))
    .option('--debug', t('options.debug'))
    .action(async (options: { backend?: string; debug?: boolean }) => {
      try {
        outputService.info(t('commands.ops.down.starting'));

        const flags: string[] = [];
        if (options.debug) flags.push('--debug');

        const backend = options.backend ? (options.backend as OpsBackend) : undefined;
        const exitCode = await opsExecutorService.runOpsStreaming('down', flags, { backend });

        if (exitCode === 0) {
          outputService.success(t('commands.ops.down.completed'));
        } else {
          outputService.error(t('commands.ops.down.failed'));
          process.exitCode = exitCode;
        }
      } catch (error) {
        handleError(error);
      }
    });
}
