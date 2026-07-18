import type { Region } from '../config/regions';

/**
 * Host classification for the www → portal handoff.
 *
 * The release channel is derived from the host — never asked of the user:
 *
 *   Host                          Kind               /account/* CTA behavior
 *   ---------------------------   ----------------   -------------------------------------
 *   www.rediacc.com               marketing-stable   region picker → stable portals
 *                                                    (eu/us/asia.rediacc.com)
 *   edge.rediacc.com              marketing-edge     region picker → edge portals
 *                                                    (edge-eu/us/asia.rediacc.com).
 *                                                    Statically serves the portal SPA
 *                                                    shell at /account/* but the API
 *                                                    returns {"error":"gone"} — so the
 *                                                    picker must forward to a regional
 *                                                    edge domain.
 *   *.rediacc.workers.dev         preview            direct navigation — PR previews
 *                                                    serve a fully functional portal
 *                                                    at /account/ backed by a per-PR D1
 *   localhost                     localhost          region picker → edge portals
 *                                                    (astro dev serves no portal; edge
 *                                                    is the dev-safe default universe)
 *   everything else               portal             direct navigation (regional cloud,
 *                                                    bench, on-prem — open-ended so
 *                                                    customer hostnames need no list)
 *
 * Closed allow-list approach: only known marketing hosts open the picker;
 * everything else navigates directly.
 *
 * Keep this rule in sync with the inline copy in BaseLayout.astro
 * (window.__rediaccIsMarketingHost) — React components import this module,
 * while inline scripts (BaseLayout's account-link interceptor and
 * CfPricingCard's checkout script) read the window mirror. All consumers
 * must agree.
 */

export type HostKind = 'marketing-stable' | 'marketing-edge' | 'preview' | 'localhost' | 'portal';

export function getHostKind(hostname: string): HostKind {
  if (hostname === 'www.rediacc.com') return 'marketing-stable';
  if (hostname === 'edge.rediacc.com') return 'marketing-edge';
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
  return kind === 'marketing-stable' || kind === 'marketing-edge' || kind === 'localhost';
}

/**
 * Portal domain for a region as seen from the given host. The channel is
 * host-determined: the stable marketing site hands off to stable portals,
 * the edge marketing site (and localhost dev) to edge portals.
 */
export function getPortalDomain(hostname: string, region: Region): string {
  return getHostKind(hostname) === 'marketing-stable' ? region.domain : region.edgeDomain;
}

/**
 * Build the cross-origin redirect URL for the region-picker handoff.
 * Preserves the target path + query (checkout, period, returnUrl) and merges
 * the visitor's captured utm_* params so attribution survives the hop.
 * Pure function so it can be unit-tested; both the picker's card select and
 * the stored-region fast path must go through it.
 */
export function buildPortalRedirectUrl(
  hostname: string,
  region: Region,
  targetPath: string,
  utmParams?: Record<string, string>
): string {
  const url = new URL(targetPath, `https://${getPortalDomain(hostname, region)}`);
  for (const [key, value] of Object.entries(utmParams ?? {})) {
    if (key.startsWith('utm_') && value && !url.searchParams.has(key)) {
      url.searchParams.set(key, value);
    }
  }
  return url.toString();
}
