import { SITE_LOCALES } from '@rediacc/locales';
import { loadManifest } from '../../scripts/lib/update-video-manifest.ts';
import { cdnBaseUrl, resolveMediaUrl } from './media-url.ts';

/**
 * Resolve a solution-page video to the right per-language files.
 *
 * Localized videos are published to Cloudflare R2 (`videos/solutions/<lang>/<slug>.mp4`
 * + `.vertical.mp4`, `.poster.jpg`) by the pipeline's `--publish-www` command, for the
 * all 13 site locales, each with its own native narrator. Bucket keys and hashes are
 * tracked in `src/data/video-manifest.json`. Nothing falls back to English any more:
 * VoxCPM2 voices every locale including Estonian, which no other model in the stack
 * supports. Estonian's CAPTIONS remain estimated rather than force-aligned — that is a
 * caption-precision caveat, not an audio one.
 *
 * WHY a constant lang-set (not derived from the manifest):
 *   Completeness (every slug × every VIDEO_LANG present in the manifest) is GUARANTEED
 *   by the hard-fail CI gate `packages/www/scripts/check-solution-videos.ts`, so the
 *   resolver can assume presence and doesn't need to derive the set dynamically.
 *
 * URL choice is LOCAL FIRST (see `media-url.ts`): a file checked out under
 * `public/assets/videos/solutions/...` wins, so a developer previewing a
 * freshly-generated-but-not-yet-published render sees it; anything else is served from
 * the CDN named by the manifest's `baseUrl` (`PUBLIC_VIDEO_CDN_BASE_URL` overrides it).
 */
export const VIDEO_LANGS = SITE_LOCALES;

type VideoLang = (typeof VIDEO_LANGS)[number];

/** The three files one locale's solution video is made of. */
export interface SolutionVideoUrls {
  landscape: string;
  vertical: string;
  poster: string;
}

/**
 * `loadManifest()` re-reads and re-parses the 448 KB manifest on EVERY call, with no cache
 * of its own. Resolving one page used to cost 3 of those; offering all thirteen languages
 * to the picker costs 39, on each of 21 solutions x 13 locales. One parse per build process
 * is enough: the manifest is a committed build input and nothing rewrites it mid-build.
 */
let manifestMemo: ReturnType<typeof loadManifest> | null = null;
function manifest(): ReturnType<typeof loadManifest> {
  manifestMemo ??= loadManifest();
  return manifestMemo;
}

function resolveUrl(slug: string, lang: VideoLang, field: 'mp4' | 'vertical' | 'poster'): string {
  // The bucket key is the local path minus `/assets/`: generate-video-manifest.ts writes `videos/solutions/<lang>/<file>` and the pipeline mirrors that layout into `public/`. Deriving the key by convention keeps a slug the manifest has not recorded yet on the URL it WILL have once published, instead of a local path that 404s.
  const fileName: Record<typeof field, string> = {
    mp4: `${slug}.mp4`,
    vertical: `${slug}.vertical.mp4`,
    poster: `${slug}.poster.jpg`,
  };
  const conventionalKey = `videos/solutions/${lang}/${fileName[field]}`;
  const localPath = `/assets/${conventionalKey}`;

  // VideoManifest types every level as Record<string, …>, so without noUncheckedIndexedAccess TypeScript believes each index access always resolves. It does not: a slug absent from the manifest yields undefined and used to throw here ("Cannot read properties of undefined"), failing the whole CDN build rather than degrading one player. Widening to admit undefined (a plain
  // assignment — Record<string, T> is assignable to Record<string, T | undefined>, no cast needed) makes the lookup honest and the optional chaining below genuinely load-bearing.
  //
  // A page can legitimately render the video section before its videos are published; check-solution-videos.ts is the gate that catches that, and this path must not become a second, louder one.
  const solutions: Record<
    string,
    Record<string, Record<string, { path?: string } | undefined> | undefined> | undefined
  > = manifest().solutions;
  const manifestKey = solutions[slug]?.[lang]?.[field]?.path;

  return resolveMediaUrl({
    localPath,
    cdnKey: manifestKey ?? conventionalKey,
    cdnBase: cdnBaseUrl(manifest().baseUrl),
  });
}

/**
 * Every language this solution's video is published in, as a picker-ready map.
 *
 * Built at BUILD time and handed to the island as one prop, because
 * `src/data/video-manifest.json` is 448 KB and covers every slug and every tutorial: a page
 * needs 13 x 3 URLs for its own video and nothing else.
 *
 * The set is read off the manifest rather than assumed, so a slug published in nine locales
 * offers nine. An empty manifest (fresh checkout, no publish yet) falls back to VIDEO_LANGS;
 * each of those then resolves local-first, CDN otherwise, like every other language.
 */
export function resolveSolutionVideoSources(slug: string): Record<string, SolutionVideoUrls> {
  const solutions: Record<string, Record<string, unknown> | undefined> = manifest().solutions;
  const published = solutions[slug];
  const langs = published
    ? VIDEO_LANGS.filter((l) => Boolean(published[l]))
    : ([...VIDEO_LANGS] as VideoLang[]);
  const use = langs.length > 0 ? langs : ([...VIDEO_LANGS] as VideoLang[]);

  const out: Record<string, SolutionVideoUrls> = {};
  for (const l of use) {
    out[l] = {
      landscape: resolveUrl(slug, l, 'mp4'),
      vertical: resolveUrl(slug, l, 'vertical'),
      poster: resolveUrl(slug, l, 'poster'),
    };
  }
  return out;
}
