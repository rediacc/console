/**
 * Test data naming conventions
 */
export const TEST_PREFIXES = {
  /** CLI context prefix */
  CONTEXT: 'test-',

  /** Test organization prefix */
  ORGANIZATION: 'TestOrg-',

  /** Temporary user prefix */
  USER: 'temp_user_',

  /** Temporary machine prefix */
  MACHINE: 'temp-machine-',

  /** Temporary repository prefix */
  REPOSITORY: 'temp-repo-',

  /** Temporary team prefix */
  TEAM: 'E2E Test Team',
} as const;

/**
 * Generate a timestamped test entity name
 */
export function generateTestName(prefix: string): string {
  return `${prefix}${Date.now()}`;
}
