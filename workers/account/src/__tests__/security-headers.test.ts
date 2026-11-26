import { describe, expect, it } from 'vitest';
import { WK_MEDIA_ORIGIN } from '../../../../packages/shared/src/config/well-known.generated.js';
import { SECURITY_HEADERS } from '../security-headers.js';

/**
 * The account Worker's CSP and Permissions-Policy, which open the microphone, WebAssembly and
 * media.rediacc.com to the AI assistant (PLAN-console-ai-assistant D12). A dropped or misspelled
 * directive would not fail the type check or the web build, so each one is pinned here.
 */

function directive(name: string): string[] {
  const csp = SECURITY_HEADERS['Content-Security-Policy'];
  const found = csp.split('; ').find((part) => part.startsWith(`${name} `));
  return found ? found.slice(name.length + 1).split(' ') : [];
}

describe('account Worker security headers', () => {
  it('opens the microphone to this origin only, and keeps passkeys and payment open', () => {
    const policy = SECURITY_HEADERS['Permissions-Policy'];
    expect(policy).toContain('microphone=(self)');
    expect(policy).toContain('camera=()');
    expect(policy).toContain('publickey-credentials-get=(self)');
    expect(policy).toContain('publickey-credentials-create=(self)');
    expect(policy).toContain('payment=(self)');
  });

  it('admits WebAssembly compilation and nothing inline or eval in script-src', () => {
    const scripts = directive('script-src');
    expect(scripts).toContain("'wasm-unsafe-eval'");
    expect(scripts).not.toContain("'unsafe-eval'");
    expect(scripts).not.toContain("'unsafe-inline'");
  });

  it('lets connect-src reach the media origin that serves the speech model', () => {
    expect(directive('connect-src')).toContain(WK_MEDIA_ORIGIN);
    expect(directive('connect-src')).toContain("'self'");
  });

  it('control: the framing, object and base defences stay closed', () => {
    expect(directive('frame-ancestors')).toEqual(["'none'"]);
    expect(directive('object-src')).toEqual(["'none'"]);
    expect(directive('default-src')).toEqual(["'self'"]);
    expect(SECURITY_HEADERS['X-Frame-Options']).toBe('DENY');
  });
});
