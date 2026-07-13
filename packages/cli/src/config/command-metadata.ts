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

interface McpMeta {
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

  // ── Detached jobs (they survive the connection that started them) ──────
  // Reading a job's spool is safe. Cancelling stops real work and gc destroys
  // logs, so both are destructive and both auto-confirm via --yes.
  // `job logs --follow` only ends when the job does, which an agent cannot
  // usefully block on, so it is hidden: an agent polls `job status` instead.

  'job list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'job status': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'job logs': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      excludeOptions: ['follow', 'debug'],
    },
  },
  'job cancel': {
    mcp: { destructive: true, idempotent: true, timeout: 'write', appendArgs: ['--yes'] },
  },
  'job gc': {
    mcp: { destructive: true, idempotent: true, timeout: 'write', appendArgs: ['--yes'] },
  },

  'machine status': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride:
        'Get connection details (ip, user, port, datastore), system info, containers (repository resolved to name, original in repository_guid, domain, autoRoute), services (repository resolved to name), repositories (name resolved from GUID, original in guid), and resource usage for a machine',
      excludeOptions: [
        'debug',
        'system',
        'repositories',
        'containers',
        'services',
        'network',
        'block-devices',
        'datastores',
        'health-check',
        'stability-check',
        'search',
      ],
    },
  },

  'machine list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'machine add': {
    mcp: { destructive: false, idempotent: false, timeout: 'write' },
  },
  'machine remove': {
    mcp: { destructive: true, idempotent: false, timeout: 'write', excludeOptions: ['yes'] },
  },

  // ── Backup noun (strategies, machine-scoped runs, artifacts) ────────────
  'backup strategy list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'backup strategy show': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'backup run': {
    mcp: {
      destructive: false,
      idempotent: false,
      timeout: 'write',
      excludeOptions: ['watch', 'debug'],
    },
  },
  'backup status': {
    mcp: { destructive: false, idempotent: true, timeout: 'read', excludeOptions: ['debug'] },
  },
  'backup cancel': {
    mcp: { destructive: false, idempotent: true, timeout: 'write', excludeOptions: ['debug'] },
  },
  'backup list': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      excludeOptions: ['watch', 'debug'],
    },
  },
  'backup restore': {
    grandGuard: true,
    mcp: { destructive: true, idempotent: false, timeout: 'write', excludeOptions: ['debug'] },
  },
  'backup strategy set': {
    mcpExcludeReason: 'Backup policy mutation; use CLI directly.',
  },
  'backup strategy remove': {
    mcpExcludeReason: 'Backup policy mutation; use CLI directly.',
  },
  'backup schedule': {
    mcpExcludeReason: 'Installs systemd backup timers on a machine; use CLI directly.',
  },

  'machine infra show': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride:
        'Show infrastructure configuration for a machine (base domain, public IPs, ports), shared TLS settings (cert email, CF DNS token), and Cloudflare zone ID',
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
      repoArg: 'ref',
      descriptionOverride:
        'Deploy/update a repository (runs Rediaccfile up via renet compose, starts containers). The machine is derived from the ref placement. Use no-start=true to mount/prepare only (first deploy, after backup pull, or after down --unmount) without running up()',
      requiredArgs: ['ref'],
      excludeOptions: [
        'all',
        'machine',
        'no-wait',
        'include-forks',
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
      repoArg: 'ref',
      descriptionOverride:
        'Stop repository Docker containers (runs Rediaccfile down). Does NOT unmount the encrypted volume by default -- repo stays mounted and can be restarted with repo_up. Use unmount=true to also close the LUKS container',
      requiredArgs: ['ref'],
      excludeOptions: [
        'all',
        'machine',
        'parallel',
        'concurrency',
        'yes',
        'debug',
        'skip-router-restart',
        'dry-run',
      ],
    },
  },

  'repo delete': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug', 'skip-router-restart', 'dry-run'],
    },
  },

  'repo fork': {
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      repoArg: 'ref',
      requiredArgs: ['ref'],
      descriptionOverride:
        'Create a near-instant CoW fork of a repository with a NEW GUID and networkId (fully independent copy). FORK IS CONSTANT-TIME regardless of repo size: BTRFS reflink clones the image so 100 GB and 1 GB repos fork in the same ~seconds, never proportional to repo size. Fork shares the parent name with a different tag (name:tag model, like Docker images). Online forking supported (parent can stay running). Fork gets new auto-route domain. After fork, deploy with repo_up. Fork-of-fork allowed (same base name, different tag). CROSS-MACHINE: fork locally first, then use repo_push to transfer fork to target machine, then repo_up on target.',
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo migrate': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      repoArg: 'ref',
      requiredArgs: ['ref'],
      descriptionOverride:
        'Move a repository to another machine with minimal downtime: a two-phase copy (bulk sync while running, then a short stop + delta sync + start on the destination) with DNS cutover. The repo keeps its identity and secrets. Use repo_push for a backup copy that stays on both machines.',
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },

  'repo push': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      repoArg: 'ref',
      descriptionOverride:
        'Push a repository backup to storage or directly to another machine. WARNING: machine-to-machine push copies with the SAME GUID (backup/migration). To create an independent fork on another machine, use repo_fork first, then push the fork. A pushed copy is a backup artifact: boot it with backup_restore, not with push',
      requiredArgs: ['ref'],
      excludeOptions: ['watch', 'debug', 'skip-router-restart'],
    },
  },

  'repo pull': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['watch', 'debug', 'skip-router-restart'],
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

  'machine provider add': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
    },
  },

  'machine provider remove': {
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
    },
  },

  'machine provider list': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride: 'List configured cloud providers for machine provisioning',
    },
  },

  // ══════════════════════════════════════════════════════════════════════
  // P4: leaves the registry-keyed coverage check never saw
  //
  // The old gate iterated COMMAND_REGISTRY, which only declares TOP-LEVEL
  // domains, so any leaf under an undeclared domain was unclassified and nobody
  // heard about it. The gate now walks the real Commander tree, and it found 32
  // such leaves. Each is classified below on the posture the rest of this file
  // already takes: lifecycle operations are tools (repo delete, machine
  // provision and backup restore all are); exclusions are for what an agent
  // must not drive — an interactive TTY, key material, a file upload, or a
  // judgment call a human owes.
  // ══════════════════════════════════════════════════════════════════════

  'machine setup': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
      descriptionOverride:
        'Finish onboarding a machine: install renet and prepare it to host repositories.',
      excludeOptions: ['debug'],
    },
  },
  'machine scan-keys': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
      descriptionOverride:
        "Record the machine's SSH host keys in the local config. Required before any command can reach it.",
      excludeOptions: ['debug'],
    },
  },
  // ★ OPERATOR-RULED (unmapped by spec §5; ruled 2026-07-13): EXCLUDE both.
  // `infra push` PROVISIONS CLOUD VMs AND SPENDS REAL MONEY. `infra set` is the loaded gun
  // that `push` fires. An agent must not be able to both arm and pull.
  'machine infra set': {
    mcpExcludeReason:
      'Sets the infra block that `machine infra push` then acts on, which provisions cloud resources and spends real money. Arming and firing are both operator decisions.',
  },
  'machine infra push': {
    mcpExcludeReason:
      'Applies the infra block to the machine: provisions cloud resources, public DNS and TLS. It spends real money and changes what the world can reach.',
  },
  // ★ OPERATOR-RULED: the cert cache is KEY MATERIAL. `clear` DESTROYS it. Only `status`,
  // which returns no material, is agent surface. (These are #61's trio: they were declared
  // destructive precisely so the console would confirm them; that is not a licence to also
  // hand them to an agent.)
  'machine infra cert pull': {
    mcpExcludeReason:
      'Moves TLS key material into the local cert cache. Key material is not agent surface.',
  },
  'machine infra cert push': {
    mcpExcludeReason: 'Moves TLS key material onto the machine. Key material is not agent surface.',
  },
  'machine infra cert status': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'machine infra cert clear': {
    mcpExcludeReason: 'Destroys cached TLS key material. Irreversible, and it is key material.',
  },

  // Archived-record bookkeeping (config-plane; see COMMAND_PLANES).
  //
  // ★ SPEC-MANDATED, and I had it wrong. spec/03 §5 says "MCP: exclude (group):
  // `Config archive bookkeeping.`" I had classified list/restore as TOOLS by inferring
  // from this file's posture, and an inference does not outrank an explicit disposition.
  // Group-level, so no leaf underneath can acquire a tool by accident.
  'repo admin archive': {
    mcpExcludeReason:
      'Config archive bookkeeping. Purge also permanently destroys the archived record that makes `repo delete` recoverable, and the safety net is not a thing an agent should be able to cut.',
  },

  // Client-side transfer. Barred from the PROXY (a remote executor cannot see the caller's
  // filesystem) AND from MCP.
  //
  // ★ SPEC-MANDATED [P0-DECIDED], and it corrects my reasoning rather than merely
  // overruling it. spec/03 §5: "MCP: exclude (all three): `Requires local filesystem paths
  // on the MCP host.`" I had made all three tools on the assumption that the MCP server runs
  // where the operator's files are. It does not have to. The paths are the CALLER's, and the
  // MCP host is not necessarily the caller.
  'repo sync upload': {
    grandGuard: true,
    mcpExcludeReason: 'Requires local filesystem paths on the MCP host. Run it from the CLI.',
  },
  'repo sync download': {
    grandGuard: true,
    mcpExcludeReason: 'Requires local filesystem paths on the MCP host. Run it from the CLI.',
  },
  'repo sync status': {
    mcpExcludeReason: 'Requires local filesystem paths on the MCP host. Run it from the CLI.',
  },

  'config list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'config show': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'config audit log': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride: 'Read the audit log of mutations made through this config.',
    },
  },
  'config audit verify': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride: "Verify the audit log's hash chain has not been tampered with.",
    },
  },
  'config audit tail': {
    mcpExcludeReason: 'Follows the audit log until Ctrl+C; it never returns on its own.',
  },
  'config init': {
    mcpExcludeReason: 'Creates a named config file — the operator decides what configs exist.',
  },
  'config delete': {
    mcpExcludeReason: 'Deletes a whole config file, credentials and all. Human decision.',
  },
  'config recover': {
    mcpExcludeReason: 'Rewrites a damaged config from backup; the operator must see what changed.',
  },
  'config prune': {
    // ★ SPEC-MANDATED: spec/03 §5 grants mcp(write, idempotent) and withholds only
    // --purge-archived (which drops EVERY archived record regardless of grace). I had
    // excluded the whole leaf by inference; the spec is narrower and better — prune is a
    // safe, idempotent cleanup, and only its nuclear option is agent-inappropriate.
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
      excludeOptions: ['purge-archived'],
    },
  },
  'config edit': {
    mcpExcludeReason: 'Opens $EDITOR on the decrypted config; it needs a TTY.',
  },
  // Whole subtree: `field get` returns DECRYPTED secret values, and `field rotate`
  // hard-refuses a non-TTY stdin. Excluded at the parent so no leaf under it can
  // acquire a tool by accident (the coverage gate treats an ancestor exclusion as
  // covering its descendants, and would conflict if one of them also declared mcp).
  'config field': {
    mcpExcludeReason: 'Reads and rewraps secret field values — key material, not agent surface.',
  },

  credits: {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      descriptionOverride: 'Show the remaining credit balance for this account.',
    },
  },

  'cluster rehearse': {
    mcpExcludeReason:
      'Boots an entire throwaway k3s control plane to dry-run a migration; expensive, and gated behind REDIACC_ALLOW_CLUSTER_OPS.',
  },

  serve: {
    mcpExcludeReason: 'Runs the executor daemon in the foreground until SIGINT; it never returns.',
  },

  'config set': {
    mcpExcludeReason: 'Config value mutation — use CLI directly',
  },
  'config clear': {
    mcpExcludeReason: 'Config value deletion — use CLI directly',
  },
  'config reconcile': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
      descriptionOverride:
        'Rebuild the local state bucket from machine truth (renet list all). Fixes stale datastore-attach and routing data; run this when a derived-machine op reports a state mismatch (exit 12).',
      excludeOptions: ['debug'],
    },
  },
  'config rotate-cek': {
    mcpExcludeReason:
      'Rotates the org config-encryption key; destructive and human-driven (portal wizard).',
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

  'repo admin template apply': {
    grandGuard: true,
    mcpExcludeReason: 'Requires file upload; use CLI directly.',
  },
  'repo admin template': {
    mcpExcludeReason: 'Template catalog and application; use CLI directly.',
  },
  'repo admin ownership': {
    grandGuard: true,
    mcpExcludeReason: 'Destructive ownership transfer.',
  },
  // ('repo sync upload' / 'repo sync download' carry grandGuard alongside their
  // MCP metadata above. They were declared twice — a duplicate key silently wins,
  // and the later bare `{ grandGuard: true }` was erasing the MCP entry.)
  'repo tunnel': {
    grandGuard: true,
    mcpExcludeReason: 'Interactive SSH tunnel — blocks until Ctrl+C',
  },
  'repo admin autostart enable': { grandGuard: true, forkBlocked: true },
  'repo admin autostart disable': { grandGuard: true, forkBlocked: true },
  // Promote swaps a validated fork into production under the parent's name.
  // Spec §5.4 [P0-DECIDED] makes it an MCP exclusion: it is exactly the verb an
  // agent should hand back to the operator.
  'repo promote': {
    grandGuard: true,
    mcpExcludeReason: 'Production swap; human decision.',
  },
  'repo status': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      repoArg: 'ref',
      requiredArgs: ['ref'],
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
  'repo cat': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo diff': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo commit': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write' as const,
      repoArg: 'ref',
      requiredArgs: ['ref', 'message'],
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
      repoArg: 'commit-or-branch-ref',
      requiredArgs: ['commit-or-branch-ref', 'tag'],
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
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug'],
    },
  },
  'repo merge': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write' as const,
      repoArg: 'ref',
      requiredArgs: ['ref', 'from'],
      descriptionOverride:
        'Lifecycle-safe merge of a source commit/fork into a target working fork. Refuses a mounted/running target unless --force (which quiesces it first); never mutates a live mount; builds the result in a reflink clone and atomically swaps it in.',
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
  'repo admin fsck': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      descriptionOverride:
        'Validate config refs (branches/HEAD) against the objects present on a machine; report dangling refs and orphan commits.',
    },
  },
  'repo admin validate': {
    grandGuard: true,
    mcpExcludeReason: 'Use repo status for MCP.',
  },
  'repo admin autostart': {
    mcpExcludeReason: 'Autostart management.',
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
  // No grandGuard: trim only releases blocks the filesystem already freed
  // (fstrim + dangling-image prune); repo data is untouched, safe on grands.
  // --docker-volumes IS data-destructive (deletes unused volumes), so it is
  // excluded from the MCP surface — CLI only.
  // `ref` is REQUIRED for the MCP tool even though the CLI positional is
  // optional: the no-ref form trims every mounted repository on the machine, and
  // `repoArg` is what the grand guard resolves. Leaving ref omittable (and
  // `machine` exposed) would let an agent run the machine-wide form unguarded
  // across grands. The machine-wide trim stays CLI-only.
  'repo trim': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug', 'docker-volumes', 'machine'],
    },
  },
  // Size policy (auto-grow/auto-trim, rediacc/renet#76). Setting policy
  // changes machine behavior (quota growth consent) — CLI-only; reading is
  // harmless but the JSON blob shape is CLI-oriented too.
  'repo policy': {
    mcpExcludeReason:
      'Size-policy management changes machine auto-grow behavior — use CLI directly',
  },
  // Gate B on the REPO arm of each connect leaf (the place arm is a machine shell,
  // class A). These were keyed 'term repo' / 'vscode repo' — paths that never
  // existed in the command tree, so the policy layer and the tree disagreed on the
  // string. Keyed to the real leaves now.
  'term connect': { grandGuard: true },
  'vscode connect': { grandGuard: true },

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
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug'],
    },
  },
  'repo secret get': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read' as const,
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug'],
    },
  },

  // ══════════════════════════════════════════════════════════════════════
  // MCP-excluded commands (with documented reasons)
  // ══════════════════════════════════════════════════════════════════════

  // ── Interactive / GUI ─────────────────────────────────────────────
  vscode: { mcpExcludeReason: 'Opens VS Code GUI; not useful for MCP agents.' },
  // §5.8: the shell itself is interactive, and the container side door it used to
  // carry (--container/--log-lines/--follow) is retired in favour of `repo logs`
  // and `repo exec`, which ARE MCP tools. An agent that wants a command run in a
  // repo now asks for exactly that, instead of asking for a shell and typing into it.
  term: { mcpExcludeReason: 'Interactive shell.' },

  // ── Local-only tooling ────────────────────────────────────────────
  ops: { mcpExcludeReason: 'Local VM provisioning — requires host KVM/QEMU, not remote-operable' },
  doctor: { mcpExcludeReason: 'Diagnoses local CLI installation — not a remote operation' },
  update: { mcpExcludeReason: 'CLI self-update — not a remote operation' },
  subscription: { mcpExcludeReason: 'License management; local concern.' },
  mcp: { mcpExcludeReason: 'The MCP server itself — cannot recurse' },

  // ── Sync requires local filesystem ────────────────────────────────

  // ── Covered by sub-operations ─────────────────────────────────────
  run: {
    agentBlocked: true,
    mcpExcludeReason: 'Escape hatch for raw renet functions — agents should use typed tools',
  },

  // ── Subcommands ───────────────────────────────────────────────────
  'storage browse': { mcpExcludeReason: 'Interactive file browser — requires TTY' },

  // ── Factory-generated CRUD (covered by higher-level operations) ──
  'storage list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read', excludeOptions: ['reveal'] },
  },
  'storage add': {
    mcp: { destructive: false, idempotent: false, timeout: 'write' },
  },
  'storage remove': {
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      excludeOptions: ['yes', 'dry-run'],
    },
  },
  'storage import': { mcpExcludeReason: 'Reads a local rclone definition file; use CLI directly.' },

  // ── repo logs / repo exec (R2-F14): the first-class replacements for the
  // container side door `term connect` used to carry. These are what make the
  // `term` MCP exclusion honest: an agent that wants a log line or a command run
  // asks for exactly that, instead of asking for an interactive shell.
  'repo logs': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      repoArg: 'ref',
      excludeOptions: ['follow', 'debug'],
    },
  },
  'repo exec': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: false,
      timeout: 'write',
      repoArg: 'ref',
      excludeOptions: ['interactive', 'debug'],
    },
  },

  // ── Repo replicate group (spec 05 §1 read replicas) ───────────────────
  // Managed state on the REPO (spec §4.4): one set per repo, keyed by the ref.
  // Gate class B — grandGuard only: replicate FORKS the primary's datastore and
  // never writes to it, so it stays within one cluster and needs no class-D
  // unlock. Kept out of MCP until the flow has live-cluster validation.
  // ★ FLIPPED 2026-07-13 on a GREEN #49 live probe. The data path is proven END TO END on
  // the shipping binary, red-then-green, one variable apart: before the fix the replica's PV
  // resolved to an EMPTY directory and the pod came up `1/1 Running` with NO FailedMount and
  // no error of any kind (a broken replica does not crashloop — it serves nothing, silently).
  // After one `datastore volumes-open`, the same directory held the nonce THE PRIMARY'S POD
  // WROTE BEFORE THE FORK EXISTED, byte-identical. No empty volume, no fresh LUKS format and
  // no default image can produce that value, which is why the nonce was the assertion.
  // spec/03 §5.4 authorizes exactly these three.
  'repo replicate': {
    grandGuard: true,
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'write',
      repoArg: 'ref',
      requiredArgs: ['ref'],
      descriptionOverride:
        'Provision read replicas of a repository. Declarative: the replica count is the desired state, so re-running with the same count is a no-op.',
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  'repo replicate status': {
    mcp: {
      destructive: false,
      idempotent: true,
      timeout: 'read',
      repoArg: 'ref',
      requiredArgs: ['ref'],
    },
  },
  'repo replicate remove': {
    grandGuard: true,
    mcp: {
      destructive: true,
      idempotent: true,
      timeout: 'write',
      repoArg: 'ref',
      requiredArgs: ['ref'],
      excludeOptions: ['debug', 'skip-router-restart'],
    },
  },
  // ★ HELD, and the reason is stated honestly rather than deferred. `refresh` re-forks every
  // replica, which makes it the exact site of #49's back-door hole: a re-fork WITHOUT the
  // LUKS re-open would roll the ENTIRE replica set to empty — on the one command whose whole
  // job is to refresh data. The fix is in and unit-pinned, but the refresh path itself has
  // never been exercised on a live cluster, and #67 (repo create cannot make a kube repo at
  // all) has so far prevented the attempt. We do not advertise a command to an agent on the
  // strength of a promise. Flip this ONLY on a green live refresh.
  'repo replicate refresh': {
    grandGuard: true,
    mcpExcludeReason:
      'Rolling replica re-clone. The re-fork path is where a missing LUKS re-open would empty the whole replica set (bug #49), and it has never been exercised on a live cluster.',
  },

  // ── Repo canary group (spec 05 §2 release ladder rung 2) ──────────────
  // ★ EXCLUDED, AND NOT ON A TECHNICALITY. The #49 probe validates REPLICATE's data path —
  // whether a fork's LUKS volume carries the parent's bytes. A CANARY IS A DIFFERENT
  // MECHANISM: it runs a NEW IMAGE against the primary's SHARED LIVE DATA, and `canary
  // weight` SHIFTS REAL PRODUCTION TRAFFIC. The probe says nothing about either.
  // Same judgement class that already excludes `repo promote`: traffic control over live
  // production is the verb an agent hands back to the operator.
  // ★ And #42 means the weighted split was INERT in production until it was fixed today, so
  // NOBODY HAS EVER WATCHED A WEIGHTED SPLIT WORK ON A REAL MACHINE. We do not hand an AI
  // agent a traffic-control primitive that has never been observed working.
  'repo canary create': {
    grandGuard: true,
    mcpExcludeReason:
      "Runs a new image against the primary's SHARED LIVE DATA. The replicate probe validates a different mechanism and says nothing about this one.",
  },
  'repo canary status': {
    mcpExcludeReason:
      'Excluded with the rest of the canary family: exposing only the read half invites an agent to drive a release it cannot safely complete.',
  },
  'repo canary weight': {
    grandGuard: true,
    mcpExcludeReason:
      'Shifts REAL PRODUCTION TRAFFIC between versions. A release decision belongs to the operator, and the weighted split has never been observed working on a live machine (bug #42 made it inert until today).',
  },
  'repo canary remove': {
    grandGuard: true,
    mcpExcludeReason:
      'Tears down a canary that is taking live traffic. Excluded with the family it belongs to.',
  },

  // ── Cluster group ──────────────────────────────────────────────────────
  'cluster status': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'cluster kubeconfig': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  // Provisioning/teardown are host-mutating and long-running; keep them out of
  // agent hands by default. Unlike `run`, this family is NOT an absolute block:
  // the operator can deliberately unlock specific clusters (or all, via `*`)
  // with REDIACC_ALLOW_CLUSTER_OPS, ancestry-verified exactly like
  // REDIACC_ALLOW_GRAND_REPO — enforced in command-policy.ts, not here.
  'cluster create': {
    agentBlocked: true,
    mcpExcludeReason: 'Provisions cloud/VM infrastructure — not an agent operation',
  },
  'cluster destroy': {
    agentBlocked: true,
    mcpExcludeReason: 'Destroys cloud/VM infrastructure — not an agent operation',
  },
  'cluster scale': {
    agentBlocked: true,
    mcpExcludeReason: 'Mutates cluster node pools — not an agent operation',
  },
  'cluster fork': {
    agentBlocked: true,
    mcpExcludeReason: 'Clones a whole cluster — not an agent operation',
  },
  'cluster migrate': {
    agentBlocked: true,
    mcpExcludeReason: 'Moves a whole cluster — not an agent operation',
  },
  'cluster join': {
    agentBlocked: true,
    mcpExcludeReason: 'Cluster membership mutation — not an agent operation',
  },
  'cluster evict': {
    agentBlocked: true,
    mcpExcludeReason: 'Cluster membership mutation — not an agent operation',
  },
  // ── Datastore family (spec §5.3) ───────────────────────────────────────
  // Mutations are class D (agentBlocked + REDIACC_ALLOW_CLUSTER_OPS): each one
  // moves or destroys a pool holding every repo inside it. Reads are class A and
  // MCP-visible, which is what lets an agent SEE placement without moving it.
  'datastore create': {
    agentBlocked: true,
    mcpExcludeReason: 'Infrastructure storage provisioning; operator unlock only.',
  },
  'datastore attach': {
    agentBlocked: true,
    mcpExcludeReason: 'Moves every repository in the pool; operator unlock only.',
  },
  'datastore detach': {
    agentBlocked: true,
    mcpExcludeReason: 'Stops every repository in the pool; operator unlock only.',
  },
  'datastore fork': {
    agentBlocked: true,
    mcpExcludeReason: 'Infrastructure storage operation; operator unlock only.',
  },
  'datastore resize': {
    agentBlocked: true,
    mcpExcludeReason: 'Destructive storage geometry change.',
  },
  'datastore delete': {
    agentBlocked: true,
    mcpExcludeReason: 'Destroys a storage pool.',
  },
  'datastore snapshot create': {
    agentBlocked: true,
    mcpExcludeReason: 'Infrastructure snapshot; operator unlock only.',
  },
  'datastore snapshot': {
    mcpExcludeReason: 'Group; its leaves carry their own dispositions.',
  },
  'datastore list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
  'datastore status': {
    mcp: { destructive: false, idempotent: true, timeout: 'read', excludeOptions: ['debug'] },
  },
  'datastore snapshot list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read', excludeOptions: ['debug'] },
  },

  // Cluster snapshot (R2-F13): create is class D like every other cluster
  // mutation; list is a read (class A) and MCP-safe.
  'cluster snapshot create': {
    agentBlocked: true,
    mcpExcludeReason: 'Infrastructure snapshot — operator unlock only',
  },
  'cluster snapshot list': {
    mcp: { destructive: false, idempotent: true, timeout: 'read' },
  },
};

/** Look up metadata for a command path. */
export function getCommandMeta(commandPath: string): CommandMeta | undefined {
  return COMMAND_METADATA[commandPath];
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
