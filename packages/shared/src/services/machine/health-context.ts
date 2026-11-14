/**
 * The shared state of one machine-health run, and the two helpers every check records through.
 * Split from parsing-health.ts so the per-area checks can live in their own files.
 */

import {
  type FindingSeverity,
  type FindingTarget,
  type HealthFinding,
  severityOfExit,
  withFix,
} from './findings.js';

/** Health check context passed between helper functions */
export interface HealthCheckContext {
  issues: string[];
  findings: HealthFinding[];
  exitCode: number;
}

/** One coded finding, its fix from the table; it raises the exit code to `exitCode`. */
export function raise(
  ctx: HealthCheckContext,
  exitCode: number,
  finding: { code: string; subject: string; detail: string; target?: FindingTarget },
  severity: FindingSeverity = severityOfExit(exitCode)
): void {
  ctx.findings.push(withFix({ ...finding, severity }));
  ctx.exitCode = Math.max(ctx.exitCode, exitCode);
}

/** An issue string and its finding: the issue text stays exactly what it was, the finding names each subject. */
export function issue(
  ctx: HealthCheckContext,
  exitCode: number,
  text: string,
  finding: { code: string; subject: string; target?: FindingTarget },
  severity?: FindingSeverity
): void {
  ctx.issues.push(text);
  raise(ctx, exitCode, { ...finding, detail: text }, severity);
}
