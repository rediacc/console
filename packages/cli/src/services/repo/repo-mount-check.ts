import { parseRepositoryListOutput } from '../../commands/repo-list-parser.js';
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { getExecutor } from '../executor/executor-factory.js';

/**
 * Options shared by both probes.
 *
 * `datastore` is the caller's answer to "which datastore is this repo recorded
 * on" (#74). It matters because `repository_list` enumerates exactly ONE
 * datastore — there is no `--all-datastores` on it the way there is on the
 * licence verbs — so a probe that declares nothing looks only at the machine's
 * default, and a repo living on a NAMED datastore reads as absent. That is a
 * false negative in the worst direction: the mount probe files a live repo as
 * unmounted. Callers hold the repo key, so they pass
 * `recordedDatastoreMount(repoKey)`; undefined keeps the default-datastore
 * behaviour for repos that live there.
 */
export interface ProbeOptions {
  debug?: boolean;
  datastore?: string;
}

/**
 * Throw a ValidationError if `repoGuid` is not currently mounted on `machineName`.
 *
 * Probe failures (machine unreachable, renet error, parse error) are treated as
 * silent passes — preflight must never block a command for a flaky probe.
 */
export async function assertRepoMountedOnMachine(
  repoName: string,
  repoGuid: string,
  machineName: string,
  options: ProbeOptions = {}
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
 * renet error, parse error) — callers decide the fallback.
 */
export async function probeRepoMounted(
  repoGuid: string,
  machineName: string,
  options: ProbeOptions = {}
): Promise<boolean | undefined> {
  const result = await getExecutor().execute({
    functionName: 'repository_list',
    machineName,
    datastore: options.datastore,
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

/**
 * Probe whether `repoGuid`'s image is PRESENT on `machineName` (mounted or not).
 *
 * This is the step-5 derived-machine check (spec/03 §2.3): the invariant a
 * mutating verb needs is "the derived machine knows this repo's image", NOT
 * "it is mounted" — a legitimately downed repo is unmounted and `repo up` must
 * still work. So it tests `entry !== undefined`, not `entry.mounted`.
 *
 * Returns `undefined` when the probe itself fails (machine unreachable, renet
 * error, parse error) — callers fail OPEN, per the convention above.
 *
 * Honest limitation (design: derived-routing repair family, R6): With the stale
 * source image still present (pre-fix configs, --keep-source, interrupted
 * migrates), the presence probe passes on the wrong machine; it cannot detect
 * defect 1's scenario by itself. It becomes the effective config recover net
 * exactly when 2b's deletion has removed the fuel: recover restores pre-migrate
 * placement, old machine no longer has the image, probe fails closed, operator
 * is pointed at reconcile, and the amended reconcile (declared-plus-strays) or
 * the rewrite-carrying config fixes routing.
 */
export async function probeRepoPresent(
  repoGuid: string,
  machineName: string,
  options: ProbeOptions = {}
): Promise<boolean | undefined> {
  const result = await getExecutor().execute({
    functionName: 'repository_list',
    machineName,
    datastore: options.datastore,
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

  return repos.some((r) => r.name === repoGuid);
}
