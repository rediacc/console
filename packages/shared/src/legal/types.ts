/**
 * Types of the legal module (agent/plans/PLAN-terms-acceptance.md Design 2).
 *
 * The generated modules (`documents.generated.ts`, `consent.generated.ts`) are typed by these,
 * so a generator bug that drops a field is a type error rather than a silent blank.
 */
import type { SupportedLanguage } from '../i18n/types.js';

/** The documents `.ci/config/legal-documents.json` versions. Only `terms-of-service` drives assent. */
export const LEGAL_DOCUMENT_IDS = [
  'terms-of-service',
  'privacy-policy',
  'acceptable-use-policy',
  'data-processing-agreement',
  'service-level-agreement',
  'enterprise-license',
] as const;
export type LegalDocumentId = (typeof LEGAL_DOCUMENT_IDS)[number];

/** How an acceptance was given. Each method has one consent notice per locale. */
export const ACCEPTANCE_METHODS = [
  'web-checkbox',
  'cli-prompt',
  'cli-flag-unattended',
  'stripe-checkout',
] as const;
export type AcceptanceMethod = (typeof ACCEPTANCE_METHODS)[number];

/** One published version of a document. `version` and `effective` are UTC dates, YYYY-MM-DD. */
export interface LegalDocumentVersion {
  readonly version: string;
  readonly effective: string;
  readonly material: boolean;
  /** sha256 of the canonical English text, which is also the archive file's sha256. */
  readonly sha256: string;
  /** Where the immutable canonical text of this version is served. */
  readonly archiveUrl: string;
}

/** The versions of one document, oldest first. */
export interface LegalDocument {
  readonly id: LegalDocumentId;
  /** The www page slug: `/<lang>/<page>`. */
  readonly page: string;
  readonly versions: readonly LegalDocumentVersion[];
}

/** One string per locale and acceptance method: the consent notices, or their sha256. */
export interface ConsentNotices
  extends Readonly<Record<SupportedLanguage, Readonly<Record<AcceptanceMethod, string>>>> {}
