// Solution page configuration - maps slug to translation key and assets
export const SOLUTIONS = {
  'development-environments': {
    contentKey: 'developmentEnvironments',
    heroImage: '/assets/images/development-environments-hero.svg',
    heroImageAlt: 'Development environment provisioning workflow showing instant production clones',
    bottomImage: '/assets/images/development-environments-bottom.svg',
    bottomImageAlt:
      'Development environment automation dashboard showing ephemeral environments and cost savings',
    bottomImageVariant: 'dark' as const,
    problemKeys: [
      'provisioningDelays',
      'environmentDrift',
      'infrastructureCosts',
      'cicdComplexity',
    ],
    ctaImageAlt: 'Rediacc development environment resources',
    hasButtonHref: true,
  },
  'disaster-recovery': {
    contentKey: 'disasterRecovery',
    heroImage: '/assets/images/disaster-recovery-hero.png',
    heroImageAlt: 'Verified backup layers with checkmarks showing tested backups',
    bottomImage: '/assets/images/disaster-recovery-bottom.png',
    bottomImageAlt:
      'Backup monitoring dashboard with extended retention timelines showing 100% verification',
    bottomImageVariant: 'dark' as const,
    problemKeys: ['unverified', 'limitedHistory', 'slowBackups'],
    ctaImageAlt: 'Rediacc backup resources and repositories',
    hasButtonHref: true,
  },
  'threat-response': {
    contentKey: 'threatResponse',
    heroImage: '/assets/images/threat-response-hero.png',
    heroImageAlt:
      'Impenetrable vault with glowing locked chains representing immutable ransomware protection',
    bottomImage: '/assets/images/threat-response-bottom.png',
    bottomImageAlt:
      'Side-by-side comparison showing manual vs automated ransomware recovery timelines',
    bottomImageVariant: 'dark' as const,
    problemKeys: ['ransomwareBackups', 'osVulnerability', 'infrastructureBlackBox'],
    ctaImageAlt: 'Rediacc threat response infrastructure',
    hasButtonHref: false,
  },
  'data-security': {
    contentKey: 'dataSecurity',
    heroImage: '/assets/images/data-security-hero.png',
    heroImageAlt:
      'Encrypted data pipeline with locked packets flowing through transparent infrastructure',
    bottomImage: '/assets/images/data-security-bottom.png',
    bottomImageAlt:
      'Compliance dashboard showing migration status, audit trail, and encryption verification with SOC 2, ISO 27001, and GDPR badges',
    bottomImageVariant: 'light' as const,
    problemKeys: ['physicalTheft', 'auditTrail', 'migrationExposure'],
    ctaImageAlt: 'Rediacc data security and compliance',
    hasButtonHref: false,
  },
  'system-portability': {
    contentKey: 'systemPortability',
    heroImage: '/assets/images/system-portability-hero.png',
    heroImageAlt:
      'Infrastructure box moving seamlessly between AWS, Azure, and Google Cloud platforms',
    bottomImage: '/assets/images/system-portability-bottom.png',
    bottomImageAlt:
      'World map showing tested failover paths between AWS, Azure, and Google Cloud with verification checkmarks',
    bottomImageVariant: 'light' as const,
    problemKeys: ['vendorLockIn', 'testingVendorSwitch', 'deployment'],
    ctaImageAlt: 'Rediacc portable system repositories',
    hasButtonHref: false,
  },
} as const;

export type SolutionSlug = keyof typeof SOLUTIONS;
export const SOLUTION_SLUGS = Object.keys(SOLUTIONS) as SolutionSlug[];
