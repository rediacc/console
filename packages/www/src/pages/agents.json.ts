import type { APIRoute } from 'astro';
import { CLI_INSTALL, CLI_TOOL } from '../config/cli-reference';
import { SITE_URL } from '../config/constants';

export const GET: APIRoute = () => {
  const data = {
    name: CLI_TOOL,
    description:
      'Self-hosted infrastructure platform with encrypted repositories, container isolation, and automated disaster recovery',
    url: SITE_URL,
    capabilities: {
      mcp: {
        command: CLI_TOOL,
        args: ['mcp', 'serve'],
        transport: 'stdio',
      },
      cli: {
        tool: CLI_TOOL,
        install: CLI_INSTALL,
      },
    },
    documentation: {
      llms_txt: `${SITE_URL}/llms.txt`,
      agents_md: `${SITE_URL}/AGENTS.md`,
      full_docs: `${SITE_URL}/llms-full.txt`,
      ai_agents_overview: `${SITE_URL}/en/docs/ai-agents-overview`,
      mcp_setup: `${SITE_URL}/en/docs/ai-agents-mcp`,
      json_output: `${SITE_URL}/en/docs/ai-agents-json-output`,
    },
  };

  return new Response(JSON.stringify(data, null, 2), {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};
