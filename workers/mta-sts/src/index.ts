/**
 * MTA-STS policy server for `mta-sts.rediacc.com` and `mta-sts.rediacc.io`.
 *
 * Receivers fetch `https://mta-sts.<domain>/.well-known/mta-sts.txt` once the
 * `_mta-sts.<domain>` TXT advertises an STS policy id, then enforce
 * TLS-on-MX delivery against `mail.rediacc.io`. RFC 8461.
 *
 * Mode is `enforce`: receivers MUST verify TLS to a listed MX or drop the
 * message and emit a TLS-RPT failure report. The receiving mail server
 * (`mail.rediacc.io`, 72.61.137.225) terminates TLS via the Traefik front
 * so any modern receiver completes successfully.
 *
 * Policy id rotation: when the policy body changes, bump the
 * `_mta-sts.<domain>` TXT id (timestamp form `2026MMDDhhmmZ`). Receivers
 * cache the policy for `max_age` seconds and re-fetch when the id changes.
 */

// Intentionally single-MX. Do NOT add `mx: mail.rediacc.com` back without
// first solving the TLS side. The Let's Encrypt cert Traefik serves on the
// hostinger MTA only covers `mail.rediacc.io` — listing `mail.rediacc.com`
// here tells STS-enforcing senders that delivering to that hostname is
// TLS-valid, but the cert presents `CN=mail.rediacc.io` with no `.com` SAN,
// so every such session fails with `certificate-host-mismatch` (Google TLS-RPT
// 2026-04-20 had 29 failures this way). Adding it back requires ONE of:
//   1. Extending the Traefik CF DNS-01 token to edit the `rediacc.com` zone
//      (blast radius: token can rewrite MX/SPF/DKIM/DMARC/MTA-STS/apex — bad),
//   2. CNAME delegation: add `_acme-challenge.mail.rediacc.com CNAME
//      _acme-challenge.mail.rediacc.io` in the rediacc.com zone so lego
//      follows the CNAME and writes the challenge TXT into rediacc.io
//      (which the current token already controls), then add
//      `tls.domains[0].sans=mail.rediacc.com` on the mail-acme router.
// Until one of those is in place, `mail.rediacc.io` is the only valid MX.
const POLICY = `version: STSv1
mode: enforce
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
