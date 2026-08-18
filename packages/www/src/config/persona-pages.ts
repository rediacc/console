/**
 * Configuration for persona-targeted landing pages.
 * Parallel to solution-pages.ts. Reuses the same SP* section components
 * but with persona-specific config and translation namespace.
 */

import { ACCOUNT_PATH } from './constants';
import type { SectionType } from './solution-pages';

/** Persona-specific section types (extends base SectionType) */
type PersonaSectionType = SectionType | 'relatedSolutions' | 'shareWithTeam';

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
  /** Base slug of the shared problem-section illustration (textless, one file
   * per slug under src/assets/images/illustrations/). */
  illustrationSlug?: string;
  /** Curated solution page slugs for the relatedSolutions section */
  relatedSolutions?: string[];
  /** Primary CTA destination (overrides persona default). Relative to /{lang}. Use 'CONSULTATION' for external booking link. */
  ctaHref?: string;
}

/** Default CTA destinations by persona. 'CONSULTATION' is resolved to EXTERNAL_LINKS.SCHEDULE_CONSULTATION at render time.
 * Anchor-only entries (e.g. `#pricing`) target the home page; the renderer
 * concatenates them as `/${lang}${rawCtaHref}` → `/en#pricing`. */
export const PERSONA_CTA_MAP: Record<PersonaType, string> = {
  devops: ACCOUNT_PATH,
  cto: 'CONSULTATION',
  ceo: '#pricing',
  'ai-agent': ACCOUNT_PATH,
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
      'techDiff',
      'benefits',
      'socialProof',
      'relatedSolutions',
      'bottomCta',
    ],
    illustrationSlug: 'environment-cloning',
    relatedSolutions: [
      'environment-cloning',
      'production-parity',
      'infrastructure-costs',
      'integrations',
    ],
  },
  'for-ctos': {
    contentKey: 'forCtos',
    personaType: 'cto',
    sections: [
      'hero',
      'stats',
      'problem',
      'costCalculator',
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
    illustrationSlug: 'infrastructure-costs',
    relatedSolutions: [
      'immutable-backups',
      'encryption',
      'instant-recovery',
      'audit-trail',
      'vendor-lock-in',
      'cloud-outage-protection',
    ],
  },
  'for-ceos': {
    contentKey: 'forCeos',
    personaType: 'ceo',
    sections: [
      'hero',
      'stats',
      'problem',
      'costCalculator',
      'benefits',
      'socialProof',
      'shareWithTeam',
      'bottomCta',
    ],
    calculatorPreset: 'rapid-recovery',
    illustrationSlug: 'rapid-recovery',
    relatedSolutions: ['rapid-recovery', 'vendor-lock-in', 'cloud-outage-protection'],
  },
  'for-ai-agents': {
    contentKey: 'forAiAgents',
    personaType: 'ai-agent',
    sections: [
      'hero',
      'stats',
      'problem',
      'howItWorks',
      'techDiff',
      'benefits',
      'relatedSolutions',
      'bottomCta',
    ],
    illustrationSlug: 'environment-cloning',
    relatedSolutions: ['environment-cloning', 'production-parity', 'integrations'],
  },
};
