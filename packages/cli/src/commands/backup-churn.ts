/**
 * `rdc backup churn <repo-ref> [--samples <n>] [--interval <duration>]`: measure how much of a
 * repository's image changes between runs, project what a fixed-grid chunk store would upload at
 * each cell size, and recommend one (W5, D-cells).
 *
 * Drives the machine's `backup_churn_probe` function. The probe keeps one reflink base under the
 * datastore, which pins extents until it is forgotten, so this verb ALWAYS removes the base when it
 * ends: after a success, after a failed probe, and when an error or an interrupt cuts it short.
 * The first probe of a repository is a `baseline` that compares nothing, so `--samples n` costs
 * `n + 1` probes and `n` intervals unless an earlier run left a base behind.
 */

import { parseDurationSeconds } from '@rediacc/shared/backup/duration';
import {
  type CellRecommendation,
  type ChurnProbeRecord,
  type ChurnSummary,
  summarizeChurn,
} from '@rediacc/shared/backup/rpo-cost';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { recordChurn } from '../services/backup/backup-churn-store.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';

const FUNCTION = 'backup_churn_probe';
const DEFAULT_SAMPLES = 3;
const MAX_SAMPLES = 48;
const DEFAULT_INTERVAL = '10m';
const MAX_INTERVAL_SECONDS = 86_400 - 1;

/** The last record on a probe's stdout: one JSON object per repository per run. */
function parseRecord(stdout: string | undefined): ChurnProbeRecord | undefined {
  let found: ChurnProbeRecord | undefined;
  for (const line of (stdout ?? '').split('\n')) {
    const start = line.indexOf('{');
    if (start === -1) continue;
    try {
      const parsed: unknown = JSON.parse(line.slice(start));
      if (parsed && typeof parsed === 'object' && 'status' in parsed) {
        found = parsed as ChurnProbeRecord;
      }
    } catch {
      // A stray log line must not hide a record that appears later in the buffer.
    }
  }
  return found;
}

export interface ChurnMeasurement {
  records: ChurnProbeRecord[];
  summary: ChurnSummary;
  /** A probe failed (the executor already rendered it) and sampling stopped. */
  failed: boolean;
  /** The reflink base is gone from the machine. */
  forgotten: boolean;
}

interface MeasureArgs {
  repoKey: string;
  machineName: string;
  samples: number;
  intervalSeconds: number;
  debug?: boolean;
  /** Wait between probes; a seam so a test does not sleep. */
  sleep?: (ms: number) => Promise<void>;
}

const realSleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** One call of the probe function, the record it printed, and whether the function succeeded. */
async function callProbe(
  args: MeasureArgs,
  forget: boolean,
  label: string
): Promise<{ record: ChurnProbeRecord | undefined; success: boolean }> {
  const result = await executeRepoFunction(
    FUNCTION,
    args.repoKey,
    args.machineName,
    { forget },
    // The record IS the answer, and a probe this verb reads must not hand back a background ticket.
    { debug: args.debug, captureOutput: true, probe: true },
    {
      starting: label,
      completed: t('commands.backup.churn.probed', { name: args.repoKey }),
      failed: t('commands.backup.churn.probeFailed', { name: args.repoKey }),
    }
  );
  return { record: parseRecord(result.stdout), success: result.success };
}

/**
 * Sample the repository's churn and remove the probe's base, whatever happens in between.
 * Exported because the strategy's estimate and `rdc backup churn` share one measurement.
 */
export async function measureChurn(args: MeasureArgs): Promise<ChurnMeasurement> {
  const sleep = args.sleep ?? realSleep;
  const records: ChurnProbeRecord[] = [];
  let failed = false;
  let forgottenPromise: Promise<boolean> | undefined;

  // Once: the interrupt path and the finally below must not both send the forget.
  const forget = (): Promise<boolean> => {
    forgottenPromise ??= callProbe(
      args,
      true,
      t('commands.backup.churn.forgetting', { name: args.repoKey })
    )
      .then(({ record, success }) => success && record?.status === 'forgotten')
      .catch(() => false);
    return forgottenPromise;
  };
  const onInterrupt = (): void => {
    void forget().finally(() => process.exit(130));
  };
  process.once('SIGINT', onInterrupt);

  let forgotten = false;
  try {
    const measured = (): number => records.filter((r) => r.status === 'measured').length;
    // The first probe of a fresh repository is a baseline, so one more probe than samples.
    for (let probe = 0; probe <= args.samples && measured() < args.samples; probe++) {
      if (probe > 0) await sleep(args.intervalSeconds * 1000);
      const { record, success } = await callProbe(
        args,
        false,
        t('commands.backup.churn.probing', { name: args.repoKey, probe: probe + 1 })
      );
      if (!success) {
        failed = true;
        break;
      }
      if (record) records.push(record);
    }
  } finally {
    process.off('SIGINT', onInterrupt);
    // Awaited in the finally so a thrown error still leaves no base behind.
    forgotten = await forget();
  }
  return { records, summary: summarizeChurn(records), failed, forgotten };
}

