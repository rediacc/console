import { PLAN_ORDER, PLAN_PRICING } from '@rediacc/shared/subscription';
import type { Language } from '../i18n/types';
import { createTranslator } from '../i18n/utils';

export interface PricingPlan {
  id: string;
  monthly: number;
  annual: number;
  contactOnly: boolean;
}

export interface PlanMetric {
  label: string;
  tooltip?: string;
  value: string;
}

/**
 * The self-serve plan grid, shared by the pricing page and the homepage preview.
 *
 * Community is deliberately absent. It is the post-cancellation fallback state
 * an account is reverted to when payment lapses, not something anyone can buy,
 * so it gets no card, no column and no signup path.
 *
 * Annual prices come from the shared constants (an explicit 15%-off value, not
 * a 10x-monthly shortcut).
 *
 * No card is badged or outlined as the popular one. "Most popular" was a claim
 * about other customers, and there are none to count yet; the same reason the
 * comparison table no longer tints a column.
 */
export function buildPlans(): PricingPlan[] {
  return PLAN_ORDER.filter((code) => code !== 'COMMUNITY').map((code) => {
    const id = code.toLowerCase();
    return {
      id,
      monthly: PLAN_PRICING[code].monthlyPriceCents / 100,
      annual: PLAN_PRICING[code].annualPriceCents / 100,
      // Enterprise is quoted, never priced on the page.
      contactOnly: id === 'enterprise',
    };
  });
}

/**
 * The five card rows, read from the plan-limit table in the catalog.
 *
 * The two key paths are spelled out rather than built from a namespace
 * parameter: check-dead-translation-keys resolves a literal and cannot resolve
 * a parameter, so a namespace argument here reported all 21 technicalSummary
 * keys as unreachable. The disaster-recovery page builds its own metrics from
 * its own literal namespace.
 */
export function buildMetricsFor(lang: Language) {
  const { ta, to } = createTranslator(lang);
  // `ta()` is typed `string[]`; this branch holds objects. Double cast, the
  // same shape ResourceBriefPage.astro:60 uses. Without it `tsc --noEmit` fails
  // TS2352 on this file, and it is the only .ts (not .astro) `ta()` call site
  // with an object array, so it is the only one tsc sees.
  const metrics = ta('pages.pricing.technicalSummary.metrics') as unknown as {
    key: string;
    label: string;
    tooltip?: string;
  }[];
  const values = to('pages.pricing.technicalSummary.values') as
    | Record<string, Record<string, string>>
    | undefined;

  return (planId: string): PlanMetric[] =>
    metrics.map((metric) => ({
      label: metric.label,
      tooltip: metric.tooltip,
      value: values?.[planId]?.[metric.key] ?? '—',
    }));
}
