/**
 * Runtime converge: the CLI half of `renet runtime converge`
 * (agent/plans/PLAN-renet-runtime-converge.md, D1 and D5).
 *
 * A renet upload that changes the runtime layout leaves every running repo
 * daemon on the old one until it restarts. Renet plans and executes the
 * restarts, but only the CLI holds each repo's env-mode secrets
 * (`REDIACC_SECRET_*` live in the config, see services/state.ts), so the CLI
 * reads `renet runtime status --json`, decides, and dispatches the
 * `machine_converge_runtime` bridge function with a vault that carries every
 * repo's own env secrets. Renet hands each repo's child only its own.
 *
 * Every remote effect goes through an injected runner, so the decision logic
 * here is unit-tested without a machine.
 */

import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { RepositoryConfig } from '../../types/index.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { parseCapturedJson } from '../executor/renet-output.js';

/** The bridge function that runs `renet runtime converge`. */
export const CONVERGE_FUNCTION = 'machine_converge_runtime';

/** Opt-out of the automatic converge pass after a renet upload. */
export const SKIP_RUNTIME_CONVERGE_ENV = 'REDIACC_SKIP_RUNTIME_CONVERGE';

/** The opt-out of the router refresh `acquireRemoteRenet` honours too. */
const SKIP_ROUTER_RESTART_ENV = 'REDIACC_SKIP_ROUTER_RESTART';

/**
 * Functions the automatic pass never runs before: the converge itself (it
 * would trigger itself), and an uninstall, which removes the daemons anyway.
 */
const NO_AUTO_CONVERGE = new Set<string>([CONVERGE_FUNCTION, 'machine_uninstall']);

export type RuntimePolicy = 'epoch' | 'always';
export const RUNTIME_POLICIES = ['epoch', 'always'] as const satisfies readonly RuntimePolicy[];

/** One repository in `renet runtime status --json`. */
interface RuntimeRepoStatus {
  guid: string;
  name?: string;
  /** `current`, `stale` or `inactive`. */
  state: string;
  reasons: string[];
  network_id: number;
  container_count?: number;
}

/** `renet runtime status --json`. */
export interface RuntimeStatus {
  runtime_epoch: number;
  renet_sha256?: string;
  policy: string;
  repos: RuntimeRepoStatus[];
  stale: number;
  pending: boolean;
}

/**
 * One refusal of the converge preflight (renet pkg/convergeguard): a container
 * the current layout's Docker API gate would refuse, so the repo was skipped
 * as `gate_refused`, `unmanaged_containers` or `needs_device_grant` and keeps running on the old layout.
 */
export interface ConvergeDenial {
  /** The compose service, or the container name for a live container; empty for a whole-file refusal. */
  service: string;
  /** `compose` or `container`. */
  source: string;
  field: string;
  tier: string;
  message: string;
  /** `gate_refused`, `unmanaged_containers` (a running container no Rediaccfile up() recreates) or `needs_device_grant`. */
  kind: string;
}

/** One repository's outcome in `renet runtime converge --json`. */
interface ConvergeResultRow {
  guid: string;
  name?: string;
  status: string;
  reason?: string;
  error?: string;
  network_id: number;
  duration_ms?: number;
  denials?: ConvergeDenial[];
  stale_unhandled?: boolean;
  manual?: boolean;
}

export interface ConvergeSummary {
  total: number;
  converged: number;
  would_converge: number;
  skipped: number;
  failed: number;
  pending: number;
  current?: number;
  inactive?: number;
  stale_unhandled?: number;
  manual?: number;
}

/** `renet runtime converge --json`. */
export interface ConvergeReport {
  policy: string;
  runtime_epoch: number;
  dry_run: boolean;
  aborted: boolean;
  resume_command?: string;
  plan: {
    guid: string;
    name?: string;
    action: string;
    stale_reasons?: string[];
    denials?: ConvergeDenial[];
  }[];
  results: ConvergeResultRow[];
  summary: ConvergeSummary;
  /** Why the pass stopped before or while planning (a lock it could not take, an unreadable repo list). */
  error?: string;
}

/** The counts the summary line prints, taken from the results themselves. */
export interface ConvergeCounts {
  converged: number;
  wouldConverge: number;
  skipped: number;
  failed: number;
  pending: number;
  staleUnhandled: number;
  manual: number;
}

