/**
 * `rdc repo canary`, release-ladder rung 2 (spec 05 §2) as MANAGED STATE on the
 * repo (R2-F17 / spec §4.4): exactly ONE canary per repo, so every leaf is keyed
 * by the repo REF and the canary's name is derived from it. Every release-class
 * mutation first takes the rung-0 group snapshot (universal undo). Orchestration
 * lives in services/cluster/repo-release.ts.
 *
 * `canary` is a PURE GROUP (no bare action): `create` is a real subcommand. That
 * is what dissolves bug #37, an actionable parent binds its own options even
 * when they trail a subcommand, which is why the old bare form had to spell its
 * weight `--initial-weight` to keep out of `canary weight`'s way. With no parent
 * options left there is no collision to carry, and the flag is `--weight` again.
 */

import type { CanarySet } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { controlDatastoreMount } from '../services/cluster/cluster-kube.js';
import { resolveExecutionTarget } from '../services/cluster/cluster-target.js';
import {
  canarySetNameFor,
  getCanaryForRepo,
  listCanaries,
  renderCanaryOverlay,
} from '../services/cluster/repo-release.js';
import { dispatch } from '../services/cluster/repo-replicate.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { jsonParam, str } from '../services/jobs/steps-support.js';
import { notFound } from '../utils/cli-exit-error.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRepoRef } from '../utils/repo-target.js';

function assertWeight(weight: number): void {
  if (!Number.isInteger(weight) || weight < 0 || weight > 100) {
    throw new Error(`--weight must be an integer 0..100, got "${weight}".`);
  }
}

/**
 * Rung 0 is the job: the release-undo GROUP snapshot of the cluster's datastores, taken on the control machine. The
 * overlay apply and the record of the managed set are the `recordCanary` step, so a ticket handed back early records
 * a canary only once its overlay is live, and an apply that fails leaves nothing recorded. Both `canary create` and
 * `canary weight` run this shape; `set` is the canary the step applies and records.
 */
async function runCanaryRelease(
  verb: 'repo canary create' | 'repo canary weight',
  set: CanarySet,
  setName: string,
  control: string,
  debug: boolean | undefined
): Promise<void> {
  outputService.info(`  rung 0: group snapshot ${set.undoSnapshot} of cluster "${set.cluster}"...`);
  const outcome = await runCommandJob(
    verb,
    {
      functionName: 'datastore_snapshot_create',
      machineName: control,
      params: { group: set.cluster, snapshot: set.undoSnapshot },
      debug,
    },
    [planStep('recordCanary', { set: setName, canary: JSON.stringify(set) })]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(
      outcome.result,
      `Replica step "datastore_snapshot_create" failed on ${control}: ${outcome.result.error ?? 'unknown error'}`
    );
  }
}

/** The `recordCanary` step: render and apply the overlay through the control node, then record the managed set. */
bindStepHandler('recordCanary', async ({ machine, params }) => {
  const setName = str(params, 'set');
  const set = jsonParam<CanarySet>(params, 'canary');
  await dispatch('kube_apply', machine, {
    mount_path: controlDatastoreMount(set.cluster),
    namespace: set.repo,
    manifest: renderCanaryOverlay({
      repo: set.repo,
      service: set.service,
      image: set.image,
      port: set.port,
      weight: set.weight,
      replicas: set.replicas,
    }),
    name: `canary-${setName}.yaml`,
    cluster: set.cluster,
  });
  await configService.setStateBucket('canaries', { ...(await listCanaries()), [setName]: set });
  outputService.success(
    set.updatedAt
      ? `Canary "${setName}" weight -> ${set.weight}% (router applies it on its refresh tick).`
      : `Canary "${setName}" live at ${set.weight}% on SHARED data (expand-contract schema discipline is the app's burden). Flip: "rdc repo canary weight ${set.repo} --weight <n>"; undo snapshot: ${set.undoSnapshot}.`
  );
});

/** The `forgetCanary` step: the overlay is gone, so the managed set is forgotten. */
bindStepHandler('forgetCanary', async ({ params }) => {
  const setName = str(params, 'set');
  const { [setName]: _gone, ...rest } = await listCanaries();
  await configService.setStateBucket('canaries', rest);
  outputService.success(
    `Canary "${setName}" removed; the stable Service serves 100% again. Undo snapshots retained.`
  );
});

async function createCanary(options: {
  repo: string;
  cluster: string;
  image: string;
  port: number;
  weight: number;
  service?: string;
  replicas?: number;
  debug?: boolean;
}): Promise<void> {
  assertWeight(options.weight);
  const setName = canarySetNameFor(options.repo);
  if (await getCanaryForRepo(options.repo)) {
    throw new Error(
      `Repository "${options.repo}" already has a canary. Change its split with ` +
        `"rdc repo canary weight ${options.repo} --weight <n>", or remove it first.`
    );
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: options.cluster });
  const now = Date.now();
  const set: CanarySet = {
    repo: options.repo,
    cluster: options.cluster,
    service: options.service ?? options.repo,
    image: options.image,
    port: options.port,
    replicas: options.replicas ?? 1,
    weight: options.weight,
    undoSnapshot: `release-undo-${now}`,
    createdAt: new Date(now).toISOString(),
  };
  await runCanaryRelease('repo canary create', set, setName, control, options.debug);
}

async function setCanaryWeight(
  repoKey: string,
  weight: number,
  debug: boolean | undefined
): Promise<void> {
  assertWeight(weight);
  const setName = canarySetNameFor(repoKey);
  const set = await getCanaryForRepo(repoKey);
  if (!set) {
    throw new Error(
      `Repository "${repoKey}" has no canary. See "rdc repo canary status ${repoKey}".`
    );
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  const now = Date.now();
  const updated: CanarySet = {
    ...set,
    weight,
    undoSnapshot: `release-undo-${now}`,
    updatedAt: new Date(now).toISOString(),
  };
  await runCanaryRelease('repo canary weight', updated, setName, control, debug);
}

/** Remove a canary: delete its label-scoped overlay on the control node, then forget the state (the step). */
async function removeCanary(repoKey: string, debug: boolean | undefined): Promise<void> {
  const setName = canarySetNameFor(repoKey);
  const set = await getCanaryForRepo(repoKey);
  if (!set) {
    outputService.success(`Repository "${repoKey}" has no canary; nothing to remove.`);
    return;
  }
  const { machineName: control } = await resolveExecutionTarget({ cluster: set.cluster });
  const outcome = await runCommandJob(
    'repo canary remove',
    {
      functionName: 'kube_delete',
      machineName: control,
      params: {
        mount_path: controlDatastoreMount(set.cluster),
        namespace: set.repo,
        replica_set: setName,
      },
      debug,
    },
    [planStep('forgetCanary', { set: setName })]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(
      outcome.result,
      `remove: kube_delete on ${control} failed: ${outcome.result.error ?? 'unknown error'}`
    );
  }
}

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
