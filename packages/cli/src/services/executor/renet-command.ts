/**
 * The env prefix and command line the CLI runs over SSH to start renet, and
 * the environment and per-repo secrets that go into it. Secrets ride stdin,
 * never argv.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { isDevBuild } from '../../utils/platform.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { configService } from '../config/config-resources.js';
import { type RenetEnv, type RenetLaunch, sudoRenet } from './renet-launch.js';

/** The settings a renet launch carries, split by whether they may ride argv. */
export interface RenetEnvParams {
  isDevelopment: boolean;
  telemetryDisabled: boolean;
  otlpCreds?: { user: string; pass: string } | null;
  /**
   * Per-repo env-mode secrets, already prefixed `REDIACC_SECRET_<NAME>`.
   * Renet's `propagateDevEnvVars` forwards this prefix into the bash
   * preamble, and the `renet compose --` wrapper interpolates them into
   * `${REDIACC_SECRET_*}` references in the user's compose YAML.
   */
  envSecrets?: Record<string, string>;
  /**
   * Remote KUBECONFIG path when the target is a cluster, the k8s analog of
   * DOCKER_HOST. The `renet kube` wrapper reads it to talk to the cluster.
   */
  kubeconfig?: string;
}

/**
 * Compose the environment that carries telemetry state and per-repo secrets
 * into a renet subprocess launched over SSH. Shared by the `renet execute`
 * path (buildRemoteRenetCommand), the detached `renet job start` path and the
 * `renet list all` path (machine-status.ts), so every invocation gets the same
 * telemetry handling: spans/metrics/logs when OTLP creds were fetched, or
 * default-deny when the user opted out via CI / REDIACC_TELEMETRY_DISABLED.
 */
export function buildRenetEnv(params: RenetEnvParams): RenetEnv {
  const { isDevelopment, telemetryDisabled, otlpCreds, envSecrets, kubeconfig } = params;
  const envParts: string[] = [];
  const secrets: Record<string, string> = {};
  if (isDevelopment) {
    // REMOTE plane: this REDIACC_ENVIRONMENT travels to the renet process on the machine, a different plane from the local CLI's dev signal. Keep the name; the env-tombstone test allowlists this one literal.
    envParts.push('REDIACC_ENVIRONMENT=development');
  }
  if (kubeconfig) {
    envParts.push(`KUBECONFIG=${shellQuote(kubeconfig)}`);
  }
  if (telemetryDisabled) {
    // Propagate the opt-out to renet. When set, renet skips its OTel SDK setup entirely (see pkg/telemetry/telemetry.go:disabled). We deliberately do NOT pass OTLP creds in this branch, even if the caller passed `otlpCreds`, ignoring them here matches the user's intent to send zero telemetry from any process.
    envParts.push('REDIACC_TELEMETRY_DISABLED=1');
  } else if (otlpCreds) {
    secrets.REDIACC_OTLP_USER = otlpCreds.user;
    secrets.REDIACC_OTLP_PASS = otlpCreds.pass;
  }
  if (envSecrets) {
    Object.assign(secrets, envSecrets);
  }
  return { prefix: envParts.length > 0 ? `env ${envParts.join(' ')} ` : '', secrets };
}

/**
 * Build the sudo `renet execute ...` launch that the CLI executes over SSH
 * on the target machine; its `stdinPrefix` goes ahead of the vault.
 *
 * Exported as a pure function so unit tests can exercise all combinations
 * of (telemetry disabled, OTLP creds present, events mode, dev environment)
 * without constructing a full LocalExecutorService with SFTP mocks.
 *
 * When `telemetryDisabled` is true, `REDIACC_TELEMETRY_DISABLED=1` is
 * injected INSTEAD OF OTLP credentials, the user's opt-out takes
 * precedence over any credentials the caller may have pre-fetched.
 */
export function buildRemoteRenetCommand(
  params: RenetEnvParams & { remoteRenetPath: string; eventsMode?: boolean; timeoutMs?: number }
): RenetLaunch {
  const { remoteRenetPath, eventsMode, timeoutMs, ...envParams } = params;
  const eventsFlag = eventsMode ? ' --events' : '';
  const timeoutFlag = timeoutMs ? ` --timeout ${timeoutMs}ms` : '';
  return sudoRenet(
    buildRenetEnv(envParams),
    `${shellQuote(remoteRenetPath)} execute --executor local${eventsFlag}${timeoutFlag}`
  );
}

/** The ceiling for a function whose run time grows with the data it moves or waits on a health gate. */
export const DATA_TRANSFER_TIMEOUT_MS = 24 * 60 * 60 * 1000;

