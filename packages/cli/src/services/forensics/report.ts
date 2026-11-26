/**
 * Signed incident reports on the CLI (PLAN-forensics-reports D3, D6, FR9): `rdc incident export
 * --stage` asks the account server for a report and writes one format of it, and `rdc forensics
 * verify --report` checks a file against the public record and the published report key. The
 * signature covers the canonical bytes of the JSON report, so a JSON file is re-canonicalized
 * before hashing and a copy that differs only in whitespace or key order still verifies.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import { type CanonicalValue, canonicalBytes } from '@rediacc/shared/incident';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import type { ForensicsClient, IncidentRecord, ReportKey, ReportRecord } from './client.js';

const REPORT_STAGES = ['early-warning', 'notification', 'final'] as const;
type ReportStageName = (typeof REPORT_STAGES)[number];

const REPORT_FORMATS = ['pdf', 'json', 'stix'] as const;
type ReportFormatName = (typeof REPORT_FORMATS)[number];

const FILE_SUFFIX: Record<ReportFormatName, string> = {
  json: 'json',
  pdf: 'pdf',
  stix: 'stix.json',
};

export interface ExportReportOptions {
  stage: string;
  format?: string;
  out?: string;
}

export interface ExportedReport {
  incident: string;
  reportId: string;
  stage: ReportStageName;
  format: ReportFormatName;
  file: string;
  sha256: string;
  keyId: string;
}

function invalid(message: string): CliExitError {
  return new CliExitError(ERROR_CODES.VALIDATION_ERROR, message);
}

function isStage(value: string): value is ReportStageName {
  return (REPORT_STAGES as readonly string[]).includes(value);
}

function isFormat(value: string): value is ReportFormatName {
  return (REPORT_FORMATS as readonly string[]).includes(value);
}

/** The validated stage and format of an export, before any request leaves the machine. */
function parseReportOptions(options: ExportReportOptions): {
  stage: ReportStageName;
  format: ReportFormatName;
} {
  if (!isStage(options.stage)) {
    throw invalid(
      t('incident.badStage', { stage: options.stage, stages: REPORT_STAGES.join(', ') })
    );
  }
  const format = options.format ?? 'json';
  if (!isFormat(format)) {
    throw invalid(t('incident.badFormat', { format, formats: REPORT_FORMATS.join(', ') }));
  }
  return { stage: options.stage, format };
}

/** The bytes written for a downloaded body: raw for the PDF, canonical for the signed JSON, plain JSON for STIX. */
function reportBytes(format: ReportFormatName, body: unknown): Uint8Array {
  if (body instanceof Uint8Array) return body;
  if (format === 'json') return canonicalBytes(body as CanonicalValue);
  return new TextEncoder().encode(JSON.stringify(body));
}

/**
 * Generate one stage's report and write one format of it to `<out>/<report id>.<suffix>`; the
 * file name carries the report id that `verify --report` reads back.
 */
export async function exportReport(
  client: ForensicsClient,
  incident: IncidentRecord,
  options: ExportReportOptions
): Promise<ExportedReport> {
  const { stage, format } = parseReportOptions(options);
  const report = await client.generateReport(incident.id, stage);
  const body = await client.downloadReport(incident.id, report.id, format);
  const dir = options.out ?? `incident-${incident.id}`;
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `${report.id}.${FILE_SUFFIX[format]}`);
  writeFileSync(file, reportBytes(format, body));
  return {
    incident: incident.id,
    reportId: report.id,
    stage,
    format,
    file,
    sha256: report.sha256,
    keyId: report.keyId,
  };
}

export type ReportReason = 'unreadable' | 'hash' | 'signature' | 'key';

export type ReportVerdictResult =
  | { valid: true; id: string; stage: string; keyId: string; sha256: string }
  | { valid: false; id: string; reason: ReportReason };

const REPORT_FILE = /^([A-Za-z0-9][A-Za-z0-9-]{0,127})\.(?:stix\.json|json|pdf)$/;

/** The report id a downloaded file name carries, or the explicit `--id`. */
function reportIdOf(file: string, id: string | undefined): string {
  if (id !== undefined) return id;
  const match = REPORT_FILE.exec(basename(file));
  if (!match?.[1]) throw invalid(t('forensics.reportIdUnknown', { file }));
  return match[1];
}

const toHex = (bytes: Uint8Array) =>
  Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');

async function signatureHolds(
  key: ReportKey,
  bytes: Uint8Array,
  signature: string
): Promise<boolean | null> {
  let imported: CryptoKey;
  try {
    imported = await crypto.subtle.importKey(
      'spki',
      Buffer.from(key.publicKey, 'base64'),
      { name: 'Ed25519' },
      false,
      ['verify']
    );
  } catch {
    return null;
  }
  try {
    return await crypto.subtle.verify(
      'Ed25519',
      imported,
      Buffer.from(signature, 'base64'),
      bytes as Uint8Array<ArrayBuffer>
    );
  } catch {
    return false;
  }
}

/**
 * Check a downloaded JSON report against the server's public record and the published key. The
 * hash, the key id and the Ed25519 signature must all hold; a changed value fails at the hash.
 */
export async function verifyReportFile(
  client: ForensicsClient,
  file: string,
  id?: string
): Promise<ReportVerdictResult> {
  const reportId = reportIdOf(file, id);
  const raw = readFileSync(file);
  if (raw.subarray(0, 5).toString('latin1') === '%PDF-') {
    throw invalid(t('forensics.reportPdfNotCheckable', { file }));
  }
  const [record, key]: [ReportRecord, ReportKey] = await Promise.all([
    client.reportRecord(reportId),
    client.reportKey(),
  ]);
  let canonical: Uint8Array;
  try {
    canonical = canonicalBytes(JSON.parse(raw.toString('utf8')) as CanonicalValue);
  } catch {
    return { valid: false, id: reportId, reason: 'unreadable' };
  }
  const digest = await crypto.subtle.digest('SHA-256', canonical as Uint8Array<ArrayBuffer>);
  if (toHex(new Uint8Array(digest)) !== record.sha256) {
    return { valid: false, id: reportId, reason: 'hash' };
  }
  if (key.keyId !== record.keyId) return { valid: false, id: reportId, reason: 'key' };
  const holds = await signatureHolds(key, canonical, record.signature);
  if (holds === null) return { valid: false, id: reportId, reason: 'key' };
  if (!holds) return { valid: false, id: reportId, reason: 'signature' };
  return {
    valid: true,
    id: reportId,
    stage: record.stage,
    keyId: key.keyId,
    sha256: record.sha256,
  };
}
