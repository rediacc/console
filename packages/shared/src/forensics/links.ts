/**
 * Deep links into the forensics timeline (PLAN-forensics-alerts-notices D3). The path is the one
 * PLAN-forensics-investigation.md mounts its timeline route at, and this file is its only
 * definition: a notice, an email and the route all build the link here.
 */

/** The account portal path of the forensics timeline. */
export const FORENSICS_TIMELINE_PATH = '/account/console/forensics';

/** Total width of the window a timeline link opens, centred on the detection time. */
export const FORENSICS_TIMELINE_WINDOW_MS = 2 * 60 * 60 * 1000;

/**
 * `/account/console/forensics?repo=<guid>&from=<iso>&to=<iso>`: a 2-hour window around `detectedAt`.
 * An unparsable `detectedAt` yields the repository link without a window, so a bad timestamp never
 * produces a link with `NaN` dates.
 */
export function forensicsTimelinePath(repoGuid: string, detectedAt: string): string {
  const centre = Date.parse(detectedAt);
  const params = new URLSearchParams({ repo: repoGuid });
  if (Number.isFinite(centre)) {
    const half = FORENSICS_TIMELINE_WINDOW_MS / 2;
    params.set('from', new Date(centre - half).toISOString());
    params.set('to', new Date(centre + half).toISOString());
  }
  return `${FORENSICS_TIMELINE_PATH}?${params.toString()}`;
}
