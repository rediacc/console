/**
 * `rdc backup retention` (show, set, clear, preview) and `rdc backup snapshots delete`: the
 * commands that decide what the server deletes, split out of backup-storage.ts. All of them talk
 * to the account server through `accountServerFetch` and never reach a machine.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat } from '../types/index.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import type { BackupManifestsResponse } from './backup-storage.js';
import { resolveLineage } from './backup-storage-browse.js';

interface BackupRetentionPolicy {
  lineageGuid: string;
  streamId?: string | null;
  keepLast: number | null;
  keepHourly: number | null;
  keepDaily: number | null;
  keepWeekly: number | null;
  keepMonthly: number | null;
  keepYearly: number | null;
  updatedAt: string;
}

interface BackupRetentionResponse {
  policies: BackupRetentionPolicy[];
}

type RetentionPolicySource = 'stream' | 'declared' | 'plan' | 'default' | 'orphan';

type RetentionKnobs = Omit<BackupRetentionPolicy, 'lineageGuid' | 'streamId' | 'updatedAt'>;

/** GET /backups/retention/preview, the dry run of the next sweep. */
interface BackupRetentionPreview {
  lineageGuid: string;
  policySource: RetentionPolicySource;
  streams: { streamId: string; policySource: RetentionPolicySource; policy: RetentionKnobs }[];
  deleted: { snapshotId: string; streamId: string; createdAt: string }[];
  keptSnapshots: number;
  freedBytes: number | null;
  freedChunks: number | null;
}

/** The label an operator reads for where an effective policy came from. */
function sourceLabel(source: RetentionPolicySource): string {
  switch (source) {
    case 'stream':
      return t('commands.backup.retention.source.stream');
    case 'declared':
      return t('commands.backup.retention.source.declared');
    case 'plan':
      return t('commands.backup.retention.source.plan');
    case 'orphan':
      return t('commands.backup.retention.source.orphan');
    default:
      return t('commands.backup.retention.source.default');
  }
}

const knobCells = (p: RetentionKnobs) => ({
  last: p.keepLast ?? '-',
  hourly: p.keepHourly ?? '-',
  daily: p.keepDaily ?? '-',
  weekly: p.keepWeekly ?? '-',
  monthly: p.keepMonthly ?? '-',
  yearly: p.keepYearly ?? '-',
});

const KNOB_COLUMNS = [
  { key: 'last', header: 'Last', align: 'right' as const },
  { key: 'hourly', header: 'Hourly', align: 'right' as const },
  { key: 'daily', header: 'Daily', align: 'right' as const },
  { key: 'weekly', header: 'Weekly', align: 'right' as const },
  { key: 'monthly', header: 'Monthly', align: 'right' as const },
  { key: 'yearly', header: 'Yearly', align: 'right' as const },
];

/**
 * The policy a repository is actually held to, with where it came from, read from the server's own
 * dry run so the answer is the one the sweep uses.
 */
function effectivePolicy(lineage: string): Promise<BackupRetentionPreview> {
  return accountServerFetch<BackupRetentionPreview>(
    `/account/api/v1/backups/retention/preview?lineage=${encodeURIComponent(lineage)}`
  );
}

/** The GFS knobs, in the order an operator thinks about them. */
const RETENTION_KNOBS = [
  ['keepLast', '--keep-last'],
  ['keepHourly', '--keep-hourly'],
  ['keepDaily', '--keep-daily'],
  ['keepWeekly', '--keep-weekly'],
  ['keepMonthly', '--keep-monthly'],
  ['keepYearly', '--keep-yearly'],
] as const;

/** The effective-policy table of one repository: its source, then each stream's own. */
function renderEffectivePolicy(repoRef: string, effective: BackupRetentionPreview): void {
  outputService.info(
    t('commands.backup.retention.effective', {
      name: repoRef,
      source: sourceLabel(effective.policySource),
    })
  );
  if (effective.streams.length === 0) return;
  const rows = effective.streams.map((s) => ({
    stream: s.streamId,
    source: sourceLabel(s.policySource),
    ...knobCells(s.policy),
  }));
  const columns = [
    { key: 'stream', header: 'Stream' },
    { key: 'source', header: 'Source' },
    ...KNOB_COLUMNS,
  ];
  outputService.print(outputService.format(rows, getOutputFormat(), columns));
}

