/**
 * `rdc backup snapshot`: the ad-hoc snapshot upload to the chunk store, run through the renet
 * `backup_snapshot` verb on the machine that holds the repo. Registered from backup-storage.ts.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  freeLicenseNoBackupMessage,
  isFreeLicenseBackupRefusal,
} from '../services/account/free-license.js';
import {
  bandwidthToBytesPerSecond,
  parseCpuLimitPercent,
  readCapBytesPerSecond,
} from '../services/backup/backup-strategy-validate.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { planStep } from '../services/jobs/steps.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { formatBytes } from '../utils/format.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { parseVerifyVerdict } from './backup-storage-parser.js';

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
export function registerBackupSnapshot(backup: Command): void {
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
            {
              debug: options.debug,
              captureOutput: true,
              // A dry run moved nothing, so it must not be recorded as a stored backup: a run history that counts plans as backups would make the next operator believe a snapshot exists that never happened. Exit 16 is the renet verb's quota refusal and it is NOT a plain failure: the operator action is prune or upgrade, never debug, so
              // the failure step records it as `quota-refused`. The run record rides the job's ticket, so a backgrounded snapshot is recorded when it finishes, not when it starts (PLAN-detached-jobs J4).
              job: {
                verb: 'backup snapshot',
                steps: options.dryRun
                  ? []
                  : [
                      planStep('recordBackupRun', {
                        repo: repoKey,
                        kind: 'snapshot',
                        status: 'stored',
                      }),
                      planStep('recordBackupRunFailed', {
                        repo: repoKey,
                        kind: 'snapshot',
                        quotaExit: RENET_QUOTA_REFUSED_EXIT,
                      }),
                    ],
              },
            },
            {
              starting: t('commands.backup.snapshot.starting', { name: repoKey }),
              completed: t('commands.backup.snapshot.completed', { name: repoKey }),
              failed: t('commands.backup.snapshot.failed', { name: repoKey }),
            }
          );
          if (result.state === 'running') return;
          const quotaRefused = result.exitCode === RENET_QUOTA_REFUSED_EXIT;
          if (result.success) printSnapshotRecord(result.stdout);
          if (quotaRefused) {
            outputService.warn(t('commands.backup.snapshot.quotaRefused', { name: repoKey }));
            setExitCode(RENET_QUOTA_REFUSED_EXIT);
          } else if (!result.success && isFreeLicenseBackupRefusal(result)) {
            // A Free License has no hosted backup plane (PLAN-free-license R13): the server refused the session, so name the way to one rather than leave the raw refusal as the last word.
            outputService.warn(freeLicenseNoBackupMessage());
          }
          // Any other failure keeps the exit code executeRepoFunction's renderer set (10 for a license refresh, for one); overwriting it with 1 lost that.
        } catch (error) {
          handleError(error);
        }
      }
    );
}
