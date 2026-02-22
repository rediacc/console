import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { opsExecutorService } from '../../services/ops-executor.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import type { OpsBackend } from '../../services/ops-executor.js';

export function registerOpsDownCommand(ops: Command, _program: Command): void {
  ops
    .command('down')
    .description(t('commands.ops.down.description'))
    .option('--backend <backend>', t('options.opsBackend'))
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
