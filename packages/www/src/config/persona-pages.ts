/**
 * Configuration for persona-targeted landing pages.
 * Parallel to solution-pages.ts — reuses the same SP* section components
 * but with persona-specific config and translation namespace.
 */

import type { ImageMetadata } from 'astro';
import illustrationEnvironmentCloning from '../assets/images/illustrations/environment-cloning.svg';
import illustrationInfrastructureCosts from '../assets/images/illustrations/infrastructure-costs.svg';
import illustrationRapidRecovery from '../assets/images/illustrations/rapid-recovery.svg';
import type { SectionType, TechItem } from './solution-pages';

/** Persona-specific section types (extends base SectionType) */
export type PersonaSectionType = SectionType | 'relatedSolutions' | 'shareWithTeam' | 'teamVideo';

export type PersonaType = 'devops' | 'cto' | 'ceo' | 'ai-agent';

export interface PersonaPageConfig {
  /** Translation content key: pages.personaPages.<contentKey> */
  contentKey: string;
  /** Which persona this page targets */
  personaType: PersonaType;
  /** Which sections to render (in order) */
  sections: PersonaSectionType[];
  /** Calculator compute preset name (reuse existing presets) */
  calculatorPreset?: string;
  /** Competitor column headers for comparison table */
  competitors?: string[];
  /** Tech strip items with category color coding */
  techStrip?: TechItem[];
  /** Problem section illustration */
  illustration?: ImageMetadata;
  /** Curated solution page slugs for the relatedSolutions section */
  relatedSolutions?: string[];
  /** Primary CTA destination (overrides persona default). Relative to /{lang}. Use 'CONSULTATION' for external booking link. */
  ctaHref?: string;
  /** Team member video for the teamVideo section */
  teamVideo?: { member: string; videoKey: string };
}

/** Default CTA destinations by persona. 'CONSULTATION' is resolved to EXTERNAL_LINKS.SCHEDULE_CONSULTATION at render time. */
export const PERSONA_CTA_MAP: Record<PersonaType, string> = {
  devops: '/install',
  cto: 'CONSULTATION',
  ceo: '/#pricing',
  'ai-agent': '/install',
};

export const PERSONA_PAGES: Record<string, PersonaPageConfig> = {
  'for-devops': {
    contentKey: 'forDevops',
    personaType: 'devops',
    sections: [
      'hero',
      'stats',
      'problem',
      'howItWorks',
      'teamVideo',
      'techDiff',
      'benefits',
      'socialProof',
      'relatedSolutions',
      'bottomCta',
    ],
    illustration: illustrationEnvironmentCloning,
    relatedSolutions: [
      'environment-cloning',
      'production-parity',
      'infrastructure-costs',
      'integrations',
    ],
    teamVideo: { member: 'founder', videoKey: 'persona-devops' },
  },
  'for-ctos': {
    contentKey: 'forCtos',
    personaType: 'cto',
    sections: [
      'hero',
      'stats',
      'problem',
      'costCalculator',
      'teamVideo',
      'techDiff',
      'benefits',
      'competitorComparison',
      'socialProof',
      'shareWithTeam',
      'relatedSolutions',
      'bottomCta',
    ],
    calculatorPreset: 'infrastructure-costs',
    competitors: ['Veeam', 'Rubrik', 'Commvault', 'Zerto'],
    illustration: illustrationInfrastructureCosts,
    relatedSolutions: [
      'immutable-backups',
      'encryption',
      'instant-recovery',
      'audit-trail',
      'vendor-lock-in',
      'cloud-outage-protection',
    ],
    teamVideo: { member: 'founder', videoKey: 'persona-ctos' },
  },
  'for-ceos': {
    contentKey: 'forCeos',
    personaType: 'ceo',
    sections: [
      'hero',
      'stats',
      'problem',
      'costCalculator',
      'teamVideo',
      'benefits',
      'socialProof',
      'shareWithTeam',
      'bottomCta',
    ],
    calculatorPreset: 'rapid-recovery',
    illustration: illustrationRapidRecovery,
    relatedSolutions: ['rapid-recovery', 'vendor-lock-in', 'cloud-outage-protection'],
    teamVideo: { member: 'founder', videoKey: 'persona-ceos' },
  },
  'for-ai-agents': {
    contentKey: 'forAiAgents',
    personaType: 'ai-agent',
    sections: [
      'hero',
      'stats',
      'problem',
      'howItWorks',
      'teamVideo',
      'techDiff',
      'benefits',
      'relatedSolutions',
      'bottomCta',
    ],
    illustration: illustrationEnvironmentCloning,
    relatedSolutions: ['environment-cloning', 'production-parity', 'integrations'],
    teamVideo: { member: 'founder', videoKey: 'persona-ai-agents' },
  },
};

export const PERSONA_PAGE_SLUGS = Object.keys(PERSONA_PAGES);
