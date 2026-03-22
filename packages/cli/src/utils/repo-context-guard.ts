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
