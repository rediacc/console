/**
 * Centralized command policy enforcement for agent security guards.
 *
 * Policy data (grandGuard, forkBlocked) is defined in command-metadata.ts.
 * This module provides the runtime enforcement and typed path constants.
 */
import path from 'node:path';
import { COMMAND_METADATA } from '../config/command-metadata.js';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { auditLog } from '../services/core/audit-log.js';
import { isAgentEnvironment } from './agent-guard.js';
import { isClusterAllowedByEnv } from './cluster-env.js';
import { ValidationError } from './errors.js';
import { isRepoAllowedByGrandEnv } from './grand-env.js';
import {
  isAncestryVerificationAvailable,
  isOverrideLegitimate,
  OVERRIDE_VAR_CLUSTER,
} from './process-ancestry.js';

export interface CommandPolicy {
  /** Block grand (non-fork) repos in agent mode. Override: REDIACC_ALLOW_GRAND_REPO */
  grandGuard: boolean;
  /** Block fork repos — command is nonsensical on interim fork environments */
  forkBlocked: boolean;
  /**
   * Block in agent mode. Absolute for most commands (run, mcp — no override).
   * The `cluster <verb>` family is the one exception: it can be deliberately
   * unlocked per cluster by the operator via REDIACC_ALLOW_CLUSTER_OPS,
   * ancestry-verified exactly like REDIACC_ALLOW_GRAND_REPO.
   */
  agentBlocked: boolean;
}

/**
 * Typed command path constants. Use these instead of string literals
 * to get compile-time safety and autocomplete.
 */
export const CMD = {
  REPO_UP: 'repo up',
  REPO_DOWN: 'repo down',
  REPO_DELETE: 'repo delete',

  REPO_SYNC_UPLOAD: 'repo sync upload',
  REPO_SYNC_DOWNLOAD: 'repo sync download',
  REPO_PUSH: 'repo push',
  REPO_PULL: 'repo pull',
  // The plumbing subtree moved under `repo admin` (§5.4). Same guards, new paths.
  REPO_ADMIN_VALIDATE: 'repo admin validate',
  REPO_ADMIN_OWNERSHIP: 'repo admin ownership',
  REPO_ADMIN_TEMPLATE: 'repo admin template apply',
  REPO_ADMIN_AUTOSTART_ENABLE: 'repo admin autostart enable',
  REPO_ADMIN_AUTOSTART_DISABLE: 'repo admin autostart disable',
  REPO_RESIZE: 'repo resize',
  REPO_EXPAND: 'repo expand',
  REPO_PROMOTE: 'repo promote',
  REPO_TUNNEL: 'repo tunnel',
  REPO_EXEC: 'repo exec',
  REPO_COMMIT: 'repo commit',
  REPO_BRANCH: 'repo branch',
  REPO_CHECKOUT: 'repo checkout',
  REPO_MERGE: 'repo merge',
  // Feature layer (spec §5.4): gate class B. Replicate and canary never mutate
  // the primary's data — replicate forks it, canary shares it — so grandGuard is
  // the whole gate; no class-D cluster unlock is required (they stay inside one
  // cluster's datastores, and replicate is the flagship agent-safe demo).
  REPO_REPLICATE: 'repo replicate',
  REPO_REPLICATE_REMOVE: 'repo replicate remove',
  REPO_REPLICATE_REFRESH: 'repo replicate refresh',
  REPO_CANARY_CREATE: 'repo canary create',
  REPO_CANARY_WEIGHT: 'repo canary weight',
  REPO_CANARY_REMOVE: 'repo canary remove',
  // NOTE: `repo secret` subcommands intentionally have no CMD entries.
  // The V2 write-only model removed grandGuard from secret commands —
  // mutation-gate is the safety property, not a command-level policy.
  // If a future need arises (e.g. an entirely new agent gate), reintroduce
  // CMD.REPO_SECRET_* and add a metadata entry that references it.
  // These were 'term repo' / 'vscode repo' — SYNTHETIC paths that never existed in
  // the tree (term has only ever had `connect`). Keyed to the real leaves now, so
  // the policy gate and the command tree finally agree on the same string.
  TERM_CONNECT: 'term connect',
  VSCODE_CONNECT: 'vscode connect',
  RUN: 'run',
  BACKUP_RESTORE: 'backup restore',
  CLUSTER_CREATE: 'cluster create',
  CLUSTER_DESTROY: 'cluster destroy',
  CLUSTER_SCALE: 'cluster scale',
  CLUSTER_FORK: 'cluster fork',
  CLUSTER_MIGRATE: 'cluster migrate',
  CLUSTER_JOIN: 'cluster join',
  CLUSTER_EVICT: 'cluster evict',
  CLUSTER_SNAPSHOT_CREATE: 'cluster snapshot create',
  // Datastore mutations are class D: a datastore holds every repo in it, so
  // moving or destroying one is an infrastructure act, not a repo act.
  DATASTORE_CREATE: 'datastore create',
  DATASTORE_ATTACH: 'datastore attach',
  DATASTORE_DETACH: 'datastore detach',
  DATASTORE_FORK: 'datastore fork',
  DATASTORE_RESIZE: 'datastore resize',
  DATASTORE_DELETE: 'datastore delete',
  DATASTORE_SNAPSHOT_CREATE: 'datastore snapshot create',
} as const;