/**
 * Count the results by status. The summary line reads these, not the
 * report's own summary, so it always matches the lines printed above it.
 */
export function countConvergeResults(report: ConvergeReport): ConvergeCounts {
  const count = (status: string) => report.results.filter((r) => r.status === status).length;
  const unhandled = report.results.filter((r) => r.stale_unhandled === true);
  return {
    converged: count('converged'),
    wouldConverge: count('would_converge'),
    skipped: count('skipped'),
    failed: count('failed'),
    pending: count('pending'),
    staleUnhandled: unhandled.length,
    manual: unhandled.filter((r) => r.manual === true).length,
  };
}

/** The flags of `rdc machine converge`, mapped onto the bridge function's params. */
export interface ConvergeOptions {
  dryRun?: boolean;
  policy?: RuntimePolicy;
  includeUnknown?: boolean;
  continueOnError?: boolean;
}

export function isRuntimeConvergeOptedOut(env: NodeJS.ProcessEnv = process.env): boolean {
  return env[SKIP_RUNTIME_CONVERGE_ENV] === '1';
}

/**
 * Whether the executor reads the runtime status before `functionName`: only
 * right after this run uploaded a new renet, never for the converge itself or
 * an uninstall, and not when opted out.
 */
export function shouldCheckRuntimeAfterUpload(
  functionName: string,
  uploaded: boolean,
  env: NodeJS.ProcessEnv = process.env
): boolean {
  return uploaded && !NO_AUTO_CONVERGE.has(functionName) && !isRuntimeConvergeOptedOut(env);
}

export function buildRuntimeStatusCommand(
  remoteRenetPath: string,
  datastore: string,
  policy?: RuntimePolicy
): string {
  const policyFlag = policy ? ` --policy ${shellQuote(policy)}` : '';
  return `sudo ${shellQuote(remoteRenetPath)} runtime status --json --datastore ${shellQuote(datastore)}${policyFlag}`;
}

function isRuntimeStatus(value: unknown): value is RuntimeStatus {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.stale === 'number' && Array.isArray(v.repos);
}

function parseRuntimeStatus(stdout: string): RuntimeStatus {
  const parsed = parseCapturedJson<unknown>(stdout);
  if (!isRuntimeStatus(parsed)) {
    throw new Error(`unexpected runtime status payload: ${stdout.slice(0, 160)}`);
  }
  return parsed;
}

/** Run `renet runtime status --json` on the machine. Throws when it fails. */
export async function readRuntimeStatus(
  sftp: Pick<SFTPClient, 'exec'>,
  remoteRenetPath: string,
  datastore: string,
  policy?: RuntimePolicy
): Promise<RuntimeStatus> {
  const stdout = await sftp.exec(buildRuntimeStatusCommand(remoteRenetPath, datastore, policy));
  return parseRuntimeStatus(stdout);
}

/** Every repository's env-mode secrets as `REDIACC_SECRET_<NAME>`, keyed by GUID. */
export function collectEnvSecretsByGuid(
  repos: { config: RepositoryConfig }[]
): Map<string, Record<string, string>> {
  const byGuid = new Map<string, Record<string, string>>();
  for (const { config } of repos) {
    const env: Record<string, string> = {};
    for (const [name, entry] of Object.entries(config.secrets ?? {})) {
      if (entry.mode === 'env') env[`REDIACC_SECRET_${name}`] = entry.value;
    }
    if (Object.keys(env).length > 0) byGuid.set(config.repositoryGuid, env);
  }
  return byGuid;
}

/**
 * Add `env_secrets` to the converge vault's repository entries. Only the
 * repositories the machine reported (`machineGuids`) get theirs, so a machine
 * never receives the env secrets of a repo it does not hold. Each entry gets
 * its own GUID's secrets and no other's.
 */
export function injectConvergeEnvSecrets(
  vaultJson: string,
  envByGuid: Map<string, Record<string, string>>,
  machineGuids: ReadonlySet<string>
): string {
  const vault = JSON.parse(vaultJson) as { repositories?: Record<string, Record<string, unknown>> };
  for (const entry of Object.values(vault.repositories ?? {})) {
    const guid = typeof entry.guid === 'string' ? entry.guid : '';
    const env = envByGuid.get(guid);
    if (env && machineGuids.has(guid)) entry.env_secrets = { ...env };
  }
  return JSON.stringify(vault);
}

