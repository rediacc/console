/**
 * Environment Composition for VS Code Remote SSH
 * Ported from desktop/src/cli/core/env_bootstrap.py and repository_env.py
 */

/**
 * Formats a dictionary of environment variables as bash export statements
 *
 * @param envVars - Environment variables to format
 * @returns Bash export statements
 */
export function formatBashExports(envVars: Record<string, string>): string {
  const lines: string[] = [];

  for (const [key, value] of Object.entries(envVars)) {
    // Escape single quotes in the value for bash
    const strValue = String(value);
    const escapedValue = strValue.replaceAll("'", "'\\''");
    lines.push(`export ${key}='${escapedValue}'`);
  }

  return lines.join('\n');
}

/**
 * Formats environment variables as SSH SetEnv directives
 * Matching Python CLI's format_ssh_setenv()
 *
 * @param envVars - Environment variables to format
 * @param indent - Indentation string (default: 4 spaces)
 * @returns SetEnv directives
 */
export function formatSSHSetEnv(envVars: Record<string, string>, indent = '    '): string {
  const lines: string[] = [];

  for (const [key, value] of Object.entries(envVars)) {
    // Quote the value if it contains spaces
    const strValue = String(value);
    const quotedValue = strValue.includes(' ') ? `"${strValue}"` : strValue;
    lines.push(`${indent}SetEnv ${key}=${quotedValue}`);
  }

  return lines.join('\n');
}

/**
 * Composes an environment block for remote setup
 * Matching Python CLI's compose_env_block()
 *
 * @param envVars - Environment variables to include
 * @param additionalLines - Optional additional command lines
 * @param separator - Line separator (default: newline)
 * @returns Composed environment block
 */
export function composeEnvBlock(
  envVars: Record<string, string>,
  additionalLines: string[] = [],
  separator = '\n'
): string {
  const parts: string[] = [];

  // Add environment exports
  const exports = formatBashExports(envVars);
  if (exports) {
    parts.push(exports);
  }

  // Add additional lines
  for (const line of additionalLines) {
    if (line.trim()) {
      parts.push(line);
    }
  }

  return parts.join(separator);
}

/**
 * Builds repository environment variables
 * Matching Python CLI's get_repository_environment()
 *
 * @param options - Repository configuration options
 * @returns Environment variables dictionary
 */
export function buildRepositoryEnvironment(options: {
  teamName: string;
  machineName: string;
  repositoryName: string;
  datastore: string;
  repositoryPath: string;
  universalUser: string;
  universalUserId?: string;
  networkId?: string;
  networkMode?: string;
  tag?: string;
  immovable?: boolean;
  dockerHost?: string;
  dockerSocket?: string;
  additionalEnv?: Record<string, string>;
}): Record<string, string> {
  const {
    teamName,
    machineName,
    repositoryName,
    datastore,
    repositoryPath,
    universalUser,
    universalUserId = '1000',
    networkId = '',
    networkMode = 'bridge',
    tag = 'latest',
    immovable = false,
    dockerHost,
    dockerSocket,
    additionalEnv = {},
  } = options;

  // Derive Docker socket from networkId (per-repo isolated daemon)
  const resolvedSocket =
    dockerSocket ??
    (networkId ? `/var/run/rediacc/docker-${networkId}.sock` : '/var/run/docker.sock');
  const resolvedHost = dockerHost ?? `unix://${resolvedSocket}`;

  const fullRepoPath = `${datastore}${repositoryPath}`;

  return {
    // Core identifiers
    REDIACC_TEAM: teamName,
    REDIACC_MACHINE: machineName,
    REDIACC_REPOSITORY: repositoryName,

    // Docker-related
    DOCKER_DATA: fullRepoPath,
    DOCKER_EXEC: `${fullRepoPath}/.docker-exec`,
    DOCKER_FOLDER: fullRepoPath,
    DOCKER_HOST: resolvedHost,
    DOCKER_SOCKET: resolvedSocket,

    // Network and datastore
    REDIACC_DATASTORE: datastore,
    REDIACC_DATASTORE_USER: universalUser,
    REDIACC_IMMOVABLE: immovable ? 'true' : 'false',

    // Repository-specific
    REPOSITORY_NETWORK_ID: networkId,
    REPOSITORY_NETWORK_MODE: networkMode,
    REPOSITORY_PATH: repositoryPath,
    REPOSITORY_TAG: tag,

    // System
    UNIVERSAL_USER_NAME: universalUser,
    UNIVERSAL_USER_ID: universalUserId,

    // Merge additional environment
    ...additionalEnv,
  };
}

/**
 * Builds machine-only environment variables
 * For connections without a repository context
 *
 * @param options - Machine configuration options
 * @returns Environment variables dictionary
 */
