/**
 * Rehype plugin: stable English heading ids across every locale.
 *
 * For every docs and blog document, heading ids are assigned POSITIONALLY from
 * the English source file (see src/plugins/heading-anchors.mjs). English pages
 * keep the ids github-slugger has always given them; translated pages get the
 * SAME ids, so `/ar/docs/quick-start#introduction` and
 * `/en/docs/quick-start#introduction` are one fragment, the way docs.claude.com
 * does it. Astro's default rehypeHeadingIds runs after user plugins and respects
 * an existing id, so the ids written here also flow into
 * `file.data.astro.headings` unchanged.
 *
 * The positional contract is enforced, not assumed: a translation whose heading
 * structure diverges from its English source FAILS THE BUILD with both
 * sequences printed. A silent fallback here would hand out locale-specific
 * fragments again, which is exactly the defect class this plugin removes, and
 * no downstream gate could see it because the page would still be
 * self-consistent.
 */
import { visit } from 'unist-util-visit';
import { contentFileInfo, englishAnchorsFor } from './heading-anchors.mjs';

export function rehypeStableHeadingIds() {
  return function transformer(tree, file) {
    const info = contentFileInfo(file.path ?? file.history?.[0]);
    if (!info) return;

    const english = englishAnchorsFor(info.collection, info.filename);

    const headings = [];
    visit(tree, 'element', (node) => {
      const match = /^h([1-6])$/.exec(node.tagName);
      if (match) headings.push({ node, depth: Number(match[1]) });
    });

    const found = headings.map((h) => `h${h.depth}`).join(' ');
    const expected = english.map((h) => `h${h.depth}`).join(' ');
    if (found !== expected) {
      throw new Error(
        `Heading structure of src/content/${info.collection}/${info.locale}/${info.filename} ` +
          `diverges from its English source, so stable anchors cannot be assigned.\n` +
          `  en (${english.length}): ${expected}\n` +
          `  ${info.locale} (${headings.length}): ${found}\n` +
          `Every locale must carry the same sections as the English document. ` +
          `Align the translation's heading structure (usually a section added to the ` +
          `English file that the translation does not have yet).`
      );
    }

    headings.forEach((h, i) => {
      h.node.properties = h.node.properties || {};
      h.node.properties.id = english[i].id;
    });
  };
}
