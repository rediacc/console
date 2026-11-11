/**
 * The legal pages that render through `LegalDocument.astro`, by their key under `pages.`.
 *
 * The list types the component's `pageKey` prop, so a page passing a key that is not here fails
 * the type check instead of rendering a bare key at build time.
 */
export const LEGAL_PAGES = [
  "termsOfService",
  "privacyPolicy",
  "acceptableUsePolicy",
  "dataProcessingAgreement",
  "serviceLevelAgreement",
  "enterpriseLicense",
  "refundPolicy",
  "cookiePolicy",
  "telemetryPolicy",
] as const;

export type LegalPage = (typeof LEGAL_PAGES)[number];

/** Translation root of a legal page, for example `pages.termsOfService`. */
export type LegalPageKey = `pages.${LegalPage}`;

/** `pages.termsOfService` becomes `termsOfService`; a key outside the list throws. */
export function legalPageName(key: LegalPageKey): LegalPage {
  const name = key.slice("pages.".length);
  if (!(LEGAL_PAGES as readonly string[]).includes(name)) {
    throw new Error(
      `${key} is not a legal page; add it to LEGAL_PAGES in legal-pages.ts`,
    );
  }
  return name as LegalPage;
}
