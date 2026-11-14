import { describe, expect, it } from 'vitest';
import { trimFailureOutput } from '../chunkCliHarness';

describe('trimFailureOutput', () => {
  it('keeps a short output whole', () => {
    expect(trimFailureOutput('a\nb\nlicense refused')).toBe('a\nb\nlicense refused');
  });

  it('keeps a licence line from the middle of a long output', () => {
    const filler = (tag: string): string => `${tag} progress line\n`.repeat(2000);
    const out = `${filler('head')}renet: license required (exit 10)\n${filler('tail')}`;
    const trimmed = trimFailureOutput(out, 2000);
    expect(trimmed).toContain('renet: license required (exit 10)');
    expect(trimmed).toContain('chars elided');
    expect(trimmed.length).toBeLessThan(out.length / 10);
  });
});
