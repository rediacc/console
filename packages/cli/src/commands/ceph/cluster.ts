import { parseGetCephClusterMachines, parseGetCephClusters } from '@rediacc/shared/api';
import type {
  CreateCephClusterParams,
  DeleteCephClusterParams,
  GetCephClusterMachinesParams,
  UpdateCephClusterVaultParams,
} from '@rediacc/shared/types';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { outputService } from '../../services/output.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';

export function registerClusterCommands(ceph: Command, program: Command): void {
  const cluster = ceph.command('cluster').description(t('commands.ceph.cluster.description'));

  // cluster list
  cluster
    .command('list')
    .description(t('commands.ceph.cluster.list.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.ceph.cluster.list.fetching'),
          () => typedApi.GetCephClusters({}),
          t('commands.ceph.cluster.list.success')
        );

        const clusters = parseGetCephClusters(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(clusters, format);
      } catch (error) {
        handleError(error);
      }
    });

  // cluster create
  cluster
    .command('create <name>')
    .description(t('commands.ceph.cluster.create.description'))
    .option('--vault <content>', t('options.vaultContent'))
    .action(async (name: string, options: { vault?: string }) => {
      try {
        await authService.requireAuth();

        const params: CreateCephClusterParams = {
          clusterName: name,
          vaultContent: options.vault,
        };

        await withSpinner(
          t('commands.ceph.cluster.create.creating', { name }),
          () => typedApi.CreateCephCluster(params),
          t('commands.ceph.cluster.create.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // cluster delete
  cluster
    .command('delete <name>')
    .description(t('commands.ceph.cluster.delete.description'))
    .option('-f, --force', t('options.force'))
    .action(async (name: string, options: { force?: boolean }) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../../utils/prompt.js');
          const confirm = await askConfirm(t('commands.ceph.cluster.delete.confirm', { name }));
          if (!confirm) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        const params: DeleteCephClusterParams = {
          clusterName: name,
        };

        await withSpinner(
          t('commands.ceph.cluster.delete.deleting', { name }),
          () => typedApi.DeleteCephCluster(params),
          t('commands.ceph.cluster.delete.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // cluster machines
  cluster
    .command('machines <name>')
    .description(t('commands.ceph.cluster.machines.description'))
    .action(async (name: string) => {
      try {
        await authService.requireAuth();

        const params: GetCephClusterMachinesParams = {
          clusterName: name,
        };

        const apiResponse = await withSpinner(
          t('commands.ceph.cluster.machines.fetching'),
          () => typedApi.GetCephClusterMachines(params),
          t('commands.ceph.cluster.machines.success')
        );

        const machines = parseGetCephClusterMachines(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(machines, format);
      } catch (error) {
        handleError(error);
      }
    });

  // cluster vault subcommand
  const clusterVault = cluster
    .command('vault')
    .description(t('commands.ceph.cluster.vault.description'));

  // cluster vault get
  clusterVault
    .command('get <name>')
    .description(t('commands.ceph.cluster.vault.get.description'))
    .action(async (name: string) => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.ceph.cluster.vault.get.fetching'),
          () => typedApi.GetCephClusters({}),
          t('commands.ceph.cluster.vault.get.success')
        );

        const clusters = parseGetCephClusters(apiResponse as never);
        const cluster = clusters.find((c) => c.clusterName === name);

        if (!cluster) {
          outputService.error(t('errors.clusterNotFound', { name }));
          return;
        }

        const format = program.opts().output as OutputFormat;
        outputService.print(
          {
            clusterName: cluster.clusterName,
            vaultVersion: cluster.vaultVersion,
            vaultContent: cluster.clusterVault,
          },
          format
        );
      } catch (error) {
        handleError(error);
      }
    });

  // cluster vault update
  clusterVault
    .command('update <name>')
    .description(t('commands.ceph.cluster.vault.update.description'))
    .requiredOption('--vault <content>', t('options.vaultContent'))
    .requiredOption('--version <version>', t('options.vaultVersion'))
    .action(async (name: string, options: { vault: string; version: string }) => {
      try {
        await authService.requireAuth();

        const params: UpdateCephClusterVaultParams = {
          clusterName: name,
          vaultContent: options.vault,
          vaultVersion: Number.parseInt(options.version, 10),
        };

        await withSpinner(
          t('commands.ceph.cluster.vault.update.updating', { name }),
          () => typedApi.UpdateCephClusterVault(params),
          t('commands.ceph.cluster.vault.update.success', { name })
        );
      } catch (error) {
        handleError(error);
      }
    });
}
