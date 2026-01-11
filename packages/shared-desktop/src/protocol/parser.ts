import { DEFAULTS } from '@rediacc/shared/config';
import type { ProtocolAction, ProtocolUrl } from '../types/index.js';

/**
 * Valid protocol actions
 */
export const VALID_ACTIONS: ProtocolAction[] = [
  'terminal',
  'sync',
  'browser',
  'desktop',
  'vscode',
  'plugin',
] as const;

/**
 * Protocol scheme
 */
export const PROTOCOL_SCHEME = 'rediacc';

/**
 * Minimum token length for validation
 */
const MIN_TOKEN_LENGTH = 32;

/**
 * Validates a protocol token format
 *
 * @param token - Token to validate
 * @returns True if token is valid
 */
export function validateToken(token: string): boolean {
  if (!token || typeof token !== 'string') {
    return false;
  }
  if (token.length < MIN_TOKEN_LENGTH) {
    return false;
  }
  // Token should only contain alphanumeric characters, dashes, underscores, and dots
  if (!/^[a-zA-Z0-9._-]+$/.test(token)) {
    return false;
  }
  return true;
}

/**
 * Sanitizes a token by removing newlines
 */
function sanitizeToken(rawToken: string): string {
  return decodeURIComponent(rawToken).replaceAll(/[\n\r]/g, '');
}

/**
 * Validates and returns a sanitized token, or throws an error
 */
function extractAndValidateToken(rawToken: string): string {
  const token = sanitizeToken(rawToken);
  if (!validateToken(token)) {
    throw new Error('Invalid or missing authentication token in protocol URL');
  }
  return token;
}

/**
 * Determines if a path part is an action
 */
function isAction(part: string): boolean {
  return VALID_ACTIONS.includes(part as ProtocolAction);
}

/**
 * Parses repository and action index from path parts
 */
function parseRepositoryAndActionIndex(
  pathParts: string[],
  startIndex: number
): { repositoryName: string | undefined; actionIndex: number } {
  if (pathParts.length <= startIndex) {
    return { repositoryName: undefined, actionIndex: startIndex };
  }

  const nextPart = pathParts[startIndex];
  if (isAction(nextPart)) {
    return { repositoryName: undefined, actionIndex: startIndex };
  }

  return {
    repositoryName: decodeURIComponent(nextPart),
    actionIndex: startIndex + 1,
  };
}

/**
 * Extracts action from path parts
 */
function extractAction(pathParts: string[], actionIndex: number): ProtocolAction {
  if (pathParts.length <= actionIndex) {
    return 'desktop';
  }

  const actionStr = pathParts[actionIndex].toLowerCase();
  if (!VALID_ACTIONS.includes(actionStr as ProtocolAction)) {
    throw new Error(`Invalid action '${actionStr}'. Must be one of: ${VALID_ACTIONS.join(', ')}`);
  }
  return actionStr as ProtocolAction;
}

/**
 * Parses query parameters from a URL
 */
function parseQueryParams(parsed: URL): Record<string, string> {
  const params: Record<string, string> = {};
  for (const [key, value] of parsed.searchParams) {
    params[key] = value;
  }
  return params;
}

/**
 * Parses URL with token in hostname format
 */
function parseHostnameFormat(
  parsed: URL,
  pathParts: string[]
): {
  token: string;
  teamName: string;
  machineName: string;
  repositoryName: string | undefined;
  actionIndex: number;
} {
  const token = extractAndValidateToken(parsed.hostname);
  const teamName = decodeURIComponent(pathParts[0]);
  const machineName = decodeURIComponent(pathParts[1]);
  const { repositoryName, actionIndex } = parseRepositoryAndActionIndex(pathParts, 2);
  return { token, teamName, machineName, repositoryName, actionIndex };
}

/**
 * Parses URL with token in path format
 */
function parsePathFormat(pathParts: string[]): {
  token: string;
  teamName: string;
  machineName: string;
  repositoryName: string | undefined;
  actionIndex: number;
} {
  const token = extractAndValidateToken(pathParts[0]);
  const teamName = decodeURIComponent(pathParts[1]);
  const machineName = decodeURIComponent(pathParts[2]);
  const { repositoryName, actionIndex } = parseRepositoryAndActionIndex(pathParts, 3);
  return { token, teamName, machineName, repositoryName, actionIndex };
}