/** `backup retention preview <repo>`, what the next sweep deletes and the bytes it frees. */
function registerRetentionPreview(retention: Command): void {
  retention
    .command('preview')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.retention.preview.description'))
    .action(async (repoRef: string) => {
      try {
        const preview = await effectivePolicy(await resolveLineage(repoRef));
        const format = getOutputFormat();
        if (format !== 'table') {
          outputService.print(preview, format);
          return;
        }
        if (preview.deleted.length === 0) {
          outputService.info(t('commands.backup.retention.preview.nothing', { name: repoRef }));
          return;
        }
        const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
        outputService.info(
          t('commands.backup.retention.preview.summary', {
            name: repoRef,
            count: preview.deleted.length,
            kept: preview.keptSnapshots,
            bytes: preview.freedBytes === null ? '?' : formatSizeBytes(preview.freedBytes),
          })
        );
        const rows = preview.deleted.map((d) => ({
          snapshot: d.snapshotId,
          stream: d.streamId,
          created: d.createdAt.replace('T', ' ').replace(/\..*$/, ''),
        }));
        const columns = [
          { key: 'snapshot', header: 'Snapshot' },
          { key: 'stream', header: 'Stream' },
          { key: 'created', header: 'Created' },
        ];
        outputService.print(outputService.format(rows, format, columns));
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * `backup snapshots delete <repo-ref> <snapshot-id>`, the manual delete (the same prune the sweep
 * uses). The id must belong to the named repository's history, so a mistyped id from another
 * repository is refused here instead of deleting a snapshot the operator did not mean.
 */
export function registerBackupSnapshots(backup: Command): void {
  const snapshots = backup
    .command('snapshots')
    .description(t('commands.backup.snapshots.description'));
  snapshots
    .command('delete')
    .argument('<repo-ref>', t('options.repoRef'))
    .argument('<snapshot-id>', t('commands.backup.snapshots.snapshotIdArgument'))
    .description(t('commands.backup.snapshots.delete.description'))
    .action(async (repoRef: string, snapshotId: string) => {
      try {
        const lineage = await resolveLineage(repoRef);
        const history = await accountServerFetch<BackupManifestsResponse>(
          `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
        );
        if (!history.manifests.some((m) => m.snapshotId === snapshotId)) {
          throw new ValidationError(
            t('commands.backup.snapshots.delete.notInRepo', { snapshot: snapshotId, name: repoRef })
          );
        }
        const result = await accountServerFetch<{ deleted: string[] }>(
          `/account/api/v1/backups/snapshots/${encodeURIComponent(snapshotId)}`,
          { method: 'DELETE' }
        );
        const format = getOutputFormat();
        if (format !== 'table') {
          outputService.print(result, format);
          return;
        }
        outputService.success(
          t('commands.backup.snapshots.delete.success', {
            name: repoRef,
            count: result.deleted.length,
            snapshot: snapshotId,
          })
        );
      } catch (error) {
        handleError(error);
      }
    });
}

/** The policy table for every lineage that has one, repos resolved to names. */
async function printPolicyTable(
  result: BackupRetentionResponse,
  format: OutputFormat
): Promise<void> {
  if (result.policies.length === 0) {
    outputService.print(t('commands.backup.retention.empty'));
    return;
  }
  const resolve = createGuidResolver(await loadGuidMap());
  const rows = result.policies.map((p) => ({
    repo: resolve(p.lineageGuid),
    stream: p.streamId ?? '-',
    ...knobCells(p),
  }));
  const columns = [
    { key: 'repo', header: 'Repo' },
    { key: 'stream', header: 'Stream' },
    ...KNOB_COLUMNS,
  ];
  outputService.print(outputService.format(rows, format, columns));
}

async function runRetentionShow(repoRef: string | undefined): Promise<void> {
  const lineage = repoRef ? await resolveLineage(repoRef) : undefined;
  const query = lineage ? `?lineage=${encodeURIComponent(lineage)}` : '';
  const result = await accountServerFetch<BackupRetentionResponse>(
    `/account/api/v1/backups/retention${query}`
  );
  // A named repo also shows the policy in force and its source (repo override, strategy-declared, plan default, server default).
  const effective = lineage ? await effectivePolicy(lineage) : undefined;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(effective ? { ...result, effective } : result, format);
  } else if (effective) {
    renderEffectivePolicy(repoRef ?? '', effective);
  } else {
    await printPolicyTable(result, format);
  }
}

/** The PUT body for `retention set`, and how many knobs it declares. Refuses a non-integer knob and an empty set. */
function retentionSetBody(
  lineageGuid: string,
  options: Record<string, string | undefined>
): { body: Record<string, unknown>; declared: number } {
  const body: Record<string, unknown> = { lineageGuid };
  if (options.stream) body.streamId = options.stream;
  let declared = 0;
  for (const [field, flag] of RETENTION_KNOBS) {
    const raw = options[field];
    if (raw === undefined) continue;
    const n = Number(raw);
    if (!Number.isInteger(n) || n < 0) {
      throw new ValidationError(
        t('commands.backup.retention.knobNotAnInteger', { flag, value: raw })
      );
    }
    body[field] = n;
    declared++;
  }
  // EVERY knob is replaced, never merged, the server says so at routes/backups.ts:167. So an empty set would silently clear the policy while reading like a no-op. Refuse instead.
  if (declared === 0) {
    throw new ValidationError(t('commands.backup.retention.noKnobs'));
  }
  return { body, declared };
}

/**
 * `backup retention [repo-ref]`, show the policy the SERVER is enforcing.
 *
 * Read back from the server rather than printed from the local config on
 * purpose: what is displayed is then always what is enforced. A policy shown
 * from config would be a statement of intent that a failed push could make a
 * lie, and this is the surface that decides what gets DELETED.
 */
export function registerBackupRetention(backup: Command): void {
  const retention = backup
    .command('retention')
    .argument('[repo-ref]', t('options.repoRef'))
    .description(t('commands.backup.retention.description'))
    .action(async (repoRef: string | undefined) => {
      try {
        await runRetentionShow(repoRef);
      } catch (error) {
        handleError(error);
      }
    });

  registerRetentionPreview(retention);

  retention
    .command('set')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.retention.set.description'))
    .option('--keep-last <n>', t('commands.backup.retention.optionKeepLast'))
    .option('--keep-hourly <n>', t('commands.backup.retention.optionKeepHourly'))
    .option('--keep-daily <n>', t('commands.backup.retention.optionKeepDaily'))
    .option('--keep-weekly <n>', t('commands.backup.retention.optionKeepWeekly'))
    .option('--keep-monthly <n>', t('commands.backup.retention.optionKeepMonthly'))
    .option('--keep-yearly <n>', t('commands.backup.retention.optionKeepYearly'))
    .option('--stream <id>', t('commands.backup.retention.optionStream'))
    .action(async (repoRef: string, options: Record<string, string | undefined>) => {
      try {
        const { body, declared } = retentionSetBody(await resolveLineage(repoRef), options);
        const result = await accountServerFetch<BackupRetentionResponse>(
          '/account/api/v1/backups/retention',
          { method: 'PUT', body }
        );
        outputService.success(
          t('commands.backup.retention.set.success', { name: repoRef, count: String(declared) })
        );
        const format = getOutputFormat();
        if (format !== 'table') outputService.print(result, format);
      } catch (error) {
        handleError(error);
      }
    });

  retention
    .command('clear')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.retention.clear.description'))
    .option('--stream <id>', t('commands.backup.retention.optionStream'))
    .action(async (repoRef: string, options: { stream?: string }) => {
      try {
        const lineage = await resolveLineage(repoRef);
        const streamQuery = options.stream ? `&stream=${encodeURIComponent(options.stream)}` : '';
        await accountServerFetch<BackupRetentionResponse>(
          `/account/api/v1/backups/retention?lineage=${encodeURIComponent(lineage)}${streamQuery}`,
          { method: 'DELETE' }
        );
        // Clearing is NOT "keep nothing": with no row the server sweeps this lineage under the plan default, else the server default (backup-gc.service.ts planRetention). Say so, because "keep nothing" would be a data-loss expectation and "keep everything" a quota surprise.
        outputService.success(t('commands.backup.retention.cleared', { name: repoRef }));
      } catch (error) {
        handleError(error);
      }
    });
}
