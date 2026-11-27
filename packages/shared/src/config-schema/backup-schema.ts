/**
 * Backup half of the config schema: destinations, retention, verification and
 * strategies. Split out of schemas.ts, which re-exports the public names.
 */

import { z } from 'zod';
import { parseDurationSeconds, rpoProblem } from '../backup/duration.js';
import { isValidCron } from './primitives.js';

// =============================================================================
// Backup strategy
// =============================================================================

// Fields shared by every destination kind.
const backupDestinationCommon = {
  name: z.string().min(1, 'Destination name cannot be empty'),
  enabled: z.boolean().optional(),
  bandwidthLimit: z.string().optional(),
};

/** A backup store id: a lowercase slug (`home`, `eu-west`, `office-rustfs`), unique per subscription. */
export const BACKUP_STORE_ID_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,62})$/;

const removedDestinationField = (field: string) =>
  z.never({
    error: `A backup destination no longer carries \`${field}\`: bucket credentials live on the account server. Register the store (\`POST /backups/stores\`) and name it with \`target\`.`,
  });

/**
 * A backup destination: the content-addressed chunk store. `target` names a store
 * registered on the account server (absent = `home`, the store every subscription
 * has), so no bucket credential sits in a config file. The removed `endpoint` and
 * `vaultContent` fields are refused with a message naming the replacement, and so
 * are destinations of the removed `storage` kind (or without a `kind`).
 */
export const BackupDestinationSchema = z
  .object({
    kind: z.literal('hosted-service'),
    ...backupDestinationCommon,
    target: z
      .string()
      .regex(
        BACKUP_STORE_ID_PATTERN,
        'A backup target is a store id: lowercase letters, digits and dashes'
      )
      .optional(),
    /** `upload` (absent) takes a machine snapshot into `target`; `replicate` has the account server copy `from` into `target`, so the machine uploads once. */
    mode: z.enum(['upload', 'replicate']).optional(),
    /** The source store of a replicate destination. Required for `replicate`, refused for `upload`. */
    from: z
      .string()
      .regex(
        BACKUP_STORE_ID_PATTERN,
        'A replication source is a store id: lowercase letters, digits and dashes'
      )
      .optional(),
    endpoint: removedDestinationField('endpoint').optional(),
    vaultContent: removedDestinationField('vaultContent').optional(),
  })
  .superRefine((dest, ctx) => {
    if (dest.mode === 'replicate' && dest.from === undefined) {
      ctx.addIssue({
        code: 'custom',
        path: ['from'],
        message: 'A replicate destination needs `from`, the store it copies from',
      });
    }
    if (dest.mode !== 'replicate' && dest.from !== undefined) {
      ctx.addIssue({
        code: 'custom',
        path: ['from'],
        message: '`from` belongs to a replicate destination; set `mode: replicate` or drop it',
      });
    }
  });

/**
 * GFS-style retention policy for a strategy's manifests.
 *
 * The CLI DECLARES this; the account server ENFORCES it (retentionPolicySweep
 * in private/account/src/services/backup-gc.service.ts, per lineage, on the
 * maintenance cron). Enforcement is server-side because the server holds the
 * only delete credential, and because the machine most likely to eat quota
 * forever is the one that died — a policy that only self-manages while a
 * machine is up is not self-managing.
 *
 * The semantics the server implements, stated exactly (the earlier wording
 * here, "unset = unbounded for that bucket", described no code and read the
 * opposite way round for a single-knob policy):
 * - `keepLast` keeps the N most recent snapshots regardless of time bucket.
 * - Each time knob keeps the most recent snapshot in each of the N most recent
 *   buckets that HAVE one — `keepDaily: 7` is "the last 7 days with a backup",
 *   not "the last 7 calendar days".
 * - Once ANY knob is set, an unset knob contributes nothing (restic/borg).
 * - A policy with EVERY knob unset declares no bound and keeps everything,
 *   which is what keeps `retention: {}` distinguishable from omitting
 *   `retention` entirely (the latter pushes no policy at all).
 * - The newest snapshot of a lineage is ALWAYS kept, whatever the policy says.
 *   A retention sweep must never empty a lineage.
 */
const RetentionPolicySchema = z.object({
  keepLast: z.number().int().min(0).optional(),
  keepHourly: z.number().int().min(0).optional(),
  keepDaily: z.number().int().min(0).optional(),
  keepWeekly: z.number().int().min(0).optional(),
  keepMonthly: z.number().int().min(0).optional(),
  keepYearly: z.number().int().min(0).optional(),
  /**
   * Keep every snapshot within this many seconds of the stream's NEWEST snapshot (not of now, so a
   * stream whose backups stop deletes nothing). Whole seconds and positive, like the wire field of
   * the same name; the CLI's `within=24h` parses to it. Adds to what the other knobs keep.
   */
  keepWithinSeconds: z.number().int().positive().optional(),
});

