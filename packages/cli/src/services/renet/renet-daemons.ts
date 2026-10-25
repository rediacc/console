/**
 * Moving renet daemons onto a replaced binary (C2) and saying which still run an old one (C4).
 *
 * After `machine setup` replaces renet, `renet daemons upgrade --json` restarts the hub units on the
 * new binary; when the remote renet predates that verb, a /proc probe still reports what is stale.
 * `machine status` and `machine health` read the same probe.
 */

import type { SFTPClient } from '../../remote/sftp/index.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { outputService } from '../core/output.js';

/** A renet process and the binary it runs. */
export interface RenetProcess {
  pid: number;
  /** The systemd unit the process belongs to, or '-' when it is outside one. */
  unit: string;
  /** /proc/<pid>/exe target; ends in " (deleted)" when the file was replaced under it. */
  exe: string;
}

/**
 * One exec that lists every renet process with its unit and binary, plus the binary `current`
 * resolves to. Reads /proc only (no renet call), so it answers on a machine whose renet predates
 * `daemons upgrade`. Output: one `pid<TAB>unit<TAB>exe<TAB>current` line per process.
 */
export function buildRenetProcessProbeCommand(currentPath: string): string {
  const script = [
    `cur=$(readlink -f ${currentPath} 2>/dev/null || true)`,
    'for d in /proc/[0-9]*; do',
    '  exe=$(readlink "$d/exe" 2>/dev/null) || continue',
    '  case "$exe" in */renet|*"/renet (deleted)") ;; *) continue ;; esac',
    `  unit=$(sed -n 's#^.*/\\([^/]*\\.service\\)$#\\1#p' "$d/cgroup" 2>/dev/null | head -n 1)`,
    '  printf "%s\\t%s\\t%s\\t%s\\n" "${d#/proc/}" "${unit:--}" "$exe" "$cur"',
    'done',
    'true',
  ].join('\n');
  return `sudo sh -c ${shellQuote(script)}`;
}

/**
 * The stale processes in a probe's output: those whose binary was deleted under them, or that run a
 * binary other than the one `current` resolves to. With no `current` link only deletion counts.
 */
export function parseStaleRenetProcesses(output: string): RenetProcess[] {
  const stale: RenetProcess[] = [];
  for (const line of output.split('\n')) {
    const [pidText, unit, exe, current] = line.split('\t');
    const pid = Number(pidText);
    if (!Number.isInteger(pid) || pid <= 0 || !exe) continue;
    const deleted = exe.endsWith(' (deleted)');
    const differs = Boolean(current) && exe !== current;
    if (deleted || differs) stale.push({ pid, unit: unit || '-', exe });
  }
  return stale.sort((a, b) => a.pid - b.pid);
}

/** The renet processes on a machine still running a replaced binary (machine status, health). */
export async function probeStaleRenetProcesses(
  sftp: Pick<SFTPClient, 'exec'>,
  currentPath: string
): Promise<RenetProcess[]> {
  return parseStaleRenetProcesses(await sftp.exec(buildRenetProcessProbeCommand(currentPath)));
}

/** What `renet daemons upgrade --json` did, or what is still stale when it could not run. */
export interface DaemonUpgradeReport {
  /** False when the remote renet has no `daemons upgrade` or it failed; `stale` then comes from the probe. */
  ran: boolean;
  restarted: RenetProcess[];
  stale: RenetProcess[];
  failed: (RenetProcess & { error?: string })[];
}

interface DaemonUpgradeEntry {
  pid?: unknown;
  unit?: unknown;
  exe?: unknown;
  action?: unknown;
  error?: unknown;
}

/**
 * Parse `renet daemons upgrade --json`: `{"processes":[{"pid","unit","exe","action","error"?}]}`
 * where action is `restarted` (a hub unit restarted on the new binary), `stale` (reported, not
 * restarted: a per-repo supervisor without --include-docker) or `failed`. Unknown actions count as
 * stale, so nothing a newer renet reports is dropped silently.
 */
export function parseDaemonUpgradeJson(output: string): Omit<DaemonUpgradeReport, 'ran'> {
  const parsed: unknown = JSON.parse(output);
  const entries: DaemonUpgradeEntry[] = Array.isArray(parsed)
    ? (parsed as DaemonUpgradeEntry[])
    : (((parsed as { processes?: unknown }).processes ?? []) as DaemonUpgradeEntry[]);
  const report: Omit<DaemonUpgradeReport, 'ran'> = { restarted: [], stale: [], failed: [] };
  for (const e of entries) {
    const proc = toRenetProcess(e);
    if (e.action === 'restarted') report.restarted.push(proc);
    else if (e.action === 'failed')
      report.failed.push({ ...proc, ...(typeof e.error === 'string' && { error: e.error }) });
    else if (e.action !== 'current') report.stale.push(proc);
  }
  return report;
}

function toRenetProcess(e: DaemonUpgradeEntry): RenetProcess {
  return {
    pid: Number(e.pid),
    unit: typeof e.unit === 'string' && e.unit ? e.unit : '-',
    exe: typeof e.exe === 'string' ? e.exe : '',
  };
}

function describeProcesses(procs: RenetProcess[]): string {
  return procs.map((p) => `${p.unit} (pid ${p.pid})`).join(', ');
}

/** Say what a daemon upgrade restarted and what is still stale. */
export function reportDaemonUpgrade(report: DaemonUpgradeReport): void {
  if (report.restarted.length > 0) {
    outputService.info(
      `Restarted renet daemons on the new binary: ${describeProcesses(report.restarted)}`
    );
  }
  for (const f of report.failed) {
    outputService.warn(
      `renet daemon restart failed: ${f.unit} (pid ${f.pid})${f.error ? `: ${f.error}` : ''}`
    );
  }
  if (report.stale.length > 0) {
    const how = report.ran
      ? 'Restart them with: rdc machine restart-services <machine> --include-docker'
      : 'This renet has no `daemons upgrade`; they keep the old binary until restarted';
    outputService.warn(
      `renet processes still running a replaced binary: ${describeProcesses(report.stale)}. ${how}`
    );
  }
}

/**
 * `renet daemons upgrade --json`: restart hub units still on a replaced binary one at a time and
 * report per-repo supervisors. When the remote renet cannot run it (an older binary, or a failure),
 * the /proc probe still says what is stale. Never throws: the binary update already happened.
 */
export async function upgradeDaemons(
  sftp: Pick<SFTPClient, 'exec'>,
  remoteInstallPath: string,
  currentPath: string
): Promise<DaemonUpgradeReport> {
  try {
    const output = await sftp.exec(
      `sudo ${shellQuote(remoteInstallPath)} daemons upgrade --json 2>/dev/null`
    );
    return { ran: true, ...parseDaemonUpgradeJson(output) };
  } catch {
    let stale: RenetProcess[] = [];
    try {
      stale = await probeStaleRenetProcesses(sftp, currentPath);
    } catch {
      stale = [];
    }
    return { ran: false, restarted: [], stale, failed: [] };
  }
}
