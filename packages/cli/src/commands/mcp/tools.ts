import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { type ExecutorOptions, executeRdcCommand } from './executor.js';

export interface ToolDef {
  name: string;
  description: string;
  schema: Record<string, z.ZodType>;
  command: (args: Record<string, unknown>) => string[];
  isDestructive: boolean;
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
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_containers',
    description: 'List Docker containers running on a machine',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'containers', args.name as string],
    isDestructive: false,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_services',
    description: 'List systemd services on a machine',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'services', args.name as string],
    isDestructive: false,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_repos',
    description: 'List deployed repositories on a machine',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'repos', args.name as string],
    isDestructive: false,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_health',
    description: 'Run health check on a machine (system, containers, services, storage)',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'health', args.name as string],
    isDestructive: false,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'config_repositories',
    description: 'List configured repositories with name-to-GUID mappings',
    schema: {},
    command: () => ['config', 'repositories'],
    isDestructive: false,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'agent_capabilities',
    description: 'List all available rdc CLI commands with their arguments and options',
    schema: {},
    command: () => ['agent', 'capabilities'],
    isDestructive: false,
    timeoutMs: READ_TIMEOUT,
  },

  // ── Write Tools (destructive) ────────────────────────────────────────
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
    timeoutMs: WRITE_TIMEOUT,
  },
  {
    name: 'repo_down',
    description: 'Stop a repository on a machine (stops containers, optionally unmounts)',
    schema: {
      name: z.string().describe('Repository name'),
      machine: z.string().describe('Target machine name'),
    },
    command: (args) => ['repo', 'down', args.name as string, '-m', args.machine as string],
    isDestructive: true,
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
    timeoutMs: READ_TIMEOUT,
  },
];

export function registerAllTools(server: McpServer, options: ExecutorOptions): void {
  for (const tool of TOOLS) {
    server.registerTool(
      tool.name,
      {
        description: tool.description,
        inputSchema: tool.schema,
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
