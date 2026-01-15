import { Command } from 'commander';
import { parseGetCephPools } from '@rediacc/shared/api';
import type {
  CreateCephPoolParams,
  DeleteCephPoolParams,
  GetCephPoolsParams,
  UpdateCephPoolVaultParams,
} from '@rediacc/shared/types';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerPoolCommands(ceph: Command, program: Command): void {
  const pool = ceph.command('pool').description(t('commands.ceph.pool.description'));

  // pool list
  pool
    .command('list')
    .description(t('commands.ceph.pool.list.description'))
    .option('--team <name>', t('options.team'))
    .option('--cluster <name>', t('options.cluster'))
    .action(async (options: { team?: string; cluster?: string }) => {
      try {
        await authService.requireAuth();

        const params: GetCephPoolsParams = {
          teamName: options.team,
          clusterName: options.cluster,
        };

        const apiResponse = await withSpinner(
          t('commands.ceph.pool.list.fetching'),
          () => typedApi.GetCephPools(params),
          t('commands.ceph.pool.list.success')
        );

        const pools = parseGetCephPools(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(pools, format);
      } catch (error) {
        handleError(error);
      }
    });

  // pool create
  pool
    .command('create <name>')
    .description(t('commands.ceph.pool.create.description'))
    .requiredOption('--cluster <name>', t('options.cluster'))
    .requiredOption('--team <name>', t('options.team'))
    .option('--vault <content>', t('options.vaultContent'))
    .action(async (name: string, options: { cluster: string; team: string; vault?: string }) => {
      try {
        await authService.requireAuth();

        const params: CreateCephPoolParams = {
          poolName: name,
          clusterName: options.cluster,
          teamName: options.team,
          vaultContent: options.vault,
        };

        await withSpinner(
          t('commands.ceph.pool.create.creating', { name }),
          () => typedApi.CreateCephPool(params),
          t('commands.ceph.pool.create.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // pool delete
  pool
    .command('delete <name>')
    .description(t('commands.ceph.pool.delete.description'))
    .requiredOption('--team <name>', t('options.team'))
    .option('-f, --force', t('options.force'))
    .action(async (name: string, options: { team: string; force?: boolean }) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../../utils/prompt.js');
          const confirm = await askConfirm(t('commands.ceph.pool.delete.confirm', { name }));
          if (!confirm) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        const params: DeleteCephPoolParams = {
          poolName: name,
          teamName: options.team,
        };

        await withSpinner(
          t('commands.ceph.pool.delete.deleting', { name }),
          () => typedApi.DeleteCephPool(params),
          t('commands.ceph.pool.delete.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // pool vault subcommand
  const poolVault = pool.command('vault').description(t('commands.ceph.pool.vault.description'));

  // pool vault get
  poolVault
    .command('get <name>')
    .description(t('commands.ceph.pool.vault.get.description'))
    .requiredOption('--team <name>', t('options.team'))
    .action(async (name: string, options: { team: string }) => {
      try {
        await authService.requireAuth();

        const params: GetCephPoolsParams = {
          teamName: options.team,
        };

        const apiResponse = await withSpinner(
          t('commands.ceph.pool.vault.get.fetching'),
          () => typedApi.GetCephPools(params),
          t('commands.ceph.pool.vault.get.success')
        );

        const pools = parseGetCephPools(apiResponse as never);
        const pool = pools.find((p) => p.poolName === name);

        if (!pool) {
          outputService.error(t('errors.poolNotFound', { name }));
          return;
        }

        const format = program.opts().output as OutputFormat;
        outputService.print(
          {
            poolName: pool.poolName,
            teamName: pool.teamName,
            vaultVersion: pool.vaultVersion,
            vaultContent: pool.poolVault,
          },
          format
        );
      } catch (error) {
        handleError(error);
      }
    });

  // pool vault update
  poolVault
    .command('update <name>')
    .description(t('commands.ceph.pool.vault.update.description'))
    .requiredOption('--team <name>', t('options.team'))
    .requiredOption('--vault <content>', t('options.vaultContent'))
    .requiredOption('--version <version>', t('options.vaultVersion'))
    .action(async (name: string, options: { team: string; vault: string; version: string }) => {
      try {
        await authService.requireAuth();

        const params: UpdateCephPoolVaultParams = {
          poolName: name,
          teamName: options.team,
          vaultContent: options.vault,
          vaultVersion: Number.parseInt(options.version, 10),
        };

        await withSpinner(
          t('commands.ceph.pool.vault.update.updating', { name }),
          () => typedApi.UpdateCephPoolVault(params),
          t('commands.ceph.pool.vault.update.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });
}
