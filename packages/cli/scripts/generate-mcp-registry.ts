#!/usr/bin/env tsx
/**
 * MCP Registry Generator (PLAN-rmcp-local-mcp LM1)
 *
 * Writes packages/shared/src/mcp/tools.generated.json, the one tool registry the stdio server and the hosted MCP Worker build `tools/list` from. The source is the tool set `rdc mcp serve` registers plus the CLI contract; see scripts/lib/mcp-registry-build.ts.
 *
 * The written file goes through the repository's biome formatter, because biome's JSON check covers packages/**\/*.json and folds short arrays onto one line, which JSON.stringify does not. `--check` therefore compares the parsed document, not the bytes, so the formatting never decides staleness.
 *
 * Usage (from packages/cli):
 *   npx tsx scripts/generate-mcp-registry.ts           write the file
 *   npx tsx scripts/generate-mcp-registry.ts --check   exit 1 when the committed file is missing or differs
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CLI_CONTRACT } from '../../shared/src/cli-contract/data/contract.generated.js';
import { mcpRegistryProblems } from '../../shared/src/mcp/schema.js';
import {
  buildMcpRegistry,
  isRegistryCurrent,
  REGISTRY_REL_PATH,
  serializeMcpRegistry,
} from './lib/mcp-registry-build.js';

const cliRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = path.resolve(cliRoot, REGISTRY_REL_PATH);
const shown = path.relative(process.cwd(), target);
const registry = buildMcpRegistry(CLI_CONTRACT);
const problems = mcpRegistryProblems(registry);
if (problems.length > 0) {
  process.stderr.write(`the built MCP registry is malformed:\n  ${problems.join('\n  ')}\n`);
  process.exit(1);
}

if (process.argv.includes('--check')) {
  const committed = fs.existsSync(target) ? fs.readFileSync(target, 'utf-8') : null;
  if (committed === null || !isRegistryCurrent(committed, registry)) {
    process.stderr.write(
      `${shown} is ${committed === null ? 'missing' : 'stale'}; run: npm run generate:mcp-registry -w @rediacc/cli\n`
    );
    process.exit(1);
  }
  process.stdout.write(`${shown} is current\n`);
} else {
  // tree-write: safe the one output of this generator, a committed generated file
  fs.writeFileSync(target, serializeMcpRegistry(registry), 'utf-8');
  const biome = path.resolve(cliRoot, '../../node_modules/.bin/biome');
  const formatted = spawnSync(biome, ['format', '--write', target], { encoding: 'utf-8' });
  if (formatted.status !== 0) {
    process.stderr.write(
      `biome format failed on ${shown} (status ${String(formatted.status)}):\n${formatted.stderr ?? ''}${formatted.error ? String(formatted.error) : ''}\n`
    );
    process.exit(1);
  }
  process.stdout.write(`wrote ${shown}\n`);
}