export function buildMachineEnvironment(options: {
  teamName: string;
  machineName: string;
  datastore: string;
  universalUser: string;
}): Record<string, string> {
  const { teamName, machineName, datastore, universalUser } = options;

  return {
    REDIACC_TEAM: teamName,
    REDIACC_MACHINE: machineName,
    REDIACC_DATASTORE: datastore,
    REDIACC_DATASTORE_USER: universalUser,
    UNIVERSAL_USER_NAME: universalUser,
  };
}

/**
 * Generates the sudo command for user switching
 * Matching Python CLI's compose_sudo_env_command()
 *
 * @param targetUser - User to switch to
 * @param envVars - Environment variables to preserve
 * @returns Sudo command string
 */
export function composeSudoEnvCommand(targetUser: string, envVars: Record<string, string>): string {
  // Build environment preservation flags
  const envFlags = Object.keys(envVars)
    .map((key) => `--preserve-env=${key}`)
    .join(' ');

  return `sudo ${envFlags} -i -u ${targetUser}`;
}

/**
 * Determines if user switching is needed
 *
 * @param sshUser - Current SSH user
 * @param universalUser - Target universal user
 * @returns True if user switching is required
 */
export function needsUserSwitch(sshUser: string, universalUser?: string): boolean {
  if (!universalUser?.trim()) {
    return false;
  }
  return universalUser !== sshUser;
}

/**
 * Default renet binary path on remote machines (symlink managed by versioned provisioning)
 */
const DEFAULT_RENET_PATH = '/usr/lib/rediacc/renet/current/renet';

/**
 * Standard system paths for Landlock sandbox
 */
export const SANDBOX_READ_ONLY = [
  '/usr',
  '/bin',
  '/sbin',
  '/lib',
  '/lib64',
  '/etc',
  '/proc',
  '/sys',
  '/var/run/rediacc',
  '/run/systemd',
] as const;
export const SANDBOX_EXECUTE = ['/usr', '/bin', '/sbin'] as const;
export const SANDBOX_READ_WRITE_SYSTEM = ['/tmp', '/dev'] as const;

/**
 * Options for Landlock sandbox isolation via renet sandbox-exec
 */
export interface SandboxOptions {
  /** Repo working directory (e.g., /mnt/rediacc/mounts/<guid>) */
  workingDirectory: string;
  /** VS Code server install path (e.g., /mnt/rediacc) */
  serverInstallPath: string;
  /** Docker network ID for socket access */
  networkId?: string;
  /** Path to renet binary on remote (default: /usr/lib/rediacc/renet/current/renet) */
  renetPath?: string;
}

/**
 * Builds the renet sandbox-exec command prefix for Landlock isolation
 * Matches renet's buildRemoteSandboxOptions() allowed paths
 *
 * @param options - Sandbox configuration
 * @returns Command prefix string, or empty string if workingDirectory is empty
 */
export function buildSandboxPrefix(options: SandboxOptions): string {
  if (!options.workingDirectory) {
    return '';
  }

  const renetPath = options.renetPath ?? DEFAULT_RENET_PATH;
  const parts: string[] = [renetPath, 'sandbox-exec'];

  // Read-write: repo directory, vscode-server, /tmp, /dev
  const rwPaths = [
    options.workingDirectory,
    `${options.serverInstallPath}/.vscode-server`,
    ...SANDBOX_READ_WRITE_SYSTEM,
  ];
  for (const p of rwPaths) {
    parts.push('--allow-rw', p);
  }

  // Read-only: system paths
  for (const p of SANDBOX_READ_ONLY) {
    parts.push('--allow-ro', p);
  }

  // Execute: binary paths
  for (const p of SANDBOX_EXECUTE) {
    parts.push('--allow-exec', p);
  }

  // Docker socket (if networkId provided)
  if (options.networkId) {
    parts.push('--docker-socket', `/var/run/rediacc/docker-${options.networkId}.sock`);
  }

  parts.push('--');
  return parts.join(' ');
}

/**
 * Builds RemoteCommand for VS Code SSH config
 * Supports optional Landlock sandbox isolation for repo-level connections
 *
 * @param sshUser - Current SSH user
 * @param universalUser - Target universal user for switching
 * @param sandbox - Optional sandbox options for repo isolation
 * @returns Object with remoteCommand and requestTTY settings
 */
export function buildRemoteCommand(
  sshUser: string,
  universalUser?: string,
  sandbox?: SandboxOptions
): { remoteCommand?: string; requestTTY?: string } {
  const sandboxPrefix = sandbox ? buildSandboxPrefix(sandbox) : '';
  const shell = sandboxPrefix ? `${sandboxPrefix} bash` : 'bash';

  if (needsUserSwitch(sshUser, universalUser)) {
    return {
      requestTTY: 'yes',
      remoteCommand: `sudo -u ${universalUser} ${shell}`,
    };
  }

  // No user switch needed — still apply sandbox if provided
  if (sandboxPrefix) {
    return {
      requestTTY: 'yes',
      remoteCommand: shell,
    };
  }

  return {};
}
