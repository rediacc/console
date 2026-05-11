/**
 * Returns true when the current page is being served from a "marketing"
 * host that does NOT serve the account portal at /account/. On those
 * hosts, clicks on /account/* anchors must open the region picker so the
 * user chooses a regional subdomain before signing up.
 *
 * Hosts that DO serve the portal (and therefore should navigate directly):
 *   - eu.rediacc.com, us.rediacc.com, asia.rediacc.com    (regional cloud)
 *   - edge-eu.rediacc.com, edge-us.rediacc.com, edge-asia.rediacc.com (edge)
 *   - bench.rediacc.com                                    (internal)
 *   - any on-prem hostname (handled by the open-ended "else" branch)
 *
 * Marketing hosts (no portal — open the picker):
 *   - www.rediacc.com                  (production marketing site)
 *   - localhost                        (dev server)
 *   - *.rediacc.workers.dev            (PR preview deployments, e.g.
 *                                       pr-477.rediacc.workers.dev)
 *
 * Closed allow-list approach: only known marketing hosts open the picker;
 * everything else navigates directly. This keeps on-prem correct without
 * needing to enumerate customer hostnames.
 *
 * Keep this rule in sync with the inline copy in BaseLayout.astro
 * (window.__rediaccIsMarketingHost) and CfPricingCard.astro's checkout
 * script. All three consume the same logic.
 */
export function isMarketingHost(hostname: string): boolean {
  return (
    hostname === 'www.rediacc.com' ||
    hostname === 'localhost' ||
    hostname.endsWith('.rediacc.workers.dev')
  );
}
