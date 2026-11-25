import { describe, expect, it } from 'vitest';
import {
  CLAIM_OVERSTATEMENT_ALLOWLIST,
  findClaimOverstatements,
} from '../validate-content-accuracy.js';

type Hit = { arm: string; line: number };
const scan = (text: string, file = 'docs/en/x.md'): Hit[] => findClaimOverstatements(text, file);

describe('claim-overstatement rule', () => {
  it('refuses the "forensic trail" arm', () => {
    expect(scan('Every action leaves a forensic trail.').map((h) => h.arm)).toEqual([
      'forensic trail',
    ]);
  });

  it('refuses the "forensic-grade" arm', () => {
    expect(scan('A forensic-grade record of changes.').map((h) => h.arm)).toEqual([
      'forensic-grade',
    ]);
  });

  it('refuses hash-chained within one sentence of audit log when no scope is named', () => {
    const hits = scan('Line one.\nThe server keeps a hash-chained audit log for you.');
    expect(hits.map((h) => h.arm)).toEqual(['hash-chained audit log']);
    expect(hits[0].line).toBe(2);
  });

  it('passes hash-chained audit log when the sentence names per org or a day file', () => {
    expect(scan('The hash-chained audit log is chained per org and day.')).toEqual([]);
    expect(scan('The hash-chained audit log lives in one day file per org.')).toEqual([]);
  });

  it('passes hash-chained when audit log sits in a different sentence', () => {
    expect(scan('Batches are hash-chained. The audit log is separate.')).toEqual([]);
  });

  it('passes an allowlisted line that carries a reason', () => {
    const line = 'The local file is a hash-chained audit log.';
    const allow = [{ file: 'docs/en/x.md', includes: 'local file', reason: 'local CLI log' }];
    expect(findClaimOverstatements(line, 'docs/en/x.md', allow)).toEqual([]);
    expect(findClaimOverstatements(line, 'docs/en/x.md', [])).toHaveLength(1);
  });

  it('ignores an allowlist entry that has no reason', () => {
    const line = 'The local file is a hash-chained audit log.';
    const allow = [{ file: 'docs/en/x.md', includes: 'local file', reason: '' }];
    expect(findClaimOverstatements(line, 'docs/en/x.md', allow)).toHaveLength(1);
  });

  it('keeps a reason on every shipped allowlist entry', () => {
    for (const entry of CLAIM_OVERSTATEMENT_ALLOWLIST) {
      expect(entry.reason.length).toBeGreaterThan(10);
    }
  });
});
