import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getCluster } from '../services/config/config-cluster-ops.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { ClusterConfig, ClusterPool, ClusterPoolRole } from '../types/index.js';
import { ValidationError } from '../utils/errors.js';

const ROLES = ['ceph', 'k8s-server', 'k8s-agent', 'hyperconverged'] as const;
const DEFAULT_NETWORK_PRIMITIVE = 'vlan';

/** Parse a `devicePath@sizeGB` disk spec (e.g. /dev/sdc@40) for OSD/data volumes. */
function parseDiskSpec(spec: string): { purpose: string; size: string } {
  const [purpose, size, ...rest] = spec.split('@');
  if (!purpose || !size || rest.length > 0) {
    throw new ValidationError(`Disk spec "${spec}" must be devicePath@sizeGB (e.g. /dev/sdc@40)`);
  }
  return { purpose, size };
}

/**
 * Parse a `name:role:count[:size][#devicePath@sizeGB...]` pool spec. The
 * optional `#`-separated disk suffixes declare block-storage volumes (e.g. Ceph
 * OSDs) that the cluster generator provisions and the Ceph install consumes;
 * the device path is where the volume appears in-guest (uniform across the pool).
 */
function parsePoolSpec(spec: string): ClusterPool {
  const [poolPart, ...diskParts] = spec.split('#');
  const parts = poolPart.split(':');
  if (parts.length < 3) {
    throw new ValidationError(
      `Pool spec "${spec}" must be name:role:count[:size][#devicePath@sizeGB]`
    );
  }
  const [name, role, countRaw, size] = parts;
  if (!ROLES.includes(role as ClusterPoolRole)) {
    throw new ValidationError(`Pool role "${role}" must be one of: ${ROLES.join(', ')}`);
  }
  // Number() (not parseInt) so "3abc" and "1.5" are rejected, not truncated.
  const count = Number(countRaw);
  if (!Number.isInteger(count) || count < 1) {
    throw new ValidationError(`Pool count "${countRaw}" must be a positive integer`);
  }
  const disks = diskParts.map(parseDiskSpec);
  return {
    name,
    role: role as ClusterPoolRole,
    count,
    ...(size ? { size } : {}),
    ...(disks.length > 0 ? { disks } : {}),
  };
}

interface AddOptions {
  name: string;
  provider: string;
  pool: string[];
  networkCidr?: string;
  networkPrimitive?: string;
  controlNode?: string;
  netName?: string;
  netBase?: string;
  netOffset?: string;
  controlId?: string;
  dockerRegistry?: string;
}

const DEFAULT_KVM_CONTROL_ID = 1;

/**
 * A KVM cluster boots on a libvirt network addressed by numeric VM id. Two
 * clusters sharing a host must not share a network, so the topology is required
 * rather than defaulted: a silent default would collide with the ops harness's
 * own fleet on renet11 / 192.168.111.
 */
function buildKvmConfig(options: AddOptions): ClusterConfig['kvm'] {
  if (!options.netName || !options.netBase) {
    throw new ValidationError(
      'A kvm cluster needs --net-name and --net-base (e.g. --net-name renet12 --net-base 192.168.112). ' +
        'Pick a network distinct from any other cluster or ops fleet on this host.'
    );
  }
  const controlId = options.controlId ? Number(options.controlId) : DEFAULT_KVM_CONTROL_ID;
  if (!Number.isInteger(controlId) || controlId < 1) {
    throw new ValidationError(`--control-id "${options.controlId}" must be a positive integer`);
  }
  const netOffset = options.netOffset ? Number(options.netOffset) : undefined;
  const netOffsetValid = netOffset === undefined || (Number.isInteger(netOffset) && netOffset >= 0);
  if (!netOffsetValid) {
    throw new ValidationError(`--net-offset "${options.netOffset}" must be a non-negative integer`);
  }
  return {
    netName: options.netName,
    netBase: options.netBase,
    controlId,
    ...(netOffset === undefined ? {} : { netOffset }),
    ...(options.dockerRegistry ? { dockerRegistry: options.dockerRegistry } : {}),
  };
}

