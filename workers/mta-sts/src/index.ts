/**
 * MTA-STS policy server for `mta-sts.rediacc.com` and `mta-sts.rediacc.io`.
 *
 * Receivers fetch `https://mta-sts.<domain>/.well-known/mta-sts.txt` once the
 * `_mta-sts.<domain>` TXT advertises an STS policy id, then enforce
 * TLS-on-MX delivery against `mail.rediacc.{com,io}`. RFC 8461.
 *
 * Mode is `enforce`: receivers MUST verify TLS to a listed MX or drop the
 * message and emit a TLS-RPT failure report. The receiving mail server
 * (`mail.rediacc.{com,io}`, both pointing at 72.61.137.225) terminates
 * TLS via the Traefik front so any modern receiver completes successfully.
 *
 * Policy id rotation: when the policy body changes, bump the
 * `_mta-sts.<domain>` TXT id (timestamp form `2026MMDDhhmmZ`). Receivers
 * cache the policy for `max_age` seconds and re-fetch when the id changes.
 */

const POLICY = `version: STSv1
mode: enforce
mx: mail.rediacc.com
mx: mail.rediacc.io
max_age: 604800
`;

export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/.well-known/mta-sts.txt') {
      return new Response(POLICY, {
        headers: {
          'content-type': 'text/plain; charset=utf-8',
          // RFC 8461 §3.3: receivers should respect cache-control. One week
          // matches `max_age` in the policy body; longer values risk
          // delivery breakage during emergency MX changes.
          'cache-control': 'public, max-age=604800',
        },
      });
    }
    return new Response('Not Found', { status: 404 });
  },
};
