// Solution page configuration - maps slug to translation key and assets
import dsAuditTrail from '../assets/images/illustrations/data-security-auditTrail.svg';
import dsBottom from '../assets/images/illustrations/data-security-bottom.svg';
import dsHero from '../assets/images/illustrations/data-security-hero.svg';
import dsMigration from '../assets/images/illustrations/data-security-migrationExposure.svg';
import dsPhysicalTheft from '../assets/images/illustrations/data-security-physicalTheft.svg';
import deCicd from '../assets/images/illustrations/dev-env-cicdComplexity.svg';
import deEnvDrift from '../assets/images/illustrations/dev-env-environmentDrift.svg';
import deInfraCosts from '../assets/images/illustrations/dev-env-infrastructureCosts.svg';
import deProvDelay from '../assets/images/illustrations/dev-env-provisioningDelays.svg';
import deBottom from '../assets/images/illustrations/development-environments-bottom.svg';
import deHero from '../assets/images/illustrations/development-environments-hero.svg';
import drBottom from '../assets/images/illustrations/disaster-recovery-bottom.svg';
// Hero & bottom images (SVGs from src/assets/images/illustrations)
import drHero from '../assets/images/illustrations/disaster-recovery-hero.svg';
import drLimitedHistory from '../assets/images/illustrations/disaster-recovery-limitedHistory.svg';
import drSlowBackups from '../assets/images/illustrations/disaster-recovery-slowBackups.svg';
// Section illustrations (SVGs from src/assets)
import drUnverified from '../assets/images/illustrations/disaster-recovery-unverified.svg';
import spBottom from '../assets/images/illustrations/system-portability-bottom.svg';
import spDeployment from '../assets/images/illustrations/system-portability-deployment.svg';
import spHero from '../assets/images/illustrations/system-portability-hero.svg';
import spTestSwitch from '../assets/images/illustrations/system-portability-testingVendorSwitch.svg';
import spVendorLock from '../assets/images/illustrations/system-portability-vendorLockIn.svg';
import trBottom from '../assets/images/illustrations/threat-response-bottom.svg';
import trHero from '../assets/images/illustrations/threat-response-hero.svg';
import trBlackBox from '../assets/images/illustrations/threat-response-infrastructureBlackBox.svg';
import trOsVuln from '../assets/images/illustrations/threat-response-osVulnerability.svg';
import trRansomware from '../assets/images/illustrations/threat-response-ransomwareBackups.svg';
import pdAiAttackSpeed from '../assets/images/illustrations/preemptive-defense-aiAttackSpeed.svg';
import pdBottom from '../assets/images/illustrations/preemptive-defense-bottom.svg';
import pdHero from '../assets/images/illustrations/preemptive-defense-hero.svg';
import pdPeriodicCompliance from '../assets/images/illustrations/preemptive-defense-periodicCompliance.svg';
import pdProductionTesting from '../assets/images/illustrations/preemptive-defense-productionTesting.svg';
import type { ImageMetadata } from 'astro';

interface SectionImage {
  src: string;
  alt: string;
}

interface SolutionConfig {
  contentKey: string;
  heroImage: ImageMetadata | string;
  heroImageAlt: string;
  bottomImage: ImageMetadata | string;
  bottomImageAlt: string;
  bottomImageVariant: 'light' | 'dark';
  problemKeys: readonly string[];
  ctaImageAlt: string;
  hasButtonHref: boolean;
  sectionImages?: Record<string, SectionImage>;
}

