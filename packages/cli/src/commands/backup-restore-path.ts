/**
 * `rdc backup restore --at <time|snapshot> --path <file-or-dir> [--to <dir>]`: restore one
 * file or directory tree from a chunk-store snapshot, without restoring the whole image.
 * A route of `backup restore`, not a second verb, split out because backup.ts is near the
 * line cap. It runs the renet `backup_restore_path` verb, which fetches only the cells that
 * cover the path, and registers no repository record on the way.
 */

import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { bindStepHandler } from '../services/jobs/steps.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { lineageOf, RENET_NO_LISTING_EXIT } from './backup-storage-browse.js';

/** One line of JSON the verb prints on success. */
interface RestorePathRecord {
  snapshotId: string;
  path: string;
  to: string;
  files: number;
  dirs: number;
  symlinks: number;
  skipped: number;
  bytesWritten: number;
  cellsTotal: number;
  cellsSelected: number;
  chunksFetched: number;
  bytesFetched: number;
}

/** The flags `--path` cannot be combined with: each belongs to the whole-image restore, or is a placement the verb cannot honour (`backup_restore_path` takes the datastore from the machine's vault, not a parameter). */
const PATH_INCOMPATIBLE_FLAGS = [
  ['as', '--as'],
  ['up', '--up'],
  ['healthWindow', '--health-window'],
  ['healthTimeout', '--health-timeout'],
  ['datastore', '--datastore'],
] as const;

/** True when `--path` was given at all, even as an empty string: the route is chosen on presence, never truthiness. */
export function isPathRoute(options: { path?: string }): boolean {
  return options.path !== undefined;
}

/** A given but blank value (an unset shell variable) refuses instead of falling back silently. */
function assertNoBlankValues(
  path: string,
  to: string | undefined,
  machine: string | undefined
): void {
  for (const [value, flag] of [
    [path, '--path'],
    [to, '--to'],
    [machine, '-m'],
  ] as const) {
    if (value !== undefined && !value.trim()) {
      throw new ValidationError(t('commands.backup.restore.pathEmpty', { flag }));
    }
  }
}

/** Refuses a bad flag combination before anything executes. */
export function assertRestorePathFlags(options: {
  at?: string;
  path?: string;
  to?: string;
  machine?: string;
  as?: string;
  datastore?: string;
  up?: boolean;
  healthWindow?: string;
  healthTimeout?: string;
}): void {
  if (options.to !== undefined && options.path === undefined) {
    throw new ValidationError(t('commands.backup.restore.toNeedsPath'));
  }
  if (options.path === undefined) return;
  assertNoBlankValues(options.path, options.to, options.machine);
  if (!options.at) {
    throw new ValidationError(t('commands.backup.restore.pathNeedsAt'));
  }
  for (const [key, flag] of PATH_INCOMPATIBLE_FLAGS) {
    if (options[key]) {
      throw new ValidationError(t('commands.backup.restore.pathConflict', { flag }));
    }
  }
}

/** Every JSON object found on a line of captured output, bare or inside a log line. */
function jsonObjectsIn(text: string | undefined): unknown[] {
  const found: unknown[] = [];
  for (const line of (text ?? '').split('\n')) {
    const start = line.indexOf('{');
    if (start === -1) continue;
    try {
      found.push(JSON.parse(line.slice(start)));
    } catch {
      // A partial line or a log prefix around escaped JSON: not a payload.
    }
  }
  return found;
}

function parseRecord(stdout: string | undefined): RestorePathRecord | undefined {
  return jsonObjectsIn(stdout)
    .reverse()
    .find(
      (v): v is RestorePathRecord =>
        v !== null && typeof v === 'object' && 'snapshotId' in v && 'bytesWritten' in v
    );
}

