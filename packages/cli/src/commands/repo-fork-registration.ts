/**
 * The registration half of `repo fork`: the config row and repo key a fork creates before its job
 * runs, and the rollback that removes them (split out of repo-fork.ts to keep it within the file
 * size budget). Importing this module binds the `rollbackFork` step handler.
 */

import { randomUUID } from 'node:crypto';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { targetFloor } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { servedRecordGuid } from '../services/jobs/attach.js';
import { bindStepHandler } from '../services/jobs/steps.js';
import { removeRepoKeyIfDeployed } from '../services/repo/repo-key-deployment.js';
import { ValidationError } from '../utils/errors.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';
import { recordTimelineStep, type TimelineStep } from '../utils/timeline.js';

/** Where a fork's repo key was put, recorded BEFORE the deploy so a failure in the deploy itself is cleaned up too. */
export interface ForkKeyState {
  machine?: string;
  guid?: string;
  /** The fork job exists on the machine (it answered, or recording its dispatch failed): the registration and key stay. */
  jobStarted?: boolean;
}

/** Remove the fork's authorized_keys line when this invocation attempted to deploy it; best-effort. */
async function removeDeployedForkKey(forkKey: string, keyState: ForkKeyState): Promise<void> {
  if (keyState.machine === undefined || keyState.guid === undefined) return;
  await removeRepoKeyIfDeployed(forkKey, keyState.machine, keyState.guid);
}

/**
 * Rollback a fork registration if it is still the one this fork made, and the repo key it deployed. The GUID is the
 * identity: a same-named fork registered since the failure (the step can run after a later command) is left alone.
 */
export async function rollbackFork(
  forkKey: string,
  keyState: ForkKeyState,
  guid: string
): Promise<void> {
  const exists = await configService.getRepository(forkKey);
  if (exists?.repositoryGuid === guid) {
    await configService.removeRepository(forkKey);
    outputService.warn(t('commands.repo.fork.rollback', { repository: forkKey }));
  }
  await removeDeployedForkKey(forkKey, keyState);
}

/** The fork image exists once its reflink or clone step completed: a failure after it is an up-phase failure. */
const FORK_IMAGE_STEPS = ['cow_reflink', 'cow_clone'] as const;

bindStepHandler('rollbackFork', async ({ params, markers }) => {
  const text = (key: string) =>
    typeof params[key] === 'string' && params[key] !== '' ? String(params[key]) : undefined;
  const repo = text('repo');
  const guid = text('guid');
  if (repo === undefined) throw new Error('step param "repo" is missing');
  if (guid === undefined) throw new Error('step param "guid" is missing');
  // A compound --up failure can happen AFTER the remote fork exists (mount, compose, readiness); rolling back the local registration then would orphan a live remote repo. An observer that did not see the stream from its start cannot tell, so it keeps the registration too.
  if (
    markers === undefined ||
    markers.some((m) => (FORK_IMAGE_STEPS as readonly string[]).includes(m))
  ) {
    outputService.warn(
      `Fork "${repo}" may exist on the machine; keeping the local registration. ` +
        `Retry with: rdc repo up ${repo}${text('machine') ? ` -m ${text('machine')}` : ''}`
    );
    return;
  }
  await rollbackFork(repo, { machine: text('machine'), guid }, guid);
});

/** Validate and register a new fork in the config. Returns the new GUID and networkId. */
export async function registerFork(
  parent: string,
  forkKey: string,
  tagName: string,
  machineName: string,
  parentConfig: NonNullable<Awaited<ReturnType<typeof configService.getRepository>>>,
  immutable: boolean,
  timeline: TimelineStep[]
): Promise<{ repositoryGuid: string; networkId: number; reattached?: true }> {
  const existing = await configService.getRepository(forkKey);
  // A POST retried with the same body id, machine and immutability finds the row its first attempt registered (the guid derives from all three): attach to it, so the fork job dedupes on the request id instead of the retry failing as a duplicate. The same id asking for another machine or immutability is a different request, and a row with no network ID cannot run a fork, so both meet the duplicate error.
  const servedGuid = servedRecordGuid(`fork:${forkKey}@${machineName}:${String(immutable)}`);
  const existingNetworkId = existing?.networkId ?? 0;
  if (
    existing?.repositoryGuid === servedGuid &&
    servedGuid !== undefined &&
    existingNetworkId > 0
  ) {
    return {
      repositoryGuid: servedGuid,
      networkId: existingNetworkId,
      reattached: true,
    };
  }
  if (existing) {
    // Exit 2 (INVALID_ARGUMENTS): the requested fork tag is already taken.
    throw new ValidationError(t('commands.repo.fork.alreadyExists', { name: forkKey }));
  }

  const repositoryGuid = servedGuid ?? randomUUID();
  // D3(a): the floor is the fork machine's used set, so a lagging counter skips IDs other devices placed there.
  // The floor read is a whole `network_used` session on the machine (connect, renet check, verify), so it is timed.
  const floor = await recordTimelineStep(timeline, 'network_floor', () =>
    targetFloor({ machine: machineName })
  );
  const networkId = await configService.allocateNetworkId({ floor });
  const { privateKey: sshPrivateKey, publicKey: sshPublicKey } = generateSSHKeyPair();

  await configService.addRepository(forkKey, {
    repositoryGuid,
    tag: tagName,
    credential: parentConfig.credential,
    networkId,
    grandGuid: parentConfig.grandGuid ?? parentConfig.repositoryGuid,
    parentGuid: parentConfig.repositoryGuid,
    ...(immutable ? { immutable: true } : {}),
    sshPrivateKey,
    sshPublicKey,
  });

  outputService.info(
    t('commands.repo.fork.registered', {
      repository: forkKey,
      guid: repositoryGuid.slice(0, 8),
      networkId,
    })
  );
  outputService.info(
    t('commands.repo.fork.starting', { parent, repository: forkKey, machine: machineName })
  );

  return { repositoryGuid, networkId };
}
