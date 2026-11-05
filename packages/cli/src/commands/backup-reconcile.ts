/**
 * `rdc backup reconcile [repo-ref] [--dry-run] [--check]`, the repair verb for the
 * storage ledger. The server lists what the store really holds, works out which
 * of it a committed manifest references, and (unless a dry run) sets the ledger
 * to those observed figures. It never deletes a chunk. `--check` is a dry run
 * that exits 1 when the ledger drifted or a lineage was skipped unchecked, so a
 * schedule or a CI leg can gate on it.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { resolveLineage } from './backup-storage-browse.js';

interface ReconcileLineage {
  lineageGuid: string;
  ledgerBytesBefore: number;
  ledgerChunksBefore: number;
  observedBytes: number;
  observedChunks: number;
  referencedBytes: number;
  referencedChunks: number;
  unreferencedBytes: number;
  unreferencedChunks: number;
  unreferencedPastGraceChunks: number;
  applied: boolean;
  skipped: 'leased' | 'unreadable' | null;
}

interface ReconcileResponse {
  subscriptionId: string;
  lineages: ReconcileLineage[];
  ledgerBytes: number;
  ledgerChunkCount: number;
  bucketChunkBytes: number;
  bucketChunkCount: number;
  driftBytes: number;
  // Optional so a server that adds fields later does not break this client.
  truncated?: boolean;
}

interface ReconcileOptions {
  dryRun?: boolean;
  check?: boolean;
}

/**
 * True when a lineage the server could reconcile has observed figures that differ
 * from its ledger, or the aggregate `driftBytes` is non-zero. Skipped lineages are
 * judged separately by `reportCheck`, which fails on them.
 */
function hasDrift(res: ReconcileResponse): boolean {
  return (
    res.driftBytes !== 0 ||
    res.lineages.some(
      (l) =>
        !l.skipped &&
        (l.observedBytes !== l.ledgerBytesBefore || l.observedChunks !== l.ledgerChunksBefore)
    )
  );
}

function statusOf(l: ReconcileLineage, dryRun: boolean): string {
  if (l.skipped === 'leased') return t('commands.backup.reconcile.skipped.leased');
  if (l.skipped === 'unreadable') return t('commands.backup.reconcile.skipped.unreadable');
  if (l.applied) return t('commands.backup.reconcile.status.applied');
  if (l.observedBytes === l.ledgerBytesBefore && l.observedChunks === l.ledgerChunksBefore) {
    return t('commands.backup.reconcile.status.clean');
  }
  return dryRun
    ? t('commands.backup.reconcile.status.drift')
    : t('commands.backup.reconcile.status.unchanged');
}

async function printTable(res: ReconcileResponse, dryRun: boolean): Promise<void> {
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const pair = (bytes: number, chunks: number) => `${formatSizeBytes(bytes)} / ${chunks}`;
  const rows = res.lineages.map((l) => ({
    lineage: l.lineageGuid,
    ledger: pair(l.ledgerBytesBefore, l.ledgerChunksBefore),
    observed: pair(l.observedBytes, l.observedChunks),
    referenced: pair(l.referencedBytes, l.referencedChunks),
    unreferenced: pair(l.unreferencedBytes, l.unreferencedChunks),
    status: statusOf(l, dryRun),
  }));
  const columns = [
    { key: 'lineage', header: t('commands.backup.reconcile.columns.lineage') },
    {
      key: 'ledger',
      header: t('commands.backup.reconcile.columns.ledger'),
      align: 'right' as const,
    },
    {
      key: 'observed',
      header: t('commands.backup.reconcile.columns.observed'),
      align: 'right' as const,
    },
    {
      key: 'referenced',
      header: t('commands.backup.reconcile.columns.referenced'),
      align: 'right' as const,
    },
    {
      key: 'unreferenced',
      header: t('commands.backup.reconcile.columns.unreferenced'),
      align: 'right' as const,
    },
    { key: 'status', header: t('commands.backup.reconcile.columns.status') },
  ];
  outputService.print(outputService.format(rows, 'table', columns));
  outputService.info(
    t('commands.backup.reconcile.summary', {
      ledger: formatSizeBytes(res.ledgerBytes),
      bucket: formatSizeBytes(res.bucketChunkBytes),
      drift: formatSizeBytes(Math.abs(res.driftBytes)),
    })
  );
}

/** --check never writes: it is a dry run with an exit code. */
function isDryRun(options: ReconcileOptions): boolean {
  return options.dryRun === true || options.check === true;
}

function reportResult(res: ReconcileResponse, dryRun: boolean): Promise<void> | void {
  const format = getOutputFormat();
  if (format !== 'table') return outputService.print(res, format);
  if (res.truncated) outputService.warn(t('commands.backup.reconcile.truncated'));
  if (res.lineages.length === 0) return outputService.print(t('commands.backup.reconcile.empty'));
  return printTable(res, dryRun);
}

function reportCheck(res: ReconcileResponse): void {
  const table = getOutputFormat() === 'table';
  const skipped = res.lineages.filter((l) => l.skipped);
  // A skipped lineage (`leased`: an upload holds it; `unreadable`) was never compared, so it is no verdict and the check fails on it; a green that compared nothing is the vacuous pass this gate exists to refuse (bench 2026-11-05: a dead run's lease kept a drifting lineage skipped while --check exited 0).
  // The reason goes to stderr in every format, so a script reading only the exit code still has it in its log.
  if (skipped.length > 0) {
    outputService.warn(
      t('commands.backup.reconcile.checkSkipped', {
        lineages: skipped.map((l) => `${l.lineageGuid} (${l.skipped})`).join(', '),
      })
    );
  }
  const drift = hasDrift(res);
  if (drift && table) outputService.warn(t('commands.backup.reconcile.driftFound'));
  if (drift || skipped.length > 0) setExitCode(1);
}

async function runReconcile(repoRef: string | undefined, options: ReconcileOptions) {
  const dryRun = isDryRun(options);
  const lineageGuid = repoRef ? await resolveLineage(repoRef) : undefined;
  outputService.info(t('commands.backup.reconcile.running'));
  const res = await accountServerFetch<ReconcileResponse>('/account/api/v1/backups/reconcile', {
    method: 'POST',
    body: { ...(lineageGuid ? { lineageGuid } : {}), dryRun },
  });

  await reportResult(res, dryRun);

  if (options.check) reportCheck(res);
}

export function registerBackupReconcile(backup: Command): void {
  backup
    .command('reconcile')
    .argument('[repo-ref]', t('commands.backup.reconcile.argRepoRef'))
    .description(t('commands.backup.reconcile.description'))
    .option('--dry-run', t('commands.backup.reconcile.optionDryRun'))
    .option('--check', t('commands.backup.reconcile.optionCheck'))
    .action(async (repoRef: string | undefined, options: ReconcileOptions) => {
      try {
        await runReconcile(repoRef, options);
      } catch (error) {
        handleError(error);
      }
    });
}
