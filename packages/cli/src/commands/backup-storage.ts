/**
 * `rdc backup usage | manifests | verify`, the read side of the content-addressed
 * chunk-store backup (spec/02). `usage` and `manifests` are control-plane READS
 * through the account tunnel (`accountServerFetch`, so the request is
 * E2E-sealed); they need the `backup:read` scope
 * on the presented token. `verify` is executor-side: it runs the renet
 * `backup_verify` verb on the machine that holds the repo, the machine, not the
 * server, owns the anchor and the cell data. `verify --store` is the exception,
 * a control-plane call: the server re-hashes the lineage's stored chunks.
 */

import { BACKUP_BROWSE_DEFAULTS } from '@rediacc/shared/config/defaults';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { recordBackupRun } from '../services/backup/backup-runs-state.js';
import {
  bandwidthToBytesPerSecond,
  parseCpuLimitPercent,
  readCapBytesPerSecond,
} from '../services/backup/backup-strategy-validate.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { formatBytes } from '../utils/format.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoRefLocal } from '../utils/repo-target.js';
import { registerBackupReconcile } from './backup-reconcile.js';
import { registerBackupRetention, registerBackupSnapshots } from './backup-retention-commands.js';
import { RENET_NO_LISTING_EXIT, resolveLineage, runBrowseAt } from './backup-storage-browse.js';
import {
  isLiveMountListing,
  parseBrowseResult,
  parseVerifyVerdict,
} from './backup-storage-parser.js';

/** GET /backups/usage, subscription aggregate + per-lineage breakdown. */
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

/** GET /backups/manifests, the server-side snapshot index. */
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

/** `backup usage`, quota vs stored bytes, plus per-repo (lineage) usage. */
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

