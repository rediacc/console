/**
 * The pure verdict folds of `machine health`: the repo-health read, the repo findings and the certificate dimension,
 * each folded into a MachineHealthResult. Split from health.ts, which owns the display and the machine calls.
 */

import type { MachineHealthResult } from '@rediacc/shared/services/machine';
import {
  type CertificatesSectionInput,
  type ChallengeSectionInput,
  checkAcmeChallengeCnames,
  checkCertificateExpiry,
} from '@rediacc/shared/services/machine/certificate-health';
import {
  type HealthFinding,
  severityExitCode,
  withFix,
} from '@rediacc/shared/services/machine/findings';
import { type ExecuteResult } from '../../services/executor/executor-factory.js';
import { isRenetFlagUnsupported } from '../../services/executor/job-client.js';
import { parseCapturedJson } from '../../services/executor/renet-output.js';
import type { RepoHealthFile, RepoHealthLevel } from '../repo-health.js';

/** One repository's report in renet's `repository health --all --strict` answer. */
export interface RepoHealthEntry {
  guid: string;
  name?: string;
  network_id?: number;
  state?: string;
  level: RepoHealthLevel;
  detail?: string;
  files?: RepoHealthFile[];
  error?: string;
}

/**
 * The repo-health read folded into `machine health`: `ok` with every mounted repo's report, `unsupported` when the
 * remote renet predates `--all --strict`, `failed` when the read itself failed.
 */
export type RepoHealthFold =
  | { status: 'ok'; repositories: RepoHealthEntry[] }
  | { status: 'unsupported'; repositories: [] }
  | { status: 'failed'; repositories: []; error: string };

const LEVELS = new Set<string>(['ok', 'warning', 'error', 'none']);
const REPO_HEALTH_READ_FAILED = 'repository health read failed';

/**
 * An older renet answers `--all` in one of two ways, both before running anything: cobra rejects the flag, or its
 * builder ignores the unknown `all` param and refuses the call for naming no repository.
 */
function isRepoHealthAllUnsupported(output: string): boolean {
  return isRenetFlagUnsupported(output) || /Repository name is required/.test(output);
}

