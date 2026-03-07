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
    description: 'List Docker containers running on a machine',
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
    description: 'Create a CoW (Copy-on-Write) fork of a repository on the same machine',
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
      'Push a repository backup to storage or directly to another machine',
    schema: {
      repo: z.string().describe('Repository name'),
      machine: z.string().describe('Source machine name'),
      to_machine: z
        .string()
        .optional()
        .describe('Destination machine name (for direct machine-to-machine transfer)'),
      to: z.string().optional().describe('Destination storage name'),
      checkpoint: z
        .boolean()
        .optional()
        .describe('Create container checkpoint (hot backup, no downtime)'),
    },
    command: (args) => {
      const cmd = ['backup', 'push', args.repo as string, '-m', args.machine as string];
      if (args.to_machine) cmd.push('--to-machine', args.to_machine as string);
      if (args.to) cmd.push('--to', args.to as string);
      if (args.checkpoint) cmd.push('--checkpoint');
      return cmd;
    },
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'backup_pull',
    description:
      'Pull a repository backup from storage or directly from another machine',
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
