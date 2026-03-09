import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { type ExecutorOptions, executeRdcCommand } from './executor.js';

export interface ToolDef {
  name: string;
  description: string;
  schema: Record<string, z.ZodType>;
  command: (args: Record<string, unknown>) => string[];
  isDestructive: boolean;
  isIdempotent: boolean;
  timeoutMs?: number;
}

const READ_TIMEOUT = 120_000;
const WRITE_TIMEOUT = 300_000;

export const TOOLS: ToolDef[] = [
  // ── Read Tools (safe) ────────────────────────────────────────────────
  {
    name: 'machine_info',
    description: 'Get system info, containers, services, and resource usage for a machine',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'info', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_containers',
    description:
      'List Docker containers on a machine with status, health, resource usage, labels, and auto-route domain ({service}.{repo}.{machine}.{baseDomain})',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'containers', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_services',
    description: 'List systemd services on a machine',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'services', args.name as string],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_repos',
    description: 'List deployed repositories on a machine',
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
      'Deploy/update a repository on a machine (mounts, configures Docker, starts containers)',
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
  },
  {
    name: 'repo_down',
    description: 'Stop a repository on a machine (stops containers, optionally unmounts)',
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
  },
  {
    name: 'repo_delete',
    description: 'Delete a repository from a machine (destroys encrypted filesystem and config)',
    schema: {
      name: z.string().describe('Repository name'),
      machine: z.string().describe('Target machine name'),
    },
    command: (args) => ['repo', 'delete', args.name as string, '-m', args.machine as string],
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'repo_fork',
    description:
      'Create a CoW fork of a repository with a NEW GUID and networkId (fully independent copy). Online forking supported (parent can stay running). Fork gets new auto-route domain ({service}-{networkId}.{baseDomain}). After fork, deploy with repo_up (use --mount). CROSS-MACHINE: fork locally first, then use backup_push to transfer fork to target machine, then repo_up on target. Do NOT use backup_push alone for forking — it copies with the SAME GUID (backup/migration, not fork)',
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
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'backup_pull',
    description: 'Pull a repository backup from storage or directly from another machine',
    schema: {
      repo: z.string().describe('Repository name'),
      machine: z.string().describe('Destination machine name'),
      from_machine: z
        .string()
        .optional()
        .describe('Source machine name (for direct machine-to-machine transfer)'),
      from: z.string().optional().describe('Source storage name'),
    },
    command: (args) => {
      const cmd = ['backup', 'pull', args.repo as string, '-m', args.machine as string];
      if (args.from_machine) cmd.push('--from-machine', args.from_machine as string);
      if (args.from) cmd.push('--from', args.from as string);
      return cmd;
    },
    isDestructive: true,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
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
    description: 'Execute a command on a remote machine via SSH',
    schema: {
      machine: z.string().describe('Machine name'),
      command: z.string().describe('Command to execute'),
    },
    command: (args) => ['term', args.machine as string, '-c', args.command as string],
    isDestructive: true,
    isIdempotent: false,
    timeoutMs: WRITE_TIMEOUT,
  },
];

export function registerAllTools(server: McpServer, options: ExecutorOptions): void {
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
