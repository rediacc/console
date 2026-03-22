/**
 * Unified Command Metadata — single source of truth for per-command policy and MCP annotations.
 *
 * Replaces the separate COMMAND_POLICIES map (command-policy.ts) and MCP tool-definitions.ts.
 * Keyed by full command path (e.g., "repo up", "config provider add").
 *
 * - Commands with `mcp` field are auto-derived as MCP tools from the Commander tree.
 * - Commands with `mcpExcludeReason` are explicitly excluded from MCP.
 * - Commands with `grandGuard`/`forkBlocked` are enforced by assertCommandPolicy().
 */

export interface McpMeta {
  destructive: boolean;
  idempotent: boolean;
  timeout: 'read' | 'write';
  /** Field name in MCP args that contains the repository name (for grand repo guard). */
  repoArg?: string;
  /** Override the Commander description for LLM-optimized text. Falls back to Commander .description(). */
  descriptionOverride?: string;
  /** Commander options (long names without --) to exclude from the MCP Zod schema. */
  excludeOptions?: string[];
  /** Commander positional args that are optional in CLI but required in MCP. */
  requiredArgs?: string[];
  /** Always append these raw argv fragments to the command (e.g., ['--force']). */
  appendArgs?: string[];
}

export interface CommandMeta {
  /** Block grand (non-fork) repos in agent mode. Override: REDIACC_ALLOW_GRAND_REPO */
  grandGuard?: boolean;
  /** Block fork repos — command is nonsensical on interim fork environments */
  forkBlocked?: boolean;
  /** MCP tool metadata. If present, auto-derive an MCP tool from Commander. */
  mcp?: McpMeta;
  /** If set, this command is explicitly excluded from MCP with this reason. */
  mcpExcludeReason?: string;
}

export const READ_TIMEOUT = 120_000;
export const WRITE_TIMEOUT = 300_000;

