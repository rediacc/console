import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { executeRdcCommand } from './executor.js';
import type { McpServerOptions } from './server.js';
import { t } from '../../i18n/index.js';
import { COMMAND_POLICIES, type CommandPath } from '../../utils/command-policy.js';

export interface ToolDef {
  name: string;
  description: string;
  schema: Record<string, z.ZodType>;
  command: (args: Record<string, unknown>) => string[];
  isDestructive: boolean;
  isIdempotent: boolean;
  timeoutMs?: number;
  /** Field name in args that contains the repository name. Used for grand repo guard in MCP. */
  repoArgField?: string;
}

const READ_TIMEOUT = 120_000;
const WRITE_TIMEOUT = 300_000;

export const TOOLS: ToolDef[] = [
  // ── Read Tools (safe) ────────────────────────────────────────────────
  {
    name: 'machine_info',
    description:
      'Get system info, containers (repository resolved to name, original in repository_guid, domain, autoRoute), services (repository resolved to name), repositories (name resolved from GUID, original in guid), and resource usage for a machine',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'info', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_containers',
    description:
      'List Docker containers on a machine. JSON includes full container details (labels, port_mappings, image), repository resolved to name (original in repository_guid), domain, and autoRoute ({service}.{repo}.{machine}.{baseDomain})',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'containers', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_services',
    description:
      'List rediacc-managed systemd services on a machine (name, state, sub-state, restart count, memory, repository resolved to name with original in repository_guid)',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'services', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_repos',
    description:
      "List deployed repositories on a machine. JSON includes name (resolved from GUID, original in guid field), nests each repo's containers (with domain, autoRoute, repository resolved) and services for hierarchical view",
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'repos', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_health',
    description: 'Run health check on a machine (system, containers, services, storage)',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'health', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_list',
    description: 'List all configured machines',
    schema: {},
    command: () => ['machine', 'list'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'config_repositories',
    description: 'List configured repositories with name-to-GUID mappings',
    schema: {},
    command: () => ['config', 'repositories'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'config_show_infra',
    description:
      'Show infrastructure configuration for a machine (base domain, public IPs, ports), shared TLS settings (cert email, CF DNS token), and Cloudflare zone ID',
    schema: { machine: z.string().describe('Machine name') },
    command: (args) => ['config', 'show-infra', args.machine as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'agent_capabilities',
    description: 'List all available rdc CLI commands with their arguments and options',
    schema: {},
    command: () => ['agent', 'capabilities'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },

  // ── Write Tools (destructive) ────────────────────────────────────────
  {
    name: 'repo_create',
    description: 'Create a new encrypted repository on a machine',
    schema: {
      name: z.string().describe('Repository name'),
      machine: z.string().describe('Target machine name'),
      size: z.string().describe('Repository size (e.g., 5G, 10G, 100G, 1T)'),
    },
    command: (args) => [
      'repo',
      'create',
      args.name as string,
      '-m',
      args.machine as string,
      '--size',
      args.size as string,
    ],
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'repo_up',
    description:
      'Deploy/update a repository on a machine (runs Rediaccfile up via renet compose, starts containers). Use mount=true for first deploy, after backup pull, or after unmount',
    schema: {
      name: z.string().describe('Repository name'),
      machine: z.string().describe('Target machine name'),
      mount: z.boolean().optional().describe('Mount the repository filesystem'),
    },
    command: (args) => {
      const cmd = ['repo', 'up', args.name as string, '-m', args.machine as string];
      if (args.mount) cmd.push('--mount');
      return cmd;
    },
    isDestructive: true,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
    repoArgField: 'name',
  },
  {
    name: 'repo_down',
    description:
      'Stop repository Docker containers (runs Rediaccfile down). Does NOT unmount the encrypted volume by default -- repo stays mounted and can be restarted with repo_up. Use unmount=true to also close the LUKS container',
    schema: {
      name: z.string().describe('Repository name'),
      machine: z.string().describe('Target machine name'),
      unmount: z.boolean().optional().describe('Unmount the repository filesystem after stopping'),
    },
    command: (args) => {
      const cmd = ['repo', 'down', args.name as string, '-m', args.machine as string];
      if (args.unmount) cmd.push('--unmount');
      return cmd;
    },
    isDestructive: true,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
    repoArgField: 'name',
  },
  {
    name: 'repo_delete',
    description:
      'Delete a repository from a machine (destroys containers, volumes, and encrypted image). Credential is archived for recovery via config restore-archived. WARNING: config mapping is removed globally -- if the repo exists on another machine (after backup_push), re-add with config add-repository',
    schema: {
      name: z.string().describe('Repository name'),
      machine: z.string().describe('Target machine name'),
    },
    command: (args) => ['repo', 'delete', args.name as string, '-m', args.machine as string],
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
    repoArgField: 'name',
  },
  {
    name: 'repo_fork',
    description:
      'Create a CoW fork of a repository with a NEW GUID and networkId (fully independent copy). Online forking supported (parent can stay running). Fork gets new auto-route domain ({service}.{forkName}.{machine}.{baseDomain}). After fork, deploy with repo_up (use --mount). CROSS-MACHINE: fork locally first, then use backup_push to transfer fork to target machine, then repo_up on target. Do NOT use backup_push alone for forking — it copies with the SAME GUID (backup/migration, not fork)',
    schema: {
      parent: z.string().describe('Parent repository name to fork from'),
      machine: z.string().describe('Machine name'),
      tag: z.string().describe('Fork name (creates <parent>-<tag>)'),
    },
    command: (args) => [
      'repo',
      'fork',
      args.parent as string,
      '-m',
      args.machine as string,
      '--tag',
      args.tag as string,
    ],
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'backup_push',
    description:
      'Push a repository backup to storage or directly to another machine. WARNING: machine-to-machine push copies with the SAME GUID (backup/migration). To create an independent fork on another machine, use repo_fork first, then push the fork',
    schema: {
      repo: z.string().describe('Repository name'),
      machine: z.string().describe('Source machine name'),
      to_machine: z
        .string()
        .optional()
        .describe('Destination machine name (for direct machine-to-machine transfer)'),
      to: z.string().optional().describe('Destination storage name'),
      provider: z
        .string()
        .optional()
        .describe('Cloud provider name to auto-provision target machine if it does not exist'),
      checkpoint: z
        .boolean()
        .optional()
        .describe('Create container checkpoint (hot backup, no downtime)'),
    },
    command: (args) => {
      const cmd = ['backup', 'push', args.repo as string, '-m', args.machine as string];
      if (args.to_machine) cmd.push('--to-machine', args.to_machine as string);
      if (args.to) cmd.push('--to', args.to as string);
      if (args.provider) cmd.push('--provider', args.provider as string);
      if (args.checkpoint) cmd.push('--checkpoint');
      return cmd;
    },
    isDestructive: true,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
    repoArgField: 'repo',
  },
  {
    name: 'backup_pull',
    description:
      'Pull a repository backup from storage or another machine (restores the encrypted LUKS image). After pull, deploy with repo_up (use mount=true). Use force=true to overwrite existing',
    schema: {
      repo: z.string().describe('Repository name'),
      machine: z.string().describe('Destination machine name'),
      from_machine: z
        .string()
        .optional()
        .describe('Source machine name (for direct machine-to-machine transfer)'),
      from: z.string().optional().describe('Source storage name'),
      force: z.boolean().optional().describe('Force overwrite existing repository'),
    },
    command: (args) => {
      const cmd = ['backup', 'pull', args.repo as string, '-m', args.machine as string];
      if (args.from_machine) cmd.push('--from-machine', args.from_machine as string);
      if (args.from) cmd.push('--from', args.from as string);
      if (args.force) cmd.push('--force');
      return cmd;
    },
    isDestructive: true,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
    repoArgField: 'repo',
  },
  {
    name: 'machine_provision',
    description:
      'Provision a new machine on a cloud provider using OpenTofu. Creates VM, waits for SSH, installs renet, and configures infrastructure (auto-inherits base domain from sibling machines). Requires a cloud provider configured via config add-provider.',
    schema: {
      name: z.string().describe('Machine name'),
      provider: z.string().describe('Cloud provider name (from config add-provider)'),
      region: z.string().optional().describe('Override default region'),
      instance_type: z.string().optional().describe('Override default instance type'),
      image: z.string().optional().describe('Override default OS image'),
      base_domain: z
        .string()
        .optional()
        .describe(
          'Base domain for infrastructure (e.g., example.com). Auto-detected from sibling machines if not specified'
        ),
      no_infra: z.boolean().optional().describe('Skip infrastructure configuration entirely'),
    },
    command: (args) => {
      const cmd = [
        'machine',
        'provision',
        args.name as string,
        '--provider',
        args.provider as string,
      ];
      if (args.region) cmd.push('--region', args.region as string);
      if (args.instance_type) cmd.push('--type', args.instance_type as string);
      if (args.image) cmd.push('--image', args.image as string);
      if (args.base_domain) cmd.push('--base-domain', args.base_domain as string);
      if (args.no_infra) cmd.push('--no-infra');
      return cmd;
    },
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'machine_deprovision',
    description:
      'Destroy a cloud-provisioned machine via OpenTofu and remove from config. Only works for machines provisioned with "machine provision".',
    schema: {
      name: z.string().describe('Machine name to destroy'),
    },
    command: (args) => ['machine', 'deprovision', args.name as string, '--force'],
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'config_add_provider',
    description:
      'Add a cloud provider configuration for automated machine provisioning. Known providers: linode/linode, hetznercloud/hcloud.',
    schema: {
      name: z.string().describe('Provider configuration name'),
      provider: z.string().describe('Provider source (e.g., linode/linode, hetznercloud/hcloud)'),
      token: z.string().describe('API token for the cloud provider'),
      region: z.string().optional().describe('Default region for new machines'),
      instance_type: z.string().optional().describe('Default instance type'),
      image: z.string().optional().describe('Default OS image'),
    },
    command: (args) => {
      const cmd = [
        'config',
        'add-provider',
        args.name as string,
        '--provider',
        args.provider as string,
        '--token',
        args.token as string,
      ];
      if (args.region) cmd.push('--region', args.region as string);
      if (args.instance_type) cmd.push('--type', args.instance_type as string);
      if (args.image) cmd.push('--image', args.image as string);
      return cmd;
    },
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'config_remove_provider',
    description: 'Remove a cloud provider configuration',
    schema: {
      name: z.string().describe('Provider configuration name to remove'),
    },
    command: (args) => ['config', 'remove-provider', args.name as string],
    isDestructive: true,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'config_providers',
    description: 'List configured cloud providers for machine provisioning',
    schema: {},
    command: () => ['config', 'providers'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'term_exec',
    description: 'Execute a command on a remote machine or repository via SSH',
    schema: {
      machine: z.string().describe('Machine name'),
      repository: z
        .string()
        .optional()
        .describe('Repository name (required for docker/repo commands)'),
      command: z.string().describe('Command to execute'),
    },
    command: (args) => {
      const argv = ['term', args.machine as string];
      if (args.repository) argv.push(args.repository as string);
      argv.push('-c', args.command as string);
      return argv;
    },
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
    repoArgField: 'repository',
  },
];

export function registerAllTools(server: McpServer, options: McpServerOptions): void {
  for (const tool of TOOLS) {
    server.registerTool(
      tool.name,
      {
        description: tool.description,
        inputSchema: tool.schema,
        annotations: {
          destructiveHint: tool.isDestructive,
          readOnlyHint: !tool.isDestructive,
          idempotentHint: tool.isIdempotent,
          openWorldHint: true,
        },
      },
      async (args: Record<string, unknown>) => {
        const guardResult = await applyGrandRepoGuard(tool, args, options);
        if (guardResult) return guardResult;

        const argv = tool.command(args);
        const result = await executeRdcCommand(argv, {
          ...options,
          timeoutMs: tool.timeoutMs ?? options.defaultTimeoutMs,
        });
        return {
          content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }],
          isError: !result.success,
        };
      }
    );
  }
}

type ToolResult = { content: [{ type: 'text'; text: string }]; isError: boolean };

function guardError(msg: string): ToolResult {
  return { content: [{ type: 'text', text: msg }], isError: true };
}

/**
 * Derive the CLI command path from a tool definition.
 * e.g., repo_up → "repo up", backup_push → "backup push"
 */
function getToolCommandPath(tool: ToolDef): string {
  const argv = tool.command({
    name: 'x',
    machine: 'x',
    size: '1G',
    command: 'x',
    parent: 'x',
    tag: 'x',
    repo: 'x',
  });
  const cmdParts: string[] = [];
  for (const part of argv) {
    if (part === 'x' || part.startsWith('-')) break;
    cmdParts.push(part);
  }
  return cmdParts.join(' ');
}

/** Check if a fork repo is running a fork-blocked command. */
function checkForkBlocked(tool: ToolDef): ToolResult | null {
  const cmdPath = getToolCommandPath(tool);
  const policy = COMMAND_POLICIES.get(cmdPath as CommandPath);
  if (policy?.forkBlocked) {
    return guardError(t('errors.agent.forkBlocked', { command: cmdPath }));
  }
  return null;
}

/** Guard a named repo — block grand repos or fork-blocked commands. */
async function guardNamedRepo(
  tool: ToolDef,
  repoName: string,
  options: McpServerOptions
): Promise<ToolResult | null> {
  const envOverride = process.env.REDIACC_ALLOW_GRAND_REPO;
  const repoInfo = await getRepoInfo(repoName, options.configName);
  if (!repoInfo) return null;

  const isFork = !!(repoInfo.grandGuid && repoInfo.grandGuid !== repoInfo.repositoryGuid);

  if (!isFork && envOverride !== '*' && envOverride !== repoName) {
    return guardError(t('errors.agent.mcpGrandGuard', { name: repoName }));
  }
  if (isFork) return checkForkBlocked(tool);
  return null;
}

/**
 * Block destructive ops on non-fork repos unless --allow-grand or env override.
 * Also blocks fork-incompatible commands on fork repos.
 */
async function applyGrandRepoGuard(
  tool: ToolDef,
  args: Record<string, unknown>,
  options: McpServerOptions
): Promise<ToolResult | null> {
  if (!tool.repoArgField || options.allowGrand) return null;

  const repoName = args[tool.repoArgField] as string | undefined;

  if (repoName) return guardNamedRepo(tool, repoName, options);

  if (tool.name === 'term_exec' && process.env.REDIACC_ALLOW_GRAND_REPO !== '*') {
    return guardError(t('errors.agent.mcpMachineGuard'));
  }

  return null;
}

/**
 * Fetch repository config for guard checks.
 * Uses dynamic import to avoid loading config service at module level.
 */
async function getRepoInfo(
  repoName: string,
  configName?: string
): Promise<{ repositoryGuid: string; grandGuid?: string } | null> {
  try {
    const { configService } = await import('../../services/config-resources.js');
    if (configName) {
      configService.setRuntimeConfig(configName);
    }
    return (await configService.getRepository(repoName)) ?? null;
  } catch {
    return null; // config not available — let the command proceed
  }
}
