import { isMarketingHost } from './marketing-host';

function hostnameFromOrigin(origin?: string): string {
  if (!origin) return typeof window !== 'undefined' ? window.location.hostname : '';
  try {
    return new URL(origin).hostname;
  } catch {
    return origin;
  }
}

/**
 * Returns the local account portal path when running on a host that serves
 * the account portal directly (regional cloud, edge, bench, on-prem).
 * Returns undefined on marketing hosts, where the region picker must be used.
 */
export function getLocalAccountUrl(origin?: string): string | undefined {
  return isMarketingHost(hostnameFromOrigin(origin)) ? undefined : '/account/';
}