function buildClusterConfig(options: AddOptions): ClusterConfig {
  const pools = options.pool.map(parsePoolSpec);
  const hasNetwork = Boolean(options.networkCidr ?? options.networkPrimitive);
  const isKvm = options.provider === 'kvm';
  return {
    provider: options.provider,
    ...(isKvm ? { kvm: buildKvmConfig(options) } : {}),
    pools,
    ...(options.controlNode ? { controlNode: options.controlNode } : {}),
    ...(hasNetwork
      ? {
          network: {
            primitive: options.networkPrimitive ?? DEFAULT_NETWORK_PRIMITIVE,
            ...(options.networkCidr ? { cidr: options.networkCidr } : {}),
          },
        }
      : {}),
  };
}

export function registerClusterConfigCommands(config: Command): void {
  const cluster = config
    .command('cluster')
    .summary(t('commands.config.cluster.descriptionShort'))
    .description(t('commands.config.cluster.description'));

  cluster
    .command('add')
    .description(t('commands.config.cluster.add.description'))
    .requiredOption('--name <name>', t('commands.config.cluster.nameOption'))
    .requiredOption('--provider <provider>', t('commands.config.cluster.providerOption'))
    .requiredOption('--pool <spec...>', t('commands.config.cluster.poolOption'))
    .option('--network-cidr <cidr>', t('commands.config.cluster.cidrOption'))
    .option('--network-primitive <primitive>', t('commands.config.cluster.primitiveOption'))
    .option('--control-node <machine>', t('commands.config.cluster.controlNodeOption'))
    .option('--net-name <name>', t('commands.config.cluster.netNameOption'))
    .option('--net-base <prefix>', t('commands.config.cluster.netBaseOption'))
    .option('--net-offset <n>', t('commands.config.cluster.netOffsetOption'))
    .option('--control-id <n>', t('commands.config.cluster.controlIdOption'))
    .option('--docker-registry <endpoint>', t('commands.config.cluster.dockerRegistryOption'))
    .action(async (options: AddOptions) => {
      await configService.addCluster(options.name, buildClusterConfig(options));
      outputService.success(t('commands.config.cluster.added', { name: options.name }));
    });

  cluster
    .command('add-pool')
    .description(t('commands.config.cluster.addPool.description'))
    .requiredOption('--name <name>', t('commands.config.cluster.nameOption'))
    .requiredOption('--pool <spec>', t('commands.config.cluster.poolOption'))
    .action(async (options: { name: string; pool: string }) => {
      const existing = await getCluster(options.name);
      const pool = parsePoolSpec(options.pool);
      if (existing.pools.some((p) => p.name === pool.name)) {
        throw new ValidationError(
          `Cluster "${options.name}" already has a pool named "${pool.name}"`
        );
      }
      await configService.updateCluster(options.name, { pools: [...existing.pools, pool] });
      outputService.success(
        t('commands.config.cluster.poolAdded', { pool: pool.name, name: options.name })
      );
    });

  cluster
    .command('list')
    .description(t('commands.config.cluster.list.description'))
    .action(async () => {
      const clusters = await configService.listClusters();
      if (clusters.length === 0) {
        outputService.info(t('commands.config.cluster.none'));
        return;
      }
      for (const c of clusters) {
        outputService.print(
          `${c.name}  [${c.config.provider}]  pools: ${c.config.pools.map((p) => p.name).join(', ')}`
        );
      }
    });

  cluster
    .command('remove')
    .description(t('commands.config.cluster.remove.description'))
    .requiredOption('--name <name>', t('commands.config.cluster.nameOption'))
    .action(async (options: { name: string }) => {
      await configService.removeCluster(options.name);
      outputService.success(t('commands.config.cluster.removed', { name: options.name }));
    });
}
