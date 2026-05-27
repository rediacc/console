import type { ImageMetadata } from 'astro';
import type { Language } from '../i18n/types';

/**
 * Resolve a solution-page illustration to the right per-language SVG.
 *
 * Localized illustrations are named `<slug>.<lang>.svg` (+ `.mobile`); English
 * stays as the flat `<slug>.svg`. We eager-glob every SVG in the illustrations
 * directory (build-time, content-hashed by Astro — no runtime fetch) and pick
 * by key with a fallback chain: requested-lang → English flat → null.
 *
 * Mirrors the per-language asset lookup in `tutorial-audio.ts`.
 */
const illustrationModules = import.meta.glob<{ default: ImageMetadata }>(
  '../assets/images/illustrations/*.svg',
  { eager: true }
  // Index access on a glob record is `T` per TS, but a missing key is
  // `undefined` at runtime — widen so the optional-chain fallback is sound.
) as Record<string, { default: ImageMetadata } | undefined>;

const BASE = '../assets/images/illustrations';

function pick(slug: string, lang: Language, mobile: boolean): ImageMetadata | null {
  const suffix = mobile ? '.mobile' : '';
  const langKey = `${BASE}/${slug}.${lang}${suffix}.svg`;
  const flatKey = `${BASE}/${slug}${suffix}.svg`;
  return illustrationModules[langKey]?.default ?? illustrationModules[flatKey]?.default ?? null;
}

export function resolveSolutionIllustration(
  slug: string,
  lang: Language
): { landscape: ImageMetadata | null; mobile: ImageMetadata | null } {
  return { landscape: pick(slug, lang, false), mobile: pick(slug, lang, true) };
}