export type CommandPath = (typeof CMD)[keyof typeof CMD];

/**
 * Look up the policy for a command path from COMMAND_METADATA.
 * Returns null if no policy is defined.
 */
function getPolicy(commandPath: string): CommandPolicy | null {
  const meta = COMMAND_METADATA[commandPath] as
    | { grandGuard?: boolean; forkBlocked?: boolean; agentBlocked?: boolean }
    | undefined;
  if (!meta || (!meta.grandGuard && !meta.forkBlocked && !meta.agentBlocked)) return null;
  return {
    grandGuard: meta.grandGuard ?? false,
    forkBlocked: meta.forkBlocked ?? false,
    agentBlocked: meta.agentBlocked ?? false,
  };
}

/**
 * Backward-compatible Map view of COMMAND_METADATA for consumers that expect a Map.
 * Constructed lazily from the unified metadata.
 */
function buildPoliciesMap(): ReadonlyMap<CommandPath, CommandPolicy> {
  const entries: [CommandPath, CommandPolicy][] = [];
  for (const [path, meta] of Object.entries(COMMAND_METADATA)) {
    if (meta.grandGuard || meta.forkBlocked || meta.agentBlocked) {
      entries.push([
        path as CommandPath,
        {
          grandGuard: meta.grandGuard ?? false,
          forkBlocked: meta.forkBlocked ?? false,
          agentBlocked: meta.agentBlocked ?? false,
        },
      ]);
    }
  }
  return new Map(entries);
}

export const COMMAND_POLICIES: ReadonlyMap<CommandPath, CommandPolicy> = buildPoliciesMap();

type OverrideResult = 'allowed' | 'not-set' | 'agent-injected';

function checkGrandOverride(repoName: string): OverrideResult {
  if (!isRepoAllowedByGrandEnv(repoName)) return 'not-set';

  // Verify override was set by user, not injected by agent
  return isOverrideLegitimate() ? 'allowed' : 'agent-injected';
}

/** Enforce the grand-guard policy: block grand repos in agent mode unless overridden. */
function enforceGrandGuard(repoName: string): void {
  const override = checkGrandOverride(repoName);
  if (override === 'agent-injected') {
    const errorKey = isAncestryVerificationAvailable()
      ? 'errors.agent.grandGuardOverride'
      : 'errors.agent.grandGuardOverrideNonLinux';
    throw new ValidationError(t(errorKey, { name: repoName, platform: process.platform }));
  }
  if (override !== 'allowed') {
    throw new ValidationError(t('errors.agent.grandGuard', { name: repoName }));
  }
}

function checkClusterOverride(clusterName: string): OverrideResult {
  if (!isClusterAllowedByEnv(clusterName)) return 'not-set';

  // Verify the override was set by the operator (pre-agent), not the agent.
  return isOverrideLegitimate(OVERRIDE_VAR_CLUSTER) ? 'allowed' : 'agent-injected';
}

