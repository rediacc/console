import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config/config-resources.js';
import { getCluster } from '../../services/config/config-cluster-ops.js';
import {
  createCluster,
  destroyCluster,
  installCluster,
  scaleCluster,
} from '../../services/cluster/cluster-provision.js';
import { forkCluster, migrateCluster } from '../../services/cluster/cluster-kube.js';
import {
  fetchAndCacheKubeconfig,
  kubeconfigCachePath,
} from '../../services/cluster/kubeconfig-cache.js';
import { outputService } from '../../services/core/output.js';
import { assertCommandPolicy, CMD } from '../../utils/command-policy.js';
import { ValidationError } from '../../utils/errors.js';
import { askConfirm } from '../../utils/prompt.js';

interface DebugOpt {
  debug?: boolean;
}

function registerCreate(cluster: Command): void {
  cluster
    .command('create')
    .summary(t('commands.cluster.create.descriptionShort'))
    .description(t('commands.cluster.create.description'))
    .requiredOption('--name <name>', t('commands.cluster.create.nameOption'))
    .option('--ssh-user <user>', t('commands.cluster.create.sshUserOption'))
    .option('--base-domain <domain>', t('commands.cluster.create.baseDomainOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; sshUser?: string; baseDomain?: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_CREATE, undefined, options.name);
      await createCluster(options.name, {
        sshUser: options.sshUser,
        baseDomain: options.baseDomain,
        debug: options.debug,
      });
    });
}

function registerStatus(cluster: Command): void {
  cluster
    .command('status')
    .summary(t('commands.cluster.status.descriptionShort'))
    .description(t('commands.cluster.status.description'))
    .option('--name <name>', t('commands.cluster.status.nameOption'))
    .option('--output <format>', t('options.outputFormat'))
    .action(async (options: { name?: string; output?: string }) => {
      if (options.name) {
        const config = await getCluster(options.name);
        outputService.print(JSON.stringify({ name: options.name, ...config }, null, 2));
        return;
      }
      const clusters = await configService.listClusters();
      if (options.output === 'json') {
        outputService.print(JSON.stringify(clusters, null, 2));
        return;
      }
      if (clusters.length === 0) {
        outputService.info(t('commands.cluster.status.none'));
        return;
      }
      for (const c of clusters) {
        const pools = c.config.pools.map((p) => `${p.name}(${p.role}x${p.count})`).join(', ');
        outputService.print(`${c.name}  [${c.config.provider}]  ${pools}`);
      }
    });
}

function registerScale(cluster: Command): void {
  cluster
    .command('scale')
    .summary(t('commands.cluster.scale.descriptionShort'))
    .description(t('commands.cluster.scale.description'))
    .requiredOption('--name <name>', t('commands.cluster.scale.nameOption'))
    .requiredOption('--pool <pool>', t('commands.cluster.scale.poolOption'))
    .requiredOption('--count <n>', t('commands.cluster.scale.countOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; pool: string; count: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_SCALE, undefined, options.name);
      const count = Number.parseInt(options.count, 10);
      if (!Number.isInteger(count) || count < 0) {
        throw new ValidationError(t('errors.cluster.countInvalid'));
      }
      await scaleCluster(options.name, { pool: options.pool, count, debug: options.debug });
    });
}

function registerInstall(cluster: Command): void {
  cluster
    .command('install')
    .summary(t('commands.cluster.install.descriptionShort'))
    .description(t('commands.cluster.install.description'))
    .requiredOption('--name <name>', t('commands.cluster.install.nameOption'))
    .action(async (options: { name: string }) => {
      await assertCommandPolicy(CMD.CLUSTER_INSTALL, undefined, options.name);
      await installCluster(options.name);
    });
}

function registerDestroy(cluster: Command): void {
  cluster
    .command('destroy')
    .summary(t('commands.cluster.destroy.descriptionShort'))
    .description(t('commands.cluster.destroy.description'))
    .requiredOption('--name <name>', t('commands.cluster.destroy.nameOption'))
    .option('--force', t('commands.cluster.destroy.forceOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; force?: boolean } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_DESTROY, undefined, options.name);
      if (!options.force) {
        const confirmed = await askConfirm(
          t('commands.cluster.destroy.confirm', { name: options.name })
        );
        if (!confirmed) {
          outputService.info(t('commands.cluster.destroy.aborted'));
          return;
        }
      }
      await destroyCluster(options.name, { force: options.force, debug: options.debug });
    });
}

function registerKubeconfig(cluster: Command): void {
  cluster
    .command('kubeconfig')
    .summary(t('commands.cluster.kubeconfig.descriptionShort'))
    .description(t('commands.cluster.kubeconfig.description'))
    .requiredOption('--name <name>', t('commands.cluster.kubeconfig.nameOption'))
    .action(async (options: { name: string }) => {
      const path = await fetchAndCacheKubeconfig(options.name);
      outputService.success(t('commands.cluster.kubeconfig.cached', { path }));
      outputService.print(`export KUBECONFIG=${kubeconfigCachePath(options.name)}`);
    });
}

function registerForkMigrate(cluster: Command): void {
  cluster
    .command('fork')
    .summary(t('commands.cluster.fork.descriptionShort'))
    .description(t('commands.cluster.fork.description'))
    .requiredOption('--name <name>', t('commands.cluster.fork.nameOption'))
    .requiredOption('--tag <tag>', t('commands.cluster.fork.tagOption'))
    .option('--cluster <dest>', t('commands.cluster.fork.clusterOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; tag: string; cluster?: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_FORK, undefined, options.name);
      await forkCluster(options.name, {
        tag: options.tag,
        cluster: options.cluster,
        debug: options.debug,
      });
    });

  cluster
    .command('migrate')
    .summary(t('commands.cluster.migrate.descriptionShort'))
    .description(t('commands.cluster.migrate.description'))
    .requiredOption('--name <name>', t('commands.cluster.migrate.nameOption'))
    .requiredOption('--to <dest>', t('commands.cluster.migrate.toOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; to: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_MIGRATE, undefined, options.name);
      await migrateCluster(options.name, { to: options.to, debug: options.debug });
    });
}

export function registerClusterCommands(program: Command): void {
  const cluster = program
    .command('cluster')
    .summary(t('commands.cluster.descriptionShort'))
    .description(t('commands.cluster.description'));

  registerCreate(cluster);
  registerStatus(cluster);
  registerScale(cluster);
  registerInstall(cluster);
  registerDestroy(cluster);
  registerKubeconfig(cluster);
  registerForkMigrate(cluster);
}
