/**
 * `rdc machine repair <name>` (D-remedy, X2): read the machine's coded findings, run the fixes its flags allow, and
 * re-check. `machine health` stays read-only; this verb is the only one that acts on a finding.
 *
 * - operator-only fixes never run: each is printed as the exact command.
 * - auto-with-backup fixes run only with `--with-backup`, after a successful snapshot of the affected repository.
 * - window-only fixes run only inside the machine's `maintenanceWindow` (`HH:MM-HH:MM`, UTC), or by hand with
 *   `--window-override`; a machine without a window never runs them on its own.
 * Each fix re-checks its finding first (a finding already gone runs nothing, so a second run reports zero actions),
 * is logged to the machine journal under the tag `rediacc-repair` and in the JSON `actions`, and the run ends with a
 * full re-check. Exit 0 when nothing is left, 1 when warnings or operator-only items are left, 2 when an error is left
 * or a fix failed.
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { MachineHealthResult } from '@rediacc/shared/services/machine';
import {
  type FindingSeverity,
  type FixAction,
  type HealthFinding,
  operatorCommand,
  severityExitCode,
} from '@rediacc/shared/services/machine/findings';
import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { type ExecuteResult, getExecutor } from '../../services/executor/executor-factory.js';
import { parseCapturedJson } from '../../services/executor/renet-output.js';
import { machineConnections } from '../../services/machine/machine-connection.js';
import { fetchMachineStatus } from '../../services/machine/machine-status.js';
import type { OutputFormat } from '../../types/index.js';
import { getOutputFormat, handleError, ValidationError } from '../../utils/errors.js';
import { loadGuidMap } from '../../utils/guid-resolver.js';
import { recordedDatastoreMount } from '../../utils/repo-executor.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { assertMachineExists } from '../_validate.js';
import { composeMachineHealth } from './health.js';

/** How one finding's fix ended in a repair run. */
type RepairResult =
  | 'ok'
  | 'failed'
  | 'planned'
  | 'skipped'
  | 'refused'
  | 'cancelled'
  | 'gone'
  | 'covered'
  | 'operator';

/** One finding's row in the run: what was due, what happened, and whether the finding is gone after the re-check. */
export interface RepairAction {
  code: string;
  subject: string;
  action: string;
  class: string;
  window_only: boolean;
  result: RepairResult;
  reason?: string;
  before: FindingSeverity;
  after?: 'present' | 'gone';
  detail?: string;
  command?: string;
}

export interface MachineRepairOptions {
  dryRun?: boolean;
  code?: string[];
  withBackup?: boolean;
  windowOverride?: boolean;
}

/** What a fix needs from the run: the repair() classes it may run and whether window-only work may run now. */
interface FixContext {
  allowClasses: string[];
  inWindow: boolean;
}

/** The machine-facing side of a repair run, injected so the decisions are testable without a machine. */
export interface RepairDeps {
  readHealth: () => Promise<MachineHealthResult>;
  runFix: (finding: HealthFinding, ctx: FixContext) => Promise<{ ok: boolean; detail?: string }>;
  snapshot: (finding: HealthFinding) => Promise<{ ok: boolean; detail?: string }>;
  journal: (machine: string, action: RepairAction) => Promise<void>;
  now: () => Date;
}

export interface RepairOutcome {
  machine: string;
  dryRun: boolean;
  window: string | null;
  inWindow: boolean;
  actions: RepairAction[];
  findings: HealthFinding[];
  exitCode: number;
}

const WINDOW_RE = /^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$/;

/** A `HH:MM-HH:MM` window as start and end minutes of the UTC day, or null when it does not parse. */
export function parseMaintenanceWindow(spec: string): { start: number; end: number } | null {
  const m = WINDOW_RE.exec(spec.trim());
  if (!m) return null;
  const start = Number(m[1]) * 60 + Number(m[2]);
  const end = Number(m[3]) * 60 + Number(m[4]);
  return start === end ? null : { start, end };
}

/** Whether `now` falls inside the window (which may wrap midnight); never true without a window. */
export function inMaintenanceWindow(spec: string | undefined, now: Date): boolean {
  if (!spec) return false;
  const w = parseMaintenanceWindow(spec);
  if (!w) return false;
  const minute = now.getUTCHours() * 60 + now.getUTCMinutes();
  return w.start < w.end
    ? minute >= w.start && minute < w.end
    : minute >= w.start || minute < w.end;
}

const findingKey = (f: Pick<HealthFinding, 'code' | 'subject'>): string =>
  `${f.code}\u0000${f.subject}`;