export const SOLUTIONS: Record<string, SolutionConfig> = {
  'development-environments': {
    contentKey: 'developmentEnvironments',
    heroImage: deHero,
    heroImageAlt: 'Development environment provisioning workflow showing instant production clones',
    bottomImage: deBottom,
    bottomImageAlt:
      'Development environment automation dashboard showing ephemeral environments and cost savings',
    bottomImageVariant: 'dark',
    problemKeys: [
      'provisioningDelays',
      'environmentDrift',
      'infrastructureCosts',
      'cicdComplexity',
    ],
    ctaImageAlt: 'Rediacc development environment resources',
    hasButtonHref: true,
    sectionImages: {
      provisioningDelays: {
        src: deProvDelay.src,
        alt: 'Hourglass waiting versus instant server cloning',
      },
      environmentDrift: {
        src: deEnvDrift.src,
        alt: 'Mismatched staging versus identical synced environments',
      },
      infrastructureCosts: {
        src: deInfraCosts.src,
        alt: 'Always-on server costs versus ephemeral on-demand savings',
      },
      cicdComplexity: {
        src: deCicd.src,
        alt: 'Tangled CI/CD pipeline versus clean organized pipeline',
      },
    },
  },
  'disaster-recovery': {
    contentKey: 'disasterRecovery',
    heroImage: drHero,
    heroImageAlt: 'Verified backup layers with checkmarks showing tested backups',
    bottomImage: drBottom,
    bottomImageAlt:
      'Backup monitoring dashboard with extended retention timelines showing 100% verification',
    bottomImageVariant: 'dark',
    problemKeys: ['unverified', 'limitedHistory', 'slowBackups'],
    ctaImageAlt: 'Rediacc backup resources and repositories',
    hasButtonHref: true,
    sectionImages: {
      unverified: {
        src: drUnverified.src,
        alt: 'Three servers with warning triangles and verification shield',
      },
      limitedHistory: {
        src: drLimitedHistory.src,
        alt: 'Backup timeline showing fading old snapshots with limited retention',
      },
      slowBackups: {
        src: drSlowBackups.src,
        alt: 'Slow winding recovery path versus fast direct recovery',
      },
    },
  },
  'threat-response': {
    contentKey: 'threatResponse',
    heroImage: trHero,
    heroImageAlt:
      'Impenetrable vault with glowing locked chains representing immutable ransomware protection',
    bottomImage: trBottom,
    bottomImageAlt:
      'Side-by-side comparison showing manual vs automated ransomware recovery timelines',
    bottomImageVariant: 'dark',
    problemKeys: ['ransomwareBackups', 'osVulnerability', 'infrastructureBlackBox'],
    ctaImageAlt: 'Rediacc threat response infrastructure',
    hasButtonHref: true,
    sectionImages: {
      ransomwareBackups: {
        src: trRansomware.src,
        alt: 'Vault protecting backup files from ransomware attacks',
      },
      osVulnerability: {
        src: trOsVuln.src,
        alt: 'Server tested in sandbox with bugs blocked outside',
      },
      infrastructureBlackBox: {
        src: trBlackBox.src,
        alt: 'Opaque black box versus transparent monitored server',
      },
    },
  },
  'data-security': {
    contentKey: 'dataSecurity',
    heroImage: dsHero,
    heroImageAlt:
      'Encrypted data pipeline with locked packets flowing through transparent infrastructure',
    bottomImage: dsBottom,
    bottomImageAlt:
      'Compliance dashboard showing migration status, audit trail, and encryption verification with SOC 2, ISO 27001, and GDPR badges',
    bottomImageVariant: 'light',
    problemKeys: ['physicalTheft', 'auditTrail', 'migrationExposure'],
    ctaImageAlt: 'Rediacc data security and compliance',
    hasButtonHref: true,
    sectionImages: {
      physicalTheft: {
        src: dsPhysicalTheft.src,
        alt: 'Unencrypted exposed drive versus encrypted locked drive',
      },
      auditTrail: {
        src: dsAuditTrail.src,
        alt: 'Audit log with gaps versus complete timestamped audit trail',
      },
      migrationExposure: {
        src: dsMigration.src,
        alt: 'Exposed data migration versus encrypted tunnel migration',
      },
    },
  },
  'system-portability': {
    contentKey: 'systemPortability',
    heroImage: spHero,
    heroImageAlt:
      'Infrastructure box moving seamlessly between AWS, Azure, and Google Cloud platforms',
    bottomImage: spBottom,
    bottomImageAlt:
      'World map showing tested failover paths between AWS, Azure, and Google Cloud with verification checkmarks',
    bottomImageVariant: 'light',
    problemKeys: ['vendorLockIn', 'testingVendorSwitch', 'deployment'],
    ctaImageAlt: 'Rediacc portable system repositories',
    hasButtonHref: true,
    sectionImages: {
      vendorLockIn: {
        src: spVendorLock.src,
        alt: 'Server trapped in vendor cage versus free multi-cloud access',
      },
      testingVendorSwitch: {
        src: spTestSwitch.src,
        alt: 'Failover test bridge between two cloud platforms',
      },
      deployment: {
        src: spDeployment.src,
        alt: 'Broken deployment gears versus clean working deployment',
      },
    },
  },
  'preemptive-defense': {
    contentKey: 'preemptiveDefense',
    heroImage: pdHero,
    heroImageAlt:
      'Clone-based security testing workflow showing production clone, AI pentesting shield, and vulnerability results',
    bottomImage: pdBottom,
    bottomImageAlt:
      'Continuous clone-test-harden cycle with zero-copy cloning, AI scanning, hardening, and ephemeral destruction',
    bottomImageVariant: 'dark',
    problemKeys: ['aiAttackSpeed', 'productionTesting', 'periodicCompliance'],
    ctaImageAlt: 'Rediacc preemptive defense infrastructure',
    hasButtonHref: true,
    sectionImages: {
      aiAttackSpeed: {
        src: pdAiAttackSpeed.src,
        alt: 'AI attacker speed versus clone-based testing speed comparison',
      },
      productionTesting: {
        src: pdProductionTesting.src,
        alt: 'Production crashing from security testing versus safe clone-based testing',
      },
      periodicCompliance: {
        src: pdPeriodicCompliance.src,
        alt: 'Annual pentest gap versus continuous clone-based testing timeline',
      },
    },
  },
};

export type SolutionSlug = keyof typeof SOLUTIONS;
export const SOLUTION_SLUGS = Object.keys(SOLUTIONS);
