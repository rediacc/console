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
import illustrationDataSovereignty from '../assets/images/illustrations/data-sovereignty.svg';
import illustrationEncryption from '../assets/images/illustrations/encryption.svg';
import illustrationEnvironmentCloning from '../assets/images/illustrations/environment-cloning.svg';
import illustrationFailoverTesting from '../assets/images/illustrations/failover-testing.svg';
import illustrationImmutableBackups from '../assets/images/illustrations/immutable-backups.svg';
import illustrationInfrastructureCosts from '../assets/images/illustrations/infrastructure-costs.svg';
import illustrationInstantRecoveryMobile from '../assets/images/illustrations/instant-recovery.mobile.svg';
import illustrationInstantRecovery from '../assets/images/illustrations/instant-recovery.svg';
import illustrationIntegrations from '../assets/images/illustrations/integrations.svg';
import illustrationKubernetesClusterMobility from '../assets/images/illustrations/kubernetes-cluster-mobility.svg';
import illustrationMigrationSafety from '../assets/images/illustrations/migration-safety.svg';
import illustrationProductionParity from '../assets/images/illustrations/production-parity.svg';
import illustrationRapidRecovery from '../assets/images/illustrations/rapid-recovery.svg';
import illustrationRetentionCompliance from '../assets/images/illustrations/retention-compliance.svg';
import illustrationSafeOsTesting from '../assets/images/illustrations/safe-os-testing.svg';
import illustrationVendorLockIn from '../assets/images/illustrations/vendor-lock-in.svg';
import illustrationVulnerabilityManagement from '../assets/images/illustrations/vulnerability-management.svg';
import { ACCOUNT_PATH } from './constants';

export type SectionType =
  | 'hero'
  | 'stats'
  | 'problem'
  | 'video'
  | 'costCalculator'
  | 'howItWorks'
  | 'techDiff'
  | 'benefits'
  | 'downloadGated'
  | 'competitorComparison'
  | 'socialProof'
  | 'bottomCta'
  | 'downloadShort'
  | 'exploreSolutions';

export type SolutionCategory =
  | 'dev-env'
  | 'ransomware'
  | 'multi-cloud'
  | 'backups'
  | 'encryption'
  | 'defense';

/**
 * What the page IS, mechanically: one of the three verbs the hero sentence
 * applies to a copy of the running system (Copy -> Test -> Recover), or a
 * `property` of the platform itself (encryption, audit trail, sovereignty,
 * lock-in freedom, integrations). This is the axis the solution constellation
 * lays out on. `category` remains the market-segment axis and keeps driving
 * CTA routing (CATEGORY_CTA_MAP) and node colors; the two are orthogonal.
 */
export type SolutionRole = 'copy' | 'test' | 'recover' | 'property';

export const ROLE_ORDER = [
  'copy',
  'test',
  'recover',
  'property',
] as const satisfies readonly SolutionRole[];

export interface SolutionPageConfig {
  /** Translation content key: pages.solutionPages.<contentKey> */
  contentKey: string;
  /** Mechanism taxonomy: which verb of "Clone Production. Break Nothing." this page is */
  role: SolutionRole;
  /** Category for explore grid color coding */
  category: SolutionCategory;
  /** Which sections to render (in canonical order) */
  sections: readonly SectionType[];
  /** Calculator compute preset name (required if costCalculator in sections) */
  calculatorPreset?: string;
  /** Competitor column headers for comparison table */
  competitors?: string[];
  /** Problem section illustration */
  illustration?: ImageMetadata;
  /** Optional portrait/mobile variant, swapped in under 768px (vector <picture>). */
  illustrationMobile?: ImageMetadata;
  /** Primary CTA destination (overrides category default). Relative to /{lang}. */
  ctaHref?: string;
}

/** Default CTA destinations by category. Relative paths are prefixed with /{lang} at render time. */
export const CATEGORY_CTA_MAP: Record<SolutionCategory, string> = {
  'dev-env': ACCOUNT_PATH,
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
  'video',
  'costCalculator',
  'howItWorks',
  'techDiff',
  'benefits',
  'downloadGated',
  'competitorComparison',
  'socialProof',
  'bottomCta',
  'downloadShort',
  'exploreSolutions',
] as const satisfies readonly SectionType[];

const SECTIONS_NO_COMPARISON = ALL_SECTIONS.filter((s) => s !== 'competitorComparison');

