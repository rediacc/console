import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { TOOLS } from '../tools.js';

describe('MCP tool definitions', () => {
  it('has exactly 16 tools defined', () => {
    expect(TOOLS.length).toBe(16);
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
      expect(names).toContain('machine_info');
      expect(names).toContain('machine_list');
      expect(names).toContain('machine_containers');
      expect(names).toContain('machine_services');
      expect(names).toContain('machine_repos');
      expect(names).toContain('machine_health');
      expect(names).toContain('config_repositories');
      expect(names).toContain('agent_capabilities');
      expect(names).toContain('backup_push');
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
      expect(names).toContain('backup_pull');
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
        'backup_push',
        'backup_pull',
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
    it('machine_info builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_info')!;
      expect(tool.command({ name: 'prod' })).toEqual(['machine', 'info', 'prod']);
    });

    it('machine_containers builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_containers')!;
      expect(tool.command({ name: 'staging' })).toEqual(['machine', 'containers', 'staging']);
    });

    it('config_repositories builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'config_repositories')!;
      expect(tool.command({})).toEqual(['config', 'repositories']);
    });

    it('agent_capabilities builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'agent_capabilities')!;
      expect(tool.command({})).toEqual(['agent', 'capabilities']);
    });

    it('repo_create builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_create')!;
      expect(tool.command({ name: 'webapp', machine: 'prod', size: '10G' })).toEqual([
        'repo',
        'create',
        'webapp',
        '-m',
        'prod',
        '--size',
        '10G',
      ]);
    });

    it('repo_up builds correct argv with machine flag', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      expect(tool.command({ name: 'gitlab', machine: 'prod' })).toEqual([
        'repo',
        'up',
        'gitlab',
        '-m',
        'prod',
      ]);
    });

    it('repo_up includes --mount when set', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      expect(tool.command({ name: 'gitlab', machine: 'prod', mount: true })).toEqual([
        'repo',
        'up',
        'gitlab',
        '-m',
        'prod',
        '--mount',
      ]);
    });

    it('repo_up excludes --mount when false', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      expect(tool.command({ name: 'gitlab', machine: 'prod', mount: false })).toEqual([
        'repo',
        'up',
        'gitlab',
        '-m',
        'prod',
      ]);
    });

    it('repo_down builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      expect(tool.command({ name: 'gitlab', machine: 'prod' })).toEqual([
        'repo',
        'down',
        'gitlab',
        '-m',
        'prod',
      ]);
    });

    it('repo_down includes --unmount when set', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      expect(tool.command({ name: 'gitlab', machine: 'prod', unmount: true })).toEqual([
        'repo',
        'down',
        'gitlab',
        '-m',
        'prod',
        '--unmount',
      ]);
    });

    it('repo_down excludes --unmount when false', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      expect(tool.command({ name: 'gitlab', machine: 'prod', unmount: false })).toEqual([
        'repo',
        'down',
        'gitlab',
        '-m',
        'prod',
      ]);
    });

    it('repo_fork builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_fork')!;
      expect(tool.command({ parent: 'webapp', machine: 'prod', tag: 'test' })).toEqual([
        'repo',
        'fork',
        'webapp',
        '-m',
        'prod',
        '--tag',
        'test',
      ]);
    });

    it('backup_push builds correct argv with --to-machine', () => {
      const tool = TOOLS.find((t) => t.name === 'backup_push')!;
      expect(tool.command({ repo: 'webapp', machine: 'prod', to_machine: 'staging' })).toEqual([
        'backup',
        'push',
        'webapp',
        '-m',
        'prod',
        '--to-machine',
        'staging',
      ]);
    });

    it('backup_pull builds correct argv with --from-machine', () => {
      const tool = TOOLS.find((t) => t.name === 'backup_pull')!;
      expect(tool.command({ repo: 'webapp', machine: 'staging', from_machine: 'prod' })).toEqual([
        'backup',
        'pull',
        'webapp',
        '-m',
        'staging',
        '--from-machine',
        'prod',
      ]);
    });

    it('repo_delete builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_delete')!;
      expect(tool.command({ name: 'webapp', machine: 'prod' })).toEqual([
        'repo',
        'delete',
        'webapp',
        '-m',
        'prod',
      ]);
    });

    it('term_exec builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'term_exec')!;
      expect(tool.command({ machine: 'prod', command: 'uptime' })).toEqual([
        'term',
        'prod',
        '-c',
        'uptime',
      ]);
    });

    it('term_exec preserves complex commands as single argv element', () => {
      const tool = TOOLS.find((t) => t.name === 'term_exec')!;
      expect(tool.command({ machine: 'prod', command: 'docker ps | grep running' })).toEqual([
        'term',
        'prod',
        '-c',
        'docker ps | grep running',
      ]);
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
      const tool = TOOLS.find((t) => t.name === 'machine_info')!;
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
});
