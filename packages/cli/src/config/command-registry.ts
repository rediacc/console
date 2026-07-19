/**
 * Command Registry — single source of truth for domain grouping. Help tags and
 * runtime guards are auto-generated from this registry.
 */
export const COMMAND_DOMAINS = {
  INFRASTRUCTURE: 'Infrastructure',
  REPOSITORIES: 'Repositories',
  EXECUTION: 'Execution',
  ORGANIZATION: 'Organization',
  TOOLS: 'Tools',
} as const;

type CommandDomain = keyof typeof COMMAND_DOMAINS;

export interface CommandDef {
  name: string;
  domain: CommandDomain;
  /**
   * Subcommands worth naming explicitly. The value is intentionally empty: the
   * entry exists so a leaf is registered rather than silently absent, which is
   * what `experimental` used to hang off before it was removed.
   */
  subcommands?: Record<string, Record<string, never>>;
}

export const COMMAND_REGISTRY: readonly CommandDef[] = [
  // ── Infrastructure ──────────────────────────────────────────────────
  {
    name: 'machine',
    domain: 'INFRASTRUCTURE',
    subcommands: {
      // containers/services/repos were folded into `machine status --containers`
      // / `--services` / `--repositories` by the P4 reshape; they are not leaves
      // any more, and a registry entry for a command that does not exist is a
      // name waiting to be silently re-bound.
      health: {},
    },
  },
  { name: 'storage', domain: 'INFRASTRUCTURE' },
  { name: 'ops', domain: 'INFRASTRUCTURE' },
  { name: 'datastore', domain: 'INFRASTRUCTURE' },
  { name: 'backup', domain: 'INFRASTRUCTURE' },
  { name: 'cluster', domain: 'INFRASTRUCTURE' },

  // ── Repositories ────────────────────────────────────────────────────
  { name: 'repo', domain: 'REPOSITORIES' },

  // ── Execution ───────────────────────────────────────────────────────
  { name: 'run', domain: 'EXECUTION' },
  { name: 'term', domain: 'EXECUTION' },
  // Detached jobs: started by any long command, outlive the connection.
  { name: 'job', domain: 'EXECUTION' },

  // ── Licensing ──────────────────────────────────────────────────────
  { name: 'subscription', domain: 'TOOLS' },

  // ── Tools ───────────────────────────────────────────────────────────
  { name: 'config', domain: 'TOOLS' },
  { name: 'doctor', domain: 'TOOLS' },
  { name: 'update', domain: 'TOOLS' },
  { name: 'vscode', domain: 'TOOLS' },
  { name: 'mcp', domain: 'TOOLS' },
  { name: 'credits', domain: 'TOOLS' },
  // The enterprise proxy executor daemon.
  { name: 'serve', domain: 'TOOLS' },
] as const;

/** Lookup a command definition by name. */
export function getCommandDef(commandName: string): CommandDef | undefined {
  return COMMAND_REGISTRY.find((c) => c.name === commandName);
}
