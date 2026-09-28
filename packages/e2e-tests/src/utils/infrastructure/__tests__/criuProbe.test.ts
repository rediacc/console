import { describe, expect, it } from 'vitest';
import { CRIU_PROBE_COMMAND, criuProbeFound } from '../InfrastructureManager';

describe('CRIU_PROBE_COMMAND', () => {
  it('searches /usr/sbin as root, where renet setup installs CRIU', () => {
    expect(CRIU_PROBE_COMMAND).toMatch(/^sudo sh -c '/);
    expect(CRIU_PROBE_COMMAND).toContain('/usr/sbin');
    expect(CRIU_PROBE_COMMAND).toContain('/usr/local/bin');
  });

  it('never falls back to the login user PATH through `which`', () => {
    expect(CRIU_PROBE_COMMAND).not.toMatch(/\bwhich\b/);
  });

  it('requires the binary to run, not only to exist', () => {
    expect(CRIU_PROBE_COMMAND).toContain('command -v criu && criu --version');
  });
});

describe('criuProbeFound', () => {
  it('accepts a path followed by the version', () => {
    expect(criuProbeFound({ code: 0, stdout: '/usr/sbin/criu\nVersion: 4.1\n' })).toBe(true);
  });

  it('rejects a non-zero exit even with a path printed', () => {
    expect(
      criuProbeFound({
        code: 1,
        stdout: '/usr/sbin/criu\ncriu: error while loading shared libraries',
      })
    ).toBe(false);
  });

  it('rejects empty output, which is what a missing CRIU prints', () => {
    expect(criuProbeFound({ code: 1, stdout: '' })).toBe(false);
  });

  it('rejects a first line that is not an absolute path', () => {
    expect(criuProbeFound({ code: 0, stdout: 'criu: command not found\n' })).toBe(false);
  });
});
