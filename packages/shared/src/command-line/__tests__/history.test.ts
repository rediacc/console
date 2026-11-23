import { describe, expect, it } from 'vitest';
import { HistoryCursor } from '../history.js';

const lines = ['rdc repo list', 'rdc machine list', 'rdc repo fork shop --tag t1'];

describe('HistoryCursor', () => {
  it('Up walks to older entries, then stops at the oldest', () => {
    const h = new HistoryCursor(lines);
    expect(h.up('')).toBe(lines[2]);
    expect(h.up(lines[2])).toBe(lines[1]);
    expect(h.up(lines[1])).toBe(lines[0]);
    expect(h.up(lines[0])).toBe(lines[0]);
  });

  it('Up then Down restores the draft', () => {
    const h = new HistoryCursor(lines);
    expect(h.up('rdc')).toBe(lines[2]);
    expect(h.up(lines[2])).toBe(lines[1]);
    expect(h.down(lines[1])).toBe(lines[2]);
    expect(h.down(lines[2])).toBe('rdc');
    expect(h.browsing).toBe(false);
  });

  it('keeps a non-empty draft while the walk filters by it', () => {
    const h = new HistoryCursor(lines);
    expect(h.up('rdc repo')).toBe(lines[2]);
    expect(h.up(lines[2])).toBe(lines[0]);
    expect(h.up(lines[0])).toBe(lines[0]);
    expect(h.down(lines[0])).toBe(lines[2]);
    expect(h.down(lines[2])).toBe('rdc repo');
    expect(h.browsing).toBe(false);
  });

  it('control: an empty draft walks every entry, including the one a prefix draft skipped', () => {
    const h = new HistoryCursor(lines);
    h.up('');
    expect(h.up('')).toBe(lines[1]);
  });

  it('Up with no match leaves the box as it is and starts no walk', () => {
    const h = new HistoryCursor(lines);
    expect(h.up('zzz')).toBe('zzz');
    expect(h.browsing).toBe(false);
    expect(h.down('zzz')).toBe('zzz');
  });

  it('Down without a walk returns the current text', () => {
    expect(new HistoryCursor(lines).down('typed')).toBe('typed');
  });

  it('Up on empty history returns the draft', () => {
    expect(new HistoryCursor().up('abc')).toBe('abc');
  });

  it('a second walk takes a fresh draft after the draft was restored', () => {
    const h = new HistoryCursor(lines);
    h.up('rdc m');
    h.down('');
    expect(h.up('rdc repo')).toBe(lines[2]);
    expect(h.down('')).toBe('rdc repo');
  });

  it('reset ends the walk without restoring', () => {
    const h = new HistoryCursor(lines);
    h.up('');
    h.reset();
    expect(h.browsing).toBe(false);
    expect(h.down('edited')).toBe('edited');
    expect(h.up('')).toBe(lines[2]);
  });

  it('push appends the newest entry, skips a blank and an immediate repeat, and ends a walk', () => {
    const h = new HistoryCursor(lines);
    h.up('');
    h.push('rdc doctor');
    expect(h.browsing).toBe(false);
    h.push('   ');
    h.push('rdc doctor');
    expect(h.up('')).toBe('rdc doctor');
    expect(h.up('')).toBe(lines[2]);
  });

  it('setEntries replaces the entries and ends a walk', () => {
    const h = new HistoryCursor(lines);
    h.up('');
    h.setEntries(['rdc one']);
    expect(h.browsing).toBe(false);
    expect(h.up('')).toBe('rdc one');
  });

  it('does not share its entries with the caller', () => {
    const source = ['rdc a'];
    const h = new HistoryCursor(source);
    source.push('rdc b');
    expect(h.up('')).toBe('rdc a');
  });
});
