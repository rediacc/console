/**
 * Remark plugin to embed videos from markdown image syntax.
 *
 * Transforms image references with video file extensions (.webm, .mp4) into
 * HTML5 <video> elements. Video files are injected post-build by CI before
 * deployment, so the plugin always renders <video> tags unconditionally.
 *
 * Example:
 *   Input:  ![Registration walkthrough](/assets/videos/user-guide/01-01-registration.webm)
 *           *(Video: Complete registration flow)*
 *
 *   Output: <div class="video-container"><video ...>...</video><em>...</em></div>
 */

import path from 'node:path';
import type { Image, Paragraph, Root, Text } from 'mdast';
import type { Node, Parent } from 'unist';
import { SKIP, visit } from 'unist-util-visit';

const VIDEO_EXTENSIONS = ['.webm', '.mp4'] as const;

/**
 * Escape special HTML characters to prevent XSS in generated HTML
 */
function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function isVideoUrl(url: string): boolean {
  const ext = path.extname(url).toLowerCase();
  return (VIDEO_EXTENSIONS as readonly string[]).includes(ext);
}

function getVideoMimeType(url: string): string {
  return url.endsWith('.mp4') ? 'video/mp4' : 'video/webm';
}

/**
 * Extract caption text from emphasis nodes following the image in a paragraph.
 */
function extractCaption(paragraph: Paragraph, imageIndex: number): string | null {
  for (let i = imageIndex + 1; i < paragraph.children.length; i++) {
    const child = paragraph.children[i];
    if (child.type !== 'emphasis' || child.children.length === 0) continue;

    const textParts = child.children
      .filter((c): c is Text => c.type === 'text')
      .map((c) => c.value);

    if (textParts.length > 0) return textParts.join('');
  }
  return null;
}

function buildVideoHtml(url: string, alt: string, caption: string | null): string {
  const mimeType = getVideoMimeType(url);
  const escapedAlt = escapeHtml(alt);
  const captionHtml = caption ? `\n  <em>${escapeHtml(caption)}</em>` : '';

  return `<div class="video-container">
  <video controls preload="none" aria-label="${escapedAlt}">
    <source src="${escapeHtml(url)}" type="${mimeType}" />
    Your browser does not support the video tag.
  </video>${captionHtml}
</div>`;
}

/**
 * Remark plugin that transforms video image references into HTML5 video elements or placeholders
 */
export function remarkVideoEmbed() {
  return function transformer(tree: Root) {
    visit(tree, 'paragraph', (node: Paragraph, index, parent) => {
      if (index === undefined || !parent) return;

      // Find an image child with a video file extension
      const imageIndex = node.children.findIndex(
        (child): child is Image => child.type === 'image' && isVideoUrl(child.url)
      );

      if (imageIndex === -1) return;

      const imageNode = node.children[imageIndex] as Image;
      const caption = extractCaption(node, imageIndex);

      // Always render <video> elements. These were meant to be filled in
      // post-build by a CI inject step, but no workflow has ever produced the
      // `e2e-videos-*` artifact it downloaded, so that step and its script were
      // removed. The sources are therefore missing in practice and the browser
      // renders an empty player. That is pre-existing behaviour, not a
      // regression from the removal, and it is tracked separately: the fix is
      // to produce the recordings or to stop emitting the element.
      const html = buildVideoHtml(imageNode.url, imageNode.alt ?? '', caption);

      // Replace the entire paragraph node with raw HTML
      (parent as Parent).children.splice(index, 1, {
        type: 'html',
        value: html,
      } as Node);

      return [SKIP, index] as const;
    });
  };
}
