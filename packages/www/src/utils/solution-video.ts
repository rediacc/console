import type { Language } from '../i18n/types';

/**
 * Resolve a solution-page video to the right per-language files.
 *
 * Localized videos are committed under
 * `public/assets/videos/solutions/<lang>/<slug>.mp4` (+ `.vertical.mp4`, `.poster.jpg`)
 * by the pipeline's `--publish-www` command, for the 10 languages Qwen3-TTS can voice.
 * The 3 remaining site locales (ar/et/tr) have no localized video and fall back to `en`
 * here at render time, so we never duplicate the English files on disk.
 *
 * WHY a constant lang-set (not a manifest, not `import.meta.glob`):
 *   - `import.meta.glob` only sees `src/`, never `public/`; and routing ~3.6GB of video
 *     through Astro's asset pipeline would blow up the build. Videos must live in `public/`
 *     and be referenced by URL.
 *   - A constant set is the simplest source of truth. Completeness (every slug × every
 *     VIDEO_LANG present) is GUARANTEED by the hard-fail CI gate
 *     `packages/www/scripts/check-solution-videos.ts`, so the resolver can assume presence.
 *   - If we ever ship partial localizations, switch to a generated manifest written by
 *     `--publish-www`; until then a manifest would just be a second source of truth to drift.
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

export function resolveSolutionVideo(slug: string, lang: Language): SolutionVideo {
  const used: VideoLang = (VIDEO_LANGS as readonly string[]).includes(lang)
    ? (lang as VideoLang)
    : 'en'; // ar / et / tr -> English video
  const base = `/assets/videos/solutions/${used}/${slug}`;
  return {
    landscape: `${base}.mp4`,
    vertical: `${base}.vertical.mp4`,
    poster: `${base}.poster.jpg`,
    lang: used,
  };
}
