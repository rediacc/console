import { Command } from 'commander';
import { registerCloneCommands } from './clone.js';
import { registerClusterCommands } from './cluster.js';
import { registerPoolCommands } from './pool.js';
import { t } from '../../i18n/index.js';
import { getOrCreateCommand } from '../bridge-utils.js';
import { addCloudOnlyGuard, markCloudOnly } from '../../utils/cloud-guard.js';

export function registerCephCommands(program: Command): void {
  const ceph = getOrCreateCommand(program, 'ceph', t('commands.ceph.description'));

  // cluster and pool are cloud-only — register then guard
  registerClusterCommands(ceph, program);
  registerPoolCommands(ceph, program);

  const cluster = ceph.commands.find((c) => c.name() === 'cluster');
  if (cluster) {
    addCloudOnlyGuard(cluster);
    markCloudOnly(cluster);
  }

  const pool = ceph.commands.find((c) => c.name() === 'pool');
  if (pool) {
    addCloudOnlyGuard(pool);
    markCloudOnly(pool);
  }

  // clone: cloud-only subcommands (machines/assign/unassign) are guarded inside registerCloneCommands
  registerCloneCommands(ceph, program);
}
