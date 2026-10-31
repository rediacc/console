import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import {
  type CommandJobOutcome,
  pendingExitCode,
  runCommandJob,
} from '../services/jobs/command-job.js';
import { bindStepHandler, type PlannedStep, planStep } from '../services/jobs/steps.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import type { RestoreOptions } from './backup.js';
import { type BackupManifestsResponse } from './backup-storage.js';
import {
  parseRestoreStats,
  parseVerifyVerdict,
  type RestoreStats,
} from './backup-storage-parser.js';

/**
 * A snapshot id as `MintSnapshotID` writes it: RFC3339-basic UTC, a dash, and
 * 16 hex. Anything else in `--at` is a TIME, and resolving a time is the CLI's
 * job by explicit contract, the `backup_restore` FunctionDef says so in the
 * parameter description, because the machine has no manifest index to search.
 */
const SNAPSHOT_ID_RE = /^\d{8}T\d{6}Z-[0-9a-f]{16}$/;

/**
 * Turn `--at` into a snapshot id. A time selects the NEWEST snapshot at or
 * before it, which is the only reading that restores a point in time rather
 * than the point after it.
 *
 * `createdAt` is read from the manifest index rather than parsed out of the
 * snapshot id, even though the id is time-sortable: the id's timestamp is when
 * the id was MINTED, and the manifest commits when the upload finishes, so on a
 * long upload the two differ by the length of the transfer.
 */
