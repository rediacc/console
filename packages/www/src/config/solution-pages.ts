/**
 * Configuration for the new templateized solution pages.
 * Separate from the existing solutions.ts — both systems coexist.
 */

import type { ImageMetadata } from 'astro';
// Problem section illustrations
import illustrationAiPentesting from '../assets/images/illustrations/ai-pentesting.svg';
import illustrationAuditTrail from '../assets/images/illustrations/audit-trail.svg';
import illustrationBackupVerification from '../assets/images/illustrations/backup-verification.svg';
import illustrationCloudOutageProtection from '../assets/images/illustrations/cloud-outage-protection.svg';
import illustrationContinuousSecurityTesting from '../assets/images/illustrations/continuous-security-testing.svg';
import illustrationEncryption from '../assets/images/illustrations/encryption.svg';
import illustrationEnvironmentCloning from '../assets/images/illustrations/environment-cloning.svg';
import illustrationFailoverTesting from '../assets/images/illustrations/failover-testing.svg';
import illustrationImmutableBackups from '../assets/images/illustrations/immutable-backups.svg';
import illustrationInfrastructureCosts from '../assets/images/illustrations/infrastructure-costs.svg';
import illustrationInstantRecovery from '../assets/images/illustrations/instant-recovery.svg';
import illustrationIntegrations from '../assets/images/illustrations/integrations.svg';
import illustrationMigrationSafety from '../assets/images/illustrations/migration-safety.svg';
import illustrationProductionParity from '../assets/images/illustrations/production-parity.svg';
import illustrationRapidRecovery from '../assets/images/illustrations/rapid-recovery.svg';
import illustrationRetentionCompliance from '../assets/images/illustrations/retention-compliance.svg';
import illustrationSafeOsTesting from '../assets/images/illustrations/safe-os-testing.svg';
import illustrationVendorLockIn from '../assets/images/illustrations/vendor-lock-in.svg';
import illustrationVulnerabilityManagement from '../assets/images/illustrations/vulnerability-management.svg';

export type SectionType =
  | 'hero'
  | 'stats'
  | 'problem'
  | 'costCalculator'
  | 'howItWorks'
  | 'techDiff'
  | 'benefits'
  | 'competitorComparison'
  | 'socialProof'
  | 'bottomCta'
  | 'techStrip'
  | 'exploreSolutions'
  | 'references';

export type SolutionCategory =
  | 'dev-env'
  | 'ransomware'
  | 'multi-cloud'
  | 'backups'
  | 'encryption'
  | 'defense';

export interface TechItem {
  name: string;
  kind: string;
}

export const CATEGORY_ORDER = [
  'ransomware',
  'multi-cloud',
  'backups',
  'encryption',
  'dev-env',
  'defense',
] as const satisfies readonly SolutionCategory[];

export interface SolutionPageConfig {
  /** Translation content key: pages.solutionPages.<contentKey> */
  contentKey: string;
  /** Category for explore grid color coding */
  category: SolutionCategory;
  /** Which sections to render (in canonical order) */
  sections: SectionType[];
  /** Calculator compute preset name (required if costCalculator in sections) */
  calculatorPreset?: string;
  /** Competitor column headers for comparison table */
  competitors?: string[];
  /** Tech strip items with category color coding */
  techStrip?: TechItem[];
  /** Problem section illustration */
  illustration?: ImageMetadata;
  /** Primary CTA destination (overrides category default). Relative to /{lang}. */
  ctaHref?: string;
}

/** Default CTA destinations by category. Relative paths are prefixed with /{lang} at render time. */
export const CATEGORY_CTA_MAP: Record<SolutionCategory, string> = {
  'dev-env': '/install',
  ransomware: '/contact?interest=threat-response',
  'multi-cloud': '/contact?interest=disaster-recovery',
  backups: '/contact?interest=disaster-recovery',
  encryption: '/contact?interest=data-security',
  defense: '/contact?interest=data-security',
};

const ALL_SECTIONS = [
  'hero',
  'stats',
  'problem',
  'costCalculator',
  'howItWorks',
  'techDiff',
  'benefits',
  'competitorComparison',
  'socialProof',
  'bottomCta',
  'techStrip',
  'exploreSolutions',
  'references',
] as const satisfies readonly SectionType[];

const SECTIONS_NO_COMPARISON = ALL_SECTIONS.filter((s) => s !== 'competitorComparison');

