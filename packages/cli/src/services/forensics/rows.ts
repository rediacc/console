/**
 * The flow and file-open reads of one repo (`rdc repo flows|opens`): the timeline rows of the
 * window narrowed to one kind, with every gap row kept so a stretch with no evidence is
 * printed where it falls instead of reading as a quiet one.
 */
import { t } from '../../i18n/index.js';
import type { ForensicsClient, TimelineRow } from './client.js';
import type { ForensicsWindow } from './window.js';

export type RowKind = 'flow' | 'open';

export interface RowsRead {
  scope: { kind: 'repo'; ref: string };
  window: ForensicsWindow;
  kind: RowKind;
  rows: TimelineRow[];
  gaps: number;
  unreadable: number;
}

/** The rows of `kind` and every gap row, in the server's time order. */
function selectRows(rows: readonly TimelineRow[], kind: RowKind): TimelineRow[] {
  return rows.filter((row) => row.kind === kind || row.kind === 'gap');
}

function text(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

function flowLine(row: TimelineRow): string {
  const d = row.data ?? {};
  const name = text(d.dstName);
  const where = `${text(d.dstAddress)}:${text(d.dstPort)}${name ? ` (${name})` : ''}`;
  const network = [d.asn === undefined ? '' : `AS${text(d.asn)}`, text(d.country)]
    .filter(Boolean)
    .join(' ');
  return [
    row.ts,
    text(d.process) || '-',
    where,
    t('forensics.flowBytes', { out: text(d.bytesOut), in: text(d.bytesIn) }),
    network,
  ]
    .filter(Boolean)
    .join('  ');
}

function openLine(row: TimelineRow): string {
  const d = row.data ?? {};
  return [
    row.ts,
    text(d.process) || '-',
    text(d.path),
    d.sensitive === true ? t('forensics.sensitive') : '',
  ]
    .filter(Boolean)
    .join('  ');
}

function gapLine(row: TimelineRow): string {
  const d = row.data ?? {};
  return t('forensics.gapLine', {
    from: text(d.from) || row.ts,
    to: text(d.to) || row.ts,
    machine: text(d.machineId),
    reason: text(d.reason),
  });
}

function rowLine(row: TimelineRow): string {
  if (row.kind === 'gap') return gapLine(row);
  return row.kind === 'flow' ? flowLine(row) : openLine(row);
}

export function rowLines(read: RowsRead): string {
  if (read.rows.length === 0)
    return t(read.kind === 'flow' ? 'forensics.noFlows' : 'forensics.noOpens');
  const lines = read.rows.map(rowLine);
  if (read.unreadable > 0) lines.push(t('forensics.unreadable', { count: read.unreadable }));
  return lines.join('\n');
}

/** Open an investigation on the repo and read the window's rows of one kind. */
export async function readRepoRows(
  client: ForensicsClient,
  repoGuid: string,
  window: ForensicsWindow,
  kind: RowKind
): Promise<RowsRead> {
  const investigationId = await client.openInvestigation({ kind: 'repo', ref: repoGuid });
  const timeline = await client.timeline(investigationId, window);
  const rows = selectRows(timeline.rows, kind);
  return {
    scope: { kind: 'repo', ref: repoGuid },
    window,
    kind,
    rows,
    gaps: rows.filter((r) => r.kind === 'gap').length,
    unreadable: timeline.unreadable,
  };
}