/**
 * Parses a rediacc:// protocol URL
 *
 * URL formats supported:
 * - rediacc://token/team/machine/repository/action?params
 * - rediacc://token/team/machine/action?params (no repository)
 * - rediacc://token/team/machine/repository?params (default action)
 *
 * @param url - The rediacc:// URL to parse
 * @returns Parsed URL components
 * @throws Error if URL is invalid
 */
export function parseProtocolUrl(url: string): ProtocolUrl {
  if (!url.startsWith(`${PROTOCOL_SCHEME}://`)) {
    throw new Error(`Invalid protocol scheme. Expected ${PROTOCOL_SCHEME}://`);
  }

  try {
    const parsed = new URL(url);
    const pathParts = parsed.pathname.split('/').filter((p) => p.length > 0);

    const hasHostnameToken = parsed.hostname && pathParts.length >= 2;
    const hasPathToken = pathParts.length >= 3;

    if (!hasHostnameToken && !hasPathToken) {
      throw new Error('URL must contain at least token, team, and machine');
    }

    const { token, teamName, machineName, repositoryName, actionIndex } = hasHostnameToken
      ? parseHostnameFormat(parsed, pathParts)
      : parsePathFormat(pathParts);

    const action = extractAction(pathParts, actionIndex);
    const params = parseQueryParams(parsed);

    return { token, teamName, machineName, repositoryName, action, params };
  } catch (e) {
    if (e instanceof Error) {
      throw new Error(`Failed to parse URL '${url}': ${e.message}`);
    }
    throw new Error(`Failed to parse URL '${url}': Unknown error`);
  }
}

/**
 * Adds common authentication arguments to command
 */
function addAuthArgs(cmd: string[], token: string, teamName: string, machineName: string): void {
  cmd.push('--token', token, '--team', teamName, '--machine', machineName);
}

/**
 * Adds repository argument if present
 */
function addRepositoryArg(cmd: string[], repositoryName: string | undefined): void {
  if (repositoryName) {
    cmd.push('--repository', repositoryName);
  }
}

/**
 * Checks if a param value is truthy ('true')
 */
function isTrueParam(value: string | undefined): boolean {
  return (value ?? '').toLowerCase() === 'true';
}

/**
 * Builds sync command arguments
 */
function buildSyncCommand(parsed: ProtocolUrl): string[] {
  const { token, teamName, machineName, repositoryName, params } = parsed;
  const cmd: string[] = ['sync'];

  const direction = params?.direction ?? DEFAULTS.PROTOCOL.ACTION;
  if (direction !== 'upload' && direction !== 'download') {
    throw new Error(`Invalid sync direction: ${direction}`);
  }
  cmd.push(direction);
  addAuthArgs(cmd, token, teamName, machineName);
  addRepositoryArg(cmd, repositoryName);

  if (params?.localPath) {
    cmd.push('--local', params.localPath);
  }
  if (isTrueParam(params?.mirror)) {
    cmd.push('--mirror');
  }
  if (isTrueParam(params?.verify)) {
    cmd.push('--verify');
  }

  return cmd;
}

/**
 * Builds docker command string for container operations
 */
function buildContainerCommand(params: Record<string, string>): string {
  const containerAction = params.action || 'terminal';
  const containerId = params.containerId;
  const shell = params.shell || 'bash';

  switch (containerAction) {
    case 'logs': {
      const lines = params.lines || '50';
      const follow = params.follow === 'true' ? '-f' : '';
      return `docker logs --tail ${lines} ${follow} ${containerId}`.trim();
    }
    case 'stats':
      return `docker stats ${containerId}`;
    case 'exec': {
      const execCommand = params.command || shell;
      return `docker exec -it ${containerId} ${execCommand}`;
    }
    default:
      return `docker exec -it ${containerId} ${shell}`;
  }
}

/**
 * Builds terminal command arguments
 */
