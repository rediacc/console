/**
 * Remark plugin to embed videos from markdown image syntax.
 *
 * Transforms image references with video file extensions (.webm, .mp4) into
 * HTML5 <video> elements. When the video file doesn't exist in the public
 * directory, renders a styled placeholder instead.
 *
 * Example:
 *   Input:  ![Registration walkthrough](/assets/videos/user-guide/01-01-registration.webm)
 *           *(Video: Complete registration flow)*
 *
 *   Output (video exists):    <div class="video-container"><video ...>...</video><em>...</em></div>
 *   Output (video missing):   <div class="video-container"><div class="video-placeholder">...</div><em>...</em></div>
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { visit, SKIP } from 'unist-util-visit';
import type { Root, Paragraph, Image, Text } from 'mdast';
import type { Node, Parent } from 'unist';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Path to the public directory (relative to this plugin at packages/www/src/plugins/)
const PUBLIC_DIR = path.resolve(__dirname, '../../public');

const VIDEO_EXTENSIONS = ['.webm', '.mp4'] as const;

/**
 * Escape special HTML characters to prevent XSS in generated HTML
 */
function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function isVideoUrl(url: string): boolean {
  const ext = path.extname(url).toLowerCase();
  return (VIDEO_EXTENSIONS as readonly string[]).includes(ext);
}

function getVideoMimeType(url: string): string {
  return url.endsWith('.mp4') ? 'video/mp4' : 'video/webm';
}

function videoFileExists(urlPath: string): boolean {
  const fullPath = path.join(PUBLIC_DIR, urlPath);
  return fs.existsSync(fullPath);
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

function buildPlaceholderHtml(alt: string, caption: string | null): string {
  const escapedAlt = escapeHtml(alt);
  const captionHtml = caption ? `\n  <em>${escapeHtml(caption)}</em>` : '';

  return `<div class="video-container">
  <div class="video-placeholder" aria-label="${escapedAlt}">
    <div class="video-placeholder-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="currentColor" width="48" height="48">
        <path d="M8 5v14l11-7z"/>
      </svg>
    </div>
    <span class="video-placeholder-text">Video coming soon</span>
  </div>${captionHtml}
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

      const exists = videoFileExists(imageNode.url);
      const html = exists
        ? buildVideoHtml(imageNode.url, imageNode.alt ?? '', caption)
        : buildPlaceholderHtml(imageNode.alt ?? '', caption);

      // Replace the entire paragraph node with raw HTML
      (parent as Parent).children.splice(index, 1, {
        type: 'html',
        value: html,
      } as Node);

      return [SKIP, index] as const;
    });
  };
}
