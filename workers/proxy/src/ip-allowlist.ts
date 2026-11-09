/**
 * The opt-in IP allowlist for a company's proxy and account Workers, applied at the top of each default fetch handler (workers/proxy/src/index.ts, workers/account/src/index.ts).
 *
 * Off when `ALLOW_IPS` is unset or empty. When set, a request from an address outside the list is refused with 403, and the one exemption is `POST` on the licence renew path: a machine outside the list would otherwise lose renewal, and the licence blob is that call's bearer proof. `GET` on the renew path, and `POST` to any other path, stay refused. It reduces exposure and replaces nothing: the token check still applies.
 */

/** packages/shared/src/subscription/constants.ts LICENSE_RENEW_PATH; the Worker bundle does not import the shared package. */
export const LICENSE_RENEW_PATH = '/account/api/v1/licenses/renew';

function ipv4ToInt(ip: string): number | undefined {
  const parts = ip.split('.');
  if (parts.length !== 4) return undefined;
  let n = 0;
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part) || Number(part) > 255) return undefined;
    n = n * 256 + Number(part);
  }
  return n;
}

/** Whether `ip` equals `entry`, or lies in `entry` when that is an IPv4 `a.b.c.d/n` range. */
function matches(ip: string, entry: string): boolean {
  const slash = entry.indexOf('/');
  if (slash === -1) return ip.toLowerCase() === entry.toLowerCase();
  const base = ipv4ToInt(entry.slice(0, slash));
  const addr = ipv4ToInt(ip);
  const prefix = entry.slice(slash + 1);
  // A strict decimal prefix only: Number('') and Number('0x0') are 0, which would match every address.
  if (!/^\d{1,2}$/.test(prefix)) return false;
  const bits = Number(prefix);
  if (base === undefined || addr === undefined || bits > 32) return false;
  const size = 2 ** (32 - bits);
  return Math.floor(base / size) === Math.floor(addr / size);
}

/** The refusal for a request the allowlist turns away, or undefined when it may proceed. */
export function allowlistRefusal(
  request: Request,
  allowIps: string | undefined
): Response | undefined {
  const entries = (allowIps ?? '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
  if (entries.length === 0) return undefined;
  if (request.method === 'POST' && new URL(request.url).pathname === LICENSE_RENEW_PATH) {
    return undefined;
  }
  const ip = request.headers.get('cf-connecting-ip')?.trim();
  if (ip && entries.some((entry) => matches(ip, entry))) return undefined;
  console.warn('worker: caller refused: ip-not-allowed');
  return Response.json({ error: 'This address is not on the allowlist.' }, { status: 403 });
}
