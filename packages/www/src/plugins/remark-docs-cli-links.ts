import type { Code, Root } from 'mdast';
import { visit } from 'unist-util-visit';
import {
  mergeContinuationLines,
  parseRdcCommand,
  SHELL_FENCE_LANGS,
  TARGET_DOC_CATEGORIES,
} from '../../scripts/lib/cli-reference-catalog.js';

interface RemarkFile {
  data: Record<string, unknown>;
}

interface Frontmatter {
  category?: string;
  language?: string;
}

function getFrontmatter(file: RemarkFile): Frontmatter {
  const astro = file.data.astro as { frontmatter?: Frontmatter } | undefined;
  return astro?.frontmatter ?? {};
}

export function remarkDocsCliLinks() {
  return function transformer(tree: Root, file: RemarkFile) {
    const { category, language = 'en' } = getFrontmatter(file);
    if (!category || !TARGET_DOC_CATEGORIES.has(category)) return;

    visit(tree, 'code', (node: Code, index, parent) => {
      if (index === undefined || !parent) return;
      if (!node.lang || !SHELL_FENCE_LANGS.has(node.lang.toLowerCase())) return;

      const lines = node.value.split(/\r?\n/);
      const commands: string[] = [];
      const seen = new Set<string>();

      for (let i = 0; i < lines.length; i++) {
        const trimmed = lines[i].trim();
        if (!trimmed || trimmed.startsWith('#') || !trimmed.startsWith('rdc')) continue;

        const { command, endIndex } = mergeContinuationLines(lines, i);
        i = endIndex;

        const parsed = parseRdcCommand(command);
        if (!parsed.ok || parsed.rootOnly || !parsed.entry) continue;

        const label = `rdc ${parsed.commandPath}`;
        if (seen.has(label)) continue;
        seen.add(label);

        const href = `/${language}/docs/${parsed.entry.slug}#${parsed.entry.anchorId}`;
        commands.push(
          `<a href="${href}" data-cli-ref-link="true" data-cli-ref-title="${label}">${label}</a>`
        );
      }

      if (commands.length === 0) return;

      const html = `<div class="cli-ref-links"><span class="cli-ref-links-label">CLI reference:</span> ${commands.join(' · ')}</div>`;
      parent.children.splice(index + 1, 0, { type: 'html', value: html });
    });
  };
}
