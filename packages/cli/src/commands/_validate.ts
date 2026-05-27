/**
 * Up-front existence guards for user-supplied resource names.
 * Call these at the start of any action that dispatches to renet
 * to surface clear "not found" errors before an opaque renet failure.
 */
import { configService } from '../services/config-resources.js';

/**
 * Assert that a machine exists in the current config.
 * Throws `Machine "<name>" not found. Available: …` when absent.
 */
export async function assertMachineExists(machineName: string): Promise<void> {
  await configService.getLocalMachine(machineName);
}

/**
 * Assert that a storage exists in the current config.
 * Throws a repository-hint error when the name matches a known repository,
 * otherwise rethrows the original storage-not-found error.
 */
export async function assertStorageExists(storageName: string): Promise<void> {
  try {
    await configService.getStorage(storageName);
  } catch (storageErr) {
    const base = storageName.split(':')[0];
    const repos = await configService.listRepositories().catch(() => []);
    const repoNames = new Set(repos.map((r) => r.name));
    if (repoNames.has(storageName) || repoNames.has(base) || repoNames.has(`${base}:latest`)) {
      throw new Error(
        `"${storageName}" is a repository, not a storage. To delete a repository image use: rdc repository delete --name ${base}`
      );
    }
    throw storageErr;
  }
}

/**
 * Assert that a repository exists in the current config.
 * Throws `Repository "<ref>" not found. Available: …` when absent.
 */
export async function assertRepositoryExists(repoRef: string): Promise<void> {
  const repo = await configService.getRepository(repoRef);
  if (repo === undefined) {
    const repos = await configService.listRepositories().catch(() => []);
    const available = repos.map((r) => r.name).join(', ') || 'none';
    throw new Error(`Repository "${repoRef}" not found. Available: ${available}`);
  }
}
