export interface RepoContextPattern {
  label: string;
  pattern: RegExp;
}

export const REPO_CONTEXT_PATTERNS: RepoContextPattern[] = [
  { label: 'docker', pattern: /\bdocker\b/i },
  { label: 'docker-compose', pattern: /\bdocker-compose\b/i },
  { label: 'DOCKER_HOST', pattern: /\bDOCKER_HOST=/ },
  { label: 'repo docker socket', pattern: /\/var\/run\/rediacc\/docker-/ },
  { label: 'renet compose', pattern: /\brenet\s+compose\b/i },
  { label: 'repo mount path', pattern: /\/mnt\/rediacc\/mounts\/[0-9a-f-]{36}/i },
];

/**
 * Detects if a command requires repository context (DOCKER_HOST, repo env vars).
 * Returns the first matching pattern or null if the command is safe for machine-level execution.
 */
export function detectRepoContextCommand(command: string): RepoContextPattern | null {
  for (const entry of REPO_CONTEXT_PATTERNS) {
    if (entry.pattern.test(command)) {
      return entry;
    }
  }
  return null;
}

const DOCKER_COMPOSE_PATTERN = /\b(docker\s+compose|docker-compose)\b/i;

/**
 * Detects `docker compose` / `docker-compose` usage. In repository context this
 * must be blocked because `renet compose` is a preprocessor that injects per-repo
 * loopback IPs, host network mode, CRIU capabilities, and compose validation —
 * bypassing it silently corrupts the deployment.
 */
export function detectDockerComposeCommand(command: string): boolean {
  return DOCKER_COMPOSE_PATTERN.test(command);
}

export interface RenetCommandMatch {
  renetCommand: string;
  cliHelpCommand: string;
}

const RENET_CLI_EQUIVALENTS: { pattern: RegExp; renetCommand: string; cliHelpCommand: string }[] = [
  {
    pattern: /\brenet\s+repository\b/,
    renetCommand: 'renet repository',
    cliHelpCommand: 'rdc repo --help',
  },
  {
    pattern: /\brenet\s+backup\b/,
    renetCommand: 'renet backup',
    cliHelpCommand: 'rdc repo backup --help',
  },
  {
    pattern: /\brenet\s+daemon\b/,
    renetCommand: 'renet daemon',
    cliHelpCommand: 'rdc repo --help',
  },
  {
    pattern: /\brenet\s+datastore\b/,
    renetCommand: 'renet datastore',
    cliHelpCommand: 'rdc machine --help',
  },
  {
    pattern: /\brenet\s+network\b/,
    renetCommand: 'renet network',
    cliHelpCommand: 'rdc machine --help',
  },
];

/**
 * Detects if a command runs a renet subcommand that has a CLI equivalent.
 * Matches both `renet <cmd>` and `sudo renet <cmd>` patterns.
 */
export function detectDirectRenetCommand(command: string): RenetCommandMatch | null {
  for (const entry of RENET_CLI_EQUIVALENTS) {
    if (entry.pattern.test(command)) {
      return { renetCommand: entry.renetCommand, cliHelpCommand: entry.cliHelpCommand };
    }
  }
  return null;
}
