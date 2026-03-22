/**
 * Shared repository function executor.
 * Validates repo, executes via localExecutorService, renders unified timeline.
 */
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService, type LocalExecuteResult } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { renderLocalExecutionFailure } from './local-execution-failures.js';
import { formatStepDuration } from './timeline.js';

export interface RepoFunctionMessages {
  starting: string;
  completed: string;
  failed: string;
}

/**
 * Execute a repository function on a remote machine.
 * Handles: validation, network ID, timeline rendering, error display.
 */
export async function executeRepoFunction(
  functionName: string,
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  options: { debug?: boolean; skipRouterRestart?: boolean },
  messages: RepoFunctionMessages
): Promise<LocalExecuteResult> {
  // Validate repository exists in context
  const repo = await configService.getRepository(repoName);
  if (!repo) {
    throw new Error(`Repository "${repoName}" not found in context`);
  }
  if (!repo.credential) {
    outputService.warn(t('commands.repo.noCredential', { name: repoName }));
  }

  // Ensure network_id is assigned (auto-allocates for legacy repos without one)
  await configService.ensureRepositoryNetworkId(repoName);

  outputService.info(messages.starting);

  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params: { repository: repoName, ...params },
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    // Steps are rendered in real-time by the onStdout step detector.
    // Just show "Total: Xs" at the end.
    if (result.allSteps && result.allSteps.length > 0) {
      const totalMs = result.allSteps.reduce((sum, s) => sum + s.duration_ms, 0);
      outputService.info(`\nTotal: ${formatStepDuration(totalMs)}`);
      outputService.setTimelineRendered();
    } else {
      outputService.success(messages.completed);
    }
  } else {
    renderLocalExecutionFailure(result, result.error ?? messages.failed);
  }

  return result;
}
