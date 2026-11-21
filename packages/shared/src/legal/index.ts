/**
 * The legal module: the contracting entity, the document versions and the consent notices
 * (agent/plans/PLAN-terms-acceptance.md Design 2). Server, portal and CLI read these, never a
 * copy, so the version a user accepts and the version a server requires are one value.
 *
 * Sources: `entity.generated.ts` (`./run.sh legal-entity sync`), `documents.generated.ts` and
 * `consent.generated.ts` (`npx tsx scripts/gen/gen-legal.ts --write`).
 */
import { WK_SITE_ORIGIN } from '../config/well-known.generated.js';
import type { SupportedLanguage } from '../i18n/types.js';
import { CONSENT_NOTICE_SHA256, CONSENT_NOTICES } from './consent.generated.js';
import { LEGAL_DOCUMENTS } from './documents.generated.js';
import type { AcceptanceMethod, LegalDocumentId, LegalDocumentVersion } from './types.js';

export { CONSENT_NOTICE_SHA256, CONSENT_NOTICES } from './consent.generated.js';
export { LEGAL_DOCUMENTS } from './documents.generated.js';
export { LEGAL_ENTITY, type LegalEntity } from './entity.generated.js';
export {
  ACCEPTANCE_METHODS,
  type AcceptanceMethod,
  type ConsentNotices,
  LEGAL_DOCUMENT_IDS,
  type LegalDocument,
  type LegalDocumentId,
  type LegalDocumentVersion,
} from './types.js';

/** Where the documents live. The English page is the binding one. */
export const LEGAL_URLS = {
  site: WK_SITE_ORIGIN,
  archiveBase: `${WK_SITE_ORIGIN}/legal/archive/`,
  terms: `${WK_SITE_ORIGIN}/en/terms-of-service`,
  privacy: `${WK_SITE_ORIGIN}/en/privacy-policy`,
  /** A document's page in one language. */
  documentUrl(page: string, lang: SupportedLanguage = 'en'): string {
    return `${WK_SITE_ORIGIN}/${lang}/${page}`;
  },
} as const;

/** The versions of a document, oldest first. */
export function documentVersions(id: LegalDocumentId): readonly LegalDocumentVersion[] {
  const doc = LEGAL_DOCUMENTS[id];
  if (!doc || doc.versions.length === 0) {
    throw new Error(`legal: ${id} has no version in .ci/config/legal-documents.json`);
  }
  return doc.versions;
}

function utcDate(now: Date): string {
  return now.toISOString().slice(0, 10);
}

export interface TermsState {
  /** The newest version in force at `now` (the oldest version when none is in force yet). */
  readonly current: LegalDocumentVersion;
  /** The newest MATERIAL version whose effective date is still ahead of `now`: the notice window. */
  readonly upcoming?: LegalDocumentVersion;
  /** The newest version declared, in force or not. */
  readonly latest: LegalDocumentVersion;
}

/** The Terms of Service at an instant. */
export function termsAt(
  now: Date,
  versions: readonly LegalDocumentVersion[] = documentVersions('terms-of-service')
): TermsState {
  const today = utcDate(now);
  const inForce = versions.filter((v) => v.effective <= today);
  const current = inForce.length > 0 ? inForce[inForce.length - 1] : versions[0];
  const ahead = versions.filter((v) => v.material && v.effective > today);
  const upcoming = ahead.length > 0 ? ahead[ahead.length - 1] : undefined;
  const latest = versions[versions.length - 1];
  return upcoming ? { current, upcoming, latest } : { current, latest };
}

/**
 * Whether an acceptance of `acceptedVersion` satisfies `required`: true when the accepted version
 * is the latest MATERIAL version at or before `required`, or a later one. A non-material version
 * (a typo fix) never asks anyone again. An accepted version the manifest does not declare
 * satisfies nothing.
 */
export function satisfies(
  acceptedVersion: string,
  required: string,
  versions: readonly LegalDocumentVersion[] = documentVersions('terms-of-service')
): boolean {
  if (!versions.some((v) => v.version === acceptedVersion)) return false;
  const material = versions.filter((v) => v.material && v.version <= required);
  if (material.length === 0) return true;
  return acceptedVersion >= material[material.length - 1].version;
}

/** The canonical notice text shown for `method` in `locale`; '' when no catalog carries it yet. */
export function consentNotice(method: AcceptanceMethod, locale: SupportedLanguage): string {
  return CONSENT_NOTICES[locale][method];
}

/** sha256 (hex, UTF-8) of the canonical notice for `method` in `locale`; '' when the notice is empty. */
export function noticeSha256(method: AcceptanceMethod, locale: SupportedLanguage): string {
  return CONSENT_NOTICE_SHA256[locale][method];
}