/** Fixes that act on the same thing run once per run, however many findings ask for them. */
function fixKey(f: HealthFinding): string {
  const action = f.fix?.action ?? '';
  switch (action) {
    case 'restart-traefik':
    case 'acme-anchor':
    case 'restart-repo-supervisors':
      return action;
    case 'trim-prune':
      return f.code === 'repo.disk.high'
        ? `${action}:${f.target?.repository ?? f.subject}`
        : action;
    case 'restart-container':
      return `${action}:${f.target?.container ?? f.subject}`;
    default:
      return `${action}:${f.target?.repository ?? f.subject}`;
  }
}

function baseAction(f: HealthFinding): Omit<RepairAction, 'result'> {
  const fix = f.fix as NonNullable<HealthFinding['fix']>;
  return {
    code: f.code,
    subject: f.subject,
    action: fix.action,
    class: fix.class,
    window_only: fix.window_only,
    before: f.severity,
  };
}

/** The decision for one finding before anything runs; undefined means it may run. */
function gate(
  f: HealthFinding,
  machine: string,
  opts: MachineRepairOptions,
  windowSpec: string | undefined,
  windowOk: boolean
): Pick<RepairAction, 'result' | 'reason' | 'command'> | undefined {
  const fix = f.fix as NonNullable<HealthFinding['fix']>;
  if (fix.class === 'operator-only') {
    return { result: 'operator', command: operatorCommand(f, machine) };
  }
  if (fix.class === 'auto-with-backup' && !opts.withBackup) {
    return { result: 'skipped', reason: t('commands.machine.repair.reasonNeedsBackup') };
  }
  if (fix.window_only && !windowOk) {
    return {
      result: 'refused',
      reason: windowSpec
        ? t('commands.machine.repair.reasonOutsideWindow', { window: windowSpec })
        : t('commands.machine.repair.reasonNoWindow'),
    };
  }
  if (opts.dryRun) return { result: 'planned' };
  return undefined;
}

/** The exit code of a finished run: 2 for a failed fix or an error left, 1 for a warning or an operator item left. */
export function repairExitCode(actions: RepairAction[], remaining: HealthFinding[]): number {
  if (actions.some((a) => a.result === 'failed')) return 2;
  let code = 0;
  for (const f of remaining) {
    code = Math.max(code, Math.min(2, severityExitCode(f.severity)));
    if (f.fix?.class === 'operator-only') code = Math.max(code, 1);
  }
  return code;
}

/** The mutable state of one run: the latest verdict, whether a fix has run since it was read, what ran. */
interface RunState {
  machine: string;
  opts: MachineRepairOptions;
  deps: RepairDeps;
  windowOk: boolean;
  current: MachineHealthResult;
  stale: boolean;
  ran: boolean;
  done: Set<string>;
  actions: RepairAction[];
}

/** The verdict as of now: re-read once a fix has run since the last read. */
async function freshHealth(state: RunState): Promise<MachineHealthResult> {
  if (state.stale) {
    state.current = await state.deps.readHealth();
    state.stale = false;
  }
  return state.current;
}

/**
 * The repair() classes a fix may run. With --with-backup, a repo repair or an auto-with-backup fix takes a snapshot
 * first: a good one adds auto-with-backup; a failed one cancels an auto-with-backup fix and leaves a repo repair at
 * auto-safe.
 */
async function backupClasses(
  f: HealthFinding,
  state: RunState
): Promise<{ allowClasses: string[]; reason?: string; cancel?: boolean }> {
  const needsSnapshot = f.fix?.class === 'auto-with-backup' || f.fix?.action === 'repo-repair';
  if (!state.opts.withBackup || !needsSnapshot) return { allowClasses: ['auto-safe'] };
  const snap = await state.deps.snapshot(f);
  if (snap.ok) return { allowClasses: ['auto-safe', 'auto-with-backup'] };
  const reason = t('commands.machine.repair.reasonSnapshotFailed', { detail: snap.detail ?? '' });
  return { allowClasses: ['auto-safe'], reason, cancel: f.fix?.class === 'auto-with-backup' };
}

/** Record a row; a row that acted (ran or was cancelled) also goes to the machine journal. */
async function record(state: RunState, action: RepairAction, journal = false): Promise<void> {
  state.actions.push(action);
  if (journal) await state.deps.journal(state.machine, action);
}