export const SOLUTION_PAGES: Record<string, SolutionPageConfig> = {
  'environment-cloning': {
    contentKey: 'environmentCloning',
    category: 'dev-env',
    illustration: illustrationEnvironmentCloning,
    sections: ALL_SECTIONS,
    calculatorPreset: 'environment-cloning',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Delphix', 'Neon'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'infrastructure-costs': {
    contentKey: 'infrastructureCosts',
    category: 'dev-env',
    illustration: illustrationInfrastructureCosts,
    sections: ALL_SECTIONS,
    calculatorPreset: 'infrastructure-costs',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Railway', 'Rediacc'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'production-parity': {
    contentKey: 'productionParity',
    category: 'dev-env',
    illustration: illustrationProductionParity,
    sections: ALL_SECTIONS,
    calculatorPreset: 'production-parity',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Railway', 'Rediacc'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  integrations: {
    contentKey: 'integrations',
    category: 'dev-env',
    illustration: illustrationIntegrations,
    sections: ALL_SECTIONS,
    calculatorPreset: 'integrations',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Railway', 'Rediacc'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'immutable-backups': {
    contentKey: 'immutableBackups',
    category: 'ransomware',
    illustration: illustrationImmutableBackups,
    sections: ALL_SECTIONS,
    calculatorPreset: 'immutable-backups',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva', 'Zerto'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Vaultwarden', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'migration-safety': {
    contentKey: 'migrationSafety',
    category: 'encryption',
    illustration: illustrationMigrationSafety,
    sections: ALL_SECTIONS,
    calculatorPreset: 'migration-safety',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'Vaultwarden', kind: 'storage' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
    ],
  },
  'instant-recovery': {
    contentKey: 'instantRecovery',
    category: 'backups',
    illustration: illustrationInstantRecovery,
    sections: ALL_SECTIONS,
    calculatorPreset: 'instant-recovery',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'safe-os-testing': {
    contentKey: 'safeOsTesting',
    category: 'ransomware',
    illustration: illustrationSafeOsTesting,
    sections: ALL_SECTIONS,
    calculatorPreset: 'safe-os-testing',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Zerto'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Vaultwarden', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'retention-compliance': {
    contentKey: 'retentionCompliance',
    category: 'backups',
    illustration: illustrationRetentionCompliance,
    sections: ALL_SECTIONS,
    calculatorPreset: 'retention-compliance',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'cloud-outage-protection': {
    contentKey: 'cloudOutageProtection',
    category: 'multi-cloud',
    illustration: illustrationCloudOutageProtection,
    sections: ALL_SECTIONS,
    calculatorPreset: 'cloud-outage-protection',
    competitors: ['AWS Backup', 'Veeam', 'Zerto', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
      { name: 'Gitea', kind: 'devops' },
    ],
  },
  'failover-testing': {
    contentKey: 'failoverTesting',
    category: 'multi-cloud',
    illustration: illustrationFailoverTesting,
    sections: ALL_SECTIONS,
    calculatorPreset: 'failover-testing',
    competitors: ['AWS Backup', 'Veeam', 'Zerto', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
      { name: 'Gitea', kind: 'devops' },
    ],
  },
  'backup-verification': {
    contentKey: 'backupVerification',
    category: 'backups',
    illustration: illustrationBackupVerification,
    sections: ALL_SECTIONS,
    calculatorPreset: 'backup-verification',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'vulnerability-management': {
    contentKey: 'vulnerabilityManagement',
    category: 'defense',
    illustration: illustrationVulnerabilityManagement,
    sections: SECTIONS_NO_COMPARISON,
    calculatorPreset: 'vulnerability-management',
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'ai-pentesting': {
    contentKey: 'aiPentesting',
    category: 'defense',
    illustration: illustrationAiPentesting,
    sections: SECTIONS_NO_COMPARISON,
    calculatorPreset: 'ai-pentesting',
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  encryption: {
    contentKey: 'encryption',
    category: 'encryption',
    illustration: illustrationEncryption,
    sections: ALL_SECTIONS,
    calculatorPreset: 'encryption',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'continuous-security-testing': {
    contentKey: 'continuousSecurityTesting',
    category: 'defense',
    illustration: illustrationContinuousSecurityTesting,
    sections: SECTIONS_NO_COMPARISON,
    calculatorPreset: 'continuous-security-testing',
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'audit-trail': {
    contentKey: 'auditTrail',
    category: 'encryption',
    illustration: illustrationAuditTrail,
    sections: ALL_SECTIONS,
    calculatorPreset: 'audit-trail',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'rapid-recovery': {
    contentKey: 'rapidRecovery',
    category: 'ransomware',
    illustration: illustrationRapidRecovery,
    sections: ALL_SECTIONS,
    calculatorPreset: 'rapid-recovery',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva', 'Zerto'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Mailcow', kind: 'mail' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Vaultwarden', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
    ],
  },
  'vendor-lock-in': {
    contentKey: 'vendorLockIn',
    category: 'multi-cloud',
    illustration: illustrationVendorLockIn,
    sections: ALL_SECTIONS,
    calculatorPreset: 'vendor-lock-in',
    competitors: ['AWS Backup', 'Veeam', 'Zerto', 'Druva'],
    techStrip: [
      { name: 'GitLab', kind: 'devops' },
      { name: 'Nextcloud', kind: 'collab' },
      { name: 'WordPress', kind: 'cms' },
      { name: 'MariaDB', kind: 'data' },
      { name: 'Grafana', kind: 'monitor' },
      { name: 'Keycloak', kind: 'auth' },
      { name: 'MinIO', kind: 'storage' },
      { name: 'Gitea', kind: 'devops' },
    ],
  },
};

export type SolutionPageSlug = keyof typeof SOLUTION_PAGES;
export const SOLUTION_PAGE_SLUGS = Object.keys(SOLUTION_PAGES);
