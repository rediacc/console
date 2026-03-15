import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { t } from '../../i18n/index.js';
import { COMMAND_POLICIES, type CommandPath } from '../../utils/command-policy.js';
import { executeRdcCommand } from './executor.js';
import type { McpServerOptions } from './server.js';
import { TOOLS, type ToolDef } from './tool-definitions.js';

export { TOOLS, type ToolDef } from './tool-definitions.js';

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
