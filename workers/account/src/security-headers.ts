import { WK_MEDIA_ORIGIN } from '../../../packages/shared/src/config/well-known.generated.js';

// Modelled on packages/www/public/_headers but deliberately not a copy: the portal is stricter (no inline scripts, no analytics origins, framing denied) and opens the microphone, WebAssembly and media.rediacc.com for the AI assistant, which the marketing site does not. Applied to every response served from this worker (SPA HTML, static assets, API JSON, redirects, 404). Responses that already declare a Content-Security-Policy (the invoice PDF routes —
// private/account/src/routes/{root,portal}-invoices.ts) keep their stricter
// per-route policy untouched.
export const SECURITY_HEADERS: Record<string, string> = {
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  // Permissions-Policy must keep WebAuthn (passkey) open or @simplewebauthn/browser calls fail under future Cloudflare-edge tightening. Stripe redirects via window.location.assign which is a top-level navigation not gated by Permissions-Policy. The microphone is open to this origin for the AI assistant's speech input (agent/plans/PLAN-console-ai-assistant.md D12).
  'Permissions-Policy':
    'camera=(), microphone=(self), geolocation=(), payment=(self), publickey-credentials-get=(self), publickey-credentials-create=(self)',
  'Content-Security-Policy': [
    "default-src 'self'",
    // admits WebAssembly compilation only (the local Whisper speech model), not eval().
    "script-src 'self' 'wasm-unsafe-eval' https://challenges.cloudflare.com",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    // media.rediacc.com serves the local speech model files, which exceed the Workers static-asset limit.
    `connect-src 'self' https://challenges.cloudflare.com ${WK_MEDIA_ORIGIN}`,
    "frame-src 'self' https://challenges.cloudflare.com",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    'upgrade-insecure-requests',
  ].join('; '),
};
