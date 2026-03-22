/**
 * Remark plugin to embed terminal tutorial players from markdown image syntax.
 *
 * Transforms image references with .cast extensions into placeholder divs
 * that the client-side tutorial-hydrate.ts script mounts as TerminalPlayer
 * React components.
 *
 * Example:
 *   Input:  ![Tutorial: rdc ops](/assets/tutorials/ops-tutorial.cast)
 *   Output: <div class="tutorial-player-container" data-tutorial-src="..." data-tutorial-title="..."></div>
 */

import path from 'node:path';
import { DEFAULTS_EXTENDED } from '@rediacc/shared/config/defaults';
import type { Image, Paragraph, Root } from 'mdast';
import type { Node, Parent } from 'unist';
import { SKIP, visit } from 'unist-util-visit';

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

export function remarkTutorialEmbed() {
  return function transformer(tree: Root) {
    visit(tree, 'paragraph', (node: Paragraph, index, parent) => {
      if (index === undefined || !parent) return;

      const imageIndex = node.children.findIndex(
        (child): child is Image => child.type === 'image' && isCastUrl(child.url)
      );

      if (imageIndex === -1) return;

      const imageNode = node.children[imageIndex] as Image;
      const title = escapeHtml(imageNode.alt ?? DEFAULTS_EXTENDED.WWW.TUTORIAL_TITLE);
      const src = escapeHtml(imageNode.url);

      const html = `<div class="tutorial-player-container" data-tutorial-src="${src}" data-tutorial-title="${title}"></div>`;

      (parent as Parent).children.splice(index, 1, {
        type: 'html',
        value: html,
      } as Node);

      return [SKIP, index] as const;
    });
  };
}
