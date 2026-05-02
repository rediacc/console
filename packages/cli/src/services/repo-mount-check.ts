import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { ValidationError } from '../utils/errors.js';
import { parseRepositoryListOutput } from '../commands/repo-list-parser.js';
import { localExecutorService } from './local-executor.js';

/**
 * Throw a ValidationError if `repoGuid` is not currently mounted on `machineName`.
 *
 * Probe failures (machine unreachable, renet error, parse error) are treated as
 * silent passes — preflight must never block a command for a flaky probe. The
 * cloud adapter is also a silent no-op until parity exists.
 */
export async function assertRepoMountedOnMachine(
  repoName: string,
  repoGuid: string,
  machineName: string,
  options: { debug?: boolean } = {}
): Promise<void> {
  const provider = await getStateProvider();
  if (provider.isCloud) return;

  const result = await localExecutorService.execute({
    functionName: 'repository_list',
    machineName,
    params: {},
    captureOutput: true,
    quietSpinners: true,
    debug: options.debug,
  });

  if (!result.success || !result.stdout) return;

  let repos: Record<string, unknown>[];
  try {
    repos = parseRepositoryListOutput(result.stdout);
  } catch {
    return;
  }

  const entry = repos.find((r) => r.guid === repoGuid);
  if (entry?.mounted !== true) {
    throw new ValidationError(
      t('errors.repoNotDeployed', { repository: repoName, machine: machineName })
    );
  }
}