function buildTerminalCommand(parsed: ProtocolUrl): string[] {
  const { token, teamName, machineName, repositoryName, params } = parsed;
  const cmd: string[] = ['term'];
  addAuthArgs(cmd, token, teamName, machineName);

  // Handle terminal type
  if (params?.terminalType === 'machine') {
    // Connect to machine directly (no repository)
    return cmd;
  }

  if (params?.terminalType === 'container' && params.containerId) {
    addRepositoryArg(cmd, repositoryName);
    cmd.push('--command', buildContainerCommand(params));
    return cmd;
  }

  // Regular repository terminal
  addRepositoryArg(cmd, repositoryName);
  if (params?.command) {
    cmd.push('--command', params.command);
  }
  return cmd;
}

/**
 * Builds browser command arguments
 */
function buildBrowserCommand(parsed: ProtocolUrl): string[] {
  const { token, teamName, machineName, repositoryName, params } = parsed;
  const cmd: string[] = ['desktop'];
  addAuthArgs(cmd, token, teamName, machineName);
  addRepositoryArg(cmd, repositoryName);

  if (params?.path) {
    cmd.push('--path', params.path);
  }
  return cmd;
}

/**
 * Builds vscode command arguments
 */
function buildVSCodeCommand(parsed: ProtocolUrl): string[] {
  const { token, teamName, machineName, repositoryName, params } = parsed;
  const cmd: string[] = ['vscode'];
  addAuthArgs(cmd, token, teamName, machineName);
  addRepositoryArg(cmd, repositoryName);

  if (params?.path) {
    cmd.push('--path', params.path);
  }
  return cmd;
}

/**
 * Builds plugin command arguments
 */
function buildPluginCommand(parsed: ProtocolUrl): string[] {
  const { token, teamName, machineName, repositoryName, params } = parsed;
  const cmd: string[] = ['plugin'];
  addAuthArgs(cmd, token, teamName, machineName);
  addRepositoryArg(cmd, repositoryName);

  if (params?.pluginName) {
    cmd.push('--name', params.pluginName);
  }
  if (params?.pluginAction) {
    cmd.push('--action', params.pluginAction);
  }
  return cmd;
}

/**
 * Builds desktop command arguments (default action)
 */
function buildDesktopCommand(parsed: ProtocolUrl): string[] {
  const { token, teamName, machineName, repositoryName, params } = parsed;
  const cmd: string[] = ['desktop'];
  addAuthArgs(cmd, token, teamName, machineName);
  addRepositoryArg(cmd, repositoryName);

  if (params?.containerId) {
    cmd.push('--container-id', params.containerId);
  }
  return cmd;
}

/**
 * Command builders map for each action type
 */
const COMMAND_BUILDERS: Record<ProtocolAction, (parsed: ProtocolUrl) => string[]> = {
  sync: buildSyncCommand,
  terminal: buildTerminalCommand,
  browser: buildBrowserCommand,
  vscode: buildVSCodeCommand,
  plugin: buildPluginCommand,
  desktop: buildDesktopCommand,
};

/**
 * Builds CLI command arguments from a parsed protocol URL
 *
 * @param parsed - Parsed protocol URL
 * @returns Array of CLI command arguments
 */
export function buildCliCommand(parsed: ProtocolUrl): string[] {
  const builder = COMMAND_BUILDERS[parsed.action];
  const cmd = builder(parsed);

  // Add API URL if specified (applies to all commands)
  if (parsed.params?.apiUrl) {
    cmd.push('--api-url', parsed.params.apiUrl);
  }

  return cmd;
}

/**
 * Builds a protocol URL from components
 *
 * @param components - URL components
 * @returns Protocol URL string
 */
export function buildProtocolUrl(components: {
  token: string;
  teamName: string;
  machineName: string;
  repositoryName?: string;
  action?: ProtocolAction;
  params?: Record<string, string>;
}): string {
  const { token, teamName, machineName, repositoryName, action, params } = components;

  let url = `${PROTOCOL_SCHEME}://${encodeURIComponent(token)}`;
  url += `/${encodeURIComponent(teamName)}`;
  url += `/${encodeURIComponent(machineName)}`;

  if (repositoryName) {
    url += `/${encodeURIComponent(repositoryName)}`;
  }

  if (action && action !== 'desktop') {
    url += `/${action}`;
  }

  if (params && Object.keys(params).length > 0) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  return url;
}
