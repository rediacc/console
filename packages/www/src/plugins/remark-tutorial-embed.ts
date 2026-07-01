/**
 * Remark plugin to embed the tutorial video player from markdown image syntax.
 *
 * Transforms image references with .cast extensions into the
 * `.tutorial-video-container` placeholder div that
 * `scripts/tutorial-video-hydrate.ts` mounts as `TutorialVideoPlayer`.
 *
 * Example:
 *   Input:  ![Tutorial: rdc ops](/assets/tutorials/ops-tutorial.cast)
 *   Output: <div class="tutorial-video-container" data-video-src=".../ops-tutorial.mp4" data-poster-src=".../ops-tutorial.en.poster.jpg" data-subtitles-src=".../ops-tutorial.en.vtt" data-chapters-src=".../ops-tutorial.en.chapters.vtt" data-words-src=".../ops-tutorial.en.words.json" data-title="..." data-lang="en"></div>
 */

import path from 'node:path';
import process from 'node:process';
import { DEFAULTS_EXTENDED } from '@rediacc/shared/config/defaults';
import type { Image, Paragraph, Root } from 'mdast';
import type { Node, Parent } from 'unist';
import { SKIP, visit } from 'unist-util-visit';
import type { VFile } from 'vfile';
import { loadManifest } from '../../scripts/lib/update-video-manifest.ts';

const TUTORIAL_FIELDS = ['mp4', 'poster', 'vtt', 'chaptersVtt', 'wordsJson'] as const;
type TutorialField = (typeof TUTORIAL_FIELDS)[number];

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

function resolveUrl(castKey: string, lang: string, field: TutorialField): string {
  const localFallback: Record<TutorialField, string> = {
    mp4: `/assets/tutorials/video/${lang}/${castKey}.mp4`,
    poster: `/assets/tutorials/video/${lang}/${castKey}.${lang}.poster.jpg`,
    vtt: `/assets/tutorials/video/${lang}/${castKey}.${lang}.vtt`,
    chaptersVtt: `/assets/tutorials/video/${lang}/${castKey}.${lang}.chapters.vtt`,
    wordsJson: `/assets/tutorials/video/${lang}/${castKey}.${lang}.words.json`,
  };
  if (!VIDEO_CDN_BASE_URL) return localFallback[field];

  const manifest = loadManifest();
  const assetPath = manifest.tutorials[castKey]?.[lang]?.[field]?.path;
  if (!assetPath) return localFallback[field];

  return `${VIDEO_CDN_BASE_URL}/${assetPath}`;
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
    ` data-title="${escapeHtml(title)}"`,
    ` data-lang="${escapeHtml(lang)}"`,
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
