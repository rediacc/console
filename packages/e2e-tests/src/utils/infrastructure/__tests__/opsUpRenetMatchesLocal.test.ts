import { describe, expect, it } from 'vitest';
import { opsUpRenetMatchesLocal } from '../InfrastructureManager';

const LOCAL = 'd41d8cd98f00b204e9800998ecf8427e';
const OTHER = '0cc175b9c0f1b6a831c399e269772661';

describe('opsUpRenetMatchesLocal', () => {
  it('accepts the resolved /usr/bin/renet holding the local binary', () => {
    expect(opsUpRenetMatchesLocal(`${LOCAL}\n`, LOCAL)).toBe(true);
  });

  it('rejects a stale binary', () => {
    expect(opsUpRenetMatchesLocal(`${OTHER}\n`, LOCAL)).toBe(false);
  });

  it('rejects a missing /usr/bin/renet, since md5sum then prints nothing', () => {
    expect(opsUpRenetMatchesLocal('', LOCAL)).toBe(false);
  });

  it('rejects extra output rather than trusting the first line', () => {
    expect(opsUpRenetMatchesLocal(`${LOCAL}\n${LOCAL}\n`, LOCAL)).toBe(false);
  });
});
