/**
 * Shared repository function executor.
 * Validates repo, executes via localExecutorService, renders unified timeline.
 */
import { t } from '../i18n/index.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { type ExecuteResult, getExecutor } from '../services/executor/executor-factory.js';
import { renderLocalExecutionFailure } from './local-execution-failures.js';
import { formatStepDuration } from './timeline.js';

export interface RepoFunctionMessages {
  starting: string;
  completed: string;
  failed: string;
}

/**
 * The mount path of the datastore a repo is RECORDED on, or undefined when it lives
 * on a machine's implicit default (#74).
 *
 * renet resolves a repo's datastore from the MACHINE VAULT (`p.Datastore()`), never
 * from the params bag, so a caller that says nothing gets the machine's default
 * docker datastore. Every verb in this family said nothing, so every one of them
 * dispatched against a datastore the repo does not live on while the config recorded
 * the right one: the config and the machine described two different places, silently.
 *
 * Deriving it HERE, once, is the point. The alternative — asking each of up, down,
 * status, validate, ownership, template and every future verb to remember to declare
 * it — is the obligation they had already all forgotten. A verb cannot forget what it
 * does not have to do.
 *
 * Placement lives on the repo FAMILY, not the per-tag record, so a fork resolves to
 * its parent's datastore, which is exactly where its reflinked data is.
 *
 * Exported for `repo fork`, which does NOT flow through executeRepoFunction below:
 * it drives the executor directly (two legs, streamed events, a shared lease), so
 * it was the one verb this derivation could not reach.
 */
export async function recordedDatastoreMount(repoKey: string): Promise<string | undefined> {
  const family = repoKey.split(':')[0];
  const config = await configService.getCurrent();
  const placement = config?.resources?.repositories?.[family]?.placement;
  if (!placement || !('datastore' in placement)) return undefined;
  return namedDatastoreMount(placement.datastore);
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
  options: {
    debug?: boolean;
    skipRouterRestart?: boolean;
    kubeCluster?: string;
    /**
     * Capture the verb's stdout into `result.stdout` instead of letting the
     * step detector drop it. Needed by verbs whose OUTPUT IS THE ANSWER: the
     * default handler keeps step events and discards every other line, which
     * is right for `repo up`/`fork`/`push` and wrong for `backup verify`,
     * whose verdict vanished entirely (exit 0, empty stdout, in both text and
     * json modes) while renet was reporting {"status":"verified",...}.
     */
    captureOutput?: boolean;
  },
  messages: RepoFunctionMessages
): Promise<ExecuteResult> {
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

  const result = await getExecutor().execute({
    functionName,
    machineName,
    kubeCluster: options.kubeCluster,
    // #74: declare the datastore the repo is RECORDED on. Undefined for a
    // {machine} placement, which correctly leaves the machine's own default in place.
    datastore: await recordedDatastoreMount(repoName),
    params: { repository: repoName, ...params },
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    captureOutput: options.captureOutput,
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
