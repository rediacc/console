/**
 * `rdc backup repair <repo> [--dry-run]`: put back chunks the store lost or holds wrong.
 *
 * Three legs, in this order, because each is only safe after the one before it:
 *  1. `verify --store` finds the hashes the server cannot serve (missing) or serves wrong (corrupt).
 *  2. The account re-hashes each one, deletes the corrupt objects (a create-only PUT could not
 *     replace an object sitting at the key) and answers what it kept, what was already absent, and
 *     which snapshots name them. `--dry-run` stops here, asking with `dryRun: true`.
 *  3. The machine re-uploads from its backup anchor, re-hashing each cell first. A hash the anchor
 *     no longer holds is named as unrepairable, and the snapshots naming it stay damaged.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { resolveLineage } from './backup-storage-browse.js';
import { parseRepairRecord, type RepairRecord } from './backup-storage-parser.js';
import { runStoreVerify } from './backup-store-verify.js';

/** The route's cap per call (BACKUP_REPAIR_HASHES_MAX on the account): each hash is a whole-object read there. */
const REPAIR_BATCH = 200;

const REASON_NO_RECORD = 'the machine returned no readable repair record';

interface ServerRepairAnswer {
  deleted: string[];
  stillGood: string[];
  absent: string[];
  affectedSnapshots: string[];
}

/** The one document the verb prints. */
interface RepairReport {
  repo: string;
  lineage: string;
  /** `clean` (nothing to do), `dry-run`, or the machine's verdict: `repaired`, `partial`, `failed`. */
  status: 'clean' | 'dry-run' | 'repaired' | 'partial' | 'failed';
  checked: number;
  missing: string[];
  corrupt: string[];
  deleted: string[];
  stillGood: string[];
  absent: string[];
  affectedSnapshots: string[];
  uploaded?: string[];
  alreadyPresent?: string[];
  unrepairable?: { hash: string; reason: string }[];
  reason?: string;
}

async function askServer(
  lineageGuid: string,
  hashes: string[],
  dryRun: boolean
): Promise<ServerRepairAnswer> {
  const total: ServerRepairAnswer = {
    deleted: [],
    stillGood: [],
    absent: [],
    affectedSnapshots: [],
  };
  for (let i = 0; i < hashes.length; i += REPAIR_BATCH) {
    const answer = await accountServerFetch<ServerRepairAnswer>(
      '/account/api/v1/backups/chunks/repair',
      { method: 'POST', body: { lineageGuid, hashes: hashes.slice(i, i + REPAIR_BATCH), dryRun } }
    );
    total.deleted.push(...answer.deleted);
    total.stillGood.push(...answer.stillGood);
    total.absent.push(...answer.absent);
    total.affectedSnapshots.push(...answer.affectedSnapshots);
  }
  total.affectedSnapshots = [...new Set(total.affectedSnapshots)];
  return total;
}

/** Re-upload from the machine's anchor. A record that cannot be read is a failure, never a success. */
async function reuploadFromAnchor(
  repoKey: string,
  machineName: string,
  hashes: string[],
  debug: boolean | undefined
): Promise<RepairRecord> {
  const result = await getExecutor().execute({
    functionName: 'backup_repair',
    machineName,
    datastore: await recordedDatastoreMount(repoKey),
    params: { repository: repoKey, hashes: hashes.join(' ') },
    debug,
    captureOutput: true,
    probe: true,
  });
  const record = parseRepairRecord(result.stdout);
  if (!record) {
    return { status: 'failed', reason: result.error ?? REASON_NO_RECORD };
  }
  // The verb exits non-zero unless every hash went back; the exit code outranks a record that says otherwise.
  if (!result.success && record.status === 'repaired') {
    return { ...record, status: 'partial', reason: result.error };
  }
  return record;
}

/** Run the repair for one repository. */
async function runBackupRepair(
  repoRef: string,
  options: { dryRun?: boolean; debug?: boolean }
): Promise<RepairReport> {
  assertHostedBackupAccount();
  const { repoKey, machineName } = await resolveRepoRef(repoRef);
  const lineage = await resolveLineage(repoRef);
  const verdict = await runStoreVerify(lineage);
  const bad = [...new Set([...verdict.missing, ...verdict.corrupt])];
  const report: RepairReport = {
    repo: repoKey,
    lineage,
    status: 'clean',
    checked: verdict.checked,
    missing: verdict.missing,
    corrupt: verdict.corrupt,
    deleted: [],
    stillGood: [],
    absent: [],
    affectedSnapshots: [],
  };
  if (bad.length === 0) return report;

  const server = await askServer(lineage, bad, options.dryRun === true);
  Object.assign(report, server);
  if (options.dryRun) return { ...report, status: 'dry-run' };

  // What the machine must put back: every hash whose bad object is gone (deleted now or never there). A hash the server found good after all is left alone.
  const toUpload = [...new Set([...server.deleted, ...server.absent])];
  if (toUpload.length === 0) return { ...report, status: 'clean' };
  const record = await reuploadFromAnchor(repoKey, machineName, toUpload, options.debug);
  return {
    ...report,
    status: record.status,
    ...(record.uploaded && { uploaded: record.uploaded }),
    ...(record.alreadyPresent && { alreadyPresent: record.alreadyPresent }),
    ...(record.unrepairable && { unrepairable: record.unrepairable }),
    ...(record.reason && { reason: record.reason }),
  };
}

/** Print the one document, then the warnings, and set the exit code: anything short of a complete repair fails. */
function renderReport(report: RepairReport): void {
  const format = getOutputFormat();
  outputService.print(report, format === 'table' ? 'json' : format);
  if (report.status === 'clean') return;
  if (report.status === 'dry-run') {
    outputService.warn(
      t('commands.backup.repair.dryRunDamage', {
        count: report.missing.length + report.corrupt.length,
      })
    );
  }
  if (report.affectedSnapshots.length > 0 && report.status !== 'repaired') {
    outputService.warn(
      t('commands.backup.repair.affected', { snapshots: report.affectedSnapshots.join(', ') })
    );
  }
  if (report.status !== 'repaired') setExitCode(1);
}

export function registerBackupRepair(backup: Command): void {
  backup
    .command('repair')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.repair.description'))
    .option('--dry-run', t('commands.backup.repair.optionDryRun'))
    .option('--debug', t('options.debug'))
    .action(async (repoRef: string, options: { dryRun?: boolean; debug?: boolean }) => {
      try {
        renderReport(await runBackupRepair(repoRef, options));
      } catch (error) {
        handleError(error);
      }
    });
}