const CronSchema = z.string().refine(isValidCron, 'Must be a valid 5-field cron expression');

/**
 * Verification of a strategy's snapshots, run on the machine by the units `backup schedule` renders.
 *
 * - `spotAfterRun` (default true): the snapshot service ends with `backup verify --level spot`.
 * - `deepSchedule`: cron of the full-verify timer, which rotates one repository per run. Unset means a daily run at a
 *   time derived from the unit name, so a fleet does not verify in the same minute.
 * - `off`: renders neither the spot nor the timer. The failure report units stay, since they only speak on failure.
 *
 * Strict, because a misspelled key stripped silently would leave verification running when the operator turned it off.
 */
const BackupVerifySchema = z
  .object({
    off: z.boolean().optional(),
    spotAfterRun: z.boolean().optional(),
    deepSchedule: z
      .string()
      .refine(isValidCron, 'Must be a valid 5-field cron expression')
      .optional(),
  })
  .strict();

const DurationSchema = z
  .string()
  .refine(
    (v) => parseDurationSeconds(v) !== undefined,
    'Must be a duration such as 30s, 15m or 1h'
  );

/**
 * The declared protection target: how far behind a repository may fall. At least 5 minutes (decision
 * O6), and a length the timer can repeat evenly (see rpoProblem).
 */
const RpoSchema = DurationSchema.superRefine((value, ctx) => {
  const seconds = parseDurationSeconds(value);
  const problem = seconds === undefined ? undefined : rpoProblem(seconds);
  if (problem) ctx.addIssue({ code: 'custom', message: `Invalid rpo "${value}": ${problem}` });
});

const HOOK_FAILURE_POLICIES = ['continue', 'abort'] as const;

/**
 * One repository's own target and the per-repo run settings that ride with it. The repo gets its own
 * unit, so `rpo` is required; the rest is optional and left to the verb's defaults when absent.
 * Strict, because a misspelt key stripped silently would leave the repository on a default the
 * operator believed they had changed.
 *
 * - `cellSize`: grid cell size (`1M`, `4M`). A value that differs from the repository's recorded grid
 *   RE-SEEDS it, so the scheduled verb never carries the consent flag; changing it is an explicit act.
 * - `indexEvery`: how often the browse index is sealed.
 * - `hookTimeout` and `hookFailure`: bound and failure policy of the pre-backup hook.
 */
const RepoTargetSchema = z
  .object({
    rpo: RpoSchema,
    cellSize: z
      .string()
      .regex(/^\d+(\.\d+)?[KMGkmg]$/, 'Must be a size such as 1M or 4M')
      .optional(),
    indexEvery: DurationSchema.optional(),
    hookTimeout: DurationSchema.optional(),
    hookFailure: z.enum(HOOK_FAILURE_POLICIES).optional(),
  })
  .strict();

export const BackupStrategyConfigSchema = z.object({
  destinations: z.array(BackupDestinationSchema),
  schedule: CronSchema,
  mode: z.enum(['hot', 'cold']).optional(),
  enabled: z.boolean().optional(),
  bandwidthLimit: z.string().optional(),
  /** Read cap for hashing and cell reads, strategy level only (the read is local to the machine). Same grammar as bandwidthLimit; 0 = unlimited. */
  readBandwidthLimit: z.string().optional(),
  /** Hard CPU ceiling of a snapshot, strategy level: percent of ALL cores (1-100, 100 = no ceiling). Unset means the verb's default, 50. */
  cpuLimit: z.number().int().min(1).max(100).optional(),
  include: z.array(z.string()).optional(),
  exclude: z.array(z.string()).optional(),
  retention: RetentionPolicySchema.optional(),
  verify: BackupVerifySchema.optional(),
  /** The strategy's protection target. When set, the strategy's main unit renders from it instead of `schedule`. */
  rpo: RpoSchema.optional(),
  /** Run settings of the main unit; the same meaning as in a per-repo target. */
  indexEvery: DurationSchema.optional(),
  hookTimeout: DurationSchema.optional(),
  hookFailure: z.enum(HOOK_FAILURE_POLICIES).optional(),
  /**
   * Per-repo targets: EXACT repo ref (`name:tag`, or a bare `name` for the grand) -> target. The repo
   * gets its own unit and leaves the main unit's scope. A bare name no longer pulls in its forks
   * (`mail:*` asks for the family).
   */
  repoTargets: z.record(z.string(), RepoTargetSchema).optional(),
  /** Removed: replaced by `repoTargets`. Declared only so a stale config is refused by name instead of having the override stripped silently. */
  repoSchedules: z
    .never({ error: '`repoSchedules` was replaced by `repoTargets` (rpo per repository)' })
    .optional(),
});
