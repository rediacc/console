import { describe, expect, it } from 'vitest';
import { buildRsyncArgs } from '../rsync.js';

const variants = [
  { verify: false },
  { verify: true },
  { verify: true, mirror: true, isUpload: true },
  { verify: false, mirror: true },
];

describe('buildRsyncArgs --inplace implies --partial', () => {
  for (const v of variants) {
    it(`real run passes --inplace (${JSON.stringify(v)})`, () => {
      const args = buildRsyncArgs(v, 'ssh', 'rediacc');
      expect(args).toContain('--inplace');
    });
  }

  it('the verify branch drops --partial but keeps --inplace, which implies it', () => {
    const args = buildRsyncArgs({ verify: true }, 'ssh');
    expect(args).not.toContain('--partial');
    expect(args).toContain('--inplace');
    expect(args).toContain('--checksum');
  });

  it('a non-verify real run passes --partial explicitly', () => {
    expect(buildRsyncArgs({}, 'ssh')).toContain('--partial');
  });

  it('a dry run never passes --inplace, and a verify dry run passes neither', () => {
    expect(buildRsyncArgs({}, 'ssh', undefined, true)).not.toContain('--inplace');
    const verifyDry = buildRsyncArgs({ verify: true }, 'ssh', undefined, true);
    expect(verifyDry).not.toContain('--inplace');
    expect(verifyDry).not.toContain('--partial');
  });
});
