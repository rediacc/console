import { describe, expect, it } from 'vitest';
import { isMachineReadableRelayLine } from '../executor/output-lines.js';

/**
 * The recorded tutorials showed 322-400 column JSON blobs on camera because
 * renet's protocol lines were rendered as if they were human output.
 */
describe('isMachineReadableRelayLine', () => {
  it('flags the push_result envelope that shipped at 324 columns', () => {
    expect(
      isMachineReadableRelayLine('{"push_result":{"repository":"14d75481","transferMode":"delta"}}')
    ).toBe(true);
  });

  it('flags the steps envelope and the repo-log envelope', () => {
    expect(isMachineReadableRelayLine('{"steps":[{"name":"a","duration_ms":1}]}')).toBe(true);
    expect(isMachineReadableRelayLine('{"success":true,"start":"46cfe739"}')).toBe(true);
  });

  it('sees through a bridge relay prefix', () => {
    expect(isMachineReadableRelayLine('[backup_push] {"push_result":{"x":1}}')).toBe(true);
  });

  it('does NOT flag ordinary human output, which must stay on screen', () => {
    expect(isMachineReadableRelayLine('sent 2,148,008,121 bytes  received 35 bytes')).toBe(false);
    expect(isMachineReadableRelayLine('total size is 2,147,483,648  speedup is 1.00')).toBe(false);
    expect(isMachineReadableRelayLine('')).toBe(false);
  });

  it('does NOT flag a JSON ARRAY or a scalar', () => {
    expect(isMachineReadableRelayLine('[{"a":1}]')).toBe(false);
    expect(isMachineReadableRelayLine('"just a string"')).toBe(false);
  });

  it('does NOT flag a line that merely CONTAINS braces', () => {
    expect(isMachineReadableRelayLine('use ${VAR} in your compose file')).toBe(false);
    expect(isMachineReadableRelayLine('{not valid json}')).toBe(false);
  });
});
