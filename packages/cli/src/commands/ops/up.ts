import { Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import type { OpsBackend } from '../../services/executor/ops-executor.js';
import { opsExecutorService } from '../../services/executor/ops-executor.js';
import { handleError } from '../../utils/errors.js';
import { OPS_BACKEND_CHOICES } from './backends.js';

/** Normalizes `31,32` to the comma list renet reads from VM_WINDOWS; the id range rule itself is renet's. */
export function parseWindowsIds(raw: string): string {
  const ids = raw.split(',').map((part) => part.trim());
  if (ids.some((id) => !/^\d+$/.test(id))) {
    throw new Error(t('commands.ops.up.windowsInvalid', { value: raw }));
  }
  return ids.join(',');
}

/** renet reads the Windows client ids from VM_WINDOWS; the spawn inherits process.env, so it is set for the run only. */
async function withWindowsEnv(
  ids: string | undefined,
  run: () => Promise<number>
): Promise<number> {
  if (!ids) return run();
  const prior = process.env.VM_WINDOWS;
  process.env.VM_WINDOWS = ids;
  try {
    return await run();
  } finally {
    if (prior === undefined) delete process.env.VM_WINDOWS;
    else process.env.VM_WINDOWS = prior;
  }
}

export function registerOpsUpCommand(ops: Command, _program: Command): void {
  ops
    .command('up')
    .summary(t('commands.ops.up.descriptionShort'))
    .description(t('commands.ops.up.description'))
    .option('--force', t('options.opsForce'))
    .option('--parallel', t('options.opsParallel'))
    .option('--basic', t('options.opsBasic'))
    .option('--lite', t('options.opsLite'))
    .option('--skip-orchestration', t('options.opsSkipOrchestration'))
    .addOption(
      new Option('--backend <backend>', t('options.opsBackend')).choices(OPS_BACKEND_CHOICES)
    )
    .option('--os <name>', t('options.opsOS'))
    .option('--windows <ids>', t('options.opsWindows'))
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
        windows?: string;
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
          ];
          const flags = booleanFlags.filter(([v]) => v).map(([, f]) => f);
          if (options.os) flags.push('--os', options.os);

          const windowsIds = options.windows ? parseWindowsIds(options.windows) : undefined;

          const backend = options.backend ? (options.backend as OpsBackend) : undefined;
          const exitCode = await withWindowsEnv(windowsIds, () =>
            opsExecutorService.runOpsStreaming('up', flags, { backend, debug: options.debug })
          );

          if (exitCode === 0) {
            outputService.success(t('commands.ops.up.completed'));
          } else {
            outputService.error(t('commands.ops.up.failed'));
            setExitCode(exitCode);
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}
