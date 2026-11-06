/**
 * `repo delete` of a repository whose machine is gone from the config (#80f7476a).
 *
 * After `machine deprovision` (or `machine remove`) the repo's placement still names the machine,
 * and every machine-side step refused with `Machine "<name>" not found`: the entry could be neither
 * deleted nor archived. Nothing can reach the image any more, so the delete is config-only: the
 * entry is ARCHIVED (its GUID and credential kept, restorable, and purged after the prune grace)
 * rather than dropped, because a repository's cloud backups restore only with that credential.
 */

import { t } from '../i18n/index.js';
import { parseRef } from '../services/addressing/ref-parser.js';
import { placementViewFromConfig, resolveMachine } from '../services/addressing/resolve-machine.js';
import { configService } from '../services/config/config-resources.js';
import { machineExists } from '../services/config/machine-gone-repos.js';
import { outputService } from '../services/core/output.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { isFork, settleCloudBackups, settleRepoLicense } from './repo-delete-settle.js';

/**
 * The machine `ref`'s placement names when the config no longer has it; undefined when the machine
 * exists or the placement cannot be read (the machine-side path then reports that as before).
 */
export async function goneMachineOf(ref: string): Promise<string | undefined> {
  const config = await configService.getCurrent();
  if (!config) return undefined;
  let machine: string;
  try {
    ({ machine } = await resolveMachine(ref, placementViewFromConfig(config), { readOnly: true }));
  } catch {
    return undefined;
  }
  return machineExists(config, machine) ? undefined : machine;
}

/** Archive the config entry of `ref`, whose machine `machine` is gone, and say what was removed. */
export async function deleteOnGoneMachine(
  ref: string,
  machine: string,
  options: { purgeBackups?: boolean; yes?: boolean; dryRun?: boolean }
): Promise<void> {
  const parsed = parseRef(ref);
  const repoKey = parsed.tag ? `${parsed.name}:${parsed.tag}` : parsed.name;
  const { key: target, config: repoConfig } = await configService.resolveDestructiveTarget(repoKey);
  await assertCommandPolicy(CMD.REPO_DELETE, target);
  if (options.purgeBackups && isFork(repoConfig)) {
    throw new ValidationError(t('commands.repo.delete.purgeForkRefused', { repository: target }));
  }

  if (options.dryRun) {
    outputService.print(
      {
        dryRun: true,
        repository: target,
        machine,
        machineGone: true,
        guid: repoConfig.repositoryGuid,
        archiveConfig: true,
        purgeBackups: !!options.purgeBackups,
      },
      getOutputFormat()
    );
    return;
  }

  if (!options.yes) {
    const { askConfirm } = await import('../utils/prompt.js');
    const confirmed = await askConfirm(
      t('commands.repo.delete.confirmMachineGone', { repository: target, machine })
    );
    if (!confirmed) {
      outputService.info(t('status.cancelled'));
      return;
    }
  }

  await configService.archiveRepository(target);
  outputService.info(
    t('commands.repo.delete.machineGoneArchived', { repository: target, machine })
  );
  outputService.info(t('commands.repo.delete.restoreHint', { guid: repoConfig.repositoryGuid }));
  await settleCloudBackups(target, repoConfig, !!options.purgeBackups);
  await settleRepoLicense(target, repoConfig);
}
