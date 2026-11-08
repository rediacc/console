import { WK_SITE_ORIGIN } from '@rediacc/shared/config/well-known.generated';

/**
 * Host classification for the www -> portal handoff.
 *
 * There is one product, so the portal host depends only on the region the visitor
 * picks, never on the host the visitor came from:
 *
 *   Host                          Kind        /account/* CTA behavior
 *   ---------------------------   ---------   -------------------------------------
 *   www.rediacc.com               marketing   region picker -> <region>.rediacc.cloud
 *   *.rediacc.workers.dev         preview     direct navigation: PR previews serve a
 *                                             fully functional portal at /account/
 *                                             backed by a per-PR D1
 *   localhost                     localhost   region picker (astro dev serves no portal)
 *   everything else               portal      direct navigation (regional cloud, bench,
 *                                             on-prem), open-ended so customer
 *                                             hostnames need no list
 *
 * Closed allow-list approach: only known marketing hosts open the picker;
 * everything else navigates directly.
 *
 * Keep this rule in sync with the inline copy in BaseLayout.astro
 * (window.__rediaccIsMarketingHost): React components import this module, while
 * inline scripts (BaseLayout's account-link interceptor and CfPricingCard's
 * checkout script) read the window mirror. All consumers must agree.
 */

export type HostKind = 'marketing' | 'preview' | 'localhost' | 'portal';

const SITE_HOST = new URL(WK_SITE_ORIGIN).hostname;

export function getHostKind(hostname: string): HostKind {
  if (hostname === SITE_HOST) return 'marketing';
  if (hostname.endsWith('.rediacc.workers.dev')) return 'preview';
  if (hostname === 'localhost') return 'localhost';
  return 'portal';
}

/**
 * True when the host must open the region picker for /account/* CTAs
 * because it serves no functional portal of its own. PR previews are NOT
 * marketing hosts: they serve a working portal backed by a per-PR D1, so
 * CTAs navigate directly and the full funnel is testable per PR.
 */
export function isMarketingHost(hostname: string): boolean {
  const kind = getHostKind(hostname);
  return kind === 'marketing' || kind === 'localhost';
}

/**
 * Build the cross-origin redirect URL for the region-picker handoff.
 * `portalHost` is a region's domain or a company host from the enterprise lookup.
 * Preserves the target path + query (checkout, period, returnUrl) and merges
 * the visitor's captured utm_* params so attribution survives the hop.
 * Pure function so it can be unit-tested; the card select, the countdown and the
 * company lookup all go through it.
 */
export function buildPortalRedirectUrl(
  portalHost: string,
  targetPath: string,
  utmParams?: Record<string, string>
): string {
  const url = new URL(targetPath, `https://${portalHost}`);
  for (const [key, value] of Object.entries(utmParams ?? {})) {
    if (key.startsWith('utm_') && value && !url.searchParams.has(key)) {
      url.searchParams.set(key, value);
    }
  }
  return url.toString();
}
