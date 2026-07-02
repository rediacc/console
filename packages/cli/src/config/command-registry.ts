/**
 * Command Registry — single source of truth for domain grouping and
 * experimental gating. Help tags and runtime guards are auto-generated
 * from this registry.
 *
 * Commands marked `experimental: true` are hidden by default.
 * Enable with REDIACC_EXPERIMENTAL=1 env var.
 */
export const COMMAND_DOMAINS = {
  INFRASTRUCTURE: 'Infrastructure',
  REPOSITORIES: 'Repositories',
  EXECUTION: 'Execution',
  ORGANIZATION: 'Organization',
  TOOLS: 'Tools',
} as const;

export type CommandDomain = keyof typeof COMMAND_DOMAINS;

export interface SubcommandDef {
  experimental?: boolean;
}

export interface CommandDef {
  name: string;
  domain: CommandDomain;
  experimental?: boolean;
  subcommands?: Record<string, SubcommandDef>;
}

export const COMMAND_REGISTRY: readonly CommandDef[] = [
  // ── Infrastructure ──────────────────────────────────────────────────
  {
    name: 'machine',
    domain: 'INFRASTRUCTURE',
    subcommands: {
      containers: { experimental: true },
      services: { experimental: true },
      repos: { experimental: true },
      health: { experimental: true },
    },
  },
  { name: 'storage', domain: 'INFRASTRUCTURE' },
  { name: 'ops', domain: 'INFRASTRUCTURE' },
  { name: 'datastore', domain: 'INFRASTRUCTURE' },

  // ── Repositories ────────────────────────────────────────────────────
  { name: 'repo', domain: 'REPOSITORIES' },

  // ── Execution ───────────────────────────────────────────────────────
  { name: 'run', domain: 'EXECUTION' },
  { name: 'term', domain: 'EXECUTION' },

  // ── Licensing ──────────────────────────────────────────────────────
  { name: 'subscription', domain: 'TOOLS' },

  // ── Tools ───────────────────────────────────────────────────────────
  { name: 'config', domain: 'TOOLS' },
  { name: 'doctor', domain: 'TOOLS' },
  { name: 'update', domain: 'TOOLS' },
  { name: 'vscode', domain: 'TOOLS' },
  { name: 'agent', domain: 'TOOLS' },
  { name: 'mcp', domain: 'TOOLS' },
] as const;

/** Lookup a command definition by name. */
export function getCommandDef(commandName: string): CommandDef | undefined {
  return COMMAND_REGISTRY.find((c) => c.name === commandName);
}

/**
 * Check if experimental mode is enabled via REDIACC_EXPERIMENTAL=1 env var.
 *
 * Experimental gating is a feature flag, not a security boundary: without the
 * env var, agents never see experimental commands (hidden from help, guard
 * reports "unknown command"), but an explicit REDIACC_EXPERIMENTAL=1 opt-in is
 * honored even in agent environments so test harnesses spawned by agents can
 * exercise hidden commands. The actual security guards (machine access, repo
 * create, config edit) remain ancestry-verified in agent-guard.ts.
 */
export function isExperimentalEnabled(): boolean {
  return process.env.REDIACC_EXPERIMENTAL === '1';
}