export const COMMAND_METADATA: Record<string, CommandMeta> = {
  // ══════════════════════════════════════════════════════════════════════
  // Auto-derived MCP tools (read)
  // ══════════════════════════════════════════════════════════════════════

  'machine query': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride:
        'Get connection details (ip, user, port, datastore), system info, containers (repository resolved to name, original in repository_guid, domain, autoRoute), services (repository resolved to name), repositories (name resolved from GUID, original in guid), and resource usage for a machine',
      // All flags handled by dedicated custom tools (machine_containers, etc.)
      excludeOptions: [
        'debug',
        'system',
        'repositories',
        'containers',
        'services',
        'network',
        'block-devices',
      ],
    },
  },

  'machine list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },

  'config repository list': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride: 'List configured repositories with name-to-GUID mappings',
    },
  },

  'config infra show': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride:
        'Show infrastructure configuration for a machine (base domain, public IPs, ports), shared TLS settings (cert email, CF DNS token), and Cloudflare zone ID',
    },
  },

  'agent capabilities': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride: 'List all available rdc CLI commands with their arguments and options',
    },
  },

  // ══════════════════════════════════════════════════════════════════════
  // Auto-derived MCP tools (write)
  // ══════════════════════════════════════════════════════════════════════

  'repo create': {
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },

  'repo up': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      repoArg: 'name',
      descriptionOverride:
        'Deploy/update a repository on a machine (runs Rediaccfile up via renet compose, starts containers). Use mount=true for first deploy, after backup pull, or after unmount',
      requiredArgs: ['name'],
      excludeOptions: [
        'include-forks',
        'mount-only',
        'parallel',
        'concurrency',
        'yes',
        'debug',
        'skip-router-restart',
        'dry-run',
      ],
    },
  },

  'repo down': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      repoArg: 'name',
      descriptionOverride:
        'Stop repository Docker containers (runs Rediaccfile down). Does NOT unmount the encrypted volume by default -- repo stays mounted and can be restarted with repo_up. Use unmount=true to also close the LUKS container',
      requiredArgs: ['name'],
      excludeOptions: ['yes', 'debug', 'skip-router-restart', 'dry-run'],
    },
  },

  'repo delete': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      repoArg: 'name',
      excludeOptions: ['debug', 'skip-router-restart', 'dry-run'],
    },
  },

  'repo fork': {
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      descriptionOverride:
        'Create a CoW fork of a repository with a NEW GUID and networkId (fully independent copy). Fork shares the parent name with a different tag (name:tag model, like Docker images). Online forking supported (parent can stay running). Fork gets new auto-route domain. After fork, deploy with repo_up (use --mount). Fork-of-fork allowed (same base name, different tag). CROSS-MACHINE: fork locally first, then use repo_push to transfer fork to target machine, then repo_up on target',
      // --tag option duplicates [tag] positional arg
      excludeOptions: ['tag', 'debug', 'skip-router-restart'],
    },
  },

  'repo push': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      repoArg: 'repo',
      descriptionOverride:
        'Push a repository backup to storage or directly to another machine. WARNING: machine-to-machine push copies with the SAME GUID (backup/migration). To create an independent fork on another machine, use repo_fork first, then push the fork',
      requiredArgs: ['repo'],
      excludeOptions: [
        'dest',
        'tag',
        'watch',
        'parallel',
        'concurrency',
        'yes',
        'debug',
        'skip-router-restart',
      ],
    },
  },

  'repo pull': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      repoArg: 'repo',
      requiredArgs: ['repo'],
      excludeOptions: ['watch', 'parallel', 'concurrency', 'yes', 'debug', 'skip-router-restart'],
    },
  },

  'machine prune': {
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      excludeOptions: ['grace-days', 'debug'],
    },
  },

  'storage prune': {
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      excludeOptions: ['grace-days', 'debug', 'skip-router-restart'],
    },
  },

  'machine provision': {
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      excludeOptions: ['ssh-user', 'debug'],
    },
  },

  'machine deprovision': {
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      excludeOptions: ['debug'],
      appendArgs: ['--force'],
    },
  },

  'config provider add': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
    },
  },

  'config provider remove': {
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
    },
  },

  'config provider list': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride: 'List configured cloud providers for machine provisioning',
    },
  },

  // ══════════════════════════════════════════════════════════════════════
  // Policy-only entries (no MCP tools — enforced by assertCommandPolicy)
  // ══════════════════════════════════════════════════════════════════════

  'repo mount': { grandGuard: true },
  'repo unmount': { grandGuard: true },
  'repo template': { grandGuard: true },
  'repo ownership': { grandGuard: true },
  'repo sync upload': { grandGuard: true },
  'repo sync download': { grandGuard: true },
  'repo autostart enable': { grandGuard: true, forkBlocked: true },
  'repo autostart disable': { grandGuard: true, forkBlocked: true },
  'repo takeover': { grandGuard: true },
  'repo resize': { grandGuard: true, forkBlocked: true },
  'repo expand': { grandGuard: true, forkBlocked: true },
  'term repo': { grandGuard: true },
  'vscode repo': { grandGuard: true },

  // ══════════════════════════════════════════════════════════════════════
  // MCP-excluded commands (with documented reasons)
  // ══════════════════════════════════════════════════════════════════════

  // ── Interactive / GUI ─────────────────────────────────────────────
  vscode: { mcpExcludeReason: 'Opens VS Code GUI — not useful for MCP agents' },
  protocol: { mcpExcludeReason: 'URL protocol handler registration — local desktop concern' },

  // ── Local-only tooling ────────────────────────────────────────────
  ops: { mcpExcludeReason: 'Local VM provisioning — requires host KVM/QEMU, not remote-operable' },
  datastore: {
    mcpExcludeReason:
      'Infrastructure datastore management — runs via bridge execution, not direct MCP',
  },
  doctor: { mcpExcludeReason: 'Diagnoses local CLI installation — not a remote operation' },
  update: { mcpExcludeReason: 'CLI self-update — not a remote operation' },
  store: { mcpExcludeReason: 'Config file sync backends — local credential management' },
  subscription: { mcpExcludeReason: 'License management — local concern' },
  mcp: { mcpExcludeReason: 'The MCP server itself — cannot recurse' },

  // ── Sync requires local filesystem ────────────────────────────────
  sync: { mcpExcludeReason: 'Requires local filesystem paths — MCP agents have no local FS' },

  // ── Covered by sub-operations ─────────────────────────────────────
  run: { mcpExcludeReason: 'Escape hatch for raw renet functions — agents should use typed tools' },

  // ── Subcommands ───────────────────────────────────────────────────
  'storage browse': { mcpExcludeReason: 'Interactive file browser — requires TTY' },

  // ── Factory-generated CRUD (covered by higher-level operations) ──
  'machine create': { mcpExcludeReason: 'Config CRUD — use config machine commands instead' },
  'machine rename': { mcpExcludeReason: 'Config CRUD — use config machine commands instead' },
  'machine delete': { mcpExcludeReason: 'Config CRUD — use config machine commands instead' },
  'machine backup': { mcpExcludeReason: 'Backup scheduling — internal operation' },
  'storage list': { mcpExcludeReason: 'Config CRUD — covered by config storage commands' },
  'storage create': { mcpExcludeReason: 'Config CRUD — covered by config storage commands' },
  'storage rename': { mcpExcludeReason: 'Config CRUD — covered by config storage commands' },
  'storage delete': { mcpExcludeReason: 'Config CRUD — covered by config storage commands' },

  // ── Cloud-only (not available in local adapter) ──────────────────
  'machine vault': { mcpExcludeReason: 'Cloud adapter only — vault management' },
  'machine vault-status': { mcpExcludeReason: 'Cloud adapter only — vault status' },
  'storage vault': { mcpExcludeReason: 'Cloud adapter only — vault management' },
};

/** Look up metadata for a command path. */
export function getCommandMeta(commandPath: string): CommandMeta | undefined {
  return COMMAND_METADATA[commandPath];
}

/** Get all command paths that have MCP tool metadata. */
export function getMcpCommandPaths(): string[] {
  return Object.entries(COMMAND_METADATA)
    .filter(([, meta]) => meta.mcp)
    .map(([path]) => path);
}

/** Get all MCP exclusion reasons. */
export function getMcpExclusions(): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [path, meta] of Object.entries(COMMAND_METADATA)) {
    if (meta.mcpExcludeReason) {
      result[path] = meta.mcpExcludeReason;
    }
  }
  return result;
}