/** One finding through the gate, the dedupe, the re-check, the snapshot and the fix. */
async function processFinding(state: RunState, f: HealthFinding, windowSpec: string | undefined) {
  const row = baseAction(f);
  const decided = gate(f, state.machine, state.opts, windowSpec, state.windowOk);
  if (decided) return record(state, { ...row, ...decided });
  const key = fixKey(f);
  if (state.done.has(key)) return record(state, { ...row, result: 'covered' });
  const current = await freshHealth(state);
  if (!current.findings.some((c) => findingKey(c) === findingKey(f))) {
    return record(state, { ...row, result: 'gone' });
  }
  const classes = await backupClasses(f, state);
  if (classes.cancel) {
    return record(state, { ...row, result: 'cancelled', reason: classes.reason }, true);
  }
  state.done.add(key);
  const outcome = await state.deps.runFix(f, {
    allowClasses: classes.allowClasses,
    inWindow: state.windowOk,
  });
  state.ran = true;
  state.stale = true;
  return record(
    state,
    {
      ...row,
      result: outcome.ok ? 'ok' : 'failed',
      ...(classes.reason ? { reason: classes.reason } : {}),
      ...(outcome.detail ? { detail: outcome.detail } : {}),
    },
    true
  );
}

/**
 * Plan and run one repair (the decisions of D-remedy). Pure apart from `deps`: reads the findings, gates each by its
 * class, the window and the flags, re-checks before each fix, runs it, journals it, and re-checks at the end.
 */
export async function runMachineRepair(
  machine: string,
  windowSpec: string | undefined,
  opts: MachineRepairOptions,
  deps: RepairDeps
): Promise<RepairOutcome> {
  const inWindow = inMaintenanceWindow(windowSpec, deps.now());
  const state: RunState = {
    machine,
    opts,
    deps,
    windowOk: inWindow || opts.windowOverride === true,
    current: await deps.readHealth(),
    stale: false,
    ran: false,
    done: new Set<string>(),
    actions: [],
  };
  const codes = opts.code && opts.code.length > 0 ? new Set(opts.code) : undefined;
  const due = state.current.findings.filter((f) => f.fix && (!codes || codes.has(f.code)));
  for (const f of due) await processFinding(state, f, windowSpec);

  const final = state.ran ? await deps.readHealth() : state.current;
  const left = new Set(final.findings.map(findingKey));
  for (const a of state.actions) a.after = left.has(findingKey(a)) ? 'present' : 'gone';
  return {
    machine,
    dryRun: opts.dryRun === true,
    window: windowSpec ?? null,
    inWindow,
    actions: state.actions,
    findings: final.findings,
    exitCode: repairExitCode(state.actions, final.findings),
  };
}

// ── The real machine side ─────────────────────────────────────────

/** The `repository_repair` RepairReport fields the CLI reads. */
interface RenetRepairReport {
  ran?: number;
  failed?: number;
  files?: { file: string; result: string; reason?: string; detail?: string }[];
}

/** One renet call's result as a fix outcome. */
function callOutcome(result: ExecuteResult): { ok: boolean; detail?: string } {
  if (result.success) return { ok: true };
  return { ok: false, detail: result.error ?? result.stderr?.trim() ?? `exit ${result.exitCode}` };
}

/** The distinct network ids of the `rediacc-docker-N` units a renet.binary.replaced finding names, so a unit named twice is restarted once. */
export function supervisorNetworkIds(subject: string): number[] {
  return [...new Set([...subject.matchAll(/rediacc-docker-(\d+)/g)].map((m) => Number(m[1])))];
}

/** The repository_repair answer as a fix outcome: failed when a repair() failed, its files named. */
export function repoRepairOutcome(stdout: string | undefined): { ok: boolean; detail?: string } {
  let report: RenetRepairReport;
  try {
    report = parseCapturedJson<RenetRepairReport>(stdout);
  } catch (error) {
    return { ok: false, detail: error instanceof Error ? error.message : String(error) };
  }
  const files = (report.files ?? [])
    .filter((f) => f.result !== 'not-needed')
    .map((f) => `${f.file}: ${f.result}${f.reason ? ` (${f.reason})` : ''}`)
    .join('; ');
  return { ok: (report.failed ?? 0) === 0, ...(files ? { detail: files } : {}) };
}

async function machineDatastore(machine: string): Promise<string> {
  const config = await configService.getLocalConfig();
  const m = config.machines[machine] as { datastore?: string } | undefined;
  return m?.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
}

/** The config key of the repository a finding names by GUID, or undefined when this config does not hold it. */
async function repoKeyOf(f: HealthFinding): Promise<string | undefined> {
  const guid = f.target?.repository;
  if (!guid) return undefined;
  return (await loadGuidMap())[guid];
}

