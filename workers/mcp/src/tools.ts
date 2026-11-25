/**
 * `tools/list` for the hosted Worker, built from the one shared registry (agent/plans/PLAN-rmcp-remote-worker.md Design 1, PLAN-rmcp-local-mcp.md LM1).
 *
 * Only `surface === 'proxy'` tools are served, filtered by the grant's scope, in the registry's order (sorted by UTF-16 code units), so two calls under one scope answer byte-identical lists. The wire shape of each entry is the one the local stdio server emits for the same tool (D18), which `packages/shared/src/mcp/__tests__/tools-list.snapshot.json` records: the SDK's JSON Schema output names its draft in `$schema` and carries no `additionalProperties` key.
 */

import { listProxyTools, type McpToolEntry } from '../../../packages/shared/src/mcp/registry.js';
import { omitKey } from '../../../packages/shared/src/utils/omit-key.js';
import { type GrantScope, scopeAdmitsTool } from './scope.js';

/** The draft the local server's schema conversion stamps on every input schema. */
const JSON_SCHEMA_DRAFT = 'https://json-schema.org/draft/2020-12/schema';

export interface WireTool {
  name: string;
  description: string;
  inputSchema: { type: 'object'; [key: string]: unknown };
  annotations: McpToolEntry['annotations'];
}

function wireInputSchema(entry: McpToolEntry): WireTool['inputSchema'] {
  const rest = omitKey(entry.inputSchema, 'additionalProperties');
  return { $schema: JSON_SCHEMA_DRAFT, ...rest, type: 'object' };
}

function toWireTool(entry: McpToolEntry): WireTool {
  return {
    name: entry.name,
    description: entry.description,
    inputSchema: wireInputSchema(entry),
    annotations: { ...entry.annotations },
  };
}

/** The tools a grant with `scope` sees, in registry order. */
export function listGrantTools(scope: GrantScope): WireTool[] {
  return listProxyTools()
    .filter((entry) => scopeAdmitsTool(scope, entry))
    .map(toWireTool);
}
