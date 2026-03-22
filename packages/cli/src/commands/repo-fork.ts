/**
 * Fork command implementation.
 * Extracted from repo-extended.ts to keep file size within limits.
 */
import { randomUUID } from 'node:crypto';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import {
  localExecutorService,
  type LocalExecuteResult,
  type RenetEvent,
} from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { generateSSHKeyPair } from '../utils/ssh-keygen.js';
import { formatStepDuration, getActiveLabel, getDoneLabel } from '../utils/timeline.js';

/** Log total step duration and mark timeline as rendered. */
function renderTimelineTotal(steps: { duration_ms: number }[]): void {
  const totalMs = steps.reduce((sum, s) => sum + s.duration_ms, 0);
  process.stdout.write(`\nTotal: ${formatStepDuration(totalMs)}\n`);
  outputService.setTimelineRendered();
}

/** Handle a log event: only show errors/warnings. */
function handleLogEvent(event: RenetEvent): void {
  if (event.level === 'error' || event.level === 'fatal' || event.level === 'warning') {
    process.stderr.write(`  ${event.msg ?? ''}\n`);
  }
}

/** Handle a step_done event: render and record the step. */
function handleStepDoneEvent(
  event: RenetEvent,
  allSteps: { name: string; duration_ms: number; detail?: string }[]
): void {
  if (!event.name || event.duration_ms === undefined) return;
  const label = getDoneLabel(event.name);
  const detail = event.detail ? ` (${event.detail})` : '';
  process.stdout.write(`\r✔ ${label}${detail} (${formatStepDuration(event.duration_ms)})\n`);
  allSteps.push({ name: event.name, duration_ms: event.duration_ms, detail: event.detail });
}

/** Create an event handler for streaming renet events during fork --up. */
function createForkEventHandler(
  allSteps: { name: string; duration_ms: number; detail?: string }[]
): (event: RenetEvent) => void {
  return (event: RenetEvent) => {
    switch (event.type) {
      case 'log':
        handleLogEvent(event);
        break;
      case 'step_start':
        process.stdout.write(`⠋ ${getActiveLabel(event.name ?? '')}...`);
        break;
      case 'step_done':
        handleStepDoneEvent(event, allSteps);
        break;
      case 'output':
        if (
          event.msg &&
          (event.msg.includes('✔') || event.msg.includes('✗') || event.msg.includes('Error'))
        ) {
          process.stdout.write(`  ${event.msg}`);
        }
        break;
    }
  };
}

/** Chain mount + up after a successful fork. */
async function chainForkUp(
  forkKey: string,
  grandGuid: string,
  result: LocalExecuteResult,
  options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }
): Promise<void> {
  const allSteps: { name: string; duration_ms: number; detail?: string }[] = [
    ...(result.allSteps ?? result.steps ?? []),
  ];

  const upResult = await localExecutorService.execute({
    functionName: 'repository_up',
    machineName: options.machine,
    params: { repository: forkKey, mount: true, grand: grandGuid },
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    eventsMode: true,
    quietSpinners: true,
    onEvent: createForkEventHandler(allSteps),
  });

  if (!upResult.success) {
    renderLocalExecutionFailure(upResult, t('commands.repo.up.failed'));
  }

  if (allSteps.length > 0) {
    renderTimelineTotal(allSteps);
  }
}

/** Rollback a fork registration if it exists. */
async function rollbackFork(forkKey: string): Promise<void> {
  const exists = await configService.getRepository(forkKey);
  if (exists) {
    await configService.removeRepository(forkKey);
    outputService.warn(t('commands.repo.fork.rollback', { repository: forkKey }));
  }
}

/** Validate and register a new fork in the config. Returns the new GUID and networkId. */
async function registerFork(
  parent: string,
  forkKey: string,
  tagName: string,
  machineName: string,
  parentConfig: NonNullable<Awaited<ReturnType<typeof configService.getRepository>>>
): Promise<{ repositoryGuid: string; networkId: number }> {
  const existing = await configService.getRepository(forkKey);
  if (existing) {
    throw new Error(t('commands.repo.fork.alreadyExists', { name: forkKey }));
  }

  const repositoryGuid = randomUUID();
  const networkId = await configService.allocateNetworkId();
  const { privateKey: sshPrivateKey, publicKey: sshPublicKey } = generateSSHKeyPair();

  await configService.addRepository(forkKey, {
    repositoryGuid,
    tag: tagName,
    credential: parentConfig.credential,
    networkId,
    grandGuid: parentConfig.grandGuid ?? parentConfig.repositoryGuid,
    parentGuid: parentConfig.repositoryGuid,
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

/** Handle the fork action body. */
export async function handleForkAction(
  parent: string,
  tagName: string,
  options: {
    machine: string;
    checkpoint?: boolean;
    up?: boolean;
    debug?: boolean;
    skipRouterRestart?: boolean;
  }
): Promise<void> {
  const { parseRepoRef, compositeKey } = await import('../utils/config-schema.js');
  const forkKey = compositeKey(parseRepoRef(parent).name, tagName);
  try {
    const parentConfig = await configService.getRepository(parent);
    if (!parentConfig) {
      throw new Error(`Repository "${parent}" not found in context`);
    }

    const { repositoryGuid, networkId } = await registerFork(
      parent,
      forkKey,
      tagName,
      options.machine,
      parentConfig
    );

    await deployRepoKeyIfNeeded(forkKey, options.machine);

    const result = await localExecutorService.execute({
      functionName: 'repository_fork',
      machineName: options.machine,
      params: {
        repository: parent,
        tag: repositoryGuid,
        network_id: networkId,
        ...(options.checkpoint ? { checkpoint: true } : {}),
      },
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
    });

    if (!result.success) {
      await configService.removeRepository(forkKey);
      outputService.warn(t('commands.repo.fork.rollback', { repository: forkKey }));
      renderLocalExecutionFailure(result, t('commands.repo.fork.failed'));
      return;
    }

    if (options.up) {
      const grandGuid = parentConfig.grandGuid ?? parentConfig.repositoryGuid;
      await chainForkUp(forkKey, grandGuid, result, options);
    } else if (result.allSteps && result.allSteps.length > 0) {
      renderTimelineTotal(result.allSteps);
    } else {
      outputService.success(
        t('commands.repo.fork.completed', { repository: forkKey, machine: options.machine })
      );
    }
  } catch (error) {
    await rollbackFork(forkKey);
    handleError(error);
  }
}