/**
 * The two timeout classes of agent/plans/PLAN-detached-jobs.md section 20, with
 * the J0b additions (machine_converge_runtime, repository_trim,
 * repository_docker_prune, and the renet daemons upgrade behind
 * `daemons-restart`). A function gets 24 hours when its run time grows with the
 * data it moves, or when it waits on a health gate; every other one keeps
 * renet's 10-minute default. There is no middle class.
 *
 * The two sets together name EVERY function in
 * packages/shared/src/renet-contract/data/license-tiers.generated.ts, and
 * renet-timeout-classes.test.ts fails on a function in neither (or both), so a
 * new renet function forces a decision instead of inheriting one silently.
 */
export const LONG_TIMEOUT_FUNCTIONS: ReadonlySet<string> = new Set([
  // The data-moving backup functions (commit d6ea91581).
  'backup_snapshot',
  'backup_push',
  'backup_pull',
  'backup_restore',
  'backup_restore_path',
  'backup_verify',
  // Health-gated repository lifecycle, and the ones that grow with the image.
  'repository_up',
  'repository_up_all',
  'repository_fork',
  'repository_create',
  'repository_resize',
  'repository_expand',
  'repository_trim',
  'repository_docker_prune',
  // Two backup pushes to the destination machine, sized by the image.
  'repository_migrate',
  // CRIU checkpoints grow with the memory they dump and restore.
  'checkpoint_create',
  'checkpoint_restore',
  // The datastore lifecycle.
  'datastore_create',
  'datastore_delete',
  'datastore_fork',
  'datastore_resize',
  'datastore_expand',
  'datastore_attach',
  'datastore_detach',
  'datastore_adopt',
  // The cluster lifecycle (ceph and kube install, join, upgrade, data copies).
  'ceph_bootstrap_cluster',
  'ceph_cluster_create',
  'ceph_cluster_destroy',
  'ceph_install_prerequisites',
  'ceph_clone_image',
  'ceph_clone_flatten',
  'ceph_image_resize',
  'kube_install',
  'kube_uninstall',
  'kube_upgrade',
  'kube_join',
  'kube_registry_up',
  'kube_prep_fork',
  'kube_fork_dest_prep',
  // Machine setup and the runtime converge restart daemons and wait on their stability.
  'setup',
  'machine_converge_runtime',
]);

/** Every other function: renet's 10-minute default. */
export const DEFAULT_TIMEOUT_FUNCTIONS: ReadonlySet<string> = new Set([
  'backup_browse',
  'backup_browse_at',
  'backup_delete',
  'backup_list',
  'ceph_client_config_export',
  'ceph_client_config_install',
  'ceph_client_mount',
  'ceph_client_unmount',
  'ceph_clone_cleanup',
  'ceph_clone_create',
  'ceph_clone_delete',
  'ceph_clone_list',
  'ceph_clone_mount',
  'ceph_clone_unmount',
  'ceph_cluster_dashboard',
  'ceph_cluster_status',
  'ceph_health',
  'ceph_image_create',
  'ceph_image_delete',
  'ceph_image_format',
  'ceph_image_info',
  'ceph_image_list',
  'ceph_image_map',
  'ceph_image_unmap',
  'ceph_pool_create',
  'ceph_pool_delete',
  'ceph_pool_info',
  'ceph_pool_list',
  'ceph_pool_stats',
  'ceph_snapshot_create',
  'ceph_snapshot_delete',
  'ceph_snapshot_list',
  'ceph_snapshot_protect',
  'ceph_snapshot_rollback',
  'ceph_snapshot_unprotect',
  'checkpoint_check_compat',
  'checkpoint_cleanup',
  'checkpoint_validate',
  'container_exec',
  'container_inspect',
  'container_kill',
  'container_list',
  'container_logs',
  'container_pause',
  'container_remove',
  'container_restart',
  'container_start',
  'container_stats',
  'container_stop',
  'container_unpause',
  'daemon_logs',
  'daemon_nop',
  'daemon_restart',
  'daemon_setup',
  'daemon_start',
  'daemon_status',
  'daemon_stop',
  'daemon_teardown',
  'daemon_wait_docker',
  'datastore_forget',
  'datastore_list',
  'datastore_snapshot_create',
  'datastore_snapshot_delete',
  'datastore_snapshot_list',
  'datastore_status',
  'datastore_validate',
  'datastore_volumes_close',
  'datastore_volumes_open',
  'kube_apply',
  'kube_delete',
  'kube_health',
  'kube_identity_rewrite',
  'kube_join_token',
  'kube_kubeconfig',
  'kube_node_label',
  'kube_node_remove',
  'kube_registry_wire',
  'machine_check_btrfs',
  'machine_check_cli',
  'machine_check_criu',
  'machine_check_drivers',
  'machine_check_kernel',
  'machine_check_memory',
  'machine_check_renet',
  'machine_check_setup',
  'machine_check_sudo',
  'machine_check_system',
  'machine_check_tools',
  'machine_check_users',
  'machine_fix_groups',
  'machine_gpu_list',
  'machine_ping',
  'machine_ssh_test',
  'machine_uninstall',
  'machine_version',
  'network_cleanup_ips',
  'network_ensure_ips',
  'network_prune',
  'network_ps_status',
  'network_used',
  'repository_autostart_disable',
  'repository_autostart_disable_all',
  'repository_autostart_enable',
  'repository_autostart_enable_all',
  'repository_autostart_list',
  'repository_cat',
  'repository_commit',
  'repository_commit_meta',
  'repository_delete',
  'repository_diff',
  'repository_down',
  'repository_down_all',
  'repository_exec',
  'repository_gc',
  'repository_gpu_grant',
  'repository_gpu_revoke',
  'repository_health',
  'repository_info',
  'repository_list',
  'repository_log',
  'repository_logs',
  'repository_merge',
  'repository_mount',
  'repository_ownership',
  'repository_policy_get',
  'repository_policy_set',
  'repository_promote',
  'repository_prune',
  'repository_status',
  'repository_template_apply',
  'repository_unmount',
  'repository_validate',
]);

