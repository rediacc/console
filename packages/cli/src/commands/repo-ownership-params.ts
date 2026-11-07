import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { writeStdout } from '../services/core/request-context.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';

/**
 * The repository_ownership params. --dry-run and --undo only qualify --root-owned and
 * exclude each other; renet refuses the same, and refusing here saves a job.
 */
export function ownershipParams(options: {
  uid?: string;
  rootOwned?: boolean;
  dryRun?: boolean;
  undo?: boolean;
}): Record<string, unknown> {
  if (
    ((options.dryRun || options.undo) && !options.rootOwned) ||
    (options.dryRun && options.undo)
  ) {
    throw new ValidationError(t('commands.repo.admin.ownership.rootOwnedQualifiers'));
  }
  const params: Record<string, unknown> = {};
  if (options.uid) params.owner_uid = options.uid;
  if (options.rootOwned) params.root_owned = true;
  if (options.dryRun) params.dry_run = true;
  if (options.undo) params.undo = true;
  return params;
}

/**
 * The `--root-owned --dry-run` answer: renet prints each entry it would hand over, one path per line relative to the
 * mount (cmd/renet/repository_ownership.go runRootOwnedOwnership). JSON and YAML get the object, the table the list and
 * its count.
 */
export function renderRootOwnedDryRun(
  repository: string,
  machine: string,
  stdout: string | undefined
): void {
  const entries = (stdout ?? '')
    .split('\n')
    // Only a CR is dropped: a path may end in spaces, and the list must name the real file.
    .map((line) => line.replace(/\r$/, ''))
    .filter((line) => line.length > 0);
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(
      { repository, machine, dryRun: true, count: entries.length, entries },
      format
    );
    return;
  }
  if (entries.length > 0) writeStdout(`${entries.join('\n')}\n`);
  outputService.info(
    t('commands.repo.admin.ownership.rootOwnedDryRunSummary', {
      count: entries.length,
      repository,
      machine,
    })
  );
}
