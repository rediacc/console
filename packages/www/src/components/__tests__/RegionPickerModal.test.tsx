import { describe, expect, it } from 'vitest';
import type { Region } from '../../config/regions';
import {
  extractDomain,
  modeFromPath,
  parseLookupHost,
  regionForCountry,
  regionForTimeZone,
} from '../RegionPickerModal';

const regions: Region[] = [
  { id: 'eu', label: 'Europe', domain: 'eu.rediacc.cloud', default: true },
  { id: 'us', label: 'United States', domain: 'us.rediacc.cloud', default: false },
  { id: 'asia', label: 'Asia Pacific', domain: 'asia.rediacc.cloud', default: false },
];

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