export const SOLUTION_PAGES: Record<string, SolutionPageConfig> = {
  'environment-cloning': {
    contentKey: 'environmentCloning',
    role: 'copy',
    category: 'dev-env',
    illustration: illustrationEnvironmentCloning,
    sections: ALL_SECTIONS,
    calculatorPreset: 'environment-cloning',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Delphix', 'Neon'],
  },
  'infrastructure-costs': {
    contentKey: 'infrastructureCosts',
    role: 'copy',
    category: 'dev-env',
    illustration: illustrationInfrastructureCosts,
    sections: ALL_SECTIONS,
    calculatorPreset: 'infrastructure-costs',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Railway'],
  },
  'production-parity': {
    contentKey: 'productionParity',
    role: 'copy',
    category: 'dev-env',
    illustration: illustrationProductionParity,
    sections: ALL_SECTIONS,
    calculatorPreset: 'production-parity',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Railway'],
  },
  integrations: {
    contentKey: 'integrations',
    role: 'property',
    category: 'dev-env',
    illustration: illustrationIntegrations,
    sections: ALL_SECTIONS,
    calculatorPreset: 'integrations',
    competitors: ['Codespaces', 'Coder', 'Vercel', 'Railway'],
  },
  'immutable-backups': {
    contentKey: 'immutableBackups',
    role: 'recover',
    category: 'ransomware',
    illustration: illustrationImmutableBackups,
    sections: ALL_SECTIONS,
    calculatorPreset: 'immutable-backups',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva', 'Zerto'],
  },
  'migration-safety': {
    contentKey: 'migrationSafety',
    role: 'test',
    category: 'encryption',
    illustration: illustrationMigrationSafety,
    sections: ALL_SECTIONS,
    calculatorPreset: 'migration-safety',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
  },
  'instant-recovery': {
    contentKey: 'instantRecovery',
    role: 'recover',
    category: 'backups',
    illustration: illustrationInstantRecovery,
    illustrationMobile: illustrationInstantRecoveryMobile,
    sections: ALL_SECTIONS,
    calculatorPreset: 'instant-recovery',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
  },
  'safe-os-testing': {
    contentKey: 'safeOsTesting',
    role: 'test',
    category: 'ransomware',
    illustration: illustrationSafeOsTesting,
    sections: ALL_SECTIONS,
    calculatorPreset: 'safe-os-testing',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Zerto'],
  },
  'retention-compliance': {
    contentKey: 'retentionCompliance',
    role: 'recover',
    category: 'backups',
    illustration: illustrationRetentionCompliance,
    sections: ALL_SECTIONS,
    calculatorPreset: 'retention-compliance',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
  },
  'cloud-outage-protection': {
    contentKey: 'cloudOutageProtection',
    role: 'recover',
    category: 'multi-cloud',
    illustration: illustrationCloudOutageProtection,
    sections: ALL_SECTIONS,
    calculatorPreset: 'cloud-outage-protection',
    competitors: ['AWS Backup', 'Veeam', 'Zerto', 'Druva'],
  },
  'failover-testing': {
    contentKey: 'failoverTesting',
    role: 'test',
    category: 'multi-cloud',
    illustration: illustrationFailoverTesting,
    sections: ALL_SECTIONS,
    calculatorPreset: 'failover-testing',
    competitors: ['AWS Backup', 'Veeam', 'Zerto', 'Druva'],
  },
  'backup-verification': {
    contentKey: 'backupVerification',
    role: 'test',
    category: 'backups',
    illustration: illustrationBackupVerification,
    sections: ALL_SECTIONS,
    calculatorPreset: 'backup-verification',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
  },
  'vulnerability-management': {
    contentKey: 'vulnerabilityManagement',
    role: 'test',
    category: 'defense',
    illustration: illustrationVulnerabilityManagement,
    sections: SECTIONS_NO_COMPARISON,
    calculatorPreset: 'vulnerability-management',
  },
  'ai-pentesting': {
    contentKey: 'aiPentesting',
    role: 'test',
    category: 'defense',
    illustration: illustrationAiPentesting,
    sections: SECTIONS_NO_COMPARISON,
    calculatorPreset: 'ai-pentesting',
  },
  encryption: {
    contentKey: 'encryption',
    role: 'property',
    category: 'encryption',
    illustration: illustrationEncryption,
    sections: ALL_SECTIONS,
    calculatorPreset: 'encryption',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
  },
  'continuous-security-testing': {
    contentKey: 'continuousSecurityTesting',
    role: 'test',
    category: 'defense',
    illustration: illustrationContinuousSecurityTesting,
    sections: SECTIONS_NO_COMPARISON,
    calculatorPreset: 'continuous-security-testing',
  },
  'audit-trail': {
    contentKey: 'auditTrail',
    role: 'property',
    category: 'encryption',
    illustration: illustrationAuditTrail,
    sections: ALL_SECTIONS,
    calculatorPreset: 'audit-trail',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva'],
  },
  'rapid-recovery': {
    contentKey: 'rapidRecovery',
    role: 'recover',
    category: 'ransomware',
    illustration: illustrationRapidRecovery,
    sections: ALL_SECTIONS,
    calculatorPreset: 'rapid-recovery',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Druva', 'Zerto'],
  },
  'data-sovereignty': {
    contentKey: 'dataSovereignty',
    role: 'property',
    category: 'encryption',
    illustration: illustrationDataSovereignty,
    sections: ALL_SECTIONS,
    calculatorPreset: 'data-sovereignty',
    competitors: ['Veeam', 'Rubrik', 'AWS Sovereign', 'Microsoft Bleu', 'Keepit'],
  },
  'kubernetes-cluster-mobility': {
    contentKey: 'kubernetesClusterMobility',
    role: 'copy',
    category: 'multi-cloud',
    illustration: illustrationKubernetesClusterMobility,
    sections: [
      'hero',
      'stats',
      'problem',
      'video',
      'howItWorks',
      'techDiff',
      'benefits',
      'downloadGated',
      'competitorComparison',
      'bottomCta',
      'downloadShort',
      'exploreSolutions',
    ],
    competitors: ['Velero', 'Kasten K10', 'Cluster API', 'RBD Mirroring'],
  },
  'vendor-lock-in': {
    contentKey: 'vendorLockIn',
    role: 'property',
    category: 'multi-cloud',
    illustration: illustrationVendorLockIn,
    sections: ALL_SECTIONS,
    calculatorPreset: 'vendor-lock-in',
    competitors: ['AWS Backup', 'Veeam', 'Zerto', 'Druva'],
  },
};
