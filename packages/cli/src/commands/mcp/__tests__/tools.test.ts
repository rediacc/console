import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { cli } from '../../../cli.js';
import { CUSTOM_TOOLS } from '../custom-tools.js';
import type { ToolDef } from '../tool-factory.js';
import { buildAllTools } from '../tools.js';

// Build the full tool list from the real Commander tree
const TOOLS: ToolDef[] = buildAllTools(cli);

describe('MCP tool definitions', () => {
  it('has at least 24 tools defined', () => {
    expect(TOOLS.length).toBeGreaterThanOrEqual(24);
  });

  it('has no duplicate tool names', () => {
    const names = TOOLS.map((t) => t.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it('all tools have non-empty descriptions', () => {
    for (const tool of TOOLS) {
      expect(tool.description.length, `${tool.name} description is empty`).toBeGreaterThan(0);
    }
  });

  describe('read tools', () => {
    const readTools = TOOLS.filter((t) => !t.isDestructive);

    it('includes expected read tools', () => {
      const names = readTools.map((t) => t.name);
      expect(names).toContain('machine_query');
      expect(names).toContain('machine_list');
      expect(names).toContain('machine_containers');
      expect(names).toContain('machine_services');
      expect(names).toContain('machine_repos');
      expect(names).toContain('machine_health');
      expect(names).toContain('agent_capabilities');
    });

    it('are not marked as destructive', () => {
      for (const tool of readTools) {
        expect(tool.isDestructive, `${tool.name} should not be destructive`).toBe(false);
      }
    });
  });

  describe('write tools', () => {
    const writeTools = TOOLS.filter((t) => t.isDestructive);

    it('includes expected write tools', () => {
      const names = writeTools.map((t) => t.name);
      expect(names).toContain('repo_create');
      expect(names).toContain('repo_up');
      expect(names).toContain('repo_down');
      expect(names).toContain('repo_delete');
      expect(names).toContain('repo_fork');
      expect(names).toContain('repo_pull');
      expect(names).toContain('term_exec');
    });

    it('are marked as destructive', () => {
      for (const tool of writeTools) {
        expect(tool.isDestructive, `${tool.name} should be destructive`).toBe(true);
      }
    });

    it('write tools have longer timeouts', () => {
      for (const name of [
        'repo_create',
        'repo_up',
        'repo_down',
        'repo_delete',
        'repo_fork',
        'repo_push',
        'repo_pull',
        'term_exec',
      ]) {
        const tool = TOOLS.find((t) => t.name === name)!;
        expect(tool.timeoutMs, `${name} should have >= 300s timeout`).toBeGreaterThanOrEqual(
          300_000
        );
      }
    });
  });

  describe('command builders produce valid argv', () => {
    it('machine_query builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_query')!;
      expect(tool.command({ name: 'prod' })).toEqual(['machine', 'query', 'prod']);
    });

    it('machine_containers builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_containers')!;
      expect(tool.command({ name: 'staging' })).toEqual([
        'machine',
        'query',
        'staging',
        '--containers',
      ]);
    });

    it('agent_capabilities builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'agent_capabilities')!;
      expect(tool.command({})).toEqual(['agent', 'capabilities']);
    });

    it('repo_create builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_create')!;
      const argv = tool.command({ name: 'webapp', machine: 'prod', size: '10G' });
      expect(argv).toContain('repo');
      expect(argv).toContain('create');
      expect(argv).toContain('webapp');
      expect(argv).toContain('10G');
      expect(argv).toContain('prod');
    });

    it('repo_up builds correct argv with machine flag', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      const argv = tool.command({ name: 'gitlab', machine: 'prod' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'up', 'gitlab']);
      expect(argv).toContain('prod');
    });

    it('repo_up includes --mount when set', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      const argv = tool.command({ name: 'gitlab', machine: 'prod', mount: true });
      expect(argv).toContain('--mount');
      expect(argv).toContain('prod');
    });

    it('repo_up excludes --mount when false', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      const argv = tool.command({ name: 'gitlab', machine: 'prod', mount: false });
      expect(argv).not.toContain('--mount');
    });

    it('repo_down builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      const argv = tool.command({ name: 'gitlab', machine: 'prod' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'down', 'gitlab']);
      expect(argv).toContain('prod');
    });

    it('repo_down includes --unmount when set', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      const argv = tool.command({ name: 'gitlab', machine: 'prod', unmount: true });
      expect(argv).toContain('--unmount');
    });

    it('repo_down excludes --unmount when false', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      const argv = tool.command({ name: 'gitlab', machine: 'prod', unmount: false });
      expect(argv).not.toContain('--unmount');
    });

    it('repo_fork builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_fork')!;
      const argv = tool.command({ parent: 'webapp', machine: 'prod', tag: 'test' });
      // Positional args: parent, tag; then option: --machine
      expect(argv.slice(0, 4)).toEqual(['repo', 'fork', 'webapp', 'test']);
      expect(argv).toContain('prod');
    });

    it('repo_push builds correct argv with --to-machine', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_push')!;
      const argv = tool.command({ repo: 'webapp', machine: 'prod', to_machine: 'staging' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'push', 'webapp']);
      expect(argv).toContain('--to-machine');
      expect(argv).toContain('staging');
      expect(argv).toContain('prod');
    });

    it('repo_pull builds correct argv with --from-machine', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_pull')!;
      const argv = tool.command({ repo: 'webapp', machine: 'staging', from_machine: 'prod' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'pull', 'webapp']);
      expect(argv).toContain('--from-machine');
      expect(argv).toContain('prod');
      expect(argv).toContain('staging');
    });

    it('repo_delete builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_delete')!;
      const argv = tool.command({ name: 'webapp', machine: 'prod' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'delete', 'webapp']);
      expect(argv).toContain('prod');
    });

    it('term_exec builds correct argv (machine only)', () => {
      const tool = TOOLS.find((t) => t.name === 'term_exec')!;
      expect(tool.command({ machine: 'prod', command: 'uptime' })).toEqual([
        'term',
        'prod',
        '-c',
        'uptime',
      ]);
    });

    it('term_exec builds correct argv with repository', () => {
      const tool = TOOLS.find((t) => t.name === 'term_exec')!;
      expect(
        tool.command({ machine: 'prod', repository: 'webapp', command: 'docker ps | grep running' })
      ).toEqual(['term', 'prod', 'webapp', '-c', 'docker ps | grep running']);
    });

    it('term_exec omits repository when not provided', () => {
      const tool = TOOLS.find((t) => t.name === 'term_exec')!;
      expect(tool.command({ machine: 'prod', command: 'df -h' })).toEqual([
        'term',
        'prod',
        '-c',
        'df -h',
      ]);
    });

    it('machine_deprovision appends --force', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_deprovision')!;
      expect(tool.command({ name: 'old-server' })).toEqual([
        'machine',
        'deprovision',
        'old-server',
        '--force',
      ]);
    });
  });

  describe('repoArgField for grand repo guard', () => {
    it('is set on guarded destructive tools', () => {
      const guarded = [
        'repo_up',
        'repo_down',
        'repo_delete',
        'repo_push',
        'repo_pull',
        'term_exec',
      ];
      for (const name of guarded) {
        const tool = TOOLS.find((t) => t.name === name)!;
        expect(tool.repoArgField, `${name} should have repoArgField`).toBeDefined();
      }
    });

    it('is not set on safe or non-repo tools', () => {
      const safe = [
        'repo_create',
        'repo_fork',
        'machine_query',
        'machine_list',
        'machine_provision',
        'machine_deprovision',
      ];
      for (const name of safe) {
        const tool = TOOLS.find((t) => t.name === name)!;
        expect(tool.repoArgField, `${name} should not have repoArgField`).toBeUndefined();
      }
    });

    it('repo_up and repo_down use "name" field', () => {
      expect(TOOLS.find((t) => t.name === 'repo_up')!.repoArgField).toBe('name');
      expect(TOOLS.find((t) => t.name === 'repo_down')!.repoArgField).toBe('name');
      expect(TOOLS.find((t) => t.name === 'repo_delete')!.repoArgField).toBe('name');
    });

    it('backup tools use "repo" field', () => {
      expect(TOOLS.find((t) => t.name === 'repo_push')!.repoArgField).toBe('repo');
      expect(TOOLS.find((t) => t.name === 'repo_pull')!.repoArgField).toBe('repo');
    });

    it('term_exec uses "repository" field', () => {
      expect(TOOLS.find((t) => t.name === 'term_exec')!.repoArgField).toBe('repository');
    });
  });

  describe('timeouts', () => {
    it('all tools have explicit timeoutMs', () => {
      for (const tool of TOOLS) {
        expect(tool.timeoutMs, `${tool.name} missing timeoutMs`).toBeDefined();
        expect(tool.timeoutMs, `${tool.name} timeoutMs should be positive`).toBeGreaterThan(0);
      }
    });
  });

  describe('schemas are valid Zod objects', () => {
    it('all schemas can be wrapped in z.object()', () => {
      for (const tool of TOOLS) {
        expect(() => z.object(tool.schema), `${tool.name} schema is invalid`).not.toThrow();
      }
    });

    it('schemas with required fields reject missing values', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_query')!;
      const schema = z.object(tool.schema);
      const result = schema.safeParse({});
      expect(result.success).toBe(false);
    });

    it('schemas with optional fields accept missing values', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      const schema = z.object(tool.schema);
      const result = schema.safeParse({ name: 'app', machine: 'prod' });
      expect(result.success).toBe(true);
    });
  });

  describe('custom tools', () => {
    it('has exactly 5 custom tools', () => {
      expect(CUSTOM_TOOLS.length).toBe(5);
    });

    it('custom tools are all present in full tool list', () => {
      const allNames = new Set(TOOLS.map((t) => t.name));
      for (const tool of CUSTOM_TOOLS) {
        expect(allNames.has(tool.name), `custom tool ${tool.name} missing from full list`).toBe(
          true
        );
      }
    });
  });
});
