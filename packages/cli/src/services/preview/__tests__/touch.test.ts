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

  it('refuses an unnamed machine or an invalid name while a preview is active', () => {
    overlay.value = { name: 'pv-amber-river-stone' };
    expect(() => previewTouchOption(undefined)).toThrow();
    expect(() => previewTouchOption('Bad_Name')).toThrow();
    expect(() => previewTouchOption('-vm')).toThrow();
  });
});
