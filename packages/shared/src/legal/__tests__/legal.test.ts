import { describe, expect, it } from 'vitest';
import { SUPPORTED_LANGUAGES } from '../../i18n/types.js';
import {
  ACCEPTANCE_METHODS,
  CONSENT_NOTICES,
  documentVersions,
  LEGAL_DOCUMENTS,
  LEGAL_ENTITY,
  LEGAL_URLS,
  type LegalDocumentVersion,
  noticeSha256,
  satisfies,
  termsAt,
} from '../index.js';

const v = (version: string, effective: string, material: boolean): LegalDocumentVersion => ({
  version,
  effective,
  material,
  sha256: version.replaceAll('-', ''),
  archiveUrl: `https://example.invalid/${version}.txt`,
});

// A material first version, a typo fix, a material rewrite, and a typo fix of the rewrite.
const VERSIONS = [
  v('2026-03-15', '2026-03-15', true),
  v('2026-04-01', '2026-04-01', false),
  v('2026-06-01', '2026-07-01', true),
  v('2026-06-10', '2026-07-01', false),
];

describe('satisfies', () => {
  it('a typo fix never asks again: the first material version satisfies a later non-material one', () => {
    expect(satisfies('2026-03-15', '2026-04-01', VERSIONS)).toBe(true);
    expect(satisfies('2026-04-01', '2026-04-01', VERSIONS)).toBe(true);
  });

  it('a material version demands itself or a later one', () => {
    expect(satisfies('2026-03-15', '2026-06-01', VERSIONS)).toBe(false);
    expect(satisfies('2026-04-01', '2026-06-01', VERSIONS)).toBe(false);
    expect(satisfies('2026-06-01', '2026-06-01', VERSIONS)).toBe(true);
    expect(satisfies('2026-06-10', '2026-06-01', VERSIONS)).toBe(true);
  });

  it('a non-material fix of a material version is satisfied by the material version', () => {
    expect(satisfies('2026-06-01', '2026-06-10', VERSIONS)).toBe(true);
    expect(satisfies('2026-04-01', '2026-06-10', VERSIONS)).toBe(false);
  });

  it('a version the manifest does not declare satisfies nothing', () => {
    expect(satisfies('2027-01-01', '2026-03-15', VERSIONS)).toBe(false);
    expect(satisfies('', '2026-03-15', VERSIONS)).toBe(false);
  });
});

describe('termsAt', () => {
  it('before a material version is effective it is upcoming, and the previous one is current', () => {
    const state = termsAt(new Date('2026-06-15T12:00:00Z'), VERSIONS);
    expect(state.current.version).toBe('2026-04-01');
    expect(state.upcoming?.version).toBe('2026-06-01');
    expect(state.latest.version).toBe('2026-06-10');
  });

  it('on the effective date the material version is current and nothing is upcoming', () => {
    const state = termsAt(new Date('2026-07-01T00:00:00Z'), VERSIONS);
    expect(state.current.version).toBe('2026-06-10');
    expect(state.upcoming).toBeUndefined();
  });

  it('reads the real manifest: the Terms of Service has a version in force today', () => {
    const versions = documentVersions('terms-of-service');
    expect(versions[0].version).toBe('2026-03-15');
    expect(versions[0].sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(versions[0].archiveUrl).toBe(`${LEGAL_URLS.archiveBase}terms-of-service-2026-03-15.txt`);
    const state = termsAt(new Date());
    expect(state.latest).toBe(versions[versions.length - 1]);
  });
});

describe('the generated modules', () => {
  it('every locale carries every acceptance method, and an empty notice has an empty hash', () => {
    expect(Object.keys(CONSENT_NOTICES)).toEqual([...SUPPORTED_LANGUAGES]);
    for (const locale of SUPPORTED_LANGUAGES) {
      expect(Object.keys(CONSENT_NOTICES[locale])).toEqual([...ACCEPTANCE_METHODS]);
      for (const method of ACCEPTANCE_METHODS) {
        const text = CONSENT_NOTICES[locale][method];
        expect(noticeSha256(method, locale)).toMatch(text ? /^[0-9a-f]{64}$/ : /^$/);
      }
    }
  });

  it('the entity projection carries no licensor and the documents carry the terms', () => {
    expect(LEGAL_ENTITY).not.toHaveProperty('licensorName');
    expect(LEGAL_ENTITY.countryCode).toMatch(/^[A-Z]{2}$/);
    expect(LEGAL_DOCUMENTS['terms-of-service']?.page).toBe('terms-of-service');
  });
});
