/**
 * Command Registry — single source of truth for command mode support and domain grouping.
 *
 * Mode tags and runtime guards are auto-generated from this registry.
 * To change which modes a command supports, update its entry here.
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
}

export interface CommandDef {
  name: string;
  modes: ModeSet;
  domain: CommandDomain;
  subcommands?: Record<string, SubcommandDef>;
}

export const COMMAND_REGISTRY: readonly CommandDef[] = [
  // ── Infrastructure ──────────────────────────────────────────────────
  {
    name: 'machine',
    modes: ALL_MODES,
    domain: 'INFRASTRUCTURE',
    subcommands: {
      'assign-bridge': { modes: ['cloud'] },
      'test-connection': { modes: ['cloud'] },
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
  { name: 'region', modes: ['cloud'], domain: 'INFRASTRUCTURE' },
  { name: 'bridge', modes: ['cloud'], domain: 'INFRASTRUCTURE' },

  // ── Repositories ────────────────────────────────────────────────────
  { name: 'repository', modes: ['cloud'], domain: 'REPOSITORIES' },
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
  { name: 'queue', modes: ['cloud'], domain: 'EXECUTION' },
  { name: 'sync', modes: ALL_MODES, domain: 'EXECUTION' },
  { name: 'term', modes: ALL_MODES, domain: 'EXECUTION' },
  // ── Organization ────────────────────────────────────────────────────
  { name: 'auth', modes: ['cloud'], domain: 'ORGANIZATION' },
  { name: 'team', modes: ['cloud'], domain: 'ORGANIZATION' },
  { name: 'organization', modes: ['cloud'], domain: 'ORGANIZATION' },
  { name: 'user', modes: ['cloud'], domain: 'ORGANIZATION' },
  { name: 'permission', modes: ['cloud'], domain: 'ORGANIZATION' },
  { name: 'audit', modes: ['cloud'], domain: 'ORGANIZATION' },
  { name: 'ceph', modes: ['cloud'], domain: 'ORGANIZATION' },

  // ── Tools ───────────────────────────────────────────────────────────
  { name: 'context', modes: ALL_MODES, domain: 'TOOLS' },
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
