import type { SliderConfig } from './cost-presets';

export const SLIDER_CONFIGS: Record<string, SliderConfig[]> = {
  'environment-cloning': [
    { id: 'devs', min: 1, max: 50, defaultValue: 10 },
    { id: 'reqs', min: 1, max: 10, defaultValue: 2 },
    { id: 'wait', min: 1, max: 5, defaultValue: 3 },
  ],
  'infrastructure-costs': [
    { id: 'envs', min: 1, max: 50, defaultValue: 15 },
    { id: 'cost', min: 50, max: 1000, step: 50, defaultValue: 200 },
    { id: 'util', min: 10, max: 80, defaultValue: 33 },
  ],
  'production-parity': [
    { id: 'devs', min: 1, max: 50, defaultValue: 10 },
    { id: 'bugs', min: 1, max: 15, defaultValue: 3 },
    { id: 'hours', min: 1, max: 16, defaultValue: 4 },
  ],
  integrations: [
    { id: 'devs', min: 1, max: 50, defaultValue: 10 },
    { id: 'failures', min: 1, max: 20, defaultValue: 4 },
    { id: 'hours', min: 1, max: 8, defaultValue: 3 },
  ],
  'immutable-backups': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'recovery', min: 1, max: 168, defaultValue: 72 },
    { id: 'incidents', min: 1, max: 6, defaultValue: 1 },
  ],
  'migration-safety': [
    { id: 'data', min: 1, max: 100, defaultValue: 20 },
    { id: 'migrations', min: 1, max: 12, defaultValue: 3 },
    { id: 'hours', min: 1, max: 48, defaultValue: 8 },
  ],
  'instant-recovery': [
    { id: 'services', min: 1, max: 30, defaultValue: 8 },
    { id: 'revenue', min: 500, max: 50000, step: 500, defaultValue: 5000 },
    { id: 'incidents', min: 1, max: 12, defaultValue: 2 },
  ],
  'safe-os-testing': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'patches', min: 1, max: 24, defaultValue: 6 },
    { id: 'recovery', min: 1, max: 48, defaultValue: 8 },
  ],
  'retention-compliance': [
    { id: 'audits', min: 1, max: 4, defaultValue: 2 },
    { id: 'hours', min: 8, max: 200, defaultValue: 80 },
    { id: 'data', min: 1, max: 100, defaultValue: 20 },
  ],
  'cloud-outage-protection': [
    { id: 'rev', min: 1, max: 100, defaultValue: 10 },
    { id: 'hours', min: 1, max: 72, defaultValue: 8 },
    { id: 'failover', min: 1, max: 24, defaultValue: 4 },
  ],
  'failover-testing': [
    { id: 'services', min: 1, max: 50, defaultValue: 12 },
    { id: 'hours', min: 1, max: 72, defaultValue: 8 },
    { id: 'rev', min: 1, max: 100, defaultValue: 10 },
  ],
  'backup-verification': [
    { id: 'jobs', min: 1, max: 50, defaultValue: 14 },
    { id: 'corruption', min: 1, max: 20, defaultValue: 5 },
    { id: 'recovery', min: 1, max: 48, defaultValue: 12 },
  ],
  'vulnerability-management': [
    { id: 'vulns', min: 1, max: 20, defaultValue: 5 },
    { id: 'fixDays', min: 1, max: 30, defaultValue: 21 },
  ],
  'ai-pentesting': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'frequency', min: 1, max: 12, defaultValue: 2 },
    { id: 'fixDays', min: 1, max: 30, defaultValue: 14 },
  ],
  encryption: [
    { id: 'data', min: 1, max: 100, defaultValue: 20 },
    { id: 'audits', min: 1, max: 4, defaultValue: 2 },
    { id: 'hours', min: 8, max: 200, defaultValue: 40 },
  ],
  'continuous-security-testing': [
    { id: 'servers', min: 1, max: 100, defaultValue: 20 },
    { id: 'frequency', min: 1, max: 12, defaultValue: 1 },
    { id: 'fixDays', min: 1, max: 30, defaultValue: 14 },
  ],
  'audit-trail': [
    { id: 'audits', min: 1, max: 4, defaultValue: 2 },
    { id: 'hours', min: 8, max: 200, defaultValue: 60 },
    { id: 'servers', min: 1, max: 100, defaultValue: 15 },
  ],
  'rapid-recovery': [
    { id: 'rev', min: 1000, max: 50000, step: 1000, defaultValue: 5000 },
    { id: 'hours', min: 1, max: 168, defaultValue: 72 },
    { id: 'inc', min: 1, max: 6, defaultValue: 1 },
  ],
  'vendor-lock-in': [
    { id: 'spend', min: 1, max: 100, defaultValue: 10 },
    { id: 'years', min: 1, max: 10, defaultValue: 3 },
    { id: 'increase', min: 5, max: 40, defaultValue: 15 },
  ],
};