interface ChurnOptions {
  samples?: string;
  interval?: string;
  debug?: boolean;
}

function parseSamples(raw: string | undefined): number {
  if (raw === undefined) return DEFAULT_SAMPLES;
  if (!/^[1-9]\d*$/.test(raw) || Number(raw) > MAX_SAMPLES) {
    throw new ValidationError(
      t('commands.backup.churn.samplesInvalid', { value: raw, max: MAX_SAMPLES })
    );
  }
  return Number(raw);
}

function parseInterval(raw: string | undefined): number {
  const seconds = parseDurationSeconds(raw ?? DEFAULT_INTERVAL);
  if (seconds === undefined || seconds > MAX_INTERVAL_SECONDS) {
    throw new ValidationError(t('commands.backup.churn.intervalInvalid', { value: raw ?? '' }));
  }
  return seconds;
}

/** The projection, one row per cell size, then the recommendation. */
async function printProjection(summary: ChurnSummary): Promise<void> {
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const labels = Object.keys(summary.changedCellsPerRun ?? {}).sort(
    (a, b) => Number.parseInt(a, 10) - Number.parseInt(b, 10)
  );
  const rows = labels.map((cell) => ({
    cell,
    cells: Math.round((summary.changedCellsPerRun?.[cell] ?? 0) * 10) / 10,
    upload: formatSizeBytes(Math.round(summary.uploadBytesPerRun?.[cell] ?? 0)),
  }));
  outputService.print(
    outputService.format(rows, getOutputFormat(), [
      { key: 'cell', header: 'Cell size' },
      { key: 'cells', header: 'Cells / run', align: 'right' as const },
      { key: 'upload', header: 'Upload / run', align: 'right' as const },
    ])
  );
  const rec = summary.recommendation;
  if (rec) outputService.info(recommendationText(rec));
}

/** One literal key per rule, so each string is found by the key-usage gate and none is built at runtime. */
function recommendationText(rec: CellRecommendation): string {
  const params = { cell: `${rec.cellBytes / (1024 * 1024)} MiB`, savedPercent: rec.savedPercent };
  switch (rec.rule) {
    case 'scattered-small':
      return t('commands.backup.churn.recommend.scattered-small', params);
    case 'clustered-large':
      return t('commands.backup.churn.recommend.clustered-large', params);
    case 'collapse-cap':
      return t('commands.backup.churn.recommend.collapse-cap', params);
    case 'idle':
      return t('commands.backup.churn.recommend.idle', params);
    default:
      return t('commands.backup.churn.recommend.default', params);
  }
}

async function runChurn(repoRef: string, options: ChurnOptions): Promise<void> {
  const samples = parseSamples(options.samples);
  const intervalSeconds = parseInterval(options.interval);
  const { repoKey, machineName } = await resolveRepoRef(repoRef);

  const measurement = await measureChurn({
    repoKey,
    machineName,
    samples,
    intervalSeconds,
    debug: options.debug,
  });
  if (!measurement.forgotten) {
    // A base left behind pins extents until it rotates: name the repository so it can be removed by hand.
    outputService.warn(t('commands.backup.churn.forgetFailed', { name: repoKey }));
    setExitCode(1);
  }
  // The executor rendered the failure and set the exit code; nothing is projected from a failed run.
  if (measurement.failed) return;

  const { summary } = measurement;
  if (summary.samples === 0) {
    outputService.warn(
      t('commands.backup.churn.noMeasurement', {
        name: repoKey,
        baselines: summary.baselines,
        skipped: summary.skipped,
      })
    );
    setExitCode(1);
    return;
  }
  await recordChurn(repoKey, summary);

  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(
      { records: measurement.records, summary, forgotten: measurement.forgotten },
      format
    );
    return;
  }
  await printProjection(summary);
  if (measurement.forgotten) {
    outputService.success(t('commands.backup.churn.forgotten', { name: repoKey }));
  }
}

/** Register `backup churn <repo-ref> [--samples] [--interval]`. */
export function registerBackupChurn(backup: Command): void {
  backup
    .command('churn')
    .argument('<repo-ref>', t('options.repoRef'))
    .summary(t('commands.backup.churn.descriptionShort'))
    .description(t('commands.backup.churn.description'))
    .option('--samples <n>', t('commands.backup.churn.optionSamples'))
    .option('--interval <duration>', t('commands.backup.churn.optionInterval'))
    .option('--debug', t('options.debug'))
    .action(async (repoRef: string, options: ChurnOptions) => {
      try {
        await runChurn(repoRef, options);
      } catch (error) {
        handleError(error);
      }
    });
}
