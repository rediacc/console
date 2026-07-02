import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { createResourceCommands } from '../../utils/commandFactory.js';

export function registerCrudCommands(parentCommand: Command): Command {
  // Create standard CRUD commands using factory
  const machine = createResourceCommands(parentCommand, {
    resourceName: 'machine',
    resourceNamePlural: 'machines',
    nameField: 'machineName',
    parentOption: 'team',
    operations: {
      list: async (params) => {
        const provider = await getStateProvider();
        return provider.machines.list({ teamName: params?.teamName as string });
      },
      create: async (payload) => {
        const provider = await getStateProvider();
        return provider.machines.create(payload);
      },
      rename: async (payload) => {
        const provider = await getStateProvider();
        return provider.machines.rename(payload);
      },
      delete: async (payload) => {
        const provider = await getStateProvider();
        return provider.machines.delete(payload);
      },
    },
    createOptions: [
      { flags: '--ip <address>', description: t('options.machineIp'), required: true },
      { flags: '--user <name>', description: t('options.sshUser'), required: true },
      { flags: '--port <port>', description: t('options.sshPort') },
      { flags: '--datastore <path>', description: t('options.datastore') },
    ],
    transformCreatePayload: (name, opts) => ({
      machineName: name,
      teamName: opts.team,
      ip: opts.ip,
      user: opts.user,
      port: opts.port === undefined ? undefined : Number(opts.port),
      datastore: opts.datastore,
    }),
  });

  return machine;
}
