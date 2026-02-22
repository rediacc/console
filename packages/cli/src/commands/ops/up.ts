import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { opsExecutorService } from '../../services/ops-executor.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import type { OpsBackend } from '../../services/ops-executor.js';

export function registerOpsUpCommand(ops: Command, _program: Command): void {
  ops
    .command('up')
    .description(t('commands.ops.up.description'))
    .option('--force', t('options.opsForce'))
    .option('--parallel', t('options.opsParallel'))
    .option('--basic', t('options.opsBasic'))
    .option('--lite', t('options.opsLite'))
    .option('--skip-orchestration', t('options.opsSkipOrchestration'))
    .option('--backend <backend>', t('options.opsBackend'))
    .option('--os <name>', t('options.opsOS'))
    .option('--debug', t('options.debug'))
    .action(
      async (options: {
        force?: boolean;
        parallel?: boolean;
        basic?: boolean;
        lite?: boolean;
        skipOrchestration?: boolean;
        backend?: string;
        os?: string;
        debug?: boolean;
      }) => {
        try {
          outputService.info(t('commands.ops.up.starting'));

          const booleanFlags: [boolean | undefined, string][] = [
            [options.force, '--force'],
            [options.parallel, '--parallel'],
            [options.basic, '--basic'],
            [options.lite, '--lite'],
            [options.skipOrchestration, '--skip-orchestration'],
            [options.debug, '--debug'],
          ];
          const flags = booleanFlags.filter(([v]) => v).map(([, f]) => f);
          if (options.os) flags.push('--os', options.os);

          const backend = options.backend ? (options.backend as OpsBackend) : undefined;
          const exitCode = await opsExecutorService.runOpsStreaming('up', flags, { backend });

          if (exitCode === 0) {
            outputService.success(t('commands.ops.up.completed'));
          } else {
            outputService.error(t('commands.ops.up.failed'));
            process.exitCode = exitCode;
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}
