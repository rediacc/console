/**
 * `rdc incident status|export` over the account read API (PLAN-forensics-investigation D4, D7):
 * the incident record with its three deadline clocks, and a directory export of the incident's
 * window (record, timeline, aggregates, the raw chain manifest, the raw files under their
 * manifest keys and the verification of both chains over them). The export directory is an
 * evidence directory: `rdc forensics verify --dir <it>` repeats the check with no other input.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import type { VerificationReport } from '@rediacc/shared/forensics';
import { clockState, incidentClocks } from '@rediacc/shared/incident';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { VERSION } from '../../version.js';
import type { ForensicsClient, IncidentRecord, RawManifest } from './client.js';
import {
  isChainKey,
  isSafeEvidenceKey,
  manifestMachineKeys,
  RAW_MANIFEST_FILE,
  verifyEvidenceDir,
} from './evidence.js';
import type { ForensicsWindow } from './window.js';

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

/** The verification an export ran over the raw files it downloaded; null when it had none to check. */
export type ExportVerification = (VerificationReport & { files: number }) | null;

export interface ExportResult {
  incident: string;
  directory: string;
  files: string[];
  timelineRows: number;
  unreadable: number;
  rawFiles: number;
  rawTooLarge: boolean;
  verification: ExportVerification;
}

function writeJson(directory: string, name: string, value: unknown): string {
  writeFileSync(join(directory, name), `${JSON.stringify(value, null, 2)}\n`);
  return name;
}

/** Download every manifest file under its key; a key that would leave `target` is refused before any write. */
async function downloadRaw(
  client: ForensicsClient,
  investigationId: string,
  window: ForensicsWindow,
  manifest: RawManifest,
  target: string
): Promise<string[]> {
  const unsafe = manifest.files.find((f) => !isSafeEvidenceKey(f.key));
  if (unsafe) {
    throw new CliExitError(
      ERROR_CODES.SERVER_ERROR,
      t('forensics.badEvidenceKey', { key: unsafe.key })
    );
  }
  const written: string[] = [];
  for (const file of manifest.files) {
    const bytes = await client.rawFile(investigationId, window, file.key);
    const full = join(target, file.key);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, bytes);
    written.push(file.key);
  }
  return written;
}

/** Write the incident's window to `directory`, download the raw files and verify both chains over them. */
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
    writeJson(target, RAW_MANIFEST_FILE, manifest),
  ];
  const raw = manifest.tooLarge
    ? []
    : await downloadRaw(client, investigationId, window, manifest, target);
  files.push(...raw);
  let verification: ExportVerification = null;
  if (raw.some(isChainKey)) {
    verification = await verifyEvidenceDir(target, window, manifestMachineKeys(target));
    files.push(writeJson(target, 'verification.json', verification));
  }
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
      verified: verification === null ? null : verification.clean,
    })
  );
  return {
    incident: incident.id,
    directory: target,
    files,
    timelineRows: timeline.rows.length,
    unreadable: timeline.unreadable,
    rawFiles: raw.length,
    rawTooLarge: manifest.tooLarge,
    verification,
  };
}
