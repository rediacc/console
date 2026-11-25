/**
 * `rdc incident status|export` over the account read API (PLAN-forensics-investigation D4, D7):
 * the incident record with its three deadline clocks, and a directory export of the incident's
 * window (record, timeline, aggregates and the raw chain manifest).
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { clockState, incidentClocks } from '@rediacc/shared/incident';
import { t } from '../../i18n/index.js';
import { VERSION } from '../../version.js';
import type { ForensicsClient, IncidentRecord } from './client.js';

export interface ClockRow {
  name: 'earlyWarning' | 'notification' | 'finalReport';
  dueAt: string;
  state: string;
}

export interface IncidentView extends IncidentRecord {
  clocks: ClockRow[];
}

/** The incident with its early-warning, notification and final-report clocks as of `now`. */
export function withClocks(incident: IncidentRecord, now: Date = new Date()): IncidentView {
  const due = incidentClocks({ awareAt: incident.awareAt, notifiedAt: incident.notifiedAt });
  const notified = incident.notifiedAt !== null;
  return {
    ...incident,
    clocks: [
      {
        name: 'earlyWarning',
        dueAt: due.earlyWarningDue,
        state: clockState(due.earlyWarningDue, now, notified),
      },
      {
        name: 'notification',
        dueAt: due.notificationDue,
        state: clockState(due.notificationDue, now, notified),
      },
      {
        name: 'finalReport',
        dueAt: due.finalReportDue,
        state: clockState(due.finalReportDue, now, incident.closedAt !== null),
      },
    ],
  };
}

export function incidentListLines(incidents: readonly IncidentRecord[]): string {
  if (incidents.length === 0) return t('incident.none');
  return incidents
    .map((i) =>
      [i.id, i.status, `${i.scopeKind}:${i.scopeRef}`, i.declaredAt, i.windowFrom, i.windowTo].join(
        '  '
      )
    )
    .join('\n');
}

export function incidentDetailLines(view: IncidentView): string {
  const lines = [
    t('incident.detailHead', { id: view.id, status: view.status }),
    t('incident.detailScope', { kind: view.scopeKind, ref: view.scopeRef }),
    t('incident.detailWindow', { from: view.windowFrom, to: view.windowTo }),
    t('incident.detailDeclared', { by: view.declaredBy, at: view.declaredAt, aware: view.awareAt }),
  ];
  if (view.forkRef) lines.push(t('incident.detailFork', { ref: view.forkRef }));
  if (view.releaseAt) lines.push(t('incident.detailRelease', { at: view.releaseAt }));
  for (const step of view.steps) {
    lines.push(
      t('incident.detailStep', {
        name: step.name,
        status: step.status,
        at: step.at,
        detail: step.detail ?? '',
      }).trimEnd()
    );
  }
  for (const clock of view.clocks) {
    lines.push(clockLine(clock));
  }
  return lines.join('\n');
}

function clockLine(clock: ClockRow): string {
  const values = { at: clock.dueAt, state: clock.state };
  if (clock.name === 'earlyWarning') return t('incident.clockEarlyWarning', values);
  if (clock.name === 'notification') return t('incident.clockNotification', values);
  return t('incident.clockFinalReport', values);
}

export interface ExportResult {
  incident: string;
  directory: string;
  files: string[];
  timelineRows: number;
  unreadable: number;
  rawFiles: number;
  rawTooLarge: boolean;
}

function writeJson(directory: string, name: string, value: unknown): string {
  writeFileSync(join(directory, name), `${JSON.stringify(value, null, 2)}\n`);
  return name;
}

/** Write the incident's window to `directory` as JSON files; the investigation covers the incident's scope and window. */
export async function exportIncident(
  client: ForensicsClient,
  incident: IncidentRecord,
  directory: string,
  now: Date = new Date()
): Promise<ExportResult> {
  const window = { from: incident.windowFrom, to: incident.windowTo };
  const investigationId = await client.openInvestigation({
    kind: incident.scopeKind,
    ref: incident.scopeRef,
  });
  const timeline = await client.timeline(investigationId, window);
  const aggregates = await client.aggregates(investigationId, window);
  const manifest = await client.rawManifest(investigationId, window);

  const target = resolve(directory);
  mkdirSync(target, { recursive: true });
  const files = [
    writeJson(target, 'incident.json', withClocks(incident, now)),
    writeJson(target, 'timeline.json', { window, ...timeline }),
    writeJson(target, 'aggregates.json', aggregates),
    writeJson(target, 'raw-manifest.json', manifest),
  ];
  files.push(
    writeJson(target, 'export.json', {
      incident: incident.id,
      window,
      exportedAt: now.toISOString(),
      exporter: 'rdc incident export',
      toolVersion: VERSION,
      files: [...files],
      timelineRows: timeline.rows.length,
      unreadable: timeline.unreadable,
      raw: { files: manifest.files.length, bytes: manifest.bytes, tooLarge: manifest.tooLarge },
    })
  );
  return {
    incident: incident.id,
    directory: target,
    files,
    timelineRows: timeline.rows.length,
    unreadable: timeline.unreadable,
    rawFiles: manifest.files.length,
    rawTooLarge: manifest.tooLarge,
  };
}
