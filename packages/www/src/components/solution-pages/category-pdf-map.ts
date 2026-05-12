/**
 * Maps each SolutionCategory to its deck pair + resource-page slug.
 *
 * Six topic decks have two variants each:
 *   - <deck>-cto.pdf  : CISO/CTO technical depth, sales-stripped
 *   - <deck>-exec.pdf : IT director / business owner, grade 5-7 plain language
 *
 * All 20 solution pages map to one of these 6 pairs via the page's `category`
 * field in solution-pages.ts. The gated inline CTA (~30% scroll) serves the
 * `-cto` variant behind an email gate; the short-form CTA (~90% scroll) and
 * the dedicated resource pages' hero CTA serve the `-exec` variant directly.
 */

import type { SolutionCategory } from '../../config/solution-pages';

export interface CategoryPdfPair {
  /** Full long-form PDF (email-gated). Filename in /public/assets/. */
  ctoPdf: string;
  /** Short presentation PDF (direct download). Filename in /public/assets/. */
  execPdf: string;
  /** Resource page slug under /resources/. */
  resourceSlug: string;
  /** i18n content key under pages.resourcesBrief.<key>. */
  resourceContentKey: string;
}

export const categoryToPdfPair: Record<SolutionCategory, CategoryPdfPair> = {
  ransomware: {
    ctoPdf: 'ransomware-survival-cto.pdf',
    execPdf: 'ransomware-survival-exec.pdf',
    resourceSlug: 'ransomware-survival-brief',
    resourceContentKey: 'ransomwareSurvival',
  },
  'multi-cloud': {
    ctoPdf: 'multi-cloud-always-cto.pdf',
    execPdf: 'multi-cloud-always-exec.pdf',
    resourceSlug: 'multi-cloud-always-brief',
    resourceContentKey: 'multiCloudAlways',
  },
  backups: {
    ctoPdf: 'verified-backups-cto.pdf',
    execPdf: 'verified-backups-exec.pdf',
    resourceSlug: 'verified-backups-brief',
    resourceContentKey: 'verifiedBackups',
  },
  encryption: {
    ctoPdf: 'encryption-control-cto.pdf',
    execPdf: 'encryption-control-exec.pdf',
    resourceSlug: 'encryption-control-brief',
    resourceContentKey: 'encryptionControl',
  },
  'dev-env': {
    ctoPdf: 'dev-environments-cto.pdf',
    execPdf: 'dev-environments-exec.pdf',
    resourceSlug: 'dev-environments-brief',
    resourceContentKey: 'devEnvironments',
  },
  defense: {
    ctoPdf: 'preemptive-defense-cto.pdf',
    execPdf: 'preemptive-defense-exec.pdf',
    resourceSlug: 'preemptive-defense-brief',
    resourceContentKey: 'preemptiveDefense',
  },
};

/**
 * Magnet name used when posting to /account/api/v1/newsletter/lead-magnet.
 * Format: `<deck>-<variant>`. Used by the backend to record which lead magnet
 * the user requested.
 */
export function magnetNameFor(category: SolutionCategory, variant: 'cto' | 'exec'): string {
  const pair = categoryToPdfPair[category];
  const pdf = variant === 'cto' ? pair.ctoPdf : pair.execPdf;
  return pdf.replace(/\.pdf$/, '');
}
