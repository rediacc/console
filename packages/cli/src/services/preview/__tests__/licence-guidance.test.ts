import { beforeEach, describe, expect, it, vi } from 'vitest';

const { active } = vi.hoisted(() => ({ active: { overlay: undefined as unknown } }));

vi.mock('../state.js', () => ({
  readPreviewOverlay: () => active.overlay,
  readRealAccountServer: () => 'https://eu.rediacc.cloud',
}));

const { resolveLicenseRecoveryGuidance } = await import(
  '../../executor/license-recovery-guidance.js'
);

const OVERLAY = {
  name: 'pv-amber-river-stone',
  host: 'https://pv-amber-river-stone.rediacc.workers.dev',
  enteredAt: '2026-11-23T10:00:00.000Z',
  channel: 'pv-amber-river-stone',
  licenceEndsAt: '2026-11-30T10:00:00.000Z',
  previous: { cliVersion: '1.3.9', cliSha256: 'a'.repeat(64) },
};

const failure = (reason: string) => ({ code: 'LICENSE_REQUIRED', reason });

describe('licence expiry guidance on a preview (D11)', () => {
  beforeEach(() => {
    active.overlay = OVERLAY;
  });

  it('answers an expired licence with the preview text, still trying a refresh first', () => {
    const g = resolveLicenseRecoveryGuidance(failure('expired'), 'vm1');
    expect(g.failFastMessage).toBeUndefined();
    expect(g.recoveryFailedMessage).toContain('pv-amber-river-stone');
    expect(g.recoveryFailedMessage).toContain('2026-11-30');
    expect(g.recoveryFailedMessage).toContain('running apps keep running');
    expect(g.recoveryFailedMessage).toContain('rdc preview leave');
    expect(g.recoveryFailedMessage).toContain('https://eu.rediacc.cloud');
    expect(g.recoveryFailedMessage).not.toContain('on-prem');
  });

  it('answers an expired cert with the preview text instead of the on-prem renewal advice, and fails fast', () => {
    const g = resolveLicenseRecoveryGuidance(failure('cert_expired'), 'vm1');
    expect(g.errorCode).toBe('REPO_LICENSE_DELEGATION_CERT_EXPIRED');
    expect(g.failFastMessage).toContain('rdc preview leave');
    expect(g.failFastMessage).not.toContain('on-prem');
    expect(g.guidance).not.toContain('delegation cert');
  });

  it('leaves every other reason on its own text', () => {
    const g = resolveLicenseRecoveryGuidance(failure('machine_mismatch'), 'vm1');
    expect(g.failFastMessage).toContain('belongs to a different machine');
  });

  it('control: outside a preview an expired cert still names the on-prem renewal', () => {
    active.overlay = undefined;
    const g = resolveLicenseRecoveryGuidance(failure('cert_expired'), 'vm1');
    expect(g.failFastMessage).toContain('on-prem');
    const expired = resolveLicenseRecoveryGuidance(failure('expired'), 'vm1');
    expect(expired.recoveryFailedMessage).toContain('rdc subscription refresh -m vm1');
  });
});
