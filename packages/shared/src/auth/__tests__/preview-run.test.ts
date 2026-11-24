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

  it('a doubtful value always reads as acting, never as a preview (review 0ff6b868.1)', () => {
    // opt-in: a non-boolean dry-run is not a preview.
    expect(isPreviewRun(OPT_IN, { 'dry-run': 'true' })).toBe(false);
    // default: a non-boolean apply may reach the executor as an apply, so it is not a preview and keeps step-up.
    expect(isPreviewRun(DEFAULT, { apply: 'true' })).toBe(false);
    expect(isPreviewRun(DEFAULT, { apply: 1 })).toBe(false);
    expect(isPreviewRun(DEFAULT, { apply: '' })).toBe(false);
  });

  it('a null act flag reads as acting, while an absent or false one is a preview (review 0c72428e.1)', () => {
    expect(isPreviewRun(DEFAULT, { apply: null })).toBe(false);
    expect(isPreviewRun(DEFAULT, { apply: undefined })).toBe(true);
    expect(isPreviewRun(OPT_IN, { 'dry-run': null })).toBe(false);
  });
});