/** `backup manifests [repo-ref]`, the server snapshot index, optionally scoped. */
function registerBackupManifests(backup: Command): void {
  backup
    .command('manifests')
    .argument('[repo-ref]', t('options.repoRef'))
    .description(t('commands.backup.manifests.description'))
    .action(async (repoRef: string | undefined) => {
      try {
        // Scope to one lineage (grand GUID) when a repo is named. Config-local resolution only, the index lives on the server, not on a machine.
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

/**
 * `backup browse <repo-ref> [--path] [--at <time|snapshot>]` -- list what a repository
 * contains. With `--at`, the listing comes from the chunk store (`backup_browse_at`).
 *
 * Without `--at`, a LOCAL read on the machine holding the image. A manifest maps grid
 * cells to the hash of their CIPHERTEXT, so it carries no filesystem information and no
 * listing is derivable from it; the only way to list files from an image is to open
 * it and walk it, which is what renet does here. A chunk-store listing exists only
 * when the snapshot stored one at snapshot time, and that is the `--at` path.
 *
 * Uses resolveRepoRef, not resolveRepoRefLocal: unlike `backup manifests`,
 * which reads the server index, this must reach a machine to read an image.
 */
function registerBackupBrowse(backup: Command): void {
  backup
    .command('browse')
    .argument('<repo-ref>', t('options.repoRef'))
    // .summary is the one-liner `--help` lists; .description is the long form a
    // reader sees on the command's own page. The long one carries the keyfile precondition and the chunk-store limit, which is too much for a list.
    .summary(t('commands.backup.browse.descriptionShort'))
    .description(t('commands.backup.browse.description'))
    .option('--path <subdir>', t('commands.backup.browse.optionPath'))
    .option('--depth <n>', t('commands.backup.browse.optionDepth'))
    .option('--limit <n>', t('commands.backup.browse.optionLimit'))
    .option('--at <time|snapshot>', t('commands.backup.browse.optionAt'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        repoRef: string,
        options: {
          path?: string;
          depth?: string;
          limit?: string;
          at?: string;
          debug?: boolean;
        }
      ) => {
        try {
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          let snapshotId = '';
          let result: Awaited<ReturnType<typeof executeRepoFunction>>;
          if (options.at) {
            ({ result, snapshotId } = await runBrowseAt(repoKey, machineName, options.at, options));
          } else {
            result = await executeRepoFunction(
              'backup_browse',
              repoKey,
              machineName,
              {
                path: options.path ?? '',
                depth: options.depth ?? BACKUP_BROWSE_DEFAULTS.DEPTH,
                limit: options.limit ?? BACKUP_BROWSE_DEFAULTS.LIMIT,
              },
              // captureOutput for the same reason as backup verify: the listing IS the answer, and without it the step detector drops the verb's JSON and browse exits 0 with EMPTY stdout.
              { debug: options.debug, captureOutput: true },
              {
                starting: t('commands.backup.browse.starting', { name: repoKey }),
                completed: t('commands.backup.browse.completed', { name: repoKey }),
                failed: t('commands.backup.browse.failed', { name: repoKey }),
              }
            );
          }

          // Exit 18: the snapshot has no stored listing (an older snapshot, or one taken without a listing). A distinct code, as with 16, so a script can tell "no listing there" from "it broke".
          if (options.at && result.exitCode === RENET_NO_LISTING_EXIT) {
            outputService.warn(
              t('commands.backup.browse.noListing', { name: repoKey, snapshot: snapshotId })
            );
            setExitCode(RENET_NO_LISTING_EXIT);
            return;
          }

          // executeRepoFunction already rendered the failure (envelope and exit code).
          // Falling through would throw "no listing" and print a SECOND envelope, so stdout would stop being one JSON document.
          if (!result.success) return;
          const listing = parseBrowseResult(result.stdout);
          if (!listing) {
            throw new Error(`browse returned no listing for "${repoKey}"`);
          }
          // A listing walked from the live mount (a repository with no autostart keyfile) can differ slightly from the stored image, and the operator is told so before reading it.
          if (options.at && isLiveMountListing(listing)) {
            outputService.warn(
              t('commands.backup.browse.liveMountListing', { snapshot: snapshotId })
            );
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
          // Columns are name/type/size/modified, byte-for-byte what the retired `storage browse` produced, so an operator who lost that verb gets the same shape back rather than a new one to learn.
          outputService.print(
            outputService.format(rows, getOutputFormat(), [
              { key: 'name', header: 'Name' },
              { key: 'type', header: 'Type' },
              { key: 'size', header: 'Size', align: 'right' as const },
              { key: 'modified', header: 'Modified' },
            ])
          );
          // A truncated listing that does not say so is how somebody concludes a file is absent from a backup when it is present.
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

/** POST /backups/verify, level `chunks`: one capped page of the lineage's re-hashed chunks. */
interface BackupChunkVerifyResponse {
  subscriptionId: string;
  chunks: {
    lineageGuid: string;
    checked: number;
    missing: string[];
    corrupt: string[];
    nextAfter: string | null;
  };
}

/** The `backup verify --store` verdict: every referenced chunk of the lineage, re-hashed by the server. */
export interface StoreVerifyVerdict {
  lineageGuid: string;
  checked: number;
  missing: string[];
  corrupt: string[];
}

/**
 * Walk the server's chunk verify for one lineage, page by page, until the
 * cursor runs out. Each page re-hashes at most the server's cap
 * (BACKUP_VERIFY_CHUNKS_MAX), so a large lineage is many requests.
 */
export async function runStoreVerify(lineageGuid: string): Promise<StoreVerifyVerdict> {
  const verdict: StoreVerifyVerdict = { lineageGuid, checked: 0, missing: [], corrupt: [] };
  let after: string | undefined;
  for (;;) {
    const page = await accountServerFetch<BackupChunkVerifyResponse>(
      '/account/api/v1/backups/verify',
      { method: 'POST', body: { lineageGuid, level: 'chunks', after } }
    );
    verdict.checked += page.chunks.checked;
    verdict.missing.push(...page.chunks.missing);
    verdict.corrupt.push(...page.chunks.corrupt);
    if (!page.chunks.nextAfter) return verdict;
    // A cursor that does not advance would loop forever on a misbehaving server.
    if (page.chunks.nextAfter === after) {
      throw new Error(`backup verify --store: the server repeated cursor ${after}`);
    }
    after = page.chunks.nextAfter;
  }
}

/**
 * `backup verify <repo> [--deep] [--store]`. Without `--store`, executor-side
 * anchor verification on the machine. With `--store`, the server re-downloads
 * every chunk the repo's lineage references and re-hashes it, so a flipped or
 * lost object in the store is named by its hash; exit 1 when any is.
 */
function registerBackupVerify(backup: Command): void {
  backup
    .command('verify')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.verify.description'))
    .option('--deep', t('commands.backup.verify.optionDeep'))
    .option('--store', t('commands.backup.verify.optionStore'))
    .option('--debug', t('options.debug'))
    .action(
      async (repoRef: string, options: { deep?: boolean; store?: boolean; debug?: boolean }) => {
        try {
          if (options.store) {
            const { repoKey } = await resolveRepoRefLocal(repoRef);
            const verdict = await runStoreVerify(await resolveLineage(repoRef));
            const format = getOutputFormat();
            outputService.print(verdict, format === 'table' ? 'json' : format);
            const clean = verdict.missing.length === 0 && verdict.corrupt.length === 0;
            await recordBackupRun(repoKey, {
              kind: 'verify',
              status: clean ? 'verified' : 'mismatch',
            });
            if (!clean) setExitCode(1);
            return;
          }
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          const level = options.deep ? 'full' : 'spot';
          const result = await executeRepoFunction(
            'backup_verify',
            repoKey,
            machineName,
            { level },
            // captureOutput: the verdict IS the answer here. Without it the step detector drops the verb's JSON and `backup verify` exits 0 with EMPTY stdout whether the anchor verified or mismatched, which is the one thing an operator must be able to tell apart.
            { debug: options.debug, captureOutput: true },
            {
              starting: t('commands.backup.verify.starting', { name: repoKey, level }),
              completed: t('commands.backup.verify.completed', { name: repoKey }),
              failed: t('commands.backup.verify.failed', { name: repoKey }),
            }
          );
          if (!result.success) {
            // executeRepoFunction already rendered the failure (envelope and exit code), and renet's verdict rides its output tail.
            // Printing the verdict too would put a SECOND JSON document on stdout.
            await recordBackupRun(repoKey, { kind: 'verify', status: 'mismatch' });
            return;
          }
          // The verdict is structured data, so it is printed as structured data in every mode -- including `table`, where the alternative would be a hand-written English sentence (a new i18n key across 13 locales) that says strictly less than the record itself.
          const verdict = parseVerifyVerdict(result.stdout) ?? { status: 'verified', level };
          const format = getOutputFormat();
          outputService.print(verdict, format === 'table' ? 'json' : format);
          await recordBackupRun(repoKey, { kind: 'verify', status: 'verified' });
        } catch (error) {
          handleError(error);
        }
      }
    );
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
 * The upload knobs of `backup snapshot`, as the renet function takes them. The rate is converted here, with the strategy's own parser, so a typo is refused before any SSH is opened; renet receives bytes/second. Before this the verb had no way to carry a cap at all and every ad-hoc snapshot uploaded at line rate.
 */
export function snapshotUploadParams(options: {
  bwlimit?: string;
  parallelism?: string;
  readBwlimit?: string;
  hashParallelism?: string;
  cpuLimit?: string;
}): {
  bwlimit?: string;
  parallelism?: number;
  read_bwlimit?: string;
  hash_parallelism?: number;
  cpu_limit?: number;
} {
  const params: {
    bwlimit?: string;
    parallelism?: number;
    read_bwlimit?: string;
    hash_parallelism?: number;
    cpu_limit?: number;
  } = {};
  // Refused here, before any SSH: renet would refuse it too, but only after a connection and a licence round trip. Omitted means renet applies its default of 50.
  if (options.cpuLimit !== undefined) params.cpu_limit = parseCpuLimitPercent(options.cpuLimit);
  if (options.bwlimit !== undefined) {
    // A given --bwlimit must name a rate: a blank one (an unset shell variable) is refused, never
    // read as "no cap".
    const bytesPerSecond =
      options.bwlimit.trim() === '' ? undefined : bandwidthToBytesPerSecond(options.bwlimit);
    if (bytesPerSecond === undefined) {
      throw new ValidationError(
        t('commands.backup.snapshot.bwlimitInvalid', { value: options.bwlimit })
      );
    }
    params.bwlimit = String(bytesPerSecond);
  }
  if (options.parallelism !== undefined) {
    const n = Number(options.parallelism);
    if (!Number.isInteger(n) || n < 1) {
      throw new ValidationError(
        t('commands.backup.snapshot.parallelismInvalid', { value: options.parallelism })
      );
    }
    params.parallelism = n;
  }
  if (options.readBwlimit !== undefined) {
    // 0 is a real value here (unlimited read) and is sent as '0': omitting it would reapply the verb's gentle default. A blank or unparseable rate is refused.
    const raw = options.readBwlimit.trim();
    const bytesPerSecond = raw === '' ? undefined : readCapBytesPerSecond(raw);
    if (bytesPerSecond === undefined) {
      throw new ValidationError(
        t('commands.backup.snapshot.readBwlimitInvalid', { value: options.readBwlimit })
      );
    }
    params.read_bwlimit = String(bytesPerSecond);
  }
  if (options.hashParallelism !== undefined) {
    const raw = options.hashParallelism.trim();
    const n = Number(raw);
    if (raw === '' || !Number.isInteger(n) || n < 0 || n > 16) {
      throw new ValidationError(
        t('commands.backup.snapshot.hashParallelismInvalid', { value: options.hashParallelism })
      );
    }
    params.hash_parallelism = n;
  }
  return params;
}

/** The fields of renet's BackupSnapshotRecord that the summary reads. */
interface SnapshotRecord {
  status: string;
  snapshotId?: string;
  imageBytes?: number;
  rehashReason?: string;
  readCapBps?: number;
  hashWorkers?: number;
  cpuLimitPercent?: number;
  cpuQuota?: string | null;
  chunksUploaded?: number;
  bytesUploaded?: number;
  durationMs?: number;
}

/** Print the record renet emitted: the object under json, a short summary in a table. A missing record prints nothing, so a successful run never turns into a crash. */
function printSnapshotRecord(stdout: string | undefined): void {
  const record = parseVerifyVerdict(stdout) as SnapshotRecord | undefined;
  if (!record) return;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(record, format);
    return;
  }
  outputService.info(
    t('commands.backup.snapshot.summary', {
      id: record.snapshotId ?? t('commands.backup.snapshot.dryRunLabel'),
      image: formatBytes(record.imageBytes ?? 0),
      bytes: formatBytes(record.bytesUploaded ?? 0),
      chunks: record.chunksUploaded ?? 0,
      seconds: ((record.durationMs ?? 0) / 1000).toFixed(1),
    })
  );
  if (record.rehashReason) {
    outputService.info(t('commands.backup.snapshot.rehashReason', { reason: record.rehashReason }));
  }
  // 0 is an explicit "no cap"; only an absent field means the record did not report one.
  if (record.readCapBps === 0) {
    outputService.info(t('commands.backup.snapshot.readCapUnlimited'));
  } else if (record.readCapBps) {
    outputService.info(
      t('commands.backup.snapshot.readCap', { cap: formatBytes(record.readCapBps) })
    );
  }
  if (record.hashWorkers) {
    outputService.info(t('commands.backup.snapshot.hashWorkers', { workers: record.hashWorkers }));
  }
  // An enforced quota is always printed. A null quota below 100 means the machine has no systemd-run, and the summary must say so rather than print a limit that did not bind; a null quota at 100 means no ceiling was asked for, so nothing is printed.
  if (record.cpuLimitPercent && record.cpuQuota) {
    outputService.info(
      t('commands.backup.snapshot.cpuLimit', {
        percent: record.cpuLimitPercent,
        quota: record.cpuQuota,
      })
    );
  } else if (record.cpuLimitPercent && record.cpuLimitPercent < 100) {
    outputService.info(
      t('commands.backup.snapshot.cpuLimitUnenforced', { percent: record.cpuLimitPercent })
    );
  }
}

/**
 * `backup snapshot <repo> [--reseed] [--dry-run]`, upload a chunk-store
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
    .option('--bwlimit <rate>', t('commands.backup.snapshot.optionBwlimit'))
    .option('--parallelism <n>', t('commands.backup.snapshot.optionParallelism'))
    .option('--read-bwlimit <rate>', t('commands.backup.snapshot.optionReadBwlimit'))
    .option('--hash-parallelism <n>', t('commands.backup.snapshot.optionHashParallelism'))
    .option('--cpu-limit <percent>', t('commands.backup.snapshot.optionCpuLimit'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        repoRef: string,
        options: {
          reseed?: boolean;
          dryRun?: boolean;
          cold?: boolean;
          bwlimit?: string;
          parallelism?: string;
          readBwlimit?: string;
          hashParallelism?: string;
          cpuLimit?: string;
          debug?: boolean;
        }
      ) => {
        try {
          const uploadParams = snapshotUploadParams(options);
          const { repoKey, machineName } = await resolveRepoRef(repoRef);
          const result = await executeRepoFunction(
            'backup_snapshot',
            repoKey,
            machineName,
            {
              reseed: options.reseed ?? false,
              dry_run: options.dryRun ?? false,
              // Without this the cold path was reachable only from a scheduled unit or by SSH-ing to the machine: the generator emits --cold, but an operator wanting one application-consistent snapshot before a risky change had no supported route to it.
              cold: options.cold ?? false,
              ...uploadParams,
            },
            // captureOutput: the record carries rehashReason, readCapBps, hashWorkers and the snapshot id, which nothing else exposes; without it the step detector drops the verb's JSON and the run prints nothing.
            { debug: options.debug, captureOutput: true },
            {
              starting: t('commands.backup.snapshot.starting', { name: repoKey }),
              completed: t('commands.backup.snapshot.completed', { name: repoKey }),
              failed: t('commands.backup.snapshot.failed', { name: repoKey }),
            }
          );
          // A dry run moved nothing, so it must not be recorded as a stored backup: a run history that counts plans as backups would make the next operator believe a snapshot exists that never happened. Exit 16 is the renet verb's quota refusal and it is NOT a plain failure: the operator action is prune or upgrade, never debug. Flattening it to 1 (as this did) threw away a
          // distinction the verb deliberately encodes, and left the quotaRefused message with no call site at all.
          const quotaRefused = result.exitCode === RENET_QUOTA_REFUSED_EXIT;
          if (!options.dryRun) {
            // Three outcomes, kept distinct on purpose (see the note above): a quota refusal is not a generic failure.
            let runStatus = 'failed';
            if (result.success) {
              runStatus = 'stored';
            } else if (quotaRefused) {
              runStatus = 'quota-refused';
            }
            await recordBackupRun(repoKey, { kind: 'snapshot', status: runStatus });
          }
          if (result.success) printSnapshotRecord(result.stdout);
          if (quotaRefused) {
            outputService.warn(t('commands.backup.snapshot.quotaRefused', { name: repoKey }));
            setExitCode(RENET_QUOTA_REFUSED_EXIT);
          }
          // Any other failure keeps the exit code executeRepoFunction's renderer set (10 for a license refresh, for one); overwriting it with 1 lost that.
        } catch (error) {
          handleError(error);
        }
      }
    );
}

/** Register the chunk-store backup reads + verification under `rdc backup`. */
export function registerBackupStorageCommands(backup: Command): void {
  registerBackupUsage(backup);
  registerBackupManifests(backup);
  registerBackupVerify(backup);
  registerBackupBrowse(backup);
  registerBackupSnapshot(backup);
  registerBackupRetention(backup);
  registerBackupSnapshots(backup);
  registerBackupReconcile(backup);
}
