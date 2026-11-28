/**
 * Honest MCP annotations (PLAN-rmcp-local-mcp LM5, Design 4). A non-destructive write was once advertised
 * `readOnlyHint: true` (readOnly was `!destructive`), so clients ran `repo up` or `backup run` in parallel and
 * without confirmation. The table pins one tool of each class; the sweep holds the rule for every tool.
 */
import { describe, expect, it } from 'vitest';
import { toolAnnotations } from '../tool-factory.js';
import { buildAllTools } from '../tools.js';

const TOOLS = new Map(buildAllTools().map((t) => [t.name, t]));

function annotationsOf(name: string) {
  const tool = TOOLS.get(name);
  if (!tool) throw new Error(`no MCP tool ${name}`);
  return toolAnnotations(tool);
}

describe('MCP tool annotations', () => {
  it.each([
    // class, tool, readOnly, destructive, idempotent
    ['read', 'repo_list', true, false, true],
    ['non-destructive write', 'backup_run', false, false, false],
    ['non-destructive idempotent write', 'machine_setup', false, false, true],
    ['destructive write', 'repo_delete', false, true, false],
    ['destructive tool with a read timeout', 'backup_reconcile', false, true, true],
  ] as const)('%s (%s)', (_cls, name, readOnly, destructive, idempotent) => {
    expect(annotationsOf(name)).toEqual({
      readOnlyHint: readOnly,
      destructiveHint: destructive,
      idempotentHint: idempotent,
      openWorldHint: true,
    });
  });

  it('no tool is advertised both read-only and destructive', () => {
    const both = [...TOOLS.values()]
      .filter((t) => {
        const a = toolAnnotations(t);
        return a.readOnlyHint && a.destructiveHint;
      })
      .map((t) => t.name);
    expect(both).toEqual([]);
  });

  it('every write-class tool is advertised as not read-only', () => {
    const readOnlyWrites = [...TOOLS.values()]
      .filter((t) => t.timeoutClass === 'write' && toolAnnotations(t).readOnlyHint)
      .map((t) => t.name);
    expect(readOnlyWrites).toEqual([]);
  });

  it('control: read-class tools exist and are advertised read-only', () => {
    const reads = [...TOOLS.values()].filter((t) => t.timeoutClass === 'read' && !t.isDestructive);
    expect(reads.length).toBeGreaterThan(10);
    for (const t of reads) expect(toolAnnotations(t).readOnlyHint, t.name).toBe(true);
  });
});
