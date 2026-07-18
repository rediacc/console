import { type Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import {
  forkCluster,
  migrateCluster,
  rehearseCluster,
} from '../../services/cluster/cluster-fork.js';
import { evictCluster, joinCluster } from '../../services/cluster/cluster-membership.js';
import {
  createCluster,
  destroyCluster,
  scaleCluster,
} from '../../services/cluster/cluster-provision.js';
import {
  createClusterSnapshot,
  listClusterSnapshots,
} from '../../services/cluster/cluster-snapshot.js';
import {
  fetchAndCacheKubeconfig,
  kubeconfigCachePath,
} from '../../services/cluster/kubeconfig-cache.js';
import { getCluster } from '../../services/config/config-cluster-ops.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { assertCommandPolicy, CMD } from '../../utils/command-policy.js';
import { getOutputFormat, ValidationError } from '../../utils/errors.js';
import { askConfirm } from '../../utils/prompt.js';

interface DebugOpt {
  debug?: boolean;
}

function registerCreate(cluster: Command): void {
  cluster
    .command('create')
    .summary(t('commands.cluster.create.descriptionShort'))
    .description(t('commands.cluster.create.description'))
    .argument('<cluster>', t('options.clusterName'))
    // Declaration flags (absorbed from `config cluster add`, 06 §2): a bare
    // `cluster create --name X` (no --provider) provisions an ALREADY-declared
    // cluster, resuming the two-phase flow; passing --provider declares first.
    .option('--provider <provider>', t('commands.cluster.create.providerOption'))
    .option('--pool <spec...>', t('commands.cluster.create.poolOption'))
    .option('--declare-only', t('commands.cluster.create.declareOnlyOption'))
    .option('--network-cidr <cidr>', t('commands.cluster.create.cidrOption'))
    .option('--network-primitive <primitive>', t('commands.cluster.create.primitiveOption'))
    .option('--control-node <machine>', t('commands.cluster.create.controlNodeOption'))
    .option('--net-name <name>', t('commands.cluster.create.netNameOption'))
    .option('--net-base <prefix>', t('commands.cluster.create.netBaseOption'))
    .option('--net-offset <n>', t('commands.cluster.create.netOffsetOption'))
    .option('--control-id <n>', t('commands.cluster.create.controlIdOption'))
    .option('--docker-registry <endpoint>', t('commands.cluster.create.dockerRegistryOption'))
    .option('--ssh-user <user>', t('commands.cluster.create.sshUserOption'))
    .option('--base-domain <domain>', t('commands.cluster.create.baseDomainOption'))
    .option('--control-ds-size <size>', t('commands.cluster.create.controlDsSizeOption'))
    .addOption(
      new Option(
        '--control-ds-backend <backend>',
        t('commands.cluster.create.controlDsBackendOption')
      ).choices(['local', 'ceph'])
    )
    .option('--control-ds-pool <pool>', t('commands.cluster.create.controlDsPoolOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        name: string,
        options: {
          provider?: string;
          pool?: string[];
          declareOnly?: boolean;
          networkCidr?: string;
          networkPrimitive?: string;
          controlNode?: string;
          netName?: string;
          netBase?: string;
          netOffset?: string;
          controlId?: string;
          dockerRegistry?: string;
          sshUser?: string;
          baseDomain?: string;
          controlDsSize?: string;
          controlDsBackend?: string;
          controlDsPool?: string;
        } & DebugOpt
      ) => {
        await assertCommandPolicy(CMD.CLUSTER_CREATE, undefined, name);
        if (
          options.controlDsBackend &&
          options.controlDsBackend !== 'local' &&
          options.controlDsBackend !== 'ceph'
        ) {
          throw new ValidationError(t('errors.cluster.controlDsBackendInvalid'));
        }

        // Declare first when --provider/--pool are given (one-step create).
        if (options.provider) {
          if (!options.pool || options.pool.length === 0) {
            throw new ValidationError(t('errors.cluster.poolRequired'));
          }
          const { buildClusterConfig } = await import('./declare.js');
          await configService.addCluster(
            name,
            buildClusterConfig({ ...options, provider: options.provider, pool: options.pool })
          );
          outputService.success(t('commands.cluster.create.declared', { name }));
          if (options.declareOnly) return;
        } else if (options.declareOnly) {
          throw new ValidationError(t('errors.cluster.declareNeedsProvider'));
        }

        await createCluster(name, {
          sshUser: options.sshUser,
          baseDomain: options.baseDomain,
          controlDs: {
            size: options.controlDsSize,
            backend: options.controlDsBackend as 'local' | 'ceph' | undefined,
            pool: options.controlDsPool,
          },
          debug: options.debug,
        });
      }
    );
}

function registerStatus(cluster: Command): void {
  cluster
    .command('status')
    .summary(t('commands.cluster.status.descriptionShort'))
    .description(t('commands.cluster.status.description'))
    .argument('[cluster]', t('options.clusterName'))
    .action(async (name?: string) => {
      if (name) {
        const config = await getCluster(name);
        outputService.print({ name, ...config }, getOutputFormat());
        return;
      }
      const clusters = await configService.listClusters();
      if (getOutputFormat() === 'json') {
        outputService.print(clusters, 'json');
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
    .argument('<cluster>', t('options.clusterName'))
    .requiredOption('--pool <pool>', t('commands.cluster.scale.poolOption'))
    .requiredOption('--count <n>', t('commands.cluster.scale.countOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { pool: string; count: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_SCALE, undefined, name);
      // Number() (not parseInt) so "3abc" and "1.5" are rejected, not truncated.
      const count = Number(options.count);
      if (!Number.isInteger(count) || count < 0) {
        throw new ValidationError(t('errors.cluster.countInvalid'));
      }
      await scaleCluster(name, { pool: options.pool, count, debug: options.debug });
    });
}

function registerDestroy(cluster: Command): void {
  cluster
    .command('destroy')
    .summary(t('commands.cluster.destroy.descriptionShort'))
    .description(t('commands.cluster.destroy.description'))
    .argument('<cluster>', t('options.clusterName'))
    .option('--force', t('commands.cluster.destroy.forceOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { force?: boolean } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_DESTROY, undefined, name);
      if (!options.force) {
        const confirmed = await askConfirm(t('commands.cluster.destroy.confirm', { name }));
        if (!confirmed) {
          outputService.info(t('commands.cluster.destroy.aborted'));
          return;
        }
      }
      await destroyCluster(name, { force: options.force, debug: options.debug });
    });
}

function registerKubeconfig(cluster: Command): void {
  cluster
    .command('kubeconfig')
    .summary(t('commands.cluster.kubeconfig.descriptionShort'))
    .description(t('commands.cluster.kubeconfig.description'))
    .argument('<cluster>', t('options.clusterName'))
    .action(async (name: string) => {
      const path = await fetchAndCacheKubeconfig(name);
      outputService.success(t('commands.cluster.kubeconfig.cached', { path }));
      outputService.print(`export KUBECONFIG=${kubeconfigCachePath(name)}`);
    });
}

function registerForkMigrate(cluster: Command): void {
  cluster
    .command('fork')
    .summary(t('commands.cluster.fork.descriptionShort'))
    .description(t('commands.cluster.fork.description'))
    .argument('<cluster>', t('options.clusterName'))
    .requiredOption('--tag <tag>', t('commands.cluster.fork.tagOption'))
    .requiredOption('--to <dest-cluster>', t('commands.cluster.fork.toOption'))
    .addOption(
      new Option('--writes <disposition>', t('commands.cluster.fork.writesOption')).choices([
        'local',
        'ceph',
      ])
    )
    .option('--up', t('commands.cluster.fork.upOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        name: string,
        options: {
          tag: string;
          to: string;
          writes?: string;
          up?: boolean;
        } & DebugOpt
      ) => {
        await assertCommandPolicy(CMD.CLUSTER_FORK, undefined, name);
        if (options.writes && options.writes !== 'local' && options.writes !== 'ceph') {
          throw new ValidationError(t('errors.cluster.forkWritesInvalid'));
        }
        await forkCluster(name, {
          tag: options.tag,
          cluster: options.to,
          writes: options.writes as 'local' | 'ceph' | undefined,
          up: options.up,
          debug: options.debug,
        });
      }
    );

  cluster
    .command('migrate')
    .summary(t('commands.cluster.migrate.descriptionShort'))
    .description(t('commands.cluster.migrate.description'))
    .argument('<cluster>', t('options.clusterName'))
    .requiredOption('--to <dest-cluster>', t('commands.cluster.migrate.toOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { to: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_MIGRATE, undefined, name);
      await migrateCluster(name, { to: options.to, debug: options.debug });
    });

  cluster
    .command('rehearse')
    .summary(t('commands.cluster.rehearse.descriptionShort'))
    .description(t('commands.cluster.rehearse.description'))
    .argument('<cluster>', t('options.clusterName'))
    .requiredOption('--on <dest-cluster>', t('commands.cluster.rehearse.onOption'))
    .option('--tag <tag>', t('commands.cluster.rehearse.tagOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { on: string; tag?: string } & DebugOpt) => {
      // Rehearse composes a fork; gate it under the same policy as cluster fork.
      await assertCommandPolicy(CMD.CLUSTER_FORK, undefined, name);
      await rehearseCluster(name, {
        cluster: options.on,
        tag: options.tag,
        debug: options.debug,
      });
    });
}

function registerSnapshot(cluster: Command): void {
  const snapshot = cluster
    .command('snapshot')
    .summary(t('commands.cluster.snapshot.descriptionShort'))
    .description(t('commands.cluster.snapshot.description'));

  snapshot
    .command('create')
    .summary(t('commands.cluster.snapshot.create.descriptionShort'))
    .description(t('commands.cluster.snapshot.create.description'))
    .argument('<cluster>', t('options.clusterName'))
    .option('--snapshot <label>', t('commands.cluster.snapshot.create.labelOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { snapshot?: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_SNAPSHOT_CREATE, undefined, name);
      await createClusterSnapshot(name, { snapshot: options.snapshot, debug: options.debug });
    });

  snapshot
    .command('list')
    .summary(t('commands.cluster.snapshot.list.descriptionShort'))
    .description(t('commands.cluster.snapshot.list.description'))
    .argument('<cluster>', t('options.clusterName'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: DebugOpt) => {
      const snapshots = await listClusterSnapshots(name, { debug: options.debug });
      outputService.print(snapshots, getOutputFormat());
    });
}

function registerMembership(cluster: Command): void {
  cluster
    .command('join')
    .summary(t('commands.cluster.join.descriptionShort'))
    .description(t('commands.cluster.join.description'))
    .argument('<machine>', t('options.machineName'))
    .requiredOption('--cluster <name>', t('commands.cluster.join.clusterOption'))
    .option('--debug', t('options.debug'))
    .action(async (machine: string, options: { cluster: string } & DebugOpt) => {
      await assertCommandPolicy(CMD.CLUSTER_JOIN, undefined, options.cluster);
      await joinCluster(machine, { cluster: options.cluster, debug: options.debug });
    });

  cluster
    .command('evict')
    .summary(t('commands.cluster.evict.descriptionShort'))
    .description(t('commands.cluster.evict.description'))
    .argument('<machine>', t('options.machineName'))
    .option('--force', t('commands.cluster.evict.forceOption'))
    .option('--debug', t('options.debug'))
    .action(async (machine: string, options: { force?: boolean } & DebugOpt) => {
      const target = await configService.getLocalMachine(machine);
      await assertCommandPolicy(CMD.CLUSTER_EVICT, undefined, target.cluster?.cluster);
      await evictCluster(machine, { force: options.force, debug: options.debug });
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
  registerDestroy(cluster);
  registerKubeconfig(cluster);
  registerForkMigrate(cluster);
  registerSnapshot(cluster);
  registerMembership(cluster);
}
