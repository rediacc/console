/**
 * Command Registry — single source of truth for command mode support and domain grouping.
 *
 * Mode tags and runtime guards are auto-generated from this registry.
 * To change which modes a command supports, update its entry here.
 *
 * Commands marked `experimental: true` are hidden by default.
 * Enable with --experimental flag or REDIACC_EXPERIMENTAL=1 env var.
 */
import type { ContextMode } from '../types/index.js';

export type ModeSet = readonly ContextMode[];

export const ALL_MODES: ModeSet = ['cloud', 'local', 's3'] as const;
export const SELF_HOSTED_MODES: ModeSet = ['local', 's3'] as const;

export const COMMAND_DOMAINS = {
  INFRASTRUCTURE: 'Infrastructure',
  REPOSITORIES: 'Repositories',
  EXECUTION: 'Execution',
  ORGANIZATION: 'Organization',
  TOOLS: 'Tools',
} as const;

export type CommandDomain = keyof typeof COMMAND_DOMAINS;

export interface SubcommandDef {
  modes: ModeSet;
  experimental?: boolean;
}

export interface CommandDef {
  name: string;
  modes: ModeSet;
  domain: CommandDomain;
  experimental?: boolean;
  subcommands?: Record<string, SubcommandDef>;
}

export const COMMAND_REGISTRY: readonly CommandDef[] = [
  // ── Infrastructure ──────────────────────────────────────────────────
  {
    name: 'machine',
    modes: ALL_MODES,
    domain: 'INFRASTRUCTURE',
    subcommands: {
      'assign-bridge': { modes: ['cloud'], experimental: true },
      'test-connection': { modes: ['cloud'], experimental: true },
    },
  },
  {
    name: 'storage',
    modes: ALL_MODES,
    domain: 'INFRASTRUCTURE',
    subcommands: {
      browse: { modes: SELF_HOSTED_MODES },
      pull: { modes: SELF_HOSTED_MODES },
    },
  },
  { name: 'region', modes: ['cloud'], domain: 'INFRASTRUCTURE', experimental: true },
  { name: 'bridge', modes: ['cloud'], domain: 'INFRASTRUCTURE', experimental: true },

  // ── Repositories ────────────────────────────────────────────────────
  { name: 'repository', modes: ['cloud'], domain: 'REPOSITORIES', experimental: true },
  { name: 'repo', modes: SELF_HOSTED_MODES, domain: 'REPOSITORIES' },
  { name: 'snapshot', modes: SELF_HOSTED_MODES, domain: 'REPOSITORIES' },
  {
    name: 'backup',
    modes: ALL_MODES,
    domain: 'REPOSITORIES',
    subcommands: {
      sync: { modes: SELF_HOSTED_MODES },
      schedule: { modes: SELF_HOSTED_MODES },
    },
  },

  // ── Execution ───────────────────────────────────────────────────────
  { name: 'run', modes: ALL_MODES, domain: 'EXECUTION' },
  { name: 'queue', modes: ['cloud'], domain: 'EXECUTION', experimental: true },
  { name: 'sync', modes: ALL_MODES, domain: 'EXECUTION' },
  { name: 'term', modes: ALL_MODES, domain: 'EXECUTION' },
  // ── Organization ────────────────────────────────────────────────────
  { name: 'auth', modes: ['cloud'], domain: 'ORGANIZATION', experimental: true },
  { name: 'team', modes: ['cloud'], domain: 'ORGANIZATION', experimental: true },
  { name: 'organization', modes: ['cloud'], domain: 'ORGANIZATION', experimental: true },
  { name: 'user', modes: ['cloud'], domain: 'ORGANIZATION', experimental: true },
  { name: 'permission', modes: ['cloud'], domain: 'ORGANIZATION', experimental: true },
  { name: 'audit', modes: ['cloud'], domain: 'ORGANIZATION', experimental: true },
  { name: 'ceph', modes: ['cloud'], domain: 'ORGANIZATION', experimental: true },

  // ── Tools ───────────────────────────────────────────────────────────
  {
    name: 'context',
    modes: ALL_MODES,
    domain: 'TOOLS',
    subcommands: {
      create: { modes: ['cloud'], experimental: true },
    },
  },
  { name: 'doctor', modes: ALL_MODES, domain: 'TOOLS' },
  { name: 'update', modes: ALL_MODES, domain: 'TOOLS' },
  { name: 'protocol', modes: ALL_MODES, domain: 'TOOLS' },
  { name: 'vscode', modes: ALL_MODES, domain: 'TOOLS' },
] as const;

/** Lookup a command definition by name. */
export function getCommandDef(commandName: string): CommandDef | undefined {
  return COMMAND_REGISTRY.find((c) => c.name === commandName);
}

/**
 * Format a mode tag for display in help text.
 */
export function formatModeTag(modes: ModeSet): string {
  return `[${modes.join('|')}]`;
}

/**
 * Check if experimental mode is enabled via --experimental flag or REDIACC_EXPERIMENTAL=1 env var.
 */
export function isExperimentalEnabled(): boolean {
  return process.env.REDIACC_EXPERIMENTAL === '1';
}
