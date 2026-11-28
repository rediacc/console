import { beforeEach, describe, expect, it, vi } from 'vitest';

const { overlay } = vi.hoisted(() => ({ overlay: { value: null as { name: string } | null } }));
vi.mock('../state.js', () => ({ readPreviewOverlay: () => overlay.value }));

const { previewTouchOption } = await import('../touch.js');

beforeEach(() => {
  overlay.value = null;
});

describe('previewTouchOption', () => {
  it('returns nothing while no preview overlay is active, even for an unnamed machine', () => {
    expect(previewTouchOption(undefined)).toEqual({});
    expect(previewTouchOption('vm1')).toEqual({});
  });

  it('names the machine while a preview is active', () => {
    overlay.value = { name: 'pv-amber-river-stone' };
    expect(previewTouchOption('vm-1')).toEqual({ previewTouch: { machine: 'vm-1' } });
  });

  it('carries the refusal for an unnamed machine or an invalid name while a preview is active, and does not throw', () => {
    overlay.value = { name: 'pv-amber-river-stone' };
    for (const name of [undefined, 'Bad_Name', '-vm']) {
      const option = previewTouchOption(name);
      expect(option.previewTouch?.machine).toBeUndefined();
      expect(option.previewTouch?.refusal).toBeInstanceOf(Error);
    }
  });
});
