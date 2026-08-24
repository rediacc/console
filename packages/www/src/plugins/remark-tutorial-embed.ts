/**
 * Remark plugin to embed the tutorial video player from markdown image syntax.
 *
 * Transforms image references with .cast extensions into the
 * `.tutorial-video-container` placeholder div that
 * `scripts/tutorial-video-hydrate.ts` mounts as `TutorialVideoPlayer`.
 *
 * Example:
 *   Input:  ![Tutorial: rdc ops](/assets/tutorials/ops-tutorial.cast)
 *   Output: <div class="tutorial-video-container" data-video-src=".../ops-tutorial.mp4" data-poster-src=".../ops-tutorial.en.poster.jpg" data-subtitles-src=".../ops-tutorial.en.vtt" data-chapters-src=".../ops-tutorial.en.chapters.vtt" data-words-src=".../ops-tutorial.en.words.json" data-sources='{"en":{...},"de":{...}}' data-title="..." data-lang="en"></div>
 */

import path from 'node:path';
import process from 'node:process';
import { SITE_LOCALES } from '@rediacc/locales';
import { DEFAULTS_EXTENDED } from '@rediacc/shared/config/defaults';
import type { Image, Paragraph, Root } from 'mdast';
import type { Node, Parent } from 'unist';
import { SKIP, visit } from 'unist-util-visit';
import type { VFile } from 'vfile';
import { asSparse, loadManifest } from '../../scripts/lib/update-video-manifest.ts';

type TutorialField = 'mp4' | 'poster' | 'vtt' | 'chaptersVtt' | 'wordsJson';

/**
 * CDN base URL for published videos (Cloudflare R2 + media.rediacc.com).
 * Read via process.env, not import.meta.env: this remark plugin runs at
 * build time and import.meta.env is only populated under Vite.
 */
const VIDEO_CDN_BASE_URL = process.env.PUBLIC_VIDEO_CDN_BASE_URL ?? '';

function isCastUrl(url: string): boolean {
  return path.extname(url).toLowerCase() === '.cast';
}

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function langFromFilePath(filePath: string | undefined): string {
  if (!filePath) return 'en';
  // Astro content paths look like .../src/content/docs/<lang>/<slug>.md(x)
  const m = /\/content\/docs\/([a-z]{2})(?:-[a-z]{2})?\//i.exec(filePath);
  return m ? m[1].toLowerCase() : 'en';
}

/**
 * `loadManifest()` re-reads and re-parses the 448 KB manifest on every call, and this
 * plugin now asks it for 5 fields x 13 locales per embed across 234 tutorial pages. One
 * read per build process is enough: the file is a committed build input that nothing
 * mutates while Astro is running.
 */
let manifestMemo: ReturnType<typeof asSparse> | null = null;
function manifest(): ReturnType<typeof asSparse> {
  manifestMemo ??= asSparse(loadManifest());
  return manifestMemo;
}

/**
 * The locales this cast is actually published in, in SITE_LOCALES order.
 *
 * Derived from the manifest rather than assumed, so a cast that is mid-publish offers only
 * the languages that exist. An empty manifest (no CDN configured, or a fresh checkout
 * before the first publish) falls back to the full site set, which is what the local
 * `/assets/tutorials/video/<lang>/...` paths below serve.
 */
function localesFor(castKey: string): string[] {
  const published = manifest().tutorials?.[castKey];
  if (!published) return [...SITE_LOCALES];
  const found = SITE_LOCALES.filter((l) => published[l]?.mp4?.path);
  return found.length > 0 ? [...found] : [...SITE_LOCALES];
}