/** The `reason` renet's NO_LISTING payload carries: absent, live-mount or no-positions. */
function noListingReason(result: { stderr?: string; stdout?: string; error?: string }): string {
  for (const text of [result.stderr, result.error, result.stdout]) {
    for (const v of jsonObjectsIn(text)) {
      if (v !== null && typeof v === 'object' && 'reason' in v) {
        return String((v as { reason: unknown }).reason);
      }
    }
  }
  return '';
}

const NO_LISTING_MESSAGES: Record<string, string> = {
  absent: 'commands.backup.restore.pathNoListingAbsent',
  'live-mount': 'commands.backup.restore.pathNoListingLiveMount',
  'no-positions': 'commands.backup.restore.pathNoListingNoPositions',
};
/** Shown when the NO_LISTING payload names no known reason. */
const NO_LISTING_FALLBACK = 'commands.backup.restore.pathNoListing';

/**
 * Run `backup_restore_path` for `repoKey` on `machineName`. `resolveSnapshot` maps the
 * `--at` value to a snapshot id; it is a parameter, not an import, because backup.ts owns
 * the resolver and the stream scope and a static import back would close a cycle.
 */
export async function runRestorePath(args: {
  repoKey: string;
  machineName: string;
  at: string;
  path: string;
  to?: string;
  debug?: boolean;
  resolveSnapshot: (lineage: string, at: string) => Promise<string>;
}): Promise<void> {
  const { repoKey, machineName, at, path, to, debug, resolveSnapshot } = args;
  const repo = await configService.getRepository(repoKey);
  if (!repo) {
    throw new ValidationError(t('commands.backup.restore.sourceUnknown', { name: repoKey }));
  }
  if (!repo.credential) {
    throw new ValidationError(t('commands.backup.restore.pathNeedsCredential', { name: repoKey }));
  }
  const lineage = lineageOf(repo);
  const snapshotId = await resolveSnapshot(lineage, at);

  const result = await executeRepoFunction(
    'backup_restore_path',
    repoKey,
    machineName,
    { lineage, at: snapshotId, path, to: to ?? '' },
    { debug, captureOutput: true },
    {
      starting: t('commands.backup.restore.pathStarting', {
        name: repoKey,
        path,
        snapshot: snapshotId,
      }),
      completed: t('commands.backup.restore.pathCompleted', { name: repoKey }),
      failed: t('commands.backup.restore.pathFailed', { name: repoKey }),
    }
  );

  if (!result.success) {
    // 18 is a distinct code, as with browse: "this snapshot cannot address the path" is not "it broke".
    if (result.exitCode === RENET_NO_LISTING_EXIT) {
      const key = NO_LISTING_MESSAGES[noListingReason(result)];
      outputService.warn(t(key ?? NO_LISTING_FALLBACK, { name: repoKey, snapshot: snapshotId }));
      setExitCode(RENET_NO_LISTING_EXIT);
    }
    // Any other failure was rendered, with its exit code, by executeRepoFunction.
    return;
  }

  await reportRestorePath(repoKey, result.stdout);
}

/** Print the restore-path record parsed from the job's stdout. */
async function reportRestorePath(repoKey: string, stdout: string | undefined): Promise<void> {
  const record = parseRecord(stdout);
  if (!record) {
    throw new Error(`restore-path returned no record for "${repoKey}"`);
  }
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(record, format);
    return;
  }
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  outputService.success(
    t('commands.backup.restore.pathRestored', {
      files: record.files,
      dirs: record.dirs,
      symlinks: record.symlinks,
      bytes: formatSizeBytes(record.bytesWritten),
      to: record.to,
    })
  );
  outputService.info(
    t('commands.backup.restore.pathFetched', {
      selected: record.cellsSelected,
      total: record.cellsTotal,
      bytes: formatSizeBytes(record.bytesFetched),
    })
  );
  if (record.skipped > 0) {
    outputService.warn(t('commands.backup.restore.pathSkipped', { count: record.skipped }));
  }
}

bindStepHandler('reportRestorePath', ({ params, output }) =>
  reportRestorePath(String(params.repo), output)
);
