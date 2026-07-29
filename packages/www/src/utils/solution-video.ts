import process from 'node:process';
import { loadManifest } from '../../scripts/lib/update-video-manifest.ts';
import type { Language } from '../i18n/types';

/**
 * CDN base URL for published videos (Cloudflare R2 + media.rediacc.com).
 * Read via process.env, not import.meta.env: this module is imported by
 * plain-tsx CI gate scripts (check-solution-videos.ts) as well as Astro
 * components, and import.meta.env is only populated under Vite.
 */
const VIDEO_CDN_BASE_URL = process.env.PUBLIC_VIDEO_CDN_BASE_URL ?? '';

/**
 * Resolve a solution-page video to the right per-language files.
 *
 * Localized videos are published to Cloudflare R2 (`videos/solutions/<lang>/<slug>.mp4`
 * + `.vertical.mp4`, `.poster.jpg`) by the pipeline's `--publish-www` command, for the
 * 11 languages the TTS pipeline can voice with a native narrator. Bucket keys and hashes
 * are tracked in `src/data/video-manifest.json`. The 2 remaining site locales (ar/et) have
 * no localized video and fall back to `en` here at render time, so we never duplicate the
 * English files. Estonian is PERMANENT fallback: it appears in no supported-language list
 * of any model in the stack. Arabic is pending a narrator a fluent speaker has approved.
 *
 * WHY a constant lang-set (not derived from the manifest):
 *   Completeness (every slug × every VIDEO_LANG present in the manifest) is GUARANTEED
 *   by the hard-fail CI gate `packages/www/scripts/check-solution-videos.ts`, so the
 *   resolver can assume presence and doesn't need to derive the set dynamically.
 *
 * URL base: `VIDEO_CDN_BASE_URL` (from `PUBLIC_VIDEO_CDN_BASE_URL`, see config/constants.ts).
 * Empty (unset) falls back to the local `/assets/videos/solutions/...` path so a
 * developer previewing a freshly-generated-but-not-yet-published local file still works.
 */
export const VIDEO_LANGS = [
  'en',
  'de',
  'es',
  'fr',
  'it',
  'pt',
  'ru',
  'ja',
  'ko',
  'tr',
  'zh',
] as const;

type VideoLang = (typeof VIDEO_LANGS)[number];

export interface SolutionVideo {
  landscape: string;
  vertical: string;
  poster: string;
  /** The language actually used (the request, or 'en' for ar/et/tr fallback). */
  lang: VideoLang;
}

function resolveUrl(slug: string, lang: VideoLang, field: 'mp4' | 'vertical' | 'poster'): string {
  const localFallback: Record<typeof field, string> = {
    mp4: `/assets/videos/solutions/${lang}/${slug}.mp4`,
    vertical: `/assets/videos/solutions/${lang}/${slug}.vertical.mp4`,
    poster: `/assets/videos/solutions/${lang}/${slug}.poster.jpg`,
  };
  if (!VIDEO_CDN_BASE_URL) return localFallback[field];

  const manifest = loadManifest();
  // VideoManifest types every level as Record<string, …>, so without
  // noUncheckedIndexedAccess TypeScript believes each index access always
  // resolves. It does not: a slug absent from the manifest yields undefined and
  // used to throw here ("Cannot read properties of undefined"), failing the
  // whole CDN build rather than degrading one player. Widening to admit
  // undefined (a plain assignment — Record<string, T> is assignable to
  // Record<string, T | undefined>, no cast needed) makes the lookup honest and
  // the optional chaining below genuinely load-bearing.
  //
  // A page can legitimately render the video section before its videos are
  // published; check-solution-videos.ts is the gate that catches that, and this
  // path must not become a second, louder one.
  const solutions: Record<
    string,
    Record<string, Record<string, { path?: string } | undefined> | undefined> | undefined
  > = manifest.solutions;
  const path = solutions[slug]?.[lang]?.[field]?.path;
  if (!path) return localFallback[field];

  return `${VIDEO_CDN_BASE_URL}/${path}`;
}

export function resolveSolutionVideo(slug: string, lang: Language): SolutionVideo {
  const used: VideoLang = (VIDEO_LANGS as readonly string[]).includes(lang)
    ? (lang as VideoLang)
    : 'en'; // ar / et / tr -> English video
  return {
    landscape: resolveUrl(slug, used, 'mp4'),
    vertical: resolveUrl(slug, used, 'vertical'),
    poster: resolveUrl(slug, used, 'poster'),
    lang: used,
  };
}
