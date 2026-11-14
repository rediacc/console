/**
 * `subscription refresh --repo <ref>`, split out of subscription-actions.ts to stay within max-lines.
 */

import { t } from '../i18n/index.js';
import { refreshRepoLicenseIdentity } from '../services/account/license.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { readSSHKey } from '../services/renet/renet-execution.js';
import { ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { withSpinner } from '../utils/spinner.js';

/**
 * `subscription refresh --repo <ref>`: reissue one repo's license. The machine
 * is derived from the ref (spec/03 §2.3), so this verb never takes `-m`.
 */
export async function executeRepoLicenseRefresh(
  ref: string,
  options: { adoptOrigin?: boolean } = {}
): Promise<void> {
  const { repoKey, machineName } = await resolveRepoRef(ref, { readOnly: true });

  await withSpinner(
    t('commands.subscription.refresh.repo.refreshing'),
    async () => {
      const localConfig = await configService.getLocalConfig();
      const machine = await configService.getLocalMachine(machineName);
      const repoConfig = await configService.getRepository(repoKey);
      if (!repoConfig) {
        throw new ValidationError(
          t('commands.subscription.refresh.repo.notFound', { repoName: repoKey })
        );
      }
      const sshPrivateKey =
        localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

      // #74: declare the datastore the repo is RECORDED on. This is the only caller that passes no requestedSizeGb, so it is the one that reaches the size probe, and without this it measured the machine's default datastore for a repo that lives on a named one, found nothing, and
      // reissued at the 1 GB floor. Undefined for a {machine} placement, which
      // correctly leaves the machine's own default in place.
      const datastoreMount = await recordedDatastoreMount(repoKey);

      const refreshed = await refreshRepoLicenseIdentity(machineName, machine, sshPrivateKey, {
        repositoryGuid: repoConfig.repositoryGuid,
        grandGuid: repoConfig.grandGuid,
        kind:
          repoConfig.grandGuid && repoConfig.grandGuid !== repoConfig.repositoryGuid
            ? 'fork'
            : 'grand',
        ...(datastoreMount !== undefined && { datastoreMount }),
        ...(options.adoptOrigin === true && { adoptOrigin: true }),
      });
      if (!refreshed) {
        throw new ValidationError(t('commands.subscription.refresh.repo.failed'));
      }
    },
    t('commands.subscription.refresh.repo.refreshed')
  );

  outputService.success(t('commands.subscription.refresh.repo.success', { repoName: repoKey }));
}
