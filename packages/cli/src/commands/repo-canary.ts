/**
 * `rdc repo canary` — release-ladder rung 2 (spec 05 §2) as MANAGED STATE on the
 * repo (R2-F17 / spec §4.4): exactly ONE canary per repo, so every leaf is keyed
 * by the repo REF and the canary's name is derived from it. Every release-class
 * mutation first takes the rung-0 group snapshot (universal undo). Orchestration
 * lives in services/cluster/repo-release.ts.
 *
 * `canary` is a PURE GROUP (no bare action): `create` is a real subcommand. That
 * is what dissolves bug #37 — an actionable parent binds its own options even
 * when they trail a subcommand, which is why the old bare form had to spell its
 * weight `--initial-weight` to keep out of `canary weight`'s way. With no parent
 * options left there is no collision to carry, and the flag is `--weight` again.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  canarySetNameFor,
  createCanary,
  getCanaryForRepo,
  removeCanary,
  setCanaryWeight,
} from '../services/cluster/repo-release.js';
import { outputService } from '../services/core/output.js';
import { notFound } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { resolveRepoRef } from '../utils/repo-target.js';

/**
 * Resolve a ref to the cluster canary needs. A canary is a weighted traffic
 * split across two k8s Deployments; a docker-placed repo has no router to split
 * on, so refuse it here (exit 2) rather than downstream.
 */
async function resolveClusterRepo(
  ref: string,
  options: { readOnly?: boolean } = {}
): Promise<{ repoKey: string; cluster: string }> {
  const { repoKey, kubeCluster } = await resolveRepoRef(ref, options);
  if (!kubeCluster) {
    throw new ValidationError(t('errors.repo.canaryNeedsCluster', { ref: repoKey }));
  }
  return { repoKey, cluster: kubeCluster };
}

export function registerRepoCanaryCommands(repo: Command): void {
  const canary = repo
    .command('canary')
    .summary(t('commands.repo.canary.descriptionShort'))
    .description(t('commands.repo.canary.description'));

  canary
    .command('create')
    .summary(t('commands.repo.canary.create.descriptionShort'))
    .description(t('commands.repo.canary.create.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--image <image>', t('commands.repo.canary.imageOption'))
    .requiredOption('--port <port>', t('commands.repo.canary.portOption'))
    .requiredOption('--weight <percent>', t('commands.repo.canary.weightOption'))
    .option('--service <name>', t('commands.repo.canary.serviceOption'))
    .option('--replicas <n>', t('commands.repo.canary.replicasOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        ref: string,
        options: {
          image: string;
          port: string;
          weight: string;
          service?: string;
          replicas?: string;
          debug?: boolean;
        }
      ) => {
        try {
          const { repoKey, cluster } = await resolveClusterRepo(ref);
          await assertCommandPolicy(CMD.REPO_CANARY_CREATE, repoKey);
          await createCanary({
            repo: repoKey,
            cluster,
            image: options.image,
            port: Number(options.port),
            weight: Number(options.weight),
            service: options.service,
            replicas: options.replicas ? Number(options.replicas) : undefined,
            debug: options.debug,
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  canary
    .command('status')
    .summary(t('commands.repo.canary.status.descriptionShort'))
    .description(t('commands.repo.canary.status.description'))
    .argument('<ref>', t('options.repoRef'))
    .action(async (ref: string) => {
      try {
        const { repoKey } = await resolveRepoRef(ref, { readOnly: true });
        const set = await getCanaryForRepo(repoKey);
        if (!set) {
          throw notFound(`repository "${repoKey}" has no canary.`, {
            details: [
              `create one with "rdc repo canary create ${repoKey} --image <i> --port <p> --weight <n>"`,
            ],
          });
        }
        outputService.print({ [canarySetNameFor(repoKey)]: set }, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });

  canary
    .command('weight')
    .summary(t('commands.repo.canary.weight.descriptionShort'))
    .description(t('commands.repo.canary.weight.description'))
    .argument('<ref>', t('options.repoRef'))
    .requiredOption('--weight <percent>', t('commands.repo.canary.weightOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: { weight: string; debug?: boolean }) => {
      try {
        const { repoKey } = await resolveRepoRef(ref);
        await assertCommandPolicy(CMD.REPO_CANARY_WEIGHT, repoKey);
        await setCanaryWeight(repoKey, Number(options.weight), options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  canary
    .command('remove')
    .summary(t('commands.repo.canary.remove.descriptionShort'))
    .description(t('commands.repo.canary.remove.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: { debug?: boolean }) => {
      try {
        const { repoKey } = await resolveRepoRef(ref);
        await assertCommandPolicy(CMD.REPO_CANARY_REMOVE, repoKey);
        await removeCanary(repoKey, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}
