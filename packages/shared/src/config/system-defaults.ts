/**
 * Default system entity names
 * These match the middleware seed data and are used as fallbacks
 */
export const SYSTEM_DEFAULTS = {
  /** Default team name created on organization setup */
  TEAM_NAME: 'Private Team',

  /** Default region name */
  REGION_NAME: 'Default Region',

  /** Default bridge group name */
  BRIDGE_NAME: 'Global Bridges',

  /** Default repository tag */
  REPOSITORY_TAG: 'latest',
} as const;
