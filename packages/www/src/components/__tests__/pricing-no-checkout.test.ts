import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { PLAN_METADATA, PLAN_ORDER } from '@rediacc/shared/subscription';
import { describe, expect, it } from 'vitest';
import { buildPlans } from '../pricing-plans';

const read = (rel: string): string =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');

describe('pricing without checkout', () => {
  it('marks no plan self-serve', () => {
    for (const code of PLAN_ORDER) {
      expect(PLAN_METADATA[code].selfServe, code).toBe(false);
    }
  });

  it('keeps the plan grid to the three sold plans, only one of them contact-only', () => {
    const plans = buildPlans();
    expect(plans.map((p) => p.id)).toEqual(['professional', 'business', 'enterprise']);
    expect(plans.filter((p) => p.contactOnly).map((p) => p.id)).toEqual(['enterprise']);
  });

  it('renders no checkout element or handler in the pricing card', () => {
    const card = read('../CfPricingCard.astro');
    expect(card).not.toMatch(/data-checkout/);
    expect(card).not.toMatch(/useCheckout/);
    expect(card).not.toMatch(/checkout_start/);
    expect(card).not.toMatch(/openRegionPicker/);
  });

  it('does not ask the card for a checkout on the pricing page', () => {
    expect(read('../../pages/[lang]/pricing.astro')).not.toMatch(/useCheckout/);
  });

  it('keeps the contact and account-link branches the card falls back to', () => {
    const card = read('../CfPricingCard.astro');
    expect(card).toMatch(/SCHEDULE_CONSULTATION/);
    expect(card).toMatch(/<AccountLink/);
  });
});
