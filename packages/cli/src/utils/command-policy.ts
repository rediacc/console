/**
 * Centralized command policy enforcement for agent security guards.
 *
 * Policy data (grandGuard, forkBlocked) is defined in command-metadata.ts.
 * This module provides the runtime enforcement and typed path constants.
 */
import path from 'node:path';
import { COMMAND_METADATA } from '../config/command-metadata.js';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { isAgentEnvironment } from './agent-guard.js';
import { ValidationError } from './errors.js';
import { isOverrideLegitimate } from './process-ancestry.js';

export interface CommandPolicy {
  /** Block grand (non-fork) repos in agent mode. Override: REDIACC_ALLOW_GRAND_REPO */
  grandGuard: boolean;
  /** Block fork repos — command is nonsensical on interim fork environments */
  forkBlocked: boolean;
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
  TERM_REPO: 'term repo',
  VSCODE_REPO: 'vscode repo',
} as const;

export type CommandPath = (typeof CMD)[keyof typeof CMD];

/**
 * Look up the policy for a command path from COMMAND_METADATA.
 * Returns null if no policy is defined.
 */
function getPolicy(commandPath: string): CommandPolicy | null {
  const meta = COMMAND_METADATA[commandPath] as
    | { grandGuard?: boolean; forkBlocked?: boolean }
    | undefined;
  if (!meta || (!meta.grandGuard && !meta.forkBlocked)) return null;
  return {
    grandGuard: meta.grandGuard ?? false,
    forkBlocked: meta.forkBlocked ?? false,
  };
}

/**
 * Backward-compatible Map view of COMMAND_METADATA for consumers that expect a Map.
 * Constructed lazily from the unified metadata.
 */
function buildPoliciesMap(): ReadonlyMap<CommandPath, CommandPolicy> {
  const entries: [CommandPath, CommandPolicy][] = [];
  for (const [path, meta] of Object.entries(COMMAND_METADATA)) {
    if (meta.grandGuard || meta.forkBlocked) {
      entries.push([
        path as CommandPath,
        { grandGuard: meta.grandGuard ?? false, forkBlocked: meta.forkBlocked ?? false },
      ]);
    }
  }
  return new Map(entries);
}

export const COMMAND_POLICIES: ReadonlyMap<CommandPath, CommandPolicy> = buildPoliciesMap();

function isGrandOverridden(repoName: string): boolean {
  const override = process.env.REDIACC_ALLOW_GRAND_REPO;
  if (!override) return false;
  if (override !== '*' && override !== repoName) return false;

  // Verify override was set by user, not injected by agent
  return isOverrideLegitimate();
}

/**
 * Unified command policy enforcement.
 *
 * Checks both grandGuard (blocks grand repos in agent mode) and forkBlocked
 * (blocks fork repos for commands that don't apply to interim environments).
 */
export async function assertCommandPolicy(
  commandPath: CommandPath,
  repoName?: string
): Promise<void> {
  if (!isAgentEnvironment()) return;

  const policy = getPolicy(commandPath);
  if (!policy || !repoName) return;

  const repo = await configService.getRepository(repoName);
  if (!repo) return;
  const isFork = !!(repo.grandGuid && repo.grandGuid !== repo.repositoryGuid);

  if (policy.grandGuard && !isFork && !isGrandOverridden(repoName)) {
    throw new ValidationError(t('errors.agent.grandGuard', { name: repoName }));
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
