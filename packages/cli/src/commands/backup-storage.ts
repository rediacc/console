/**
 * `rdc backup usage | manifests | verify` — the read side of the content-addressed
 * chunk-store backup (spec/02). `usage` and `manifests` are control-plane READS
 * through the account tunnel (`accountServerFetch`, so the request is
 * E2E-sealed); they need the `backup:read` scope
 * on the presented token. `verify` is executor-side: it runs the renet
 * `backup_verify` verb on the machine that holds the repo — the machine, not the
 * server, owns the anchor and the cell data.
 */

import { BACKUP_BROWSE_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { recordBackupRun } from '../services/backup/backup-runs-state.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoRefLocal } from '../utils/repo-target.js';

/** GET /backups/usage — subscription aggregate + per-lineage breakdown. */
interface BackupUsageResponse {
  subscriptionId: string;
  storedBytes: number;
  chunkCount: number;
  usageAdjustment: number;
  leasedBytes: number;
  activeLeases: number;
  usedBytes: number;
  quotaBytes: number;
  overLimit: boolean;
  retentionStartedAt: string | null;
  lineages: {
    lineageGuid: string;
    storedBytes: number;
    chunkCount: number;
    logicalBytes: number;
    updatedAt: string;
  }[];
}

/** GET /backups/manifests — the server-side snapshot index. */
interface BackupManifestEntry {
  snapshotId: string;
  lineageGuid: string;
  streamId: string;
  parentSnapshotId?: string;
  cellSizeBytes: number;
  totalBytes: number;
  addedBytes: number;
  addedChunkCount: number;
  createdAt: string;
}
/**
 * Exported because `backup restore --at` resolves a TIME against this same
 * index (backup.ts::resolveSnapshotAt). One declaration, not two: a
 * hand-written twin of a wire shape is how the two sides drift apart while both
 * stay green.
 */
export interface BackupManifestsResponse {
  manifests: BackupManifestEntry[];
}

/** `backup usage` — quota vs stored bytes, plus per-repo (lineage) usage. */
function registerBackupUsage(backup: Command): void {
  backup
    .command('usage')
    .description(t('commands.backup.usage.description'))
    .action(async () => {
      try {
        outputService.info(t('commands.backup.usage.fetching'));
        const usage = await accountServerFetch<BackupUsageResponse>(
          '/account/api/v1/backups/usage'
        );

        const format = getOutputFormat();
        if (format !== 'table') {
          outputService.print(usage, format);
          return;
        }

        const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
        outputService.info(
          `Used ${formatSizeBytes(usage.usedBytes)} of ${formatSizeBytes(usage.quotaBytes)}` +
            ` (stored ${formatSizeBytes(usage.storedBytes)}, leased ${formatSizeBytes(usage.leasedBytes)}` +
            `, ${usage.chunkCount} chunks)${usage.overLimit ? '  OVER LIMIT' : ''}`
        );

        if (usage.lineages.length === 0) {
          outputService.print(t('commands.backup.usage.empty'));
          return;
        }

        const resolve = createGuidResolver(await loadGuidMap());
        const rows = usage.lineages
          .map((l) => ({
            repo: resolve(l.lineageGuid),
            lineage: l.lineageGuid,
            stored: formatSizeBytes(l.storedBytes),
            logical: formatSizeBytes(l.logicalBytes),
            chunks: l.chunkCount,
            updated: l.updatedAt.replace('T', ' ').replace(/\..*$/, ''),
          }))
          .sort((a, b) => a.repo.localeCompare(b.repo));

        const columns = [
          { key: 'repo', header: 'Repo' },
          { key: 'lineage', header: 'Lineage' },
          { key: 'stored', header: 'Stored', align: 'right' as const },
          { key: 'logical', header: 'Logical', align: 'right' as const },
          { key: 'chunks', header: 'Chunks', align: 'right' as const },
          { key: 'updated', header: 'Updated' },
        ];
        outputService.print(outputService.format(rows, format, columns));
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * The lineage (grand) GUID a repo ref belongs to. ONE implementation, shared by
 * `manifests` and `retention`: both address the server-side index by lineage,
 * and a second copy of this resolution is how the two commands would come to
 * disagree about which repo the operator named.
 */
async function resolveLineage(repoRef: string): Promise<string> {
  const { repoKey } = await resolveRepoRefLocal(repoRef);
  const repo = await configService.getRepository(repoKey);
  if (!repo) {
    throw new Error(`Repository "${repoKey}" not found in this config.`);
  }
  return repo.grandGuid ?? repo.repositoryGuid;
}

/** `backup manifests [repo-ref]` — the server snapshot index, optionally scoped. */
function registerBackupManifests(backup: Command): void {
  backup
    .command('manifests')
    .argument('[repo-ref]', t('options.repoRef'))
    .description(t('commands.backup.manifests.description'))
    .action(async (repoRef: string | undefined) => {
      try {
        // Scope to one lineage (grand GUID) when a repo is named. Config-local
        // resolution only — the index lives on the server, not on a machine.
        const lineage = repoRef ? await resolveLineage(repoRef) : undefined;

        outputService.info(t('commands.backup.manifests.fetching'));
        const query = lineage ? `?lineage=${encodeURIComponent(lineage)}` : '';
        const result = await accountServerFetch<BackupManifestsResponse>(
          `/account/api/v1/backups/manifests${query}`
        );

        const format = getOutputFormat();
        if (format !== 'table') {
          outputService.print(result, format);
          return;
        }
        if (result.manifests.length === 0) {
          outputService.print(t('commands.backup.manifests.empty'));
          return;
        }

        const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
        const resolve = createGuidResolver(await loadGuidMap());
        const rows = result.manifests
          .map((m) => ({
            repo: resolve(m.lineageGuid),
            snapshot: m.snapshotId,
            created: m.createdAt.replace('T', ' ').replace(/\..*$/, ''),
            total: formatSizeBytes(m.totalBytes),
            added: formatSizeBytes(m.addedBytes),
            chunks: m.addedChunkCount,
          }))
          // Most recent first (ISO timestamps sort lexicographically).
          .sort((a, b) => b.created.localeCompare(a.created));

        const columns = [
          { key: 'repo', header: 'Repo' },
          { key: 'snapshot', header: 'Snapshot' },
          { key: 'created', header: 'Created' },
          { key: 'total', header: 'Total', align: 'right' as const },
          { key: 'added', header: 'Added', align: 'right' as const },
          { key: 'chunks', header: 'Chunks', align: 'right' as const },
        ];
        outputService.print(outputService.format(rows, format, columns));
      } catch (error) {
        handleError(error);
      }
    });
}

/** The verdict `renet backup verify` prints, when it can be recovered. */
export interface VerifyVerdict {
  status: string;
  level?: string;
  checkedCells?: number;
}

/**
 * Recover the verify verdict from the verb's captured stdout.
 *
 * Exported for testing. renet emits one JSON object, but it can arrive with
 * relay prefixes or log lines around it, so this scans for the LAST line that
 * parses and carries a `status` rather than assuming the whole buffer is JSON.
 * Returns undefined rather than throwing: a verdict we cannot parse must not
 * turn a successful verification into a crash, and the caller falls back to
 * the exit code.
 */
export function parseVerifyVerdict(stdout: string | undefined): VerifyVerdict | undefined {
  if (!stdout) return undefined;
  let found: VerifyVerdict | undefined;
  for (const line of stdout.split('\n')) {
    const start = line.indexOf('{');
    if (start === -1) continue;
    try {
      const parsed: unknown = JSON.parse(line.slice(start));
      if (parsed && typeof parsed === 'object' && 'status' in parsed) {
        found = parsed as VerifyVerdict;
      }
    } catch {
      // Not JSON, or a partial line. Keep scanning; a stray log line must not
      // hide a verdict that appears later in the buffer.
    }
  }
  return found;
}

/** One filesystem object as `renet backup browse` reports it. */
interface BrowseEntry {
  path: string;
  type: string;
  size: number;
  modTime: string;
}

/** The listing plus what it is a listing OF. */
export interface BrowseListing {
  source: string;
  entries: BrowseEntry[];
  truncated: boolean;
  totalSize: number;
}

/**
 * Recover the listing from the verb's captured stdout.
 *
 * Exported for testing. Two shapes have to be handled, and the second is the
 * one that bit this wave already: a verb's stdout can arrive WRAPPED inside a
 * log line as `msg="[backup_browse] {...}"` with the quotes escaped, in which
 * case scanning for a bare `{` finds the brace but JSON.parse chokes on the
 * escapes. A parser that accepts only the bare form reports "no listing" for a
 * listing that was produced correctly.
 *
 * Returns undefined rather than throwing, so an unparseable buffer surfaces as
 * a named error instead of a stack trace.
 */
/**
 * Candidate JSON payloads on one line of captured output.
 *
 * TWO shapes, and the second is the one that cost this wave a CI round: a
 * verb's stdout can arrive WRAPPED inside a log line as
 * `msg="[backup_browse] {...}"` with the quotes escaped, in which case scanning
 * for a bare `{` finds the brace but JSON.parse chokes on the escapes.
 */
function browseJsonCandidates(line: string): string[] {
  const out: string[] = [];
  const wrapped = /msg="\[[a-z_]+\] (\{.*?\})"\s*$/.exec(line);
  if (wrapped) {
    // JSON.parse the quoted span rather than replaceAll('\\"', '"').
    //
    // The naive unescape handled ONLY escaped quotes, so a filename containing
    // a newline or a backslash -- both legal on Linux -- came back as invalid
    // JSON. It failed safe (parseBrowseResult returns undefined, browse names
    // the error), but "fails safe" here means REFUSING a repository that is
    // perfectly fine, and the operator would have no way to tell that from a
    // real fault. Wrapping the span in quotes and parsing it as a JSON string
    // literal applies the same unescaping rules the writer used, for every
    // escape rather than one of them.
    try {
      out.push(JSON.parse(`"${wrapped[1]}"`) as string);
    } catch {
      // Not a decodable string literal: fall through to the bare-JSON attempt
      // below rather than discarding the line.
    }
  }
  const start = line.indexOf('{');
  if (start !== -1) out.push(line.slice(start));

  return out;
}

/** True when a parsed value is shaped like a browse listing and not another verb's record. */
function isBrowseListing(parsed: unknown): parsed is BrowseListing {
  return (
    parsed !== null &&
    typeof parsed === 'object' &&
    'entries' in parsed &&
    'source' in parsed &&
    Array.isArray((parsed as BrowseListing).entries)
  );
}

export function parseBrowseResult(stdout: string | undefined): BrowseListing | undefined {
  if (!stdout) return undefined;
  let found: BrowseListing | undefined;
  for (const raw of stdout.split('\n')) {
    for (const candidate of browseJsonCandidates(raw.trim())) {
      try {
        const parsed: unknown = JSON.parse(candidate);
        if (isBrowseListing(parsed)) found = parsed;
      } catch {
        // Not JSON, or a partial line. Keep scanning: a stray log line must not
        // hide a listing that appears later in the buffer.
      }
    }
  }

  return found;
}

/**
 * `backup browse <repo-ref> [--path]` -- list what a repository contains.
 *
 * A LOCAL read on the machine holding the image. The chunk store cannot answer
 * this question at all: a manifest maps grid cells to the hash of their
 * CIPHERTEXT, so it carries no filesystem information and no listing is
 * derivable from it. The only way to list files is to open the image and walk
 * it, which is what renet does here.
 *
 * Uses resolveRepoRef, not resolveRepoRefLocal: unlike `backup manifests`,
 * which reads the server index, this must reach a machine to read an image.
 */
function registerBackupBrowse(backup: Command): void {
  backup
    .command('browse')
    .argument('<repo-ref>', t('options.repoRef'))
    // .summary is the one-liner `--help` lists; .description is the long form a
    // reader sees on the command's own page. The long one carries the keyfile
    // precondition and the chunk-store limit, which is too much for a list.
    .summary(t('commands.backup.browse.descriptionShort'))
    .description(t('commands.backup.browse.description'))
    .option('--path <subdir>', t('commands.backup.browse.optionPath'))
    .option('--depth <n>', t('commands.backup.browse.optionDepth'))
    .option('--limit <n>', t('commands.backup.browse.optionLimit'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        repoRef: string,
        options: { path?: string; depth?: string; limit?: string; debug?: boolean }
      ) => {
        try {
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          const result = await executeRepoFunction(
            'backup_browse',
            repoKey,
            machineName,
            {
              path: options.path ?? '',
              depth: options.depth ?? BACKUP_BROWSE_DEFAULTS.DEPTH,
              limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
            },
            // captureOutput for the same reason as backup verify: the listing
            // IS the answer, and without it the step detector drops the verb's
            // JSON and browse exits 0 with EMPTY stdout.
            { debug: options.debug, captureOutput: true },
            {
              starting: t('commands.backup.browse.starting', { name: repoKey }),
              completed: t('commands.backup.browse.completed', { name: repoKey }),
              failed: t('commands.backup.browse.failed', { name: repoKey }),
            }
          );

          const listing = parseBrowseResult(result.stdout);
          if (!listing) {
            throw new Error(`browse returned no listing for "${repoKey}"`);
          }
          if (listing.entries.length === 0) {
            outputService.info(t('commands.backup.browse.empty', { name: repoKey }));
            return;
          }

          const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
          const rows = listing.entries.map((e) => ({
            name: e.path,
            type: e.type,
            size: e.type === 'file' ? formatSizeBytes(e.size) : '-',
            modified: e.modTime.replace('T', ' ').replace(/\..*$/, ''),
          }));
          // Columns are name/type/size/modified, byte-for-byte what the retired
          // `storage browse` produced, so an operator who lost that verb gets
          // the same shape back rather than a new one to learn.
          outputService.print(
            outputService.format(rows, getOutputFormat(), [
              { key: 'name', header: 'Name' },
              { key: 'type', header: 'Type' },
              { key: 'size', header: 'Size', align: 'right' as const },
              { key: 'modified', header: 'Modified' },
            ])
          );
          // A truncated listing that does not say so is how somebody concludes
          // a file is absent from a backup when it is present.
          if (listing.truncated) {
            outputService.warn(
              t('commands.backup.browse.truncated', {
                limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
              })
            );
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}

/** `backup verify <repo> [--deep]` — executor-side anchor verification. */
function registerBackupVerify(backup: Command): void {
  backup
    .command('verify')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.verify.description'))
    .option('--deep', t('commands.backup.verify.optionDeep'))
    .option('--debug', t('options.debug'))
    .action(async (repoRef: string, options: { deep?: boolean; debug?: boolean }) => {
      try {
        const { repoKey, machineName } = await resolveRepoRef(repoRef);
        const level = options.deep ? 'full' : 'spot';
        const result = await executeRepoFunction(
          'backup_verify',
          repoKey,
          machineName,
          { level },
          // captureOutput: the verdict IS the answer here. Without it the step
          // detector drops the verb's JSON and `backup verify` exits 0 with
          // EMPTY stdout whether the anchor verified or mismatched, which is
          // the one thing an operator must be able to tell apart.
          { debug: options.debug, captureOutput: true },
          {
            starting: t('commands.backup.verify.starting', { name: repoKey, level }),
            completed: t('commands.backup.verify.completed', { name: repoKey }),
            failed: t('commands.backup.verify.failed', { name: repoKey }),
          }
        );
        // The verdict is structured data, so it is printed as structured data
        // in every mode -- including `table`, where the alternative would be a
        // hand-written English sentence (a new i18n key across 13 locales) that
        // says strictly less than the record itself.
        const verdict = parseVerifyVerdict(result.stdout) ?? {
          status: result.success ? 'verified' : 'mismatch',
          level,
        };
        const format = getOutputFormat();
        outputService.print(verdict, format === 'table' ? 'json' : format);
        await recordBackupRun(repoKey, {
          kind: 'verify',
          status: result.success ? 'verified' : 'mismatch',
        });
        // The renet verb exits non-zero on mismatch/failure; carry that out so a
        // script or CI step sees a failed verification as a failure.
        if (!result.success) process.exitCode = 1;
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * The renet verb exits 16 when the server refuses on storage quota
 * (cmd/renet/backup_snapshot.go). The CLI propagates it verbatim rather than
 * collapsing it to 1, so a script can tell "out of space, prune or upgrade"
 * from "it broke, go debug". 11 through 15 are already spent in the CLI's own
 * exit table, which is why the verb picked 16.
 */
const RENET_QUOTA_REFUSED_EXIT = 16;

/**
 * `backup snapshot <repo> [--reseed] [--dry-run]` — upload a chunk-store
 * snapshot. This is the write side of the chunk path: the first run uploads the
 * full non-zero inventory, every run after it uploads only changed cells.
 */
function registerBackupSnapshot(backup: Command): void {
  backup
    .command('snapshot')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.snapshot.description'))
    .option('--reseed', t('commands.backup.snapshot.optionReseed'))
    .option('--dry-run', t('commands.backup.snapshot.optionDryRun'))
    .option('--cold', t('commands.backup.snapshot.optionCold'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        repoRef: string,
        options: { reseed?: boolean; dryRun?: boolean; cold?: boolean; debug?: boolean }
      ) => {
        try {
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          const result = await executeRepoFunction(
            'backup_snapshot',
            repoKey,
            machineName,
            {
              reseed: options.reseed ?? false,
              dry_run: options.dryRun ?? false,
              // Without this the cold path was reachable only from a scheduled
              // unit or by SSH-ing to the machine: the generator emits --cold,
              // but an operator wanting one application-consistent snapshot
              // before a risky change had no supported route to it.
              cold: options.cold ?? false,
            },
            { debug: options.debug },
            {
              starting: t('commands.backup.snapshot.starting', { name: repoKey }),
              completed: t('commands.backup.snapshot.completed', { name: repoKey }),
              failed: t('commands.backup.snapshot.failed', { name: repoKey }),
            }
          );
          // A dry run moved nothing, so it must not be recorded as a stored
          // backup: a run history that counts plans as backups would make the
          // next operator believe a snapshot exists that never happened.
          // Exit 16 is the renet verb's quota refusal and it is NOT a plain
          // failure: the operator action is prune or upgrade, never debug.
          // Flattening it to 1 (as this did) threw away a distinction the verb
          // deliberately encodes, and left the quotaRefused message with no
          // call site at all.
          const quotaRefused = result.exitCode === RENET_QUOTA_REFUSED_EXIT;
          if (!options.dryRun) {
            // Three outcomes, kept distinct on purpose (see the note above):
            // a quota refusal is not a generic failure.
            let runStatus = 'failed';
            if (result.success) {
              runStatus = 'stored';
            } else if (quotaRefused) {
              runStatus = 'quota-refused';
            }
            await recordBackupRun(repoKey, { kind: 'snapshot', status: runStatus });
          }
          if (quotaRefused) {
            outputService.warn(t('commands.backup.snapshot.quotaRefused', { name: repoKey }));
            process.exitCode = RENET_QUOTA_REFUSED_EXIT;
          } else if (!result.success) {
            process.exitCode = 1;
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}

/** Register the chunk-store backup reads + verification under `rdc backup`. */
interface BackupRetentionPolicy {
  lineageGuid: string;
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

/** The GFS knobs, in the order an operator thinks about them. */
const RETENTION_KNOBS = [
  ['keepLast', '--keep-last'],
  ['keepHourly', '--keep-hourly'],
  ['keepDaily', '--keep-daily'],
  ['keepWeekly', '--keep-weekly'],
  ['keepMonthly', '--keep-monthly'],
  ['keepYearly', '--keep-yearly'],
] as const;

/**
 * `backup retention [repo-ref]` — show the policy the SERVER is enforcing.
 *
 * Read back from the server rather than printed from the local config on
 * purpose: what is displayed is then always what is enforced. A policy shown
 * from config would be a statement of intent that a failed push could make a
 * lie, and this is the surface that decides what gets DELETED.
 */
function registerBackupRetention(backup: Command): void {
  const retention = backup
    .command('retention')
    .argument('[repo-ref]', t('options.repoRef'))
    .description(t('commands.backup.retention.description'))
    .action(async (repoRef: string | undefined) => {
      try {
        const lineage = repoRef ? await resolveLineage(repoRef) : undefined;
        const query = lineage ? `?lineage=${encodeURIComponent(lineage)}` : '';
        const result = await accountServerFetch<BackupRetentionResponse>(
          `/account/api/v1/backups/retention${query}`
        );
        const format = getOutputFormat();
        if (format !== 'table') {
          outputService.print(result, format);
          return;
        }
        if (result.policies.length === 0) {
          outputService.print(t('commands.backup.retention.empty'));
          return;
        }
        const resolve = createGuidResolver(await loadGuidMap());
        const rows = result.policies.map((p) => ({
          repo: resolve(p.lineageGuid),
          last: p.keepLast ?? '-',
          hourly: p.keepHourly ?? '-',
          daily: p.keepDaily ?? '-',
          weekly: p.keepWeekly ?? '-',
          monthly: p.keepMonthly ?? '-',
          yearly: p.keepYearly ?? '-',
        }));
        const columns = [
          { key: 'repo', header: 'Repo' },
          { key: 'last', header: 'Last', align: 'right' as const },
          { key: 'hourly', header: 'Hourly', align: 'right' as const },
          { key: 'daily', header: 'Daily', align: 'right' as const },
          { key: 'weekly', header: 'Weekly', align: 'right' as const },
          { key: 'monthly', header: 'Monthly', align: 'right' as const },
          { key: 'yearly', header: 'Yearly', align: 'right' as const },
        ];
        outputService.print(outputService.format(rows, format, columns));
      } catch (error) {
        handleError(error);
      }
    });

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
    .action(async (repoRef: string, options: Record<string, string | undefined>) => {
      try {
        const lineageGuid = await resolveLineage(repoRef);
        const body: Record<string, unknown> = { lineageGuid };
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
        // EVERY knob is replaced, never merged — the server says so at
        // routes/backups.ts:167. So an empty set would silently clear the
        // policy while reading like a no-op. Refuse instead.
        if (declared === 0) {
          throw new ValidationError(t('commands.backup.retention.noKnobs'));
        }
        const result = await accountServerFetch<BackupRetentionResponse>(
          '/account/api/v1/backups/retention',
          { method: 'PUT', body: JSON.stringify(body) }
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
    .action(async (repoRef: string) => {
      try {
        const lineage = await resolveLineage(repoRef);
        await accountServerFetch<BackupRetentionResponse>(
          `/account/api/v1/backups/retention?lineage=${encodeURIComponent(lineage)}`,
          { method: 'DELETE' }
        );
        // Clearing is NOT "keep nothing": with no row the sweep never looks at
        // this lineage again, so every snapshot is kept. Say so, because the
        // opposite reading would be a data-loss expectation.
        outputService.success(t('commands.backup.retention.cleared', { name: repoRef }));
      } catch (error) {
        handleError(error);
      }
    });
}

export function registerBackupStorageCommands(backup: Command): void {
  registerBackupUsage(backup);
  registerBackupManifests(backup);
  registerBackupVerify(backup);
  registerBackupBrowse(backup);
  registerBackupSnapshot(backup);
  registerBackupRetention(backup);
}
