import { describe, expect, it } from 'vitest';
import { isPreviewRun } from '../preview-run.js';

const OPT_IN = { preview: { flag: 'dry-run', polarity: 'opt-in' as const } };
const DEFAULT = { preview: { flag: 'apply', polarity: 'default' as const } };

describe('isPreviewRun', () => {
  it('a command without a preview switch is never a preview', () => {
    expect(isPreviewRun({}, {})).toBe(false);
    expect(isPreviewRun({}, { 'dry-run': true })).toBe(false);
  });

  it('opt-in: previews only when the flag is true', () => {
    expect(isPreviewRun(OPT_IN, { 'dry-run': true })).toBe(true);
    expect(isPreviewRun(OPT_IN, {})).toBe(false);
    expect(isPreviewRun(OPT_IN, { 'dry-run': false })).toBe(false);
  });

  it('default: previews unless the act flag is true', () => {
    expect(isPreviewRun(DEFAULT, {})).toBe(true);
    expect(isPreviewRun(DEFAULT, { apply: false })).toBe(true);
    expect(isPreviewRun(DEFAULT, { apply: true })).toBe(false);
  });

  it('a non-boolean value is never the flag being given', () => {
    expect(isPreviewRun(OPT_IN, { 'dry-run': 'true' })).toBe(false);
    expect(isPreviewRun(DEFAULT, { apply: 'true' })).toBe(true);
  });
});
