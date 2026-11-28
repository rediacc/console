/**
 * The region of a grant and of this Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 12, D58).
 *
 * A grant id starts `<region>_` (the account's `agentGrantInRegion`), so the id alone says which region's Worker may serve it. A grant presented to another region is refused here, before the grant lookup, the executor and any OAuth state: the answer names the right region's MCP URL when the id carries a known region prefix, and anything else falls through to the bare 401 an unknown grant gets.
 */

/** The regions a grant id may be prefixed with; the bench regions reuse them. */
export const GRANT_REGIONS: readonly string[] = ['eu', 'us', 'asia'] as const;

/** The grant id a `/g/<id>` path names. */
const GRANT_PATH = /^\/g\/([A-Za-z0-9_-]{1,64})$/;

/** The region a grant id is prefixed with, or null for an id with no known prefix. */
export function grantRegionOf(grantId: string): string | null {
  const underscore = grantId.indexOf('_');
  if (underscore <= 0 || underscore === grantId.length - 1) return null;
  const prefix = grantId.slice(0, underscore);
  return GRANT_REGIONS.includes(prefix) ? prefix : null;
}

/** Whether this Worker may serve `grantId`: any id where no region is set (on-premise), else one prefixed `<region>_` with something after it. */
export function grantServedHere(grantId: string, region: string | undefined): boolean {
  if (!region) return true;
  return grantId.startsWith(`${region}_`) && grantId.length > region.length + 1;
}

/** The MCP host of `region`, derived from this Worker's host by swapping the region at the end of its second label (`mcp.eu.x` to `mcp.us.x`, `mcp.bench-eu.x` to `mcp.bench-us.x`); null when the host has no such label. */
export function hostOfRegion(host: string, ownRegion: string, region: string): string | null {
  const labels = host.split('.');
  const label = labels[1];
  if (label === undefined || !label.endsWith(ownRegion)) return null;
  labels[1] = `${label.slice(0, label.length - ownRegion.length)}${region}`;
  return labels.join('.');
}

/** The refusal for a request at `/g/<id>` whose grant id carries another region's prefix, or null for every other request. */
export function wrongRegionResponse(
  request: Request,
  worker: { host: string; region: string | undefined }
): Response | null {
  if (!worker.region) return null;
  const grantId = GRANT_PATH.exec(new URL(request.url).pathname)?.[1];
  if (grantId === undefined) return null;
  const grantRegion = grantRegionOf(grantId);
  if (grantRegion === null || grantRegion === worker.region) return null;
  const host = hostOfRegion(worker.host, worker.region, grantRegion);
  if (host === null) return null;
  const mcpUrl = `https://${host}/g/${grantId}`;
  return new Response(
    JSON.stringify({
      code: 'REDIACC_WRONG_REGION',
      message: `This grant lives in the ${grantRegion} region. Use ${mcpUrl}.`,
      region: grantRegion,
      mcpUrl,
    }),
    {
      status: 421,
      headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
    }
  );
}