type Exec = (o: Parameters<ReturnType<typeof getExecutor>['execute']>[0]) => Promise<ExecuteResult>;
type FixOutcome = { ok: boolean; detail?: string };
type FixHandler = (
  f: HealthFinding,
  ctx: FixContext,
  env: { machine: string; exec: Exec; datastore: string }
) => Promise<FixOutcome>;

/** The repository a repo-scoped fix acts on, by config key and recorded datastore. */
async function repoScope(
  f: HealthFinding
): Promise<{ repoKey: string; datastore: string | undefined } | undefined> {
  const repoKey = await repoKeyOf(f);
  return repoKey ? { repoKey, datastore: await recordedDatastoreMount(repoKey) } : undefined;
}

const NO_REPOSITORY = (): FixOutcome => ({
  ok: false,
  detail: t('commands.machine.repair.reasonNoRepository'),
});

const trimPrune: FixHandler = async (f, _ctx, { machine, exec, datastore }) => {
  // A repo.disk.high finding is one repository's: without it named, an unscoped trim would reach every repository.
  if (f.code === 'repo.disk.high' && !f.target?.repository) return NO_REPOSITORY();
  const one = f.code === 'repo.disk.high' && f.target?.repository;
  return callOutcome(
    await exec({
      functionName: 'repository_trim',
      machineName: machine,
      datastore,
      params: {
        docker: true,
        docker_volumes: true,
        ...(one ? { name: f.target?.repository } : {}),
      },
    })
  );
};

const proxyFix =
  (restart: boolean): FixHandler =>
  async (_f, _ctx, { machine, exec, datastore }) =>
    callOutcome(
      await exec({
        functionName: 'proxy_acme_fix',
        machineName: machine,
        datastore,
        params: restart ? { restart: true } : {},
      })
    );

const restartSupervisors: FixHandler = async (f, _ctx, { machine, exec }) => {
  const ids = supervisorNetworkIds(f.subject);
  // Without the stale supervisors' ids the restart would reach every docker supervisor on the machine.
  if (ids.length === 0)
    return { ok: false, detail: t('commands.machine.repair.reasonNoNetworkIds') };
  return callOutcome(
    await exec({
      functionName: 'daemons-restart',
      machineName: machine,
      commandKind: {
        name: 'daemons-restart',
        args: { 'include-docker': true, 'network-ids': ids },
      },
    })
  );
};

const restartContainer: FixHandler = async (f, _ctx, { machine, exec }) => {
  const scope = await repoScope(f);
  if (!scope) return NO_REPOSITORY();
  return callOutcome(
    await exec({
      functionName: 'container_restart',
      machineName: machine,
      datastore: scope.datastore,
      params: { repository: scope.repoKey, container: f.target?.container ?? f.subject },
    })
  );
};

const repoRepair: FixHandler = async (f, ctx, { machine, exec }) => {
  const scope = await repoScope(f);
  if (!scope) return NO_REPOSITORY();
  const result = await exec({
    functionName: 'repository_repair',
    machineName: machine,
    datastore: scope.datastore,
    params: {
      repository: scope.repoKey,
      allow_classes: ctx.allowClasses.join(','),
      in_window: ctx.inWindow,
    },
  });
  return result.success ? repoRepairOutcome(result.stdout) : callOutcome(result);
};

/** The renet call behind each auto-run fix action. */
export const FIX_HANDLERS: Partial<Record<FixAction, FixHandler>> = {
  'trim-prune': trimPrune,
  'restart-traefik': proxyFix(true),
  'acme-anchor': proxyFix(false),
  'restart-repo-supervisors': restartSupervisors,
  'restart-container': restartContainer,
  'repo-repair': repoRepair,
};

export function realDeps(machine: string): RepairDeps {
  const exec: Exec = (o) => getExecutor().execute({ ...o, probe: true, captureOutput: true });
  return {
    readHealth: async () =>
      (await composeMachineHealth(machine, await fetchMachineStatus(machine))).health,
    now: () => new Date(),
    snapshot: async (f) => {
      const scope = await repoScope(f);
      if (!scope) return NO_REPOSITORY();
      return callOutcome(
        await exec({
          functionName: 'backup_snapshot',
          machineName: machine,
          datastore: scope.datastore,
          params: { repository: scope.repoKey },
        })
      );
    },
    runFix: async (f, ctx) => {
      const handler = f.fix ? FIX_HANDLERS[f.fix.action] : undefined;
      if (!handler) return { ok: false, detail: t('commands.machine.repair.reasonNoAction') };
      return handler(f, ctx, { machine, exec, datastore: await machineDatastore(machine) });
    },
    journal: async (m, action) => {
      let lease: Awaited<ReturnType<typeof machineConnections.acquire>> | undefined;
      try {
        lease = await machineConnections.acquire(m);
        await lease.sftp.exec(`logger -t rediacc-repair -- ${shellQuote(JSON.stringify(action))}`);
      } catch {
        // The journal line is a record, not a precondition: the JSON output carries the same row.
      } finally {
        lease?.release();
      }
    },
  };
}

