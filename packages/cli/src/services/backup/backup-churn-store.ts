/**
 * The churn measurements `rdc backup churn` leaves behind, and the estimate `backup strategy set
 * --rpo` prints from them (D-cost, D-rpo).
 *
 * A measurement is host-local convenience state, like `state.backupRuns`: the probe is the truth, and
 * a stale or missing entry only means the estimate is refused until the repository is measured again.
 * It lives in a sidecar under the config directory (`churn-probes/<config>.json`), not in the config's
 * `state` bucket, because the state schema is a synced, versioned contract and a measurement is
 * neither. A write failure never fails the measurement it records.
 */

import { promises as fs } from 'node:fs';
import { join } from 'node:path';
import {
  type ChurnSummary,
  estimateRpoCost,
  type RpoCostEstimate,
} from '@rediacc/shared/backup/rpo-cost';
import { getConfigDir } from '@rediacc/shared/paths';
import {
  getStorageQuotaBytesForPlan,
  PLAN_BACKUP_KEEP_WITHIN,
} from '@rediacc/shared/subscription/constants';
import { t } from '../../i18n/index.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import type { RpoDeps, RpoEstimateReport, RpoTargetAsk } from './backup-rpo-plan.js';

/** One repository's last measurement. */
interface StoredChurn {
  measuredAt: string;
  summary: ChurnSummary;
}

type Store = Record<string, StoredChurn>;

/** The cell size the estimate prices: the default grid, so the figure compares across repositories. */
const ESTIMATE_CELL_BYTES = 4 * 1024 * 1024;
const ESTIMATE_CELL_LABEL = '4MiB';
const DAY_SECONDS = 86_400;

function storePath(): string {
  return join(getConfigDir(), 'churn-probes', `${getEffectiveConfigName()}.json`);
}

async function readStore(): Promise<Store> {
  try {
    return JSON.parse(await fs.readFile(storePath(), 'utf8')) as Store;
  } catch {
    // Absent or unreadable: nothing measured yet.
    return {};
  }
}

/** Keep a repository's measurement. A summary with no measured sample is not stored: it says nothing about churn. */
export async function recordChurn(repoKey: string, summary: ChurnSummary): Promise<void> {
  if (summary.samples === 0) return;
  try {
    const store = await readStore();
    store[repoKey] = { measuredAt: new Date().toISOString(), summary };
    await fs.mkdir(join(getConfigDir(), 'churn-probes'), { recursive: true });
    await fs.writeFile(storePath(), JSON.stringify(store, null, 2), { mode: 0o600 });
  } catch {
    // Convenience state: the measurement already printed.
  }
}

/** The stored measurements for the repositories the ask names: one ref, or (strategy-level) every measured one. */
function measurementsFor(store: Store, ask: RpoTargetAsk): [string, StoredChurn][] {
  if (ask.ref === undefined) return Object.entries(store);
  // A target ref is `name`, `name:tag` or `name:*`; measurements are keyed by the repo key the probe ran against.
  const family = ask.ref.replace(/:\*$/, '');
  return Object.entries(store).filter(([key]) =>
    ask.ref?.endsWith(':*') ? key === family || key.startsWith(`${family}:`) : key === ask.ref
  );
}

const usd = (n: number): string => `$${n.toFixed(n < 1 ? 3 : 2)}`;
const gib = (n: number): string => `${n.toFixed(n < 10 ? 2 : 1)} GiB`;

/** The estimate lines of one target, from the cells its repositories were measured to change per run. */
function linesFor(
  name: string,
  rpoSeconds: number,
  cells: number,
  estimate: RpoCostEstimate
): string[] {
  const lines = [
    t('commands.backup.churn.estimate.target', {
      name,
      cells: Math.round(cells * 10) / 10,
      runs: Math.round(estimate.runsPerDay),
    }),
    t('commands.backup.churn.estimate.cost', {
      total: usd(estimate.totalUsd),
      classA: Math.round(estimate.monthlyClassA),
      classB: Math.round(estimate.monthlyClassB),
      storage: usd(estimate.storageUsd),
      window: gib(estimate.windowGiB),
      waiting: gib(estimate.waitingGiB),
    }),
  ];
  if (estimate.cap) {
    lines.push(
      estimate.cap.sustainable
        ? t('commands.backup.churn.estimate.capHeld', {
            waiting: gib(estimate.cap.steadyWaitingGiB),
            cap: gib(estimate.cap.capGiB),
          })
        : t('commands.backup.churn.estimate.capExceeded', {
            waiting: gib(estimate.cap.steadyWaitingGiB),
            cap: gib(estimate.cap.capGiB),
            days: estimate.cap.daysToCap === null ? '-' : estimate.cap.daysToCap.toFixed(1),
            seconds: rpoSeconds,
          })
    );
  }
  return lines;
}

/**
 * The production estimate: price each target from the stored measurement, or answer undefined when a
 * target has none (the verb then refuses without `--no-estimate`). The window priced is the plan's
 * default keep-within, one day when the plan is unknown, and the cap is against the plan's quota.
 */
export async function estimateFromStore(
  asks: RpoTargetAsk[],
  planCode: RpoDeps['planCode']
): Promise<RpoEstimateReport | undefined> {
  const store = await readStore();
  const plan = await planCode();
  const quotaBytes = plan ? getStorageQuotaBytesForPlan(plan) : undefined;
  const windowSeconds =
    plan && plan in PLAN_BACKUP_KEEP_WITHIN
      ? PLAN_BACKUP_KEEP_WITHIN[plan as keyof typeof PLAN_BACKUP_KEEP_WITHIN].defaultSeconds
      : null;
  const windowDays = (windowSeconds ?? DAY_SECONDS) / DAY_SECONDS;
  const lines: string[] = [];
  for (const ask of asks) {
    const found = measurementsFor(store, ask);
    if (found.length === 0) return undefined;
    // N per run, summed over the repositories the target covers: the largest sample, since a cap check must hold against the worst measured run.
    const cells = found.reduce(
      (sum, [, m]) => sum + (m.summary.maxChangedCellsPerRun?.[ESTIMATE_CELL_LABEL] ?? 0),
      0
    );
    const estimate = estimateRpoCost({
      changedCells: cells,
      cellBytes: ESTIMATE_CELL_BYTES,
      targetSeconds: ask.rpoSeconds,
      windowDays,
      ...(quotaBytes === undefined ? {} : { quotaBytes }),
    });
    lines.push(
      ...linesFor(ask.ref ?? found.map(([k]) => k).join(', '), ask.rpoSeconds, cells, estimate)
    );
  }
  return { lines };
}
