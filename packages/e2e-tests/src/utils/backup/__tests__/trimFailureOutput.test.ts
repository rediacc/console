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

  it('marks the cut when the diagnostic lines exceed maxChars', () => {
    const errors = Array.from({ length: 200 }, (_, i) => `error number ${i}`).join('\n');
    const out = `${'x'.repeat(500)}\n${errors}\n${'y'.repeat(500)}`;
    const trimmed = trimFailureOutput(out, 400);
    expect(trimmed).toMatch(/\[\.\.\. \d+ more chars of diagnostic lines cut \.\.\.\]/);
    expect(trimmed).toContain('error number 0');
    expect(trimmed).not.toContain('error number 199');
  });

  it('adds no cut marker when every diagnostic line fits', () => {
    const out = `${'x'.repeat(3000)}\nerror: one\n${'y'.repeat(3000)}`;
    const trimmed = trimFailureOutput(out, 2000);
    expect(trimmed).toContain('error: one');
    expect(trimmed).not.toContain('more chars of diagnostic lines cut');
  });

  it('caps one diagnostic line at 600 chars', () => {
    const out = `${'x'.repeat(3000)}\nerror ${'z'.repeat(2000)}\n${'y'.repeat(3000)}`;
    const trimmed = trimFailureOutput(out, 2000);
    expect(trimmed).toContain(`error ${'z'.repeat(594)}...`);
    expect(trimmed).not.toContain('z'.repeat(601));
  });

  it.each([0, 1, 3])('does not repeat the output when maxChars is %i', (maxChars) => {
    const out = 'line one\nline two error\nline three';
    const trimmed = trimFailureOutput(out, maxChars);
    expect(trimmed).toContain('chars elided');
    expect(trimmed).not.toContain(out);
  });

  it.each([
    ['ab', 0],
    ['ab', 1],
  ])('clamps the short output %j to maxChars %i', (out, maxChars) => {
    const trimmed = trimFailureOutput(out, maxChars);
    expect(trimmed).toBe(
      `${out.slice(0, maxChars)}\n[... ${out.length - maxChars} chars elided ...]`
    );
  });
});
