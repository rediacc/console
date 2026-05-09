import en from '../i18n/translations/en.json';

/**
 * Single source of truth for the www-side Design Partner Program state.
 *
 * Drives:
 *   - AnnouncementBar visibility (top of every page)
 *   - CfPricingCard overlay (badge, struck-through price, "FREE" headline,
 *     unified "Claim Design Partner →" CTA pointing at /account/)
 *
 * To DISABLE the entire on-site program treatment in one shot:
 *   set "announcement.enabled": false in
 *   packages/www/src/i18n/translations/en.json
 *
 * Reads EN canonically so the bar and the cards never disagree across
 * locales (other locale JSONs may carry stale `enabled` values; only EN
 * controls the runtime decision).
 *
 * The account-side auto-grant (DESIGN_PARTNER_PROGRAM_ENABLED in
 * workers/account/wrangler.*.toml [vars]) is independent — flip it
 * separately when you want to stop granting lifetime BUSINESS at signup.
 */
export function isDesignPartnerProgramActive(): boolean {
  return en.announcement.enabled === true;
}

/**
 * The single plan tier auto-granted to design partners on signup. Mirrors
 * the hardcoded value in
 * private/account/src/services/initial-subscription.ts. If the account-side
 * grant ever changes (e.g., to PROFESSIONAL), update this constant in lock
 * step. Used by:
 *   - CfPricingCard.astro: only this tier's card gets the overlay; other
 *     tiers (Enterprise) render with their normal price + CTA so visitors
 *     aren't misled into thinking Enterprise is free.
 *   - pricing.astro / PricingPreview.astro / disaster-recovery.astro:
 *     filters out tiers below this one (Community, Professional) so the
 *     pricing page focuses on "claim your BUSINESS plan" with Enterprise
 *     as the upgrade reference.
 */
export const DESIGN_PARTNER_GRANTED_PLAN = 'business';

/**
 * Plan IDs hidden from pricing surfaces while the program is active.
 * Community is redundant (everything's free for partners anyway) and
 * Professional is below the granted tier so it adds noise.
 */
export const DESIGN_PARTNER_HIDDEN_PLANS = new Set(['community', 'professional']);

/**
 * Apply the program's plan filter to a list of plans. When the program is
 * inactive this is a no-op; when active it removes plans that should not
 * appear next to the granted tier.
 */
export function filterPlansForProgram<T extends { id: string }>(plans: T[]): T[] {
  if (!isDesignPartnerProgramActive()) return plans;
  return plans.filter((p) => !DESIGN_PARTNER_HIDDEN_PLANS.has(p.id));
}
