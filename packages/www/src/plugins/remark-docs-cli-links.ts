import type { Code, Root } from 'mdast';
import { visit } from 'unist-util-visit';
import {
  mergeContinuationLines,
  parseRdcCommand,
  SHELL_FENCE_LANGS,
  TARGET_DOC_CATEGORIES,
} from '../../scripts/lib/cli-reference-catalog.js';
import type { Language } from '../i18n/types';
import { createTranslator } from '../i18n/utils';

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

function isShellFence(node: Code): boolean {
  return !!node.lang && SHELL_FENCE_LANGS.has(node.lang.toLowerCase());
}

function isRdcLine(line: string): boolean {
  const trimmed = line.trim();
  return !!trimmed && !trimmed.startsWith('#') && trimmed.startsWith('rdc');
}

function buildCommandLink(command: string, language: string, seen: Set<string>): string | null {
  const parsed = parseRdcCommand(command);
  if (!parsed.ok || parsed.rootOnly || !parsed.entry) return null;

  const label = `rdc ${parsed.commandPath}`;
  if (seen.has(label)) return null;
  seen.add(label);

  const href = `/${language}/docs/${parsed.entry.slug}#${parsed.entry.anchorId}`;
  return `<a href="${href}" data-cli-ref-link="true" data-cli-ref-title="${label}">${label}</a>`;
}

function collectCommandLinks(lines: string[], language: string): string[] {
  const commands: string[] = [];
  const seen = new Set<string>();

  for (let i = 0; i < lines.length; i++) {
    if (!isRdcLine(lines[i])) continue;

    const { command, endIndex } = mergeContinuationLines(lines, i);
    i = endIndex;

    const link = buildCommandLink(command, language, seen);
    if (link) commands.push(link);
  }
  return commands;
}

export function remarkDocsCliLinks() {
  return function transformer(tree: Root, file: RemarkFile) {
    const { category, language = 'en' } = getFrontmatter(file);
    if (!category || !TARGET_DOC_CATEGORIES.has(category)) return;

    const { t } = createTranslator(language as Language);

    visit(tree, 'code', (node: Code, index, parent) => {
      if (index === undefined || !parent) return;
      if (!isShellFence(node)) return;

      const commands = collectCommandLinks(node.value.split(/\r?\n/), language);
      if (commands.length === 0) return;

      const html = `<div class="cli-ref-links"><span class="cli-ref-links-label">${t('documentation.cliReferenceLabel')}</span> ${commands.join(' · ')}</div>`;
      parent.children.splice(index + 1, 0, { type: 'html', value: html });
    });
  };
}
