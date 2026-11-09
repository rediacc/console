import { BAKED_IN_REGIONS } from '@rediacc/shared/regions';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Region } from '../../config/regions';
import {
  createPickTracker,
  extractDomain,
  modeFromPath,
  openPhase,
  parseLookupHost,
  preselectFromGeo,
  regionForCountry,
  regionForTimeZone,
} from '../RegionPickerModal';

const regions: Region[] = BAKED_IN_REGIONS;

describe('modeFromPath', () => {
  it.each([
    ['/account/', 'login'],
    ['/account', 'login'],
    ['/account/login', 'login'],
    ['/account/?returnUrl=https%3A%2F%2Fwww.rediacc.com%2F', 'login'],
    ['/account/?checkout=PROFESSIONAL&period=monthly', 'signup'],
    ['/account/signup', 'signup'],
    ['/account/register?x=1', 'signup'],
    ['/account/signupfoo', 'login'],
  ] as const)('%s -> %s', (path, mode) => {
    expect(modeFromPath(path)).toBe(mode);
  });
});

describe('regionForCountry', () => {
  it.each([
    ['DE', 'eu'],
    ['gb', 'eu'],
    ['ZA', 'eu'],
    ['US', 'us'],
    ['BR', 'us'],
    ['CA', 'us'],
    ['JP', 'asia'],
    ['AU', 'asia'],
    ['IN', 'asia'],
  ] as const)('%s -> %s', (country, id) => {
    expect(regionForCountry(regions, country)?.id).toBe(id);
  });

  it('answers null for a missing or malformed country so the time zone decides', () => {
    expect(regionForCountry(regions, null)).toBeNull();
    expect(regionForCountry(regions, undefined)).toBeNull();
    expect(regionForCountry(regions, '')).toBeNull();
    expect(regionForCountry(regions, 'XXX')).toBeNull();
  });
});

describe('regionForTimeZone', () => {
  it('maps zone prefixes and falls back to the default region', () => {
    expect(regionForTimeZone(regions, 'Europe/Berlin').id).toBe('eu');
    expect(regionForTimeZone(regions, 'America/New_York').id).toBe('us');
    expect(regionForTimeZone(regions, 'Asia/Tokyo').id).toBe('asia');
    expect(regionForTimeZone(regions, 'UTC').id).toBe('eu');
  });
});

describe('extractDomain', () => {
  it('keeps only the domain part of an address', () => {
    expect(extractDomain('Jane.Doe@Acme.Example')).toBe('acme.example');
    expect(extractDomain('  acme.example ')).toBe('acme.example');
    expect(extractDomain('a@b@acme.example')).toBe('acme.example');
  });

  it('refuses what is not a domain', () => {
    expect(extractDomain('')).toBeNull();
    expect(extractDomain('localhost')).toBeNull();
    expect(extractDomain('acme')).toBeNull();
    expect(extractDomain('jane@')).toBeNull();
    expect(extractDomain('acme.example/path')).toBeNull();
    expect(extractDomain('-acme.example')).toBeNull();
  });
});

describe('parseLookupHost', () => {
  it('accepts a host under the product domain', () => {
    expect(parseLookupHost({ host: 'acme.eu.rediacc.cloud' })).toBe('acme.eu.rediacc.cloud');
    expect(parseLookupHost({ host: 'ACME.eu.rediacc.cloud' })).toBe('acme.eu.rediacc.cloud');
  });

  it('treats a miss, a malformed answer and an off-site host alike', () => {
    expect(parseLookupHost({ host: null })).toBeNull();
    expect(parseLookupHost({})).toBeNull();
    expect(parseLookupHost(null)).toBeNull();
    expect(parseLookupHost('x')).toBeNull();
    expect(parseLookupHost({ host: 'evil.example' })).toBeNull();
    expect(parseLookupHost({ host: 'rediacc.cloud.evil.example' })).toBeNull();
    expect(parseLookupHost({ host: 'evilrediacc.cloud' })).toBeNull();
    expect(parseLookupHost({ host: 'a.rediacc.cloud/../x' })).toBeNull();
    expect(parseLookupHost({ host: 'a.rediacc.cloud:8080' })).toBeNull();
  });
});

describe('openPhase', () => {
  it('counts down for a login with a stored region and resolves geo without one', () => {
    expect(openPhase('login', true, false)).toBe('counting');
    expect(openPhase('login', false, false)).toBe('resolving');
  });

  it('shows the cards for sign-up', () => {
    expect(openPhase('signup', true, false)).toBe('choosing');
    expect(openPhase('signup', false, false)).toBe('choosing');
  });

  it('shows the cards for a forced open, so a stored region never forwards on its own', () => {
    expect(openPhase('login', true, true)).toBe('choosing');
    expect(openPhase('login', false, true)).toBe('choosing');
  });
});

describe('preselectFromGeo', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const stubGeo = (country: string | null, ok = true) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok, json: async () => ({ country }) }))
    );
  };
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('selects the geo region when none is stored and the run is current', async () => {
    stubGeo('DE');
    const select = vi.fn();
    preselectFromGeo(true, () => true, select);
    await settle();
    expect(select).toHaveBeenCalledWith('eu');
  });

  it('asks live when the answer arrives, so a visitor who chose a card meanwhile keeps it', async () => {
    stubGeo('DE');
    const select = vi.fn();
    let live = true;
    preselectFromGeo(true, () => live, select);
    live = false;
    await settle();
    expect(select).not.toHaveBeenCalled();
  });

  it('selects nothing when a region is stored, the run ended, or the lookup failed', async () => {
    const select = vi.fn();
    stubGeo('DE');
    preselectFromGeo(false, () => true, select);
    preselectFromGeo(true, () => false, select);
    stubGeo(null);
    preselectFromGeo(true, () => true, select);
    stubGeo('DE', false);
    preselectFromGeo(true, () => true, select);
    await settle();
    expect(select).not.toHaveBeenCalled();
  });
});

describe('createPickTracker', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is free until a card is picked, selects the picked card, and is free again after reset', () => {
    const tracker = createPickTracker();
    const select = vi.fn();
    expect(tracker.isFree()).toBe(true);
    tracker.pick('us', select);
    expect(select).toHaveBeenCalledWith('us');
    expect(tracker.isFree()).toBe(false);
    tracker.reset();
    expect(tracker.isFree()).toBe(true);
  });

  it('keeps a late /api/geo answer off a card the visitor picked, until the next open', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => ({ country: 'DE' }) }))
    );
    const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
    const tracker = createPickTracker();
    const select = vi.fn();
    preselectFromGeo(true, () => tracker.isFree(), select);
    tracker.pick('us', () => {});
    await settle();
    expect(select).not.toHaveBeenCalled();
    tracker.reset();
    preselectFromGeo(true, () => tracker.isFree(), select);
    await settle();
    expect(select).toHaveBeenCalledWith('eu');
  });
});
