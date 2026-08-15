import { describe, it, expect } from 'vitest';
import { parseVerifyVerdict } from '../backup-storage.js';

// REGRESSION, found on a live fleet 2026-08-15: `rdc backup verify` exited 0
// with EMPTY stdout in BOTH text and json modes while the renet verb underneath
// reported {"status":"verified","level":"full","checkedCells":31}. An operator
// could not tell a verified anchor from a mismatched one -- the one distinction
// the command exists to make.
describe('parseVerifyVerdict', () => {
  it('recovers the verdict renet actually prints', () => {
    const v = parseVerifyVerdict('{"status":"verified","level":"full","checkedCells":31}');
    expect(v).toEqual({ status: 'verified', level: 'full', checkedCells: 31 });
  });

  it('finds the verdict among relay prefixes and log lines', () => {
    const out = [
      'time="2026-08-15T04:14:18Z" level=info msg="starting"',
      '[backup_verify] {"status":"verified","level":"spot","checkedCells":8}',
      'time="2026-08-15T04:14:19Z" level=info msg="done"',
    ].join('\n');
    expect(parseVerifyVerdict(out)?.status).toBe('verified');
    expect(parseVerifyVerdict(out)?.checkedCells).toBe(8);
  });

  it('reports a MISMATCH rather than swallowing it', () => {
    // The whole point: a failing verification must be distinguishable.
    const v = parseVerifyVerdict('{"status":"mismatch","level":"full","checkedCells":31}');
    expect(v?.status).toBe('mismatch');
  });

  it('takes the LAST verdict when several are printed', () => {
    const out = '{"status":"verified"}\n{"status":"mismatch"}';
    expect(parseVerifyVerdict(out)?.status).toBe('mismatch');
  });

  it('returns undefined instead of throwing on unparseable output', () => {
    // A verdict we cannot read must not crash a successful verification.
    expect(parseVerifyVerdict('not json at all')).toBeUndefined();
    expect(parseVerifyVerdict('{"broken":')).toBeUndefined();
    expect(parseVerifyVerdict(undefined)).toBeUndefined();
    expect(parseVerifyVerdict('')).toBeUndefined();
  });

  it('ignores JSON that carries no status', () => {
    expect(parseVerifyVerdict('{"progress":50}')).toBeUndefined();
  });
});