/**
 * The converge vault: the base vault (every repository's GUID, network id,
 * password and file secrets, the same entries up-all ships) plus the env
 * secrets of the repositories `status` lists on this machine.
 */
export async function prepareConvergeVault(
  baseVault: string,
  status: RuntimeStatus
): Promise<string> {
  const repos = await configService.listRepositories();
  const machineGuids = new Set(status.repos.map((r) => r.guid));
  return injectConvergeEnvSecrets(baseVault, collectEnvSecretsByGuid(repos), machineGuids);
}

export function buildConvergeParams(options: ConvergeOptions): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  if (options.dryRun) params.dry_run = true;
  if (options.policy) params.policy = options.policy;
  if (options.includeUnknown) params.include_unknown = true;
  if (options.continueOnError) params.continue_on_error = true;
  return params;
}

function isConvergeReport(value: unknown): value is ConvergeReport {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return Array.isArray(v.results) && typeof v.summary === 'object' && v.summary !== null;
}

/** The converge report in a captured function stdout, or null when there is none. */
export function parseConvergeReport(stdout: string | undefined): ConvergeReport | null {
  try {
    const parsed = parseCapturedJson<unknown>(stdout);
    return isConvergeReport(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function convergeResumeCommand(machineName: string): string {
  return `rdc machine converge ${machineName}`;
}

/** One preflight denial as a line: an unmanaged container is "not recreated", any other kind "refused". */
function denialText(d: ConvergeDenial): string {
  const service = d.service || d.source;
  return d.kind === 'unmanaged_containers'
    ? t('commands.machine.converge.unmanagedLine', { service, message: d.message })
    : t('commands.machine.converge.denialLine', { service, field: d.field, message: d.message });
}

/**
 * Print the plan line, one line per repository (a skipped repo with its
 * reason and each preflight denial), the error that stopped the pass early,
 * and a summary counted from the results: a real pass reports `converged`, a
 * dry run `would converge`, never one under the other's name.
 */
export function renderConvergeReport(report: ConvergeReport, machineName: string): void {
  const stale = report.plan.filter((e) => (e.stale_reasons ?? []).length > 0).length;
  outputService.info(
    t('commands.machine.converge.planLine', {
      stale,
      total: report.plan.length,
      policy: report.policy,
      epoch: report.runtime_epoch,
    })
  );
  report.results.forEach((r, i) => {
    let detail = r.status;
    if (r.reason) detail += ` (${r.reason})`;
    if (r.error) detail += `: ${r.error}`;
    outputService.info(
      t('commands.machine.converge.repoLine', {
        index: i + 1,
        count: report.results.length,
        name: r.name ?? r.guid,
        networkId: r.network_id,
        detail,
      })
    );
    for (const d of r.denials ?? []) outputService.info(denialText(d));
  });
  if (report.error) {
    outputService.warn(t('commands.machine.converge.passError', { error: report.error }));
  }
  const c = countConvergeResults(report);
  const counts = { skipped: c.skipped, failed: c.failed, pending: c.pending };
  outputService.info(
    report.dry_run
      ? t('commands.machine.converge.summaryLineDryRun', { would: c.wouldConverge, ...counts })
      : t('commands.machine.converge.summaryLine', { converged: c.converged, ...counts })
  );
  // A manual-only stale_unhandled pass (hub, immutable) has nothing a resume could fix.
  const resumable = c.staleUnhandled > c.manual && !report.dry_run;
  if (report.aborted || report.error || c.failed > 0 || resumable) {
    outputService.warn(
      t('commands.machine.converge.resume', { command: convergeResumeCommand(machineName) })
    );
  }
}

/**
 * Whether the router is refreshed after a converge pass (decision 2: the
 * router switches layout after the repos did, never before).
 *
 * - No pass ran (nothing stale, opted out, status unreadable): the refresh the
 *   upload owed, if any.
 * - A dry run: the owed refresh only when no repo would move, since refreshing
 *   would drop the routes of the repos still on the old layout.
 * - A real pass: the owed refresh, or any repo converged (an upload whose
 *   refresh was skipped earlier, by a dry run or an opt-out, is otherwise
 *   never repaid).
 *
 * `REDIACC_SKIP_ROUTER_RESTART=1` or `skipRouterRestart` wins over all of it.
 */
export function routerRefreshAfterPass(input: {
  due: boolean;
  dryRun?: boolean;
  summary?: ConvergeSummary | null;
  skipRouterRestart?: boolean;
  env?: NodeJS.ProcessEnv;
}): boolean {
  const env = input.env ?? process.env;
  if (input.skipRouterRestart === true || env[SKIP_ROUTER_RESTART_ENV]) return false;
  const summary = input.summary;
  if (!summary) return input.due;
  if (input.dryRun) return input.due && summary.would_converge === 0;
  return input.due || summary.converged > 0;
}

/** What a dispatched converge run returns; the subset of ExecuteResult this module reads. */
interface ConvergeRunResult {
  success: boolean;
  stdout?: string;
  error?: string;
}

export interface AutoConvergeDeps {
  sftp: Pick<SFTPClient, 'exec'>;
  remoteRenetPath: string;
  machineName: string;
  datastore: string;
  /** Builds the converge vault (function name and params already set) before the env secrets are added. */
  buildBaseVault: (params: Record<string, unknown>) => string;
  /** Runs the converge vault on the machine with output captured. */
  run: (vault: string, params: Record<string, unknown>) => Promise<ConvergeRunResult>;
  /** Refreshes the router; returns whether it restarted. */
  refreshRouter: () => Promise<boolean>;
  debug?: boolean;
}

export interface AutoConvergeOutcome {
  /** Whether a converge pass ran. */
  converged: boolean;
  report: ConvergeReport | null;
  routerRefreshed: boolean;
}

/**
 * The pass the executor runs after uploading renet and `machine setup` runs
 * after setup: read the status, converge when a repo is stale, then refresh
 * the router when {@link routerRefreshAfterPass} says so. A failed status read
 * or a failed pass is a warning naming the resume command, never a failure of
 * the operation the user asked for.
 */
export async function convergeIfStale(
  deps: AutoConvergeDeps,
  input: { checkRuntime: boolean; routerRefreshDue: boolean; skipRouterRestart?: boolean }
): Promise<AutoConvergeOutcome> {
  let report: ConvergeReport | null = null;
  let ran = false;
  if (input.checkRuntime) {
    ({ report, ran } = await runStalePass(deps));
  }
  const refresh = routerRefreshAfterPass({
    due: input.routerRefreshDue,
    summary: report?.summary ?? null,
    skipRouterRestart: input.skipRouterRestart,
  });
  let routerRefreshed = false;
  if (refresh) {
    routerRefreshed = await deps.refreshRouter();
    if (routerRefreshed) {
      outputService.info(
        t('commands.machine.converge.routerRefreshed', { machine: deps.machineName })
      );
    }
  }
  return { converged: ran, report, routerRefreshed };
}

async function runStalePass(
  deps: AutoConvergeDeps
): Promise<{ report: ConvergeReport | null; ran: boolean }> {
  let status: RuntimeStatus;
  try {
    status = await readRuntimeStatus(deps.sftp, deps.remoteRenetPath, deps.datastore);
  } catch (error) {
    outputService.warn(
      t('commands.machine.converge.statusUnreadable', {
        machine: deps.machineName,
        error: error instanceof Error ? error.message : String(error),
      })
    );
    return { report: null, ran: false };
  }
  if (status.stale === 0) {
    if (deps.debug) {
      outputService.info(
        t('commands.machine.converge.nothingStale', { machine: deps.machineName })
      );
    }
    return { report: null, ran: false };
  }

  outputService.info(
    t('commands.machine.converge.autoStarting', {
      machine: deps.machineName,
      stale: status.stale,
      envVar: SKIP_RUNTIME_CONVERGE_ENV,
    })
  );
  const params = buildConvergeParams({});
  const vault = await prepareConvergeVault(deps.buildBaseVault(params), status);
  const result = await deps.run(vault, params);
  const report = parseConvergeReport(result.stdout);
  if (report) renderConvergeReport(report, deps.machineName);
  // A report already named each failed repo and the resume command.
  if (!result.success && !report) {
    outputService.warn(
      t('commands.machine.converge.autoFailed', {
        machine: deps.machineName,
        error: result.error ?? '',
        command: convergeResumeCommand(deps.machineName),
      })
    );
  }
  return { report, ran: true };
}
