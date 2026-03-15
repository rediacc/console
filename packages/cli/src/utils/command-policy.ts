/**
 * Centralized command policy matrix for agent security guards.
 *
 * Single source of truth for which commands are blocked on grand repos (fork-only mode)
 * and which commands are blocked on fork repos (nonsensical on interim environments).
 */
import path from 'node:path';
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
  TERM_REPO: 'term repo',
  VSCODE_REPO: 'vscode repo',
} as const;

export type CommandPath = (typeof CMD)[keyof typeof CMD];

/**
 * Policy matrix keyed by command path.
 * Commands not listed here have no agent restrictions.
 */
export const COMMAND_POLICIES: ReadonlyMap<CommandPath, CommandPolicy> = new Map<
  CommandPath,
  CommandPolicy
>([
  // Standard write commands — grand guard only
  [CMD.REPO_UP, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_DOWN, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_DELETE, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_MOUNT, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_UNMOUNT, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_TEMPLATE, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_OWNERSHIP, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_SYNC_UPLOAD, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_SYNC_DOWNLOAD, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_PUSH, { grandGuard: true, forkBlocked: false }],
  [CMD.REPO_PULL, { grandGuard: true, forkBlocked: false }],

  [CMD.TERM_REPO, { grandGuard: true, forkBlocked: false }],
  [CMD.VSCODE_REPO, { grandGuard: true, forkBlocked: false }],

  // Fork-blocked — nonsensical on interim fork repos
  [CMD.REPO_AUTOSTART_ENABLE, { grandGuard: true, forkBlocked: true }],
  [CMD.REPO_AUTOSTART_DISABLE, { grandGuard: true, forkBlocked: true }],
  [CMD.REPO_RESIZE, { grandGuard: true, forkBlocked: true }],
  [CMD.REPO_EXPAND, { grandGuard: true, forkBlocked: true }],
]);

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

  const policy = COMMAND_POLICIES.get(commandPath);
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
