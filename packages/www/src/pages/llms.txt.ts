import { getCollection } from 'astro:content';
import type { APIRoute } from 'astro';
import {
  AUTO_JSON_NOTE,
  CLI_COMMANDS,
  CLI_FLAGS,
  CLI_TOOL,
  JSON_ENVELOPE,
  TERMINOLOGY,
} from '../config/cli-reference';
import { SITE_URL } from '../config/constants';
import { getBaseSlug } from '../utils/slug';

// Docs excluded from the LLM index (auto-generated references)
const EXCLUDED_SLUGS = [
  'en/cli-application',
  'en/cli-application-cloud',
  'en/web-application',
] as const;

// Category display order (matches DocsTopTabs / DocsSidebar)
const CATEGORY_ORDER: Record<string, number> = {
  Guides: 0,
  Concepts: 1,
  Reference: 2,
  'Use Cases': 3,
};

const ORDER_FALLBACK = 99;

export const GET: APIRoute = async () => {
  const docs = await getCollection(
    'docs',
    (d) => d.data.language === 'en' && !EXCLUDED_SLUGS.includes(d.slug)
  );

  // Group by category
  const byCategory = new Map<string, typeof docs>();
  for (const doc of docs) {
    const cat = doc.data.category;
    if (!byCategory.has(cat)) byCategory.set(cat, []);
    byCategory.get(cat)!.push(doc);
  }

  // Sort categories
  const sortedCategories = [...byCategory.keys()].sort((a, b) => {
    const pa = CATEGORY_ORDER[a] ?? ORDER_FALLBACK;
    const pb = CATEGORY_ORDER[b] ?? ORDER_FALLBACK;
    if (pa !== pb) return pa - pb;
    return a.localeCompare(b);
  });

  // Sort docs within each category by order
  for (const [, catDocs] of byCategory) {
    catDocs.sort((a, b) => (a.data.order ?? ORDER_FALLBACK) - (b.data.order ?? ORDER_FALLBACK));
  }

  // Build CLI reference from shared config
  const flagLines = CLI_FLAGS.map((f) => `- \`${f.flag}\` — ${f.description}`).join('\n');
  const COMMAND_LABELS: Record<string, string> = {
    deploy: 'Deploy',
    status: 'Status',
    containers: 'Containers',
    ssh: 'SSH',
    health: 'Health',
    capabilities: 'Capabilities',
  };
  const commandLines = Object.entries(CLI_COMMANDS)
    .map(([key, cmd]) => `- ${COMMAND_LABELS[key] ?? key}: \`${cmd}\``)
    .join('\n');
  const terminologyLines = TERMINOLOGY.map((t) => `- ${t}`).join('\n');

  // Build content
  let content = `# Rediacc

> Self-hosted infrastructure platform with encrypted repositories, container isolation, and automated disaster recovery.

Rediacc enables you to deploy and manage isolated, encrypted application environments on your own servers. Each repository gets its own Docker daemon, network namespace, and encrypted storage.

## AI Agent Instructions

> The CLI tool is called \`${CLI_TOOL}\` (not \`rediacc\`). Always use \`${CLI_TOOL}\` in commands.

### Key Flags
${flagLines}
- ${AUTO_JSON_NOTE}

### JSON Envelope
All JSON output uses a consistent envelope:
\`${JSON_ENVELOPE}\`

### Terminology
${terminologyLines}

### Common Commands
${commandLines}

### MCP Server
- Command: \`rdc mcp serve\` (stdio transport, stateless)
- [MCP Setup Guide](${SITE_URL}/en/docs/ai-agents-mcp.txt): Claude Code, Cursor, and other agent configuration

### Agent Configuration
- [AGENTS.md](${SITE_URL}/AGENTS.md): Machine-readable agent configuration file
- [AGENTS.md Template](${SITE_URL}/en/docs/agents-md-template.txt): Copy-paste template for configuring AI assistants
- [agents.json](${SITE_URL}/agents.json): API discovery endpoint

`;

  for (const category of sortedCategories) {
    const catDocs = byCategory.get(category)!;
    content += `## ${category}\n\n`;
    for (const doc of catDocs) {
      const slug = getBaseSlug(doc.slug);
      content += `- [${doc.data.title}](${SITE_URL}/en/docs/${slug}.txt): ${doc.data.description}\n`;
    }
    content += '\n';
  }

  content += `## Optional\n\n- [Full Documentation](${SITE_URL}/llms-full.txt): Complete documentation in a single file\n`;

  return new Response(content, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