/** Read the `repository_health --all --strict` result. Pure: the caller runs the call. */
export function foldRepoHealthResult(
  result: Pick<ExecuteResult, 'success' | 'error' | 'stdout' | 'stderr'>
): RepoHealthFold {
  const combined = `${result.stderr ?? ''}\n${result.stdout ?? ''}`;
  if (!result.success) {
    if (isRepoHealthAllUnsupported(combined)) return { status: 'unsupported', repositories: [] };
    return {
      status: 'failed',
      repositories: [],
      error: result.error ?? REPO_HEALTH_READ_FAILED,
    };
  }
  let parsed: { repositories?: unknown };
  try {
    parsed = parseCapturedJson<{ repositories?: unknown }>(result.stdout);
  } catch (error) {
    return {
      status: 'failed',
      repositories: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
  // An answer without the list is an older renet's single report: it ran without --all.
  if (!Array.isArray(parsed.repositories)) return { status: 'unsupported', repositories: [] };
  const repositories = (parsed.repositories as RepoHealthEntry[]).map((r) =>
    // A level renet did not send (or one this CLI does not know) is never read as healthy.
    LEVELS.has(r.level) ? r : { ...r, level: 'error' as const }
  );
  return { status: 'ok', repositories };
}

export const repoLabel = (r: RepoHealthEntry): string => r.name ?? r.guid;

function repoHealthDetail(r: RepoHealthEntry): string {
  if (r.error) return r.error;
  const files = (r.files ?? []).filter((f) => f.level === 'warning' || f.level === 'error');
  return files.map((f) => `${f.file} exit ${f.exit}${f.detail ? `: ${f.detail}` : ''}`).join('; ');
}

/** The finding of one repo whose health() is not ok; none for ok or "no check". */
function repoFinding(r: RepoHealthEntry): HealthFinding | null {
  if (r.level !== 'warning' && r.level !== 'error') return null;
  return withFix({
    code: r.level === 'warning' ? 'repo.health.warning' : 'repo.health.error',
    severity: r.level,
    subject: repoLabel(r),
    detail: repoHealthDetail(r),
    target: { repository: r.guid, networkId: r.network_id },
  });
}

/** The findings a repo-health read raises: one per repo not ok, or one for an older renet or a failed read. */
function repoHealthFindings(fold: RepoHealthFold, machineName: string): HealthFinding[] {
  if (fold.status === 'unsupported') {
    return [
      withFix({
        code: 'renet.repo-health.unsupported',
        severity: 'warning',
        subject: machineName,
        detail: `renet on ${machineName} predates repository health checks; update it with rdc machine setup ${machineName}`,
      }),
    ];
  }
  if (fold.status === 'failed') {
    return [
      withFix({
        code: 'repo.health.failed',
        severity: 'error',
        subject: machineName,
        detail: `repository health checks could not run: ${fold.error}`,
      }),
    ];
  }
  return fold.repositories.map(repoFinding).filter((f): f is HealthFinding => f !== null);
}

function findingIssue(f: HealthFinding): string {
  if (f.code === 'repo.health.warning' || f.code === 'repo.health.error') {
    return `Repository ${f.subject} health ${f.severity}${f.detail ? `: ${f.detail}` : ''}`;
  }
  return f.detail;
}

/**
 * Fold every repo's health() into the machine verdict (D-repohealth): a warning raises the exit code to 1, an error
 * to 2, each with one finding. A repo with no check adds nothing. An older renet is one warning
 * (`renet.repo-health.unsupported`), so the verdict is never green by error, and a failed read is exit 2.
 */
export function applyRepoHealth(
  health: MachineHealthResult,
  fold: RepoHealthFold,
  machineName: string
): MachineHealthResult {
  const repoFindings = repoHealthFindings(fold, machineName);
  const issues = [...health.issues, ...repoFindings.map(findingIssue)];
  const findings = [...health.findings, ...repoFindings];
  const exitCode = Math.max(
    health.exitCode,
    ...repoFindings.map((f) => severityExitCode(f.severity))
  );
  if (exitCode === health.exitCode) return { ...health, issues, findings };
  const message = exitCode >= 2 ? 'System has errors' : 'System has warnings';
  return { ...health, issues, findings, exitCode, healthy: false, message };
}

/** The listing's certificates section, read by both the expiry check (G5) and the shared-CNAME detector (G6). */
export type CertificatesListing = CertificatesSectionInput & ChallengeSectionInput;

/**
 * Fold the certificate dimension (D-certs) into the verdict: each `cert.expiry.near` finding names its certificate and
 * raises the exit code to 1 (under 21 days) or 2 (under 7), and each `acme.challenge.cname-shared` finding (G6) is a
 * warning naming the chain end and the names landing there. The section comes from the listing; a machine without the
 * proxy has none and raises nothing.
 */
export function applyCertificates(
  health: MachineHealthResult,
  section: CertificatesListing | null | undefined,
  now: Date = new Date()
): MachineHealthResult {
  const certFindings: HealthFinding[] = [
    ...checkCertificateExpiry(section, now),
    ...checkAcmeChallengeCnames(section),
  ].map((f) =>
    withFix({
      code: f.code,
      severity: f.severity,
      subject: f.subject,
      detail: f.detail,
    })
  );
  if (certFindings.length === 0) return health;
  const exitCode = Math.max(
    health.exitCode,
    ...certFindings.map((f) => severityExitCode(f.severity))
  );
  const findings = [...health.findings, ...certFindings];
  const issues = [...health.issues, ...certFindings.map((f) => f.detail)];
  if (exitCode === health.exitCode) return { ...health, issues, findings };
  const message = exitCode >= 2 ? 'System has errors' : 'System has warnings';
  return { ...health, issues, findings, exitCode, healthy: false, message };
}

/** The listing's certificates section; the generated ListResult type gains it with the next contract regeneration. */
export function certificatesOf(listResult: unknown): CertificatesListing | undefined {
  if (!listResult || typeof listResult !== 'object') return undefined;
  const section = (listResult as { certificates?: unknown }).certificates;
  return section && typeof section === 'object' ? (section as CertificatesListing) : undefined;
}