const RESULT_KEY: Record<RepairResult, string> = {
  ok: 'commands.machine.repair.resultOk',
  failed: 'commands.machine.repair.resultFailed',
  planned: 'commands.machine.repair.resultPlanned',
  skipped: 'commands.machine.repair.resultSkipped',
  refused: 'commands.machine.repair.resultRefused',
  cancelled: 'commands.machine.repair.resultCancelled',
  gone: 'commands.machine.repair.resultGone',
  covered: 'commands.machine.repair.resultCovered',
  operator: 'commands.machine.repair.resultOperator',
};

/** One row of the text report. */
function printAction(a: RepairAction): void {
  // The code and subject are data; only the result word is copy.
  const line = `  ${a.code} ${a.subject}: ${t(RESULT_KEY[a.result])}`;
  if (a.result === 'failed') outputService.error(line);
  else if (a.result === 'ok' || a.result === 'gone') outputService.success(line);
  else outputService.info(line);
  for (const extra of [a.reason, a.detail]) if (extra) outputService.info(`    ${extra}`);
  if (a.command) outputService.info(t('commands.machine.repair.runByHand', { command: a.command }));
}

/** Print a finished run, as tables or as data. */
function renderRepairOutcome(outcome: RepairOutcome, format: OutputFormat): void {
  if (format === 'json') {
    outputService.print(
      {
        machine: outcome.machine,
        dry_run: outcome.dryRun,
        maintenance_window: outcome.window,
        in_window: outcome.inWindow,
        actions: outcome.actions,
        findings: outcome.findings,
        exitCode: outcome.exitCode,
      },
      format
    );
    return;
  }
  outputService.info(t('commands.machine.repair.header', { name: outcome.machine }));
  if (outcome.actions.length === 0) outputService.info(t('commands.machine.repair.nothingDue'));
  for (const a of outcome.actions) printAction(a);
  const ran = outcome.actions.filter((a) => a.result === 'ok' || a.result === 'failed').length;
  const failed = outcome.actions.filter((a) => a.result === 'failed').length;
  outputService.info(
    t('commands.machine.repair.summary', { ran, failed, remaining: outcome.findings.length })
  );
}

/** Store or clear the machine's maintenance window; an unparseable one is refused. */
async function setMaintenanceWindow(machine: string, spec: string): Promise<void> {
  if (spec === 'off') {
    await configService.updateMachine(machine, { maintenanceWindow: undefined });
    outputService.success(t('commands.machine.repair.windowCleared', { name: machine }));
    return;
  }
  if (!parseMaintenanceWindow(spec)) {
    throw new ValidationError(t('commands.machine.repair.windowInvalid', { window: spec }));
  }
  await configService.updateMachine(machine, { maintenanceWindow: spec });
  outputService.success(t('commands.machine.repair.windowSet', { name: machine, window: spec }));
}

export function registerRepairCommand(machine: Command): void {
  machine
    .command('repair')
    .summary(t('commands.machine.repair.descriptionShort'))
    .description(t('commands.machine.repair.description'))
    .argument('<name>', t('options.name'))
    .option('--dry-run', t('commands.machine.repair.optionDryRun'))
    .option(
      '--code <code>',
      t('commands.machine.repair.optionCode'),
      (v: string, acc: string[]) => [...acc, v],
      [] as string[]
    )
    .option('--with-backup', t('commands.machine.repair.optionWithBackup'))
    .option('--window-override', t('commands.machine.repair.optionWindowOverride'))
    .option('--set-window <window>', t('commands.machine.repair.optionSetWindow'))
    .action(async (name: string, options: MachineRepairOptions & { setWindow?: string }) => {
      try {
        await assertMachineExists(name);
        if (options.setWindow !== undefined) {
          await setMaintenanceWindow(name, options.setWindow);
          return;
        }
        const config = await configService.getLocalConfig();
        const windowSpec = (config.machines[name] as { maintenanceWindow?: string } | undefined)
          ?.maintenanceWindow;
        const outcome = await runMachineRepair(name, windowSpec, options, realDeps(name));
        renderRepairOutcome(outcome, getOutputFormat());
        if (outcome.exitCode !== 0) setExitCode(outcome.exitCode);
      } catch (error) {
        handleError(error);
      }
    });
}
