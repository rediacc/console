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
  const mounted = await probeRepoMounted(repoGuid, machineName, options);
  if (mounted === false) {
    throw new ValidationError(
      t('errors.repoNotDeployed', { repository: repoName, machine: machineName })
    );
  }
}

/**
 * Probe whether `repoGuid` is mounted on `machineName`.
 *
 * Returns `undefined` when the probe itself fails (machine unreachable,
 * renet error, parse error, cloud adapter) — callers decide the fallback.
 */
export async function probeRepoMounted(
  repoGuid: string,
  machineName: string,
  options: { debug?: boolean } = {}
): Promise<boolean | undefined> {
  const provider = await getStateProvider();
  if (provider.isCloud) return undefined;

  const result = await localExecutorService.execute({
    functionName: 'repository_list',
    machineName,
    params: {},
    captureOutput: true,
    quietSpinners: true,
    debug: options.debug,
  });

  if (!result.success || !result.stdout) return undefined;

  let repos: Record<string, unknown>[];
  try {
    repos = parseRepositoryListOutput(result.stdout);
  } catch {
    return undefined;
  }

  // renet's `list repositories --json` keys repos by GUID under `name` and has no `guid` field.
  const entry = repos.find((r) => r.name === repoGuid);
  return entry?.mounted === true;
}
