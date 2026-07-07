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
  REPO_MOUNT: 'repo mount',
  REPO_UNMOUNT: 'repo unmount',
  REPO_TEMPLATE: 'repo template',
  REPO_OWNERSHIP: 'repo ownership',
  REPO_SYNC_UPLOAD: 'repo sync upload',
  REPO_SYNC_DOWNLOAD: 'repo sync download',
  REPO_PUSH: 'repo push',
  REPO_PULL: 'repo pull',
  REPO_AUTOSTART_ENABLE: 'repo autostart enable',
  REPO_AUTOSTART_DISABLE: 'repo autostart disable',
  REPO_RESIZE: 'repo resize',
  REPO_EXPAND: 'repo expand',
  REPO_TAKEOVER: 'repo takeover',
  REPO_TUNNEL: 'repo tunnel',
  REPO_COMMIT: 'repo commit',
  REPO_BRANCH: 'repo branch',
  REPO_CHECKOUT: 'repo checkout',
  REPO_MERGE: 'repo merge',
  // NOTE: `repo secret` subcommands intentionally have no CMD entries.
  // The V2 write-only model removed grandGuard from secret commands —
  // mutation-gate is the safety property, not a command-level policy.
  // If a future need arises (e.g. an entirely new agent gate), reintroduce
  // CMD.REPO_SECRET_* and add a metadata entry that references it.
  TERM_REPO: 'term repo',
  VSCODE_REPO: 'vscode repo',
  RUN: 'run',
  CONFIG_REPOSITORY_REMOVE: 'config repository remove',
  CLUSTER_CREATE: 'cluster create',
  CLUSTER_DESTROY: 'cluster destroy',
  CLUSTER_SCALE: 'cluster scale',
  CLUSTER_INSTALL: 'cluster install',
  CLUSTER_FORK: 'cluster fork',
  CLUSTER_MIGRATE: 'cluster migrate',
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
 * Enforce the cluster-ops guard: cluster verbs are blocked in agent mode unless
 * the operator set REDIACC_ALLOW_CLUSTER_OPS before the agent started. Both a
 * missing override and an agent-injected (self-set) one fail closed — only the
 * operator can authorize this, and never from inside the agent.
 */
function enforceClusterGuard(commandPath: string, clusterName: string | undefined): void {
  const name = clusterName ?? '';
  if (checkClusterOverride(name) === 'allowed') {
    auditClusterOverride(commandPath, name);
    return;
  }
  throw new ValidationError(t('errors.agent.clusterOpBlocked', { command: commandPath }));
}

/**
 * Enforce an agentBlocked policy. Cluster verbs are the one family an operator
 * can unlock via REDIACC_ALLOW_CLUSTER_OPS (ancestry-verified); every other
 * agentBlocked command (run, mcp) stays an absolute block.
 */
function enforceAgentBlock(commandPath: string, clusterName: string | undefined): void {
  if (commandPath.startsWith('cluster ')) {
    enforceClusterGuard(commandPath, clusterName);
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
  clusterName?: string
): Promise<void> {
  if (!isAgentEnvironment()) return;

  const policy = getPolicy(commandPath);
  if (!policy) return;

  if (policy.agentBlocked) {
    enforceAgentBlock(commandPath, clusterName);
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