/**
 * Record that an agent ran a cluster op through a legitimate operator override.
 * actor.kind is stamped `agent` automatically by auditLog. Best-effort: an
 * audit-log failure must never block the allowed operation.
 */
function auditClusterOverride(commandPath: string, clusterName: string): void {
  try {
    const xdg = process.env.XDG_CONFIG_HOME ?? `${process.env.HOME ?? ''}/.config`;
    auditLog(`${xdg}/rediacc`, {
      command: commandPath,
      paths: clusterName ? [clusterName] : [],
      outcome: 'ok',
      reason: `${OVERRIDE_VAR_CLUSTER} override honored`,
    });
  } catch {
    /* audit-log failure must never block the operation */
  }
}

/**
 * Enforce the infrastructure-operations guard (gate class D, spec §4.7): the verb
 * is blocked in agent mode unless the operator set REDIACC_ALLOW_CLUSTER_OPS
 * before the agent started. Both a missing override and an agent-injected
 * (self-set) one fail closed — only the operator can authorize this, and never
 * from inside the agent.
 *
 * `subject` is the name the per-name unlock matches, and it is the SUBJECT of the
 * verb, not always a cluster: a cluster name for `cluster <verb>`, the DATASTORE
 * name for `datastore <verb>` (spec §4.7 ruling R6). `*` covers both.
 */
function enforceInfraGuard(commandPath: string, subject: string | undefined): void {
  const name = subject ?? '';
  if (checkClusterOverride(name) === 'allowed') {
    auditClusterOverride(commandPath, name);
    return;
  }
  throw new ValidationError(t('errors.agent.clusterOpBlocked', { command: commandPath }));
}

/**
 * Enforce an agentBlocked policy. The class-D families (`cluster`, `datastore`)
 * are the ones an operator can unlock via REDIACC_ALLOW_CLUSTER_OPS
 * (ancestry-verified). They share the env var because they share a blast radius:
 * a datastore verb moves every repo in the pool at once. Every other agentBlocked
 * command (run, mcp) stays an absolute block with no unlock at all.
 */
function enforceAgentBlock(commandPath: string, subject: string | undefined): void {
  if (commandPath.startsWith('cluster ') || commandPath.startsWith('datastore ')) {
    enforceInfraGuard(commandPath, subject);
    return;
  }
  throw new ValidationError(t('errors.agent.commandBlocked', { command: commandPath }));
}

/**
 * Unified command policy enforcement.
 *
 * Checks both grandGuard (blocks grand repos in agent mode) and forkBlocked
 * (blocks fork repos for commands that don't apply to interim environments).
 */
export async function assertCommandPolicy(
  commandPath: CommandPath,
  repoName?: string,
  subject?: string
): Promise<void> {
  if (!isAgentEnvironment()) return;

  const policy = getPolicy(commandPath);
  if (!policy) return;

  if (policy.agentBlocked) {
    enforceAgentBlock(commandPath, subject);
    return;
  }

  if (!repoName) return;

  const repo = await configService.getRepository(repoName);
  if (!repo) return;
  const isFork = !!(repo.grandGuid && repo.grandGuid !== repo.repositoryGuid);

  if (policy.grandGuard && !isFork) {
    enforceGrandGuard(repoName);
  }

  if (policy.forkBlocked && isFork) {
    throw new ValidationError(t('errors.agent.forkBlocked', { command: commandPath }));
  }
}

/**
 * Validate that a sync --remote path doesn't escape the repository boundary.
 * Rejects absolute paths and path traversal sequences.
 */
export function validateRemotePath(remotePath: string): void {
  if (remotePath.startsWith('/')) {
    throw new ValidationError(t('errors.sync.absolutePathBlocked'));
  }
  const normalized = path.posix.normalize(remotePath);
  if (normalized.startsWith('..')) {
    throw new ValidationError(t('errors.sync.pathTraversalBlocked'));
  }
}
