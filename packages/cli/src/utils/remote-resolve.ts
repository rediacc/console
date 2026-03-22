/**
 * Resolves a remote name to either a machine or storage from config.
 * Used by push/pull commands to unify --to/--from flags.
 */
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { ValidationError } from './errors.js';

export type RemoteType = 'machine' | 'storage';

export interface ResolvedRemote {
  type: RemoteType;
  name: string;
}

/**
 * Resolve a remote name to either a machine or storage.
 * Resolution order: machine first, then storage.
 */
export async function resolveRemoteName(name: string): Promise<ResolvedRemote> {
  try {
    await configService.getLocalMachine(name);
    return { type: 'machine', name };
  } catch {
    // Not a machine
  }

  try {
    await configService.getStorage(name);
    return { type: 'storage', name };
  } catch {
    // Not a storage
  }

  const machines = await configService.listMachines();
  const storages = await configService.listStorages();
  const machineNames = machines.map((m) => m.name).join(', ') || 'none';
  const storageNames = storages.map((s) => s.name).join(', ') || 'none';
  throw new ValidationError(
    t('errors.remoteNotFound', { name, machines: machineNames, storages: storageNames })
  );
}
