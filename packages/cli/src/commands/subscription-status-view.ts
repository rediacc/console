/**
 * The human view of `subscription status`: a table of the repositories this config holds, one line
 * summarising every other licence the account tracks, and the `--all` table of those others, which
 * `subscription retire --expired` lists too.
 */

import { shortGuid } from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import {
  LICENCE_STATE_KEYS,
  type LicenceRow,
  liveLicences,
  otherLicences,
} from '../services/account/license-retire.js';
import { outputService } from '../services/core/output.js';

type Cell = Record<string, string>;
type Column = { key: string; header: string };

function printTable(rows: Cell[], columns: Column[]): void {
  outputService.print(outputService.format(rows, 'table', columns), 'table');
}

const day = (value: string | null): string => value?.slice(0, 10) ?? '-';

function liveCell(row: LicenceRow): Cell {
  return {
    repo: String(row.name),
    machine: row.machine ?? '-',
    kind: row.kind ?? '-',
    state: t(LICENCE_STATE_KEYS[row.freshness]),
    refreshBy: day(row.refreshRecommendedAt),
    hardExpiry: day(row.hardExpiresAt),
  };
}

function otherCell(row: LicenceRow): Cell {
  const where =
    row.presence === 'deleted'
      ? 'commands.subscription.status.whereDeleted'
      : 'commands.subscription.status.whereAbsent';
  return {
    guid: shortGuid(row.guid),
    name: row.name ?? '-',
    kind: row.kind ?? '-',
    state: t(LICENCE_STATE_KEYS[row.freshness]),
    hardExpiry: day(row.hardExpiresAt),
    where: t(where),
  };
}

/** The table of licences of deleted or unknown repositories, for `status --all` and `retire --expired`. */
export function printOtherLicences(rows: LicenceRow[]): void {
  printTable(rows.map(otherCell), [
    { key: 'guid', header: t('commands.subscription.status.colGuid') },
    { key: 'name', header: t('commands.subscription.status.colName') },
    { key: 'kind', header: t('commands.subscription.status.colKind') },
    { key: 'state', header: t('commands.subscription.status.colState') },
    { key: 'hardExpiry', header: t('commands.subscription.status.colHardExpiry') },
    { key: 'where', header: t('commands.subscription.status.colWhere') },
  ]);
}

/** `1 deleted (valid), 107 not in this config (hard expired)`: the others counted by presence and state. */
function elsewhereItems(others: LicenceRow[]): string[] {
  const counts = new Map<string, { row: LicenceRow; count: number }>();
  for (const row of others) {
    const key = `${row.presence}/${row.freshness}`;
    const entry = counts.get(key) ?? { row, count: 0 };
    entry.count += 1;
    counts.set(key, entry);
  }
  return [...counts.values()]
    .sort((a, b) => {
      if (a.row.presence !== b.row.presence) return a.row.presence === 'deleted' ? -1 : 1;
      return a.row.freshness.localeCompare(b.row.freshness);
    })
    .map(({ row, count }) =>
      t(
        row.presence === 'deleted'
          ? 'commands.subscription.status.elsewhereDeleted'
          : 'commands.subscription.status.elsewhereAbsent',
        { count, state: t(LICENCE_STATE_KEYS[row.freshness]) }
      )
    );
}

/** The live table, its refresh hint, the one-line summary of the rest, and with `all` the table of the rest. */
export function renderLicenceView(rows: LicenceRow[], all: boolean): void {
  if (rows.length === 0) return;
  const live = liveLicences(rows);
  const others = otherLicences(rows);
  outputService.report(t('commands.subscription.status.licencesHeader'));
  if (live.length === 0) {
    outputService.report(t('commands.subscription.status.noLiveLicences'));
  } else {
    printTable(live.map(liveCell), [
      { key: 'repo', header: t('commands.subscription.status.colRepo') },
      { key: 'machine', header: t('commands.subscription.status.colMachine') },
      { key: 'kind', header: t('commands.subscription.status.colKind') },
      { key: 'state', header: t('commands.subscription.status.colState') },
      { key: 'refreshBy', header: t('commands.subscription.status.colRefreshBy') },
      { key: 'hardExpiry', header: t('commands.subscription.status.colHardExpiry') },
    ]);
  }
  if (live.some((row) => row.freshness !== 'valid')) {
    outputService.report(t('commands.subscription.status.refreshHint'));
  }
  if (others.length === 0) return;

  outputService.report(
    t('commands.subscription.status.elsewhereSummary', { items: elsewhereItems(others).join(', ') })
  );
  if (others.some((row) => row.freshness === 'hard_expired')) {
    outputService.report(t('commands.subscription.status.retireHint'));
  }
  if (all) {
    outputService.report(t('commands.subscription.status.othersHeader'));
    printOtherLicences(others);
  } else {
    outputService.report(t('commands.subscription.status.listHint'));
  }
}

/** The machine slots as a table: the id, when it was last seen, and whether it is soft-claimed beyond the limit. */
export function renderMachineTable(
  machines: { machineId: string; lastSeenAt: string; overLimit?: boolean }[]
): void {
  if (machines.length === 0) return;
  printTable(
    machines.map((m) => ({
      machine: `${m.machineId.slice(0, 12)}...`,
      lastSeen: m.lastSeenAt,
      state: m.overLimit ? t('commands.subscription.status.overLimitCell') : '-',
    })),
    [
      { key: 'machine', header: t('commands.subscription.status.colMachine') },
      { key: 'lastSeen', header: t('commands.subscription.status.colLastSeen') },
      { key: 'state', header: t('commands.subscription.status.colState') },
    ]
  );
}
