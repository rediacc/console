/**
 * `rdc backup reconcile [repo-ref] [--dry-run] [--check]`, the repair verb for the
 * storage ledger. The server lists what the store really holds, works out which
 * of it a committed manifest references, and (unless a dry run) sets the ledger
 * to those observed figures. It never deletes a chunk. `--check` is a dry run
 * whose exit code says whether the ledger drifted, so a schedule or a CI leg can
 * gate on it.
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
 * from its ledger. A lineage the server skipped (`leased`: an upload is running;
 * `unreadable`) was deliberately left alone, so `--check` neither judges it nor
 * fails on it; it is listed in the output with its reason instead. The aggregate
 * `driftBytes` includes skipped lineages, so it counts only when none was skipped:
 * with a skip it cannot be told apart from the skipped lineage's own drift.
 */
function hasDrift(res: ReconcileResponse): boolean {
  const judged = res.lineages.filter((l) => !l.skipped);
  const aggregateDrift = judged.length === res.lineages.length && res.driftBytes !== 0;
  return (
    aggregateDrift ||
    judged.some(
      (l) => l.observedBytes !== l.ledgerBytesBefore || l.observedChunks !== l.ledgerChunksBefore
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
  // The skip warning goes to stderr in every format: under -o json the lineages are in the printed response too, but a script reading only the exit code would otherwise see a clean 0 with nothing checked.
  if (skipped.length > 0) {
    outputService.warn(
      t('commands.backup.reconcile.checkSkipped', {
        lineages: skipped.map((l) => `${l.lineageGuid} (${l.skipped})`).join(', '),
      })
    );
  }
  if (!hasDrift(res)) return;
  if (table) outputService.warn(t('commands.backup.reconcile.driftFound'));
  setExitCode(1);
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
