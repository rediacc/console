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
  /** Absolute agent block — command is fundamentally incompatible with agent usage. No override. */
  agentBlocked?: boolean;
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
        'Create a near-instant CoW fork of a repository with a NEW GUID and networkId (fully independent copy). FORK IS CONSTANT-TIME regardless of repo size: BTRFS reflink clones the image so 100 GB and 1 GB repos fork in the same ~seconds, never proportional to repo size. Fork shares the parent name with a different tag (name:tag model, like Docker images). Online forking supported (parent can stay running). Fork gets new auto-route domain. After fork, deploy with repo_up (use --mount). Fork-of-fork allowed (same base name, different tag). CROSS-MACHINE: fork locally first, then use repo_push to transfer fork to target machine, then repo_up on target.',
      excludeOptions: ['debug', 'skip-router-restart'],
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

  'config set': {
    mcpExcludeReason: 'Config value mutation — use CLI directly',
  },
  'config clear': {
    mcpExcludeReason: 'Config value deletion — use CLI directly',
  },
  'config ssh': {
    mcpExcludeReason: 'SSH key management — writes key material to config, use CLI directly',
  },
  'config remote': {
    mcpExcludeReason: 'Remote config management — interactive browser flow, use CLI directly',
  },

  // ══════════════════════════════════════════════════════════════════════
  // Policy-only entries (no MCP tools — enforced by assertCommandPolicy)
  // ══════════════════════════════════════════════════════════════════════

  'repo mount': { grandGuard: true },
  'repo unmount': { grandGuard: true },
  'repo template': {
    grandGuard: true,
    mcpExcludeReason: 'Template application requires file upload — use CLI directly',
  },
  'repo ownership': {
    grandGuard: true,
    mcpExcludeReason: 'Ownership transfer — destructive operation, use CLI directly',
  },
  'repo sync upload': { grandGuard: true },
  'repo sync download': { grandGuard: true },
  'repo tunnel': {
    grandGuard: true,
    mcpExcludeReason: 'Interactive SSH tunnel — blocks until Ctrl+C',
  },
  'repo autostart enable': { grandGuard: true, forkBlocked: true },
  'repo autostart disable': { grandGuard: true, forkBlocked: true },
  'repo takeover': { grandGuard: true },
  'config repository remove': { grandGuard: true },
  'repo status': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      repoArg: 'repo',
      requiredArgs: ['repo'],
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo list': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo diff': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      repoArg: 'name',
      requiredArgs: ['name'],
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo commit': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write' as const,
      repoArg: 'name',
      requiredArgs: ['name', 'message'],
      descriptionOverride:
        'Freeze a mounted working fork into a new immutable commit (git-like). Records message/author/parent in the commit and advances the working fork tip. The commit refuses to mount; check it out to get a writable copy.',
      excludeOptions: ['debug'],
    },
  },
  'repo branch': {
    grandGuard: true,
    mcpExcludeReason: 'Config-only ref operation — use CLI directly',
  },
  'repo checkout': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write' as const,
      requiredArgs: ['tag'],
      descriptionOverride:
        'Reflink-clone an immutable commit (or branch tip) into a fresh writable working fork and point HEAD at it.',
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo log': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      repoArg: 'name',
      requiredArgs: ['name'],
      excludeOptions: ['debug'],
    },
  },
  'repo merge': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write' as const,
      repoArg: 'name',
      requiredArgs: ['name', 'from'],
      descriptionOverride:
        'Lifecycle-safe merge of a source commit/fork into a target working fork. Refuses a mounted/running target unless --force (which quiesces it first); never mutates a live mount — builds the result in a reflink clone and atomically swaps it in.',
      excludeOptions: ['debug'],
    },
  },
  'repo gc': {
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write' as const,
      descriptionOverride:
        'Reachability garbage-collection: delete immutable commit objects on a machine that no branch/HEAD reaches. Dry-run by default; pass --apply to delete. Never touches a mounted object or a working fork.',
      excludeOptions: ['debug'],
    },
  },
  'repo fsck': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      descriptionOverride:
        'Validate config refs (branches/HEAD) against the objects present on a machine; report dangling refs and orphan commits.',
    },
  },
  'repo validate': {
    grandGuard: true,
    mcpExcludeReason: 'Validation runs on remote machine — use repo status for MCP',
  },
  'repo autostart': {
    mcpExcludeReason: 'Autostart management — use CLI directly',
  },
  'repo resize': {
    grandGuard: true,
    forkBlocked: true,
    mcpExcludeReason: 'Disk resize — destructive infrastructure operation, use CLI directly',
  },
  'repo expand': {
    grandGuard: true,
    forkBlocked: true,
    mcpExcludeReason: 'Storage expansion — destructive infrastructure operation, use CLI directly',
  },
  'term repo': { grandGuard: true },
  'vscode repo': { grandGuard: true },

  // Per-repo secrets — V2 write-only model.
  //
  // No `grandGuard`: with `get` returning digest only (never plaintext),
  // there's no read-attack to gate. The mutation-gate is the actual safety
  // property; symmetric for humans and agents.
  //
  // Group-level `mcpExcludeReason` satisfies the coverage gate (registry
  // only enumerates 2-word subcommand paths; per-subcommand 3-word
  // exclusions come back as "stale"). Per-subcommand `mcp:` blocks below
  // still take effect via the tool factory which walks the live commander
  // tree, so `repo_secret_list` and `repo_secret_get` are still exposed.
  // Writes (`set`/`unset`) intentionally have no `mcp:` block — the
  // `--current` / `--rotate-secret` precondition ceremony requires human
  // eyes-on; exposing as MCP would invite blind-retry loops.
  'repo secret': {
    mcpExcludeReason:
      'Writes (set/unset) require --current/--rotate-secret ceremony — CLI-only. Reads (list/get) ARE exposed as repo_secret_list and repo_secret_get MCP tools.',
  },
  'repo secret list': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      excludeOptions: ['debug'],
    },
  },
  'repo secret get': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      excludeOptions: ['debug'],
    },
  },

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
  subscription: { mcpExcludeReason: 'License management — local concern' },
  mcp: { mcpExcludeReason: 'The MCP server itself — cannot recurse' },

  // ── Sync requires local filesystem ────────────────────────────────
  sync: { mcpExcludeReason: 'Requires local filesystem paths — MCP agents have no local FS' },

  // ── Covered by sub-operations ─────────────────────────────────────
  run: {
    agentBlocked: true,
    mcpExcludeReason: 'Escape hatch for raw renet functions — agents should use typed tools',
  },

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
