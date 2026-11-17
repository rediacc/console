import { PLAN_ORDER, PLAN_PRICING, type PlanCode } from '@rediacc/shared/subscription';
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
 * The plans the grid SELLS. Community is deliberately absent: it is the post-cancellation
 * fallback state an account is reverted to when payment lapses, not something anyone can buy.
 * Free is absent too: it is the no-account licence a machine takes from the CLI
 * (agent/plans/PLAN-free-license.md), with its own `#free-license` section. It joined
 * PLAN_ORDER on 2026-10-31 and the old filter named only Community, so a fourth card
 * appeared with a $0 price, a dead "Start trial" button and the raw text
 * `pages.pricing.plans.free.name` as its title in all 13 locales. A fifth code added to
 * PLAN_ORDER stays off the grid until someone gives it copy on purpose.
 */
const GRID_PLANS: ReadonlySet<PlanCode> = new Set(['PROFESSIONAL', 'BUSINESS', 'ENTERPRISE']);

/**
 * The self-serve plan grid, built from GRID_PLANS and shared by the pricing page and the
 * homepage preview.
 *
 * Annual prices come from the shared constants (an explicit 15%-off value, not
 * a 10x-monthly shortcut).
 *
 * No card is badged or outlined as the popular one. "Most popular" was a claim
 * about other customers, and there are none to count yet; the same reason the
 * comparison table no longer tints a column.
 */
export function buildPlans(): PricingPlan[] {
  return PLAN_ORDER.filter((code) => GRID_PLANS.has(code)).map((code) => {
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
  const { t, ta } = createTranslator(lang);
  // `ta()` is typed `string[]`; this branch holds objects. Double cast, the
  // same shape ResourceBriefPage.astro:60 uses. Without it `tsc --noEmit` fails TS2352 on this file, and it is the only .ts (not .astro) `ta()` call site
  // with an object array, so it is the only one tsc sees.
  const metrics = ta('pages.pricing.technicalSummary.metrics') as unknown as {
    key: string;
    label: string;
    tooltip?: string;
  }[];
  // Each value goes through t(), not a default dash: the default drew a dash in every row of a card whose plan had no values, which reads as "not included" rather than as missing copy, and a production build now fails on the miss instead (translator.ts strictByDefault).
  return (planId: string): PlanMetric[] =>
    metrics.map((metric) => ({
      label: metric.label,
      tooltip: metric.tooltip,
      value: t(`pages.pricing.technicalSummary.values.${planId}.${metric.key}`),
    }));
}
