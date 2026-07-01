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
 * 10 languages Qwen3-TTS can voice. Bucket keys and hashes are tracked in
 * `src/data/video-manifest.json`. The 3 remaining site locales (ar/et/tr) have no
 * localized video and fall back to `en` here at render time, so we never duplicate the
 * English files.
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
export const VIDEO_LANGS = ['en', 'de', 'es', 'fr', 'it', 'pt', 'ru', 'ja', 'ko', 'zh'] as const;

export type VideoLang = (typeof VIDEO_LANGS)[number];

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
  const path = manifest.solutions[slug]?.[lang]?.[field]?.path;
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
