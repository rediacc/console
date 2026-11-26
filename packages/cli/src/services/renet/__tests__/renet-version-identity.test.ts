/**
 * A preview build's version identity (PLAN-preview-signer.md B1, D7): `X.Y.Z-preview.<sha7>` is neither a
 * dev build nor the release it precedes. `isDevVersion` and `bareVersion` are private to the replacement
 * guard, so the classification is read through its verdicts.
 */
import { describe, expect, it } from 'vitest';
import { decideRenetReplacement } from '../renet-replacement.js';

const PREVIEW = '1.2.4-preview.abcdef0';

function decide(over: {
  cli: string;
  local: string | null;
  running: string | null;
  embedded: boolean;
}) {
  return decideRenetReplacement({ host: 'srv', ...over });
}

describe('a preview version in the renet replacement guard', () => {
  it('is not a dev build: a preview renet on the machine is replaced by the release, the way back', () => {
    expect(decide({ cli: '1.2.3', local: '1.2.3', running: PREVIEW, embedded: true })).toBeNull();
  });

  it('is not a dev build: a preview CLI deploying its own preview renet is admitted over a release', () => {
    expect(decide({ cli: PREVIEW, local: PREVIEW, running: '1.2.3', embedded: false })).toBeNull();
  });

  it('is not the release: a release CLI holding a preview-stamped renet outside a SEA is unverified', () => {
    expect(
      decide({ cli: '1.2.4', local: PREVIEW, running: '1.2.3', embedded: false })
    ).toMatchObject({
      code: 'RENET_BUILD_UNVERIFIED',
    });
  });

  it('still refuses what a dev or newer release machine refuses (controls)', () => {
    expect(
      decide({ cli: '1.2.3', local: '1.2.3', running: '0.0.0-dev', embedded: true })
    ).toMatchObject({
      code: 'RENET_DEV_ON_MACHINE',
    });
    expect(
      decide({ cli: '1.2.3', local: '1.2.3', running: '1.3.0', embedded: true })
    ).toMatchObject({
      code: 'RENET_DOWNGRADE_REFUSED',
    });
  });

  it('keeps the placeholder core 0.0.0 a dev build even with the preview suffix', () => {
    expect(
      decide({ cli: '1.2.3', local: '1.2.3', running: '0.0.0-preview.abcdef0', embedded: true })
    ).toMatchObject({ code: 'RENET_DEV_ON_MACHINE' });
  });
});
