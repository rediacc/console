import { describe, expect, it } from 'vitest';
import { GIB } from '../largeRepoBudget';
import {
  dockerErrorDetail,
  dockerSkipDetail,
  parseDfAvailBytes,
  storeSpaceVerdict,
} from '../storeSpace';

const LOCAL = 'http://127.0.0.1:9100';

describe('storeSpaceVerdict', () => {
  it('fails with the named message when the local store has less free space than needed', () => {
    const v = storeSpaceVerdict({ endpoint: LOCAL, neededBytes: 7 * GIB, freeBytes: 1_900_000 });
    expect(v.kind).toBe('full');
    if (v.kind === 'full') {
      expect(v.message).toContain('backup store disk is full');
      expect(v.message).toContain('account-config-rustfs:/data');
      expect(v.message).toContain('docker builder prune');
    }
  });

  it('passes when the local store has enough', () => {
    expect(
      storeSpaceVerdict({ endpoint: LOCAL, neededBytes: 7 * GIB, freeBytes: 20 * GIB })
    ).toEqual({ kind: 'ok', freeBytes: 20 * GIB });
    expect(
      storeSpaceVerdict({ endpoint: LOCAL, neededBytes: 7 * GIB, freeBytes: 7 * GIB }).kind
    ).toBe('ok');
  });

  it('skips with a reason for a remote store', () => {
    const v = storeSpaceVerdict({
      endpoint: 'https://abc.r2.cloudflarestorage.com',
      neededBytes: GIB,
      freeBytes: undefined,
    });
    expect(v.kind).toBe('skipped');
    if (v.kind === 'skipped') expect(v.reason).toContain('r2.cloudflarestorage.com');
  });

  it('skips with a reason when the local free space is unreadable', () => {
    const v = storeSpaceVerdict({ endpoint: LOCAL, neededBytes: GIB, freeBytes: undefined });
    expect(v.kind).toBe('skipped');
    if (v.kind === 'skipped') expect(v.reason).toContain('could not be read');
  });
});

describe('parseDfAvailBytes', () => {
  it('reads the number under the header', () => {
    expect(parseDfAvailBytes('      Avail\n19935260672\n')).toBe(19935260672);
    expect(parseDfAvailBytes('Error: no such container')).toBeUndefined();
  });
});

describe('docker exec skip detail', () => {
  const execErr = Object.assign(
    new Error(
      'Command failed: docker exec account-config-rustfs df\nError: No such container: x\n'
    ),
    { stderr: 'Error: No such container: x\n' }
  );

  it('names the docker stderr line, not the echoed command', () => {
    expect(dockerErrorDetail(execErr)).toBe('Error: No such container: x');
  });

  it('reads the message past the Command failed line when stderr is absent', () => {
    expect(dockerErrorDetail(new Error('Command failed: docker exec c df\nboom\n'))).toBe('boom');
  });

  it('falls back to the Command failed line when nothing else was said, and to a string error', () => {
    expect(dockerErrorDetail(new Error('Command failed: docker exec c df'))).toBe(
      'Command failed: docker exec c df'
    );
    expect(dockerErrorDetail('plain')).toBe('plain');
  });

  it('suffixes the local store skip only when docker failed', () => {
    expect(dockerSkipDetail(LOCAL, execErr)).toBe(' (docker exec: Error: No such container: x)');
    expect(dockerSkipDetail(LOCAL, undefined)).toBe('');
  });

  it('leaves a remote endpoint skip without a docker suffix', () => {
    expect(dockerSkipDetail('https://abc.r2.cloudflarestorage.com', execErr)).toBe('');
  });
});