/**
 * The command-kind jobs (`job start --command`, section 14) and their class.
 * `setup` installs packages and `backup-unit` runs a whole backup inside the
 * job; `daemons-restart` is the renet daemons upgrade (J0b finding 5); a
 * `list-all` read keeps the default.
 */
export const COMMAND_KIND_TIMEOUT_MS: Readonly<Record<string, number | undefined>> = {
  setup: DATA_TRANSFER_TIMEOUT_MS,
  'backup-unit': DATA_TRANSFER_TIMEOUT_MS,
  'daemons-restart': DATA_TRANSFER_TIMEOUT_MS,
  'list-all': undefined,
};

/**
 * The `--timeout` a renet run carries. Both `renet execute` and `renet job start` cancel at 10 minutes when none is passed, which killed the hostinger seed's foreground snapshot of mautic at duration_ms=600019 with `signal: terminated` (2026-10-29), mid-upload under a 100 Mbps cap. A function in LONG_TIMEOUT_FUNCTIONS gets a ceiling sized for the transfer or the health gate instead: a 200 GB repo at 12.5 MB/s needs about 4.5 hours, and 24 hours leaves room for a slower link. The cost is that a hung job holds its overlap lock until that ceiling, which `rdc job cancel` ends sooner. An explicit caller value always wins.
 */
export function resolveRenetTimeoutMs(
  functionName: string,
  explicitMs: number | undefined
): number | undefined {
  if (explicitMs) return explicitMs;
  return LONG_TIMEOUT_FUNCTIONS.has(functionName) ? DATA_TRANSFER_TIMEOUT_MS : undefined;
}

/**
 * Resolve env-mode per-repo secrets for the focal repository, prefixed
 * `REDIACC_SECRET_<NAME>`. Returns undefined when no repo is targeted.
 * File-mode secrets ride inside the vault; env-mode secrets ride the stdin
 * prefix that `sudoRenet` puts ahead of it. Neither appears in `ps`.
 */
export async function resolveEnvSecrets(
  repoRef: string | undefined
): Promise<Record<string, string> | undefined> {
  if (!repoRef) return undefined;
  try {
    const repoConfig = await configService.getRepository(repoRef);
    const secrets = repoConfig?.secrets;
    if (!secrets) return undefined;
    const out: Record<string, string> = {};
    for (const [name, entry] of Object.entries(secrets)) {
      if (entry.mode === 'env') out[`REDIACC_SECRET_${name}`] = entry.value;
    }
    return Object.keys(out).length > 0 ? out : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Detect whether CLI is running in development (tsx) or production.
 */
export function detectEnvironment(): string {
  const execArgs = process.execArgv.join(' ');
  if (
    execArgs.includes('tsx') ||
    execArgs.includes('ts-node') ||
    process.argv[1]?.endsWith('.ts')
  ) {
    return 'development';
  }
  return isDevBuild() ? 'development' : DEFAULTS.TELEMETRY.ENVIRONMENT;
}
