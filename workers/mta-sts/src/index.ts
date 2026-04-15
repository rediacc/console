/**
 * MTA-STS policy server for `mta-sts.rediacc.com` and `mta-sts.rediacc.io`.
 *
 * Receivers fetch `https://mta-sts.<domain>/.well-known/mta-sts.txt` once the
 * `_mta-sts.<domain>` TXT advertises an STS policy id, then enforce
 * TLS-on-MX delivery against `mail.rediacc.{com,io}`. RFC 8461.
 *
 * Initial deployment is `mode: testing` — receivers report TLS failures via
 * TLS-RPT (already configured at `_smtp._tls.rediacc.{com,io}`) but do NOT
 * actually drop mail when TLS handshake fails. After 7 days of clean
 * reports, promote to `mode: enforce` by editing the POLICY constant below
 * and bumping the policy id in DNS.
 *
 * Policy id rotation: when the policy body changes, also bump the
 * `_mta-sts.<domain>` TXT id (timestamp form `2026MMDDhhmmZ`). Receivers
 * cache the policy for `max_age` seconds and re-fetch when the id changes.
 */

const POLICY = `version: STSv1
mode: testing
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
          // RFC 8461 §3.3: receivers should respect cache-control. 24h is
          // a sensible cache length while in `mode: testing`; bump to a week
          // once enforce is locked in.
          'cache-control': 'public, max-age=86400',
        },
      });
    }
    return new Response('Not Found', { status: 404 });
  },
};
