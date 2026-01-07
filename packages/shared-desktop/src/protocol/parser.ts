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

    let token: string;
    let teamName: string;
    let machineName: string;
    let repositoryName: string | undefined;
    let actionIndex: number;

    // Check if token is in hostname (netloc) or path
    if (parsed.hostname && pathParts.length >= 2) {
      // Format: rediacc://token/team/machine[/repository][/action]
      token = decodeURIComponent(parsed.hostname).replace(/[\n\r]/g, '');
      if (!validateToken(token)) {
        throw new Error('Invalid or missing authentication token in protocol URL');
      }
      teamName = decodeURIComponent(pathParts[0]);
      machineName = decodeURIComponent(pathParts[1]);

      // Check if we have repository or action next
      if (pathParts.length >= 3) {
        const thirdPart = pathParts[2];
        if (VALID_ACTIONS.includes(thirdPart as ProtocolAction)) {
          // Third part is action, no repository
          repositoryName = undefined;
          actionIndex = 2;
        } else {
          // Third part is repository
          repositoryName = decodeURIComponent(thirdPart);
          actionIndex = 3;
        }
      } else {
        repositoryName = undefined;
        actionIndex = 2;
      }
    } else if (pathParts.length >= 3) {
      // Format: rediacc:///token/team/machine[/repository][/action] in path
      token = decodeURIComponent(pathParts[0]).replace(/[\n\r]/g, '');
      if (!validateToken(token)) {
        throw new Error('Invalid or missing authentication token in protocol URL');
      }
      teamName = decodeURIComponent(pathParts[1]);
      machineName = decodeURIComponent(pathParts[2]);

      // Check if we have repository or action next
      if (pathParts.length >= 4) {
        const fourthPart = pathParts[3];
        if (VALID_ACTIONS.includes(fourthPart as ProtocolAction)) {
          // Fourth part is action, no repository
          repositoryName = undefined;
          actionIndex = 3;
        } else {
          // Fourth part is repository
          repositoryName = decodeURIComponent(fourthPart);
          actionIndex = 4;
        }
      } else {
        repositoryName = undefined;
        actionIndex = 3;
      }
    } else {
      throw new Error('URL must contain at least token, team, and machine');
    }

    // Extract action if present
    let action: ProtocolAction = 'desktop'; // Default action
    if (pathParts.length > actionIndex) {
      const actionStr = pathParts[actionIndex].toLowerCase();
      if (VALID_ACTIONS.includes(actionStr as ProtocolAction)) {
        action = actionStr as ProtocolAction;
      } else {
        throw new Error(
          `Invalid action '${actionStr}'. Must be one of: ${VALID_ACTIONS.join(', ')}`
        );
      }
    }

    // Parse query parameters
    const params: Record<string, string> = {};
    for (const [key, value] of parsed.searchParams) {
      params[key] = value;
    }

    return {
      token,
      teamName,
      machineName,
      repositoryName,
      action,
      params,
    };
  } catch (e) {
    if (e instanceof Error) {
      throw new Error(`Failed to parse URL '${url}': ${e.message}`);
    }
    throw new Error(`Failed to parse URL '${url}': Unknown error`);
  }
}

/**
 * Builds CLI command arguments from a parsed protocol URL
 *
 * @param parsed - Parsed protocol URL
 * @returns Array of CLI command arguments
 */
export function buildCliCommand(parsed: ProtocolUrl): string[] {
  const { token, teamName, machineName, repositoryName, action, params } = parsed;

  const cmd: string[] = [];

  switch (action) {
    case 'sync': {
      cmd.push('sync');
      const direction = params?.direction ?? 'download';
      if (direction !== 'upload' && direction !== 'download') {
        throw new Error(`Invalid sync direction: ${direction}`);
      }
      cmd.push(direction);
      cmd.push('--token', token, '--team', teamName, '--machine', machineName);
      if (repositoryName) {
        cmd.push('--repository', repositoryName);
      }
      if (params?.localPath) {
        cmd.push('--local', params.localPath);
      }
      if ((params?.mirror ?? '').toLowerCase() === 'true') {
        cmd.push('--mirror');
      }
      if ((params?.verify ?? '').toLowerCase() === 'true') {
        cmd.push('--verify');
      }
      break;
    }

    case 'terminal': {
      cmd.push('term');
      cmd.push('--token', token, '--team', teamName, '--machine', machineName);

      // Handle terminal type
      if (params?.terminalType === 'machine') {
        // Connect to machine directly (no repository)
        // Already have the base command, just don't add repository
      } else if (params?.terminalType === 'container' && params.containerId) {
        // Container terminal operations
        const containerAction = params.action || 'terminal';
        const containerId = params.containerId;

        if (repositoryName) {
          cmd.push('--repository', repositoryName);
        }

        if (containerAction === 'logs') {
          // Docker logs with optional tail and follow
          const lines = params.lines || '50'; // Default to 50 lines like Python CLI
          const follow = params.follow === 'true' ? '-f' : '';
          cmd.push('--command', `docker logs --tail ${lines} ${follow} ${containerId}`.trim());
        } else if (containerAction === 'stats') {
          // Docker stats for the container
          cmd.push('--command', `docker stats ${containerId}`);
        } else if (containerAction === 'exec') {
          // Docker exec with specified shell
          const shell = params.shell || 'bash';
          const execCommand = params.command || shell;
          cmd.push('--command', `docker exec -it ${containerId} ${execCommand}`);
        } else {
          // Default: interactive shell in container
          const shell = params.shell || 'bash';
          cmd.push('--command', `docker exec -it ${containerId} ${shell}`);
        }
      } else {
        // Regular repository terminal
        if (repositoryName) {
          cmd.push('--repository', repositoryName);
        }
        if (params?.command) {
          cmd.push('--command', params.command);
        }
      }
      break;
    }

    case 'browser': {
      // Route browser action to desktop command (file browser functionality)
      // There is no separate 'browser' CLI command - it's handled by 'desktop'
      cmd.push('desktop');
      cmd.push('--token', token, '--team', teamName, '--machine', machineName);
      if (repositoryName) {
        cmd.push('--repository', repositoryName);
      }
      if (params?.path) {
        cmd.push('--path', params.path);
      }
      break;
    }

    case 'vscode': {
      cmd.push('vscode');
      cmd.push('--token', token, '--team', teamName, '--machine', machineName);
      if (repositoryName) {
        cmd.push('--repository', repositoryName);
      }
      if (params?.path) {
        cmd.push('--path', params.path);
      }
      break;
    }

    case 'plugin': {
      cmd.push('plugin');
      cmd.push('--token', token, '--team', teamName, '--machine', machineName);
      if (repositoryName) {
        cmd.push('--repository', repositoryName);
      }
      if (params?.pluginName) {
        cmd.push('--name', params.pluginName);
      }
      if (params?.pluginAction) {
        cmd.push('--action', params.pluginAction);
      }
      break;
    }

    case 'desktop':
    default: {
      cmd.push('desktop');
      cmd.push('--token', token, '--team', teamName, '--machine', machineName);
      if (repositoryName) {
        cmd.push('--repository', repositoryName);
      }
      if (params?.containerId) {
        cmd.push('--container-id', params.containerId);
      }
      break;
    }
  }

  // Add API URL if specified (applies to all commands)
  if (params?.apiUrl) {
    cmd.push('--api-url', params.apiUrl);
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
