import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { registerCloneCommands } from './clone.js';
import { registerClusterCommands } from './cluster.js';
import { registerImageCommands } from './image.js';
import { registerPoolCommands } from './pool.js';
import { registerSnapshotCommands } from './snapshot.js';

export function registerCephCommands(program: Command): void {
  const ceph = program.command('ceph').description(t('commands.ceph.description'));

  registerClusterCommands(ceph, program);
  registerPoolCommands(ceph, program);
  registerImageCommands(ceph, program);
  registerSnapshotCommands(ceph, program);
  registerCloneCommands(ceph, program);
}
