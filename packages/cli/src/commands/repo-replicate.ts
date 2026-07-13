/**
 * `rdc repo replicate` — instant read replicas (spec 05 §1) as MANAGED STATE on
 * the repo (R2-F17 / spec §4.4): there is exactly ONE replica set per repo, so
 * every leaf here is keyed by the repo REF and the set's name, snapshot and fork
 * tags are all derived from it. Orchestration lives in
 * services/cluster/repo-replicate-ops.ts.
 *
 * ★ `replicate` is an ACTIONABLE PARENT (a bare create form plus subcommands),
 * which carries two Commander traps. Both are load-bearing, so read them before
 * editing this file:
 *
 *  1. `_checkForMissingMandatoryOptions()` WALKS UP the parent chain, so a
 *     `.requiredOption()` here would fire on `replicate status <ref>` too
 *     ("required option --replicas not specified"). The create form's required
 *     flags are therefore plain `.option()`s validated in the action.
 *  2. An option declared on the parent is bound to the PARENT even when it
 *     trails a subcommand (this was bug #37). `--debug` is declared on both, so
 *     the subcommands read it through `optsWithGlobals()`, which merges the
 *     parent's parsed value back in. repo-collision.test.ts pins both.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getReplicaSetForRepo, replicaSetNameFor } from '../services/cluster/repo-replicate.js';
import {
  refreshReplicaSet,
  removeReplicaSet,
  replicateRepo,
} from '../services/cluster/repo-replicate-ops.js';
import { outputService } from '../services/core/output.js';
import { notFound } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { resolveRepoRef } from '../utils/repo-target.js';

interface CreateOptions {
  replicas?: string;
  image?: string;
  port?: string;
  pvc?: string;
  primaryApp?: string;
  headless?: boolean;
  refresh?: string;
  debug?: boolean;
}

/**
 * Resolve a ref to the cluster + datastore replicate needs. Replicate is a
 * cluster feature: a docker-placed repo has no cluster to spread replicas
 * across, and refusing here (exit 2, spec §5.4) beats a downstream kubectl
 * failure the operator cannot read.
 */
async function resolveClusterRepo(
  ref: string,
  options: { readOnly?: boolean } = {}
): Promise<{ repoKey: string; cluster: string; datastore: string }> {
  const { repoKey, kubeCluster, datastore } = await resolveRepoRef(ref, options);
  if (!kubeCluster || !datastore) {
    throw new ValidationError(t('errors.repo.replicateNeedsCluster', { ref: repoKey }));
  }
  return { repoKey, cluster: kubeCluster, datastore };
}

export function registerRepoReplicateCommands(repo: Command): void {
  const replicate = repo
    .command('replicate')
    .summary(t('commands.repo.replicate.descriptionShort'))
    .description(t('commands.repo.replicate.description'))
    .argument('<ref>', t('options.repoRef'))
    // Deliberately NOT requiredOption — see the trap note at the top of the file.
    .option('--replicas <n>', t('commands.repo.replicate.replicasOption'))
    .option('--image <image>', t('commands.repo.replicate.imageOption'))
    .option('--port <port>', t('commands.repo.replicate.portOption'))
    .option('--pvc <name>', t('commands.repo.replicate.pvcOption'))
    .option('--primary-app <label>', t('commands.repo.replicate.primaryAppOption'))
    .option('--headless', t('commands.repo.replicate.headlessOption'))
    .option('--refresh <interval>', t('commands.repo.replicate.refreshOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: CreateOptions) => {
      try {
        for (const [flag, value] of [
          ['--replicas', options.replicas],
          ['--image', options.image],
          ['--port', options.port],
        ] as const) {
          if (!value) throw new ValidationError(`${flag} is required`);
        }
        const { repoKey, cluster, datastore } = await resolveClusterRepo(ref);
        await assertCommandPolicy(CMD.REPO_REPLICATE, repoKey);
        await replicateRepo({
          repo: repoKey,
          cluster,
          datastore,
          replicas: Number(options.replicas),
          image: options.image as string,
          port: Number(options.port),
          pvc: options.pvc,
          primaryApp: options.primaryApp,
          headless: options.headless,
          refresh: options.refresh,
          debug: options.debug,
        });
      } catch (error) {
        handleError(error);
      }
    });

  replicate
    .command('status')
    .summary(t('commands.repo.replicate.status.descriptionShort'))
    .description(t('commands.repo.replicate.status.description'))
    .argument('<ref>', t('options.repoRef'))
    .action(async (ref: string) => {
      try {
        const { repoKey } = await resolveRepoRef(ref, { readOnly: true });
        const set = await getReplicaSetForRepo(repoKey);
        if (!set) {
          throw notFound(`repository "${repoKey}" has no replica set.`, {
            details: [`create one with "rdc repo replicate ${repoKey} --replicas <n>"`],
          });
        }
        outputService.print({ [replicaSetNameFor(repoKey)]: set }, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });

  replicate
    .command('remove')
    .summary(t('commands.repo.replicate.remove.descriptionShort'))
    .description(t('commands.repo.replicate.remove.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .action(async function (this: Command, ref: string) {
      try {
        const { repoKey } = await resolveRepoRef(ref);
        await assertCommandPolicy(CMD.REPO_REPLICATE_REMOVE, repoKey);
        await removeReplicaSet(repoKey, this.optsWithGlobals().debug);
      } catch (error) {
        handleError(error);
      }
    });

  replicate
    .command('refresh')
    .summary(t('commands.repo.replicate.refresh.descriptionShort'))
    .description(t('commands.repo.replicate.refresh.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .action(async function (this: Command, ref: string) {
      try {
        const { repoKey } = await resolveRepoRef(ref);
        await assertCommandPolicy(CMD.REPO_REPLICATE_REFRESH, repoKey);
        await refreshReplicaSet(repoKey, this.optsWithGlobals().debug);
      } catch (error) {
        handleError(error);
      }
    });
}