function resolveUrl(castKey: string, lang: string, field: TutorialField): string {
  const localFallback: Record<TutorialField, string> = {
    mp4: `/assets/tutorials/video/${lang}/${castKey}.mp4`,
    poster: `/assets/tutorials/video/${lang}/${castKey}.${lang}.poster.jpg`,
    vtt: `/assets/tutorials/video/${lang}/${castKey}.${lang}.vtt`,
    chaptersVtt: `/assets/tutorials/video/${lang}/${castKey}.${lang}.chapters.vtt`,
    wordsJson: `/assets/tutorials/video/${lang}/${castKey}.${lang}.words.json`,
  };
  if (!VIDEO_CDN_BASE_URL) return localFallback[field];

  // asSparse + optional chaining, because every level here is SPARSE at read
  // time: a cast key, a locale under it, or a single field can each be absent
  // while that locale is still being published. VideoManifest describes what a
  // WRITER produces, so its levels are total, and trusting that made all three
  // index accesses look infallible to TypeScript while the runtime still
  // returned undefined -- so `if (!assetPath)` could never run, because the
  // expression above it threw first.
  //
  // src/utils/solution-video.ts already carries a comment saying this exact
  // crash "failed the whole CDN build rather than degrading one player". The
  // fix was applied there and never swept to here.
  const assetPath = manifest().tutorials?.[castKey]?.[lang]?.[field]?.path;
  if (!assetPath) return localFallback[field];

  return `${VIDEO_CDN_BASE_URL}/${assetPath}`;
}

/**
 * The per-locale source sets handed to the player's language picker.
 *
 * Emitted as ONE `data-sources` attribute rather than shipping
 * `src/data/video-manifest.json` to the browser: the manifest is 448 KB and describes
 * every cast and every solution video, where a player needs 13 x 5 URLs for its own cast.
 */
function buildSources(castKey: string): Record<string, Record<string, string>> {
  const out: Record<string, Record<string, string>> = {};
  for (const l of localesFor(castKey)) {
    out[l] = {
      mp4: resolveUrl(castKey, l, 'mp4'),
      poster: resolveUrl(castKey, l, 'poster'),
      vtt: resolveUrl(castKey, l, 'vtt'),
      chapters: resolveUrl(castKey, l, 'chaptersVtt'),
      words: resolveUrl(castKey, l, 'wordsJson'),
    };
  }
  return out;
}

function buildVideoContainerHtml(castUrl: string, lang: string, title: string): string {
  const castKey = path.basename(castUrl, '.cast');
  return [
    '<div class="tutorial-video-container"',
    ` data-video-src="${escapeHtml(resolveUrl(castKey, lang, 'mp4'))}"`,
    ` data-poster-src="${escapeHtml(resolveUrl(castKey, lang, 'poster'))}"`,
    ` data-subtitles-src="${escapeHtml(resolveUrl(castKey, lang, 'vtt'))}"`,
    ` data-chapters-src="${escapeHtml(resolveUrl(castKey, lang, 'chaptersVtt'))}"`,
    ` data-words-src="${escapeHtml(resolveUrl(castKey, lang, 'wordsJson'))}"`,
    ` data-sources="${escapeHtml(JSON.stringify(buildSources(castKey)))}"`,
    ` data-title="${escapeHtml(title)}"`,
    ` data-lang="${escapeHtml(lang)}"`,
    // The language picker renders INSIDE the player frame, the same as on the solution
    // heroes. It does not touch Plyr's settings menu at all (that pane plays a language
    // nobody chose; see the Plyr config comment in TutorialVideoPlayer), so it does not
    // interact with the captions menu these embeds do have.
    ' data-in-player-language="true"',
    '></div>',
  ].join('');
}

export function remarkTutorialEmbed() {
  return function transformer(tree: Root, file: VFile) {
    const lang = langFromFilePath(file.path);

    visit(tree, 'paragraph', (node: Paragraph, index, parent) => {
      if (index === undefined || !parent) return;

      const imageIndex = node.children.findIndex(
        (child): child is Image => child.type === 'image' && isCastUrl(child.url)
      );

      if (imageIndex === -1) return;

      const imageNode = node.children[imageIndex] as Image;
      const title = imageNode.alt ?? DEFAULTS_EXTENDED.WWW.TUTORIAL_TITLE;
      const html = buildVideoContainerHtml(imageNode.url, lang, title);

      (parent as Parent).children.splice(index, 1, {
        type: 'html',
        value: html,
      } as Node);

      return [SKIP, index] as const;
    });
  };
}
