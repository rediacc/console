/** GET /api/geo: the visitor's country from Cloudflare's own edge data, so the region picker can forward at login without a third party. */

interface CfRequest extends Request {
  cf?: { country?: unknown };
}

export function handleGeo(request: Request): Response {
  const raw = (request as CfRequest).cf?.country;
  // Cloudflare reports "XX" for an unknown country and "T1" for Tor; neither names a region.
  const country =
    typeof raw === 'string' && /^[A-Z]{2}$/.test(raw) && raw !== 'XX' && raw !== 'T1' ? raw : null;
  return new Response(JSON.stringify({ country }), {
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}
