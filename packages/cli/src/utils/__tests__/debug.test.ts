import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { debugEnabled } from '../debug.js';

describe('debugEnabled', () => {
  const original = process.env.REDIACC_DEBUG;

  beforeEach(() => {
    delete process.env.REDIACC_DEBUG;
  });

  afterEach(() => {
    if (original === undefined) delete process.env.REDIACC_DEBUG;
    else process.env.REDIACC_DEBUG = original;
  });

  const SCOPES = ['daemon', 'renet', 'timing', 'otel'] as const;

  it('unset: everything off (unscoped and every scope)', () => {
    delete process.env.REDIACC_DEBUG;
    expect(debugEnabled()).toBe(false);
    for (const s of SCOPES) expect(debugEnabled(s)).toBe(false);
  });

  it('empty string: everything off', () => {
    process.env.REDIACC_DEBUG = '';
    expect(debugEnabled()).toBe(false);
    for (const s of SCOPES) expect(debugEnabled(s)).toBe(false);
  });

  it('"1": every scope and unscoped on', () => {
    process.env.REDIACC_DEBUG = '1';
    expect(debugEnabled()).toBe(true);
    for (const s of SCOPES) expect(debugEnabled(s)).toBe(true);
  });

  it('"*": every scope and unscoped on', () => {
    process.env.REDIACC_DEBUG = '*';
    expect(debugEnabled()).toBe(true);
    for (const s of SCOPES) expect(debugEnabled(s)).toBe(true);
  });

  it('single scope "daemon": that scope on, others off, unscoped on', () => {
    process.env.REDIACC_DEBUG = 'daemon';
    expect(debugEnabled()).toBe(true); // any debug intent enables baseline logging
    expect(debugEnabled('daemon')).toBe(true);
    expect(debugEnabled('renet')).toBe(false);
    expect(debugEnabled('timing')).toBe(false);
    expect(debugEnabled('otel')).toBe(false);
  });

  it('comma list "daemon,timing": both listed on, others off', () => {
    process.env.REDIACC_DEBUG = 'daemon,timing';
    expect(debugEnabled()).toBe(true);
    expect(debugEnabled('daemon')).toBe(true);
    expect(debugEnabled('timing')).toBe(true);
    expect(debugEnabled('renet')).toBe(false);
    expect(debugEnabled('otel')).toBe(false);
  });

  it('single scope "renet": that scope on, others off', () => {
    process.env.REDIACC_DEBUG = 'renet';
    expect(debugEnabled('renet')).toBe(true);
    expect(debugEnabled('daemon')).toBe(false);
  });

  it('tolerates whitespace around scopes', () => {
    process.env.REDIACC_DEBUG = ' daemon , otel ';
    expect(debugEnabled('daemon')).toBe(true);
    expect(debugEnabled('otel')).toBe(true);
    expect(debugEnabled('renet')).toBe(false);
  });
});