export async function resolveSnapshotAt(
  lineage: string,
  at: string,
  // Omitted means every stream: read-only `backup browse --at` calls it this way (plan E4 scopes restore only). `restore --at` always passes a scope.
  scope: StreamScope = { anyStream: true }
): Promise<string> {
  if (SNAPSHOT_ID_RE.test(at)) return at;

  const when = new Date(at);
  if (Number.isNaN(when.getTime())) {
    throw new ValidationError(t('commands.backup.restore.atUnparsable', { at }));
  }

  // Resolving a time reads the hosted snapshot index, which a Free License (or no login) does not have.
  assertHostedBackupAccount();
  const result = await accountServerFetch<BackupManifestsResponse>(
    `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
  );
  const streamId = scope.anyStream ? undefined : ownStreamOf(result.manifests, scope);
  const candidates = result.manifests
    .filter((m) => streamId === undefined || m.streamId === streamId)
    .filter((m) => new Date(m.createdAt).getTime() <= when.getTime())
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  // `.at(0)` rather than `[0]`: this repo does not set noUncheckedIndexedAccess,
  // so `candidates[0]` is TYPED as always-present and eslint then calls the guard
  // below an unnecessary condition. It is not - an empty candidate list is the normal "no snapshot at or before this time" case, and dropping the guard to satisfy the linter would dereference undefined on the next line.
  const chosen = candidates.at(0);
  if (!chosen) {
    throw new ValidationError(t('commands.backup.restore.atNoSnapshot', { at }));
  }
  outputService.info(
    t('commands.backup.restore.atResolved', {
      at,
      snapshot: chosen.snapshotId,
      created: chosen.createdAt,
    })
  );
  return chosen.snapshotId;
}

/**
 * Which snapshots `--at` may pick from. The lineage is shared by every fork and
 * every machine that backs up a repo (that is what makes them dedup), so a time
 * alone can land on a snapshot some OTHER stream wrote, and the restore then
 * succeeds with the wrong machine's bytes. A stream is one (repo GUID, machine)
 * pair, minted by the server, so the default scope names it by the one snapshot
 * the source machine itself records as its anchor: that snapshot's stream is
 * this repo's stream on that machine. `--any-stream` widens it on purpose.
 */
export type StreamScope =
  | { anyStream: true }
  | { anyStream: false; anchorSnapshotId: string | undefined };

function ownStreamOf(
  manifests: BackupManifestsResponse['manifests'],
  scope: { anchorSnapshotId: string | undefined }
): string {
  const anchor = manifests.find((m) => m.snapshotId === scope.anchorSnapshotId);
  // A row without a streamId would make the caller's filter match every stream, the widening this scope exists to prevent.
  if (!anchor?.streamId) {
    throw new ValidationError(t('commands.backup.restore.streamUnknown'));
  }
  return anchor.streamId;
}

/**
 * The snapshot the SOURCE machine's journal anchors for this repo, read through
 * `backup_verify` (the verb already reports it). Undefined when the machine has
 * no committed snapshot, its verify fails, or the verdict cannot be read;
 * the streamUnknown refusal names both causes.
 */
async function readSourceAnchor(
  source: { repoName: string; machine: string },
  debug?: boolean
): Promise<string | undefined> {
  const result = await executeRepoFunction(
    'backup_verify',
    source.repoName,
    source.machine,
    { level: 'spot' },
    // A probe: the anchor decides which snapshot `--at` restores, so `--background` must not hand back a ticket here.
    { debug, captureOutput: true, probe: true },
    {
      starting: t('commands.backup.verify.starting', { name: source.repoName, level: 'spot' }),
      completed: t('commands.backup.verify.completed', { name: source.repoName }),
      failed: t('commands.backup.verify.failed', { name: source.repoName }),
    }
  );
  if (!result.success) return undefined;
  const verdict = parseVerifyVerdict(result.stdout) as { snapshotId?: string } | undefined;
  return verdict?.snapshotId;
}

/**
 * The stream scope `--at` resolves under, shared by the whole-image restore and `--path` so
 * the two cannot pick different snapshots for one time. An explicit snapshot id is a
 * deliberate choice and needs no scope; only a TIME does.
 */
export async function streamScopeFor(args: {
  at: string;
  anyStream: boolean;
  source: { repoName: string; machine: string };
  debug?: boolean;
}): Promise<StreamScope> {
  if (args.anyStream || SNAPSHOT_ID_RE.test(args.at)) return { anyStream: true };
  return {
    anyStream: false,
    anchorSnapshotId: await readSourceAnchor(args.source, args.debug),
  };
}

/**
 * Run `backup_restore` for a point-in-time restore from the chunk store, and
 * unwind the just-registered record on failure exactly as the pull path does,
 * so a retry is not blocked by target-exists.
 */
export async function runChunkRestore(args: {
  targetName: string;
  targetMachine: string;
  datastore: string | undefined;
  lineage: string;
  at: string;
  anyStream: boolean;
  noSeed: boolean;
  source: { repoName: string; machine: string };
  debug?: boolean;
  after: PlannedStep[];
}): Promise<void> {
  const { targetName, targetMachine, datastore, lineage, at, anyStream, noSeed, source, debug } =
    args;
  const scope = await streamScopeFor({ at, anyStream, source, debug });
  const snapshotId = await resolveSnapshotAt(lineage, at, scope);

  outputService.info(
    t('commands.backup.restore.restoringSnapshot', { name: targetName, snapshot: snapshotId })
  );
  await deployRepoKeyIfNeeded(targetName, targetMachine);
  const outcome = await runCommandJob(
    'backup restore',
    {
      functionName: 'backup_restore',
      machineName: targetMachine,
      datastore,
      params: {
        repository: targetName,
        lineage,
        at: snapshotId,
        dry_run: false,
        no_seed: noSeed,
      },
      debug,
      // The record on stdout carries the restore's measurements; without capture they are dropped.
      captureOutput: true,
    },
    [
      planStep('recordBackupRun', { repo: targetName, kind: 'restore', status: 'ok', snapshotId }),
      planStep('recordBackupRunFailed', { repo: targetName, kind: 'restore', snapshotId }),
      ...args.after,
    ]
  );
  settleRestore(outcome, targetName, targetMachine);
}

/**
 * The restore summary (plan L6): what was fetched, reused from a local seed or anchor, and punched
 * out, so a restore that moved little reads as one. Structured formats print the whole record.
 */
export async function reportRestoreStats(stats: RestoreStats | undefined): Promise<void> {
  if (!stats) return;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(stats, format);
    return;
  }
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const bytes = (n: number | undefined) => formatSizeBytes(n ?? 0);
  outputService.info(
    t('commands.backup.restore.stats', {
      fetched: stats.chunksFetched ?? 0,
      reused: stats.chunksReused ?? 0,
      known: stats.cellsKnown ?? 0,
      punched: stats.cellsPunched ?? 0,
      bytes: bytes(stats.bytesFetched),
      cellBytes: bytes(stats.cellBytes),
    })
  );
  if (stats.seed) {
    outputService.info(
      t('commands.backup.restore.statsSeed', {
        seed: stats.seed,
        guid: stats.seedGuid ?? '-',
        probe: bytes(stats.seedProbeBytes),
      })
    );
  }
  for (const skipped of stats.seedsSkipped ?? []) {
    outputService.info(t('commands.backup.restore.statsSeedSkipped', { skipped }));
  }
}

bindStepHandler('reportRestoreStats', ({ output }) =>
  reportRestoreStats(parseRestoreStats(output))
);

// `--up`: the deploy runs as its own job once the restore job succeeded, from whichever observer sees it finish first.
bindStepHandler('restoreDeploy', async ({ machine, params }) => {
  const datastore = typeof params.datastore === 'string' ? params.datastore : undefined;
  await restoreDeploy(String(params.repo), machine, datastore, {
    ...(typeof params.healthWindow === 'string' ? { healthWindow: params.healthWindow } : {}),
    ...(typeof params.healthTimeout === 'string' ? { healthTimeout: params.healthTimeout } : {}),
    debug: params.debug === true,
  });
});

/** Render a restore job's outcome: the failure, the success line, or nothing for a ticket (the executor printed it). */
export function settleRestore(
  outcome: CommandJobOutcome,
  targetName: string,
  targetMachine: string
): void {
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(
      outcome.result,
      t('commands.backup.restore.failed', { name: targetName })
    );
    return;
  }
  outputService.success(
    t('commands.backup.restore.restored', { name: targetName, machine: targetMachine })
  );
}

/** Deploy a restored repo (`--up`), rendering the health-gate outcome. */
async function restoreDeploy(
  name: string,
  machine: string,
  datastore: string | undefined,
  options: RestoreOptions
): Promise<void> {
  outputService.info(t('commands.backup.restore.deploying', { name, machine }));
  const params: Record<string, unknown> = { repository: name, mount: true };
  if (options.healthWindow) params.health_window = Number(options.healthWindow);
  if (options.healthTimeout) params.health_timeout = Number(options.healthTimeout);
  const up = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: machine,
    // The same mount the pull wrote into (#74).
    datastore,
    params,
    debug: options.debug,
  });
  if (up.success) {
    outputService.success(t('commands.backup.restore.deployed', { name, machine }));
  } else {
    renderLocalExecutionFailure(up, t('commands.backup.restore.deployFailed', { name }));
  }
}
