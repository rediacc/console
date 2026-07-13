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
      expect(names).toContain('machine_status');
      expect(names).toContain('machine_list');
      expect(names).toContain('machine_containers');
      expect(names).toContain('machine_services');
      expect(names).toContain('machine_repos');
      expect(names).toContain('machine_health');
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
      expect(names).toContain('repo_exec');
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
        'repo_exec',
      ]) {
        const tool = TOOLS.find((t) => t.name === name)!;
        expect(tool.timeoutMs, `${name} should have >= 300s timeout`).toBeGreaterThanOrEqual(
          300_000
        );
      }
    });
  });

  describe('command builders produce valid argv', () => {
    it('machine_status builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_status')!;
      expect(tool.command({ name: 'prod' })).toEqual(['machine', 'status', 'prod']);
    });

    it('machine_containers builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_containers')!;
      expect(tool.command({ name: 'staging' })).toEqual([
        'machine',
        'status',
        'staging',
        '--containers',
      ]);
    });

    it('repo_create builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_create')!;
      const argv = tool.command({ name: 'webapp', machine: 'prod', size: '10G' });
      // `repo create <name>` takes the repo name POSITIONALLY (spec §5.4 placement
      // union); the old `--name` flag is gone, and placement is --machine XOR
      // --datastore.
      expect(argv.slice(0, 3)).toEqual(['repo', 'create', 'webapp']);
      expect(argv).not.toContain('--name');
      expect(argv).toContain('--machine');
      expect(argv).toContain('prod');
      expect(argv).toContain('--size');
      expect(argv).toContain('10G');
    });

    it('repo_up builds correct argv on the <ref> positional (machine derived)', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      const argv = tool.command({ ref: 'gitlab' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'up', 'gitlab']);
      expect(argv).not.toContain('--name');
      expect(argv).not.toContain('--machine');
    });

    it('repo_down builds correct argv on the <ref> positional', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      const argv = tool.command({ ref: 'gitlab' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'down', 'gitlab']);
      expect(argv).not.toContain('--name');
      expect(argv).not.toContain('--machine');
    });

    it('repo_down includes --unmount when set', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      const argv = tool.command({ ref: 'gitlab', unmount: true });
      expect(argv).toContain('--unmount');
    });

    it('repo_down excludes --unmount when false', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_down')!;
      const argv = tool.command({ ref: 'gitlab', unmount: false });
      expect(argv).not.toContain('--unmount');
    });

    it('repo_fork builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_fork')!;
      // repo fork <parent-ref>: the parent is positional; the machine is derived
      // from its placement (spec §2.3), so there is no --parent or --machine flag.
      const argv = tool.command({ ref: 'webapp', tag: 'test' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'fork', 'webapp']);
      expect(argv).not.toContain('--parent');
      expect(argv).toContain('--tag');
      expect(argv).toContain('test');
    });

    it('repo_push builds correct argv on the <ref> positional with --to-machine', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_push')!;
      const argv = tool.command({ ref: 'webapp', to_machine: 'staging' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'push', 'webapp']);
      expect(argv).not.toContain('--name');
      expect(argv).not.toContain('--machine');
      expect(argv).toContain('--to-machine');
      expect(argv).toContain('staging');
    });

    it('repo_pull builds correct argv on the <ref> positional with --from-machine', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_pull')!;
      const argv = tool.command({ ref: 'webapp', from_machine: 'prod' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'pull', 'webapp']);
      expect(argv).not.toContain('--name');
      expect(argv).not.toContain('--machine');
      expect(argv).toContain('--from-machine');
      expect(argv).toContain('prod');
    });

    it('repo_delete builds correct argv', () => {
      const tool = TOOLS.find((t) => t.name === 'repo_delete')!;
      // repo delete <ref>: the repo is a positional; the machine is DERIVED, so
      // there is no --machine flag to carry (spec §2.3).
      const argv = tool.command({ ref: 'webapp' });
      expect(argv.slice(0, 3)).toEqual(['repo', 'delete', 'webapp']);
      expect(argv).not.toContain('--name');
    });

    it('machine_deprovision appends --force', () => {
      const tool = TOOLS.find((t) => t.name === 'machine_deprovision')!;
      expect(tool.command({ name: 'old-server' })).toEqual([
        'machine',
        'deprovision',
        '--name',
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
        // repo_exec replaced term_exec (w2b): the tool that used to build
        // `term connect -m <machine> -c <cmd>` and whose argv silently went
        // invalid when -m died. It is a real leaf now, so it is auto-derived.
        'repo_exec',
      ];
      for (const name of guarded) {
        const tool = TOOLS.find((t) => t.name === name)!;
        expect(tool.repoArgField, `${name} should have repoArgField`).toBeDefined();
      }
    });

    it('is not set on safe or non-repo tools', () => {
      const safe = [
        'repo_create',
        'machine_status',
        'machine_list',
        'machine_provision',
        'machine_deprovision',
      ];
      for (const name of safe) {
        const tool = TOOLS.find((t) => t.name === name)!;
        expect(tool.repoArgField, `${name} should not have repoArgField`).toBeUndefined();
      }
    });

    it('the positional-converted repo tools bind their repo to the <ref> arg', () => {
      // repo cat/status/delete/fork/migrate/up/down carry a positional <ref>
      // (spec §2.2); the guard's repo field is the positional name, not a dead
      // --name flag.
      for (const name of [
        'repo_cat',
        'repo_status',
        'repo_delete',
        'repo_fork',
        'repo_migrate',
        'repo_up',
        'repo_down',
        'repo_commit',
        'repo_log',
        'repo_merge',
        'repo_secret_get',
        'repo_secret_list',
        'repo_diff',
      ]) {
        expect(TOOLS.find((t) => t.name === name)!.repoArgField, name).toBe('ref');
      }
    });

    it('repo_checkout binds its repo to the <commit-or-branch-ref> positional', () => {
      // Checkout clones a commit/branch (not a family) into a fresh fork, so its
      // positional is role-named; the guard field is the positional name.
      expect(TOOLS.find((t) => t.name === 'repo_checkout')!.repoArgField).toBe(
        'commit-or-branch-ref'
      );
    });

    it('the backup tools bind their repo to the <ref> positional too', () => {
      // Previously repoArg was 'repo', but no such field existed in the derived
      // MCP schema (it had 'name'), so the grand-repo guard silently no-op'd on
      // repo_push / repo_pull. Binding to the real positional actually enables it.
      expect(TOOLS.find((t) => t.name === 'repo_push')!.repoArgField).toBe('ref');
      expect(TOOLS.find((t) => t.name === 'repo_pull')!.repoArgField).toBe('ref');
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
      // machine_status' name is now an OPTIONAL positional; machine_containers
      // still requires the machine name, so it is the required-field example.
      const tool = TOOLS.find((t) => t.name === 'machine_containers')!;
      const schema = z.object(tool.schema);
      const result = schema.safeParse({});
      expect(result.success).toBe(false);
    });

    it('schemas with optional fields accept missing values', () => {
      // repo_up requires only its <ref> positional; no-start/skip-checkpoint/tls
      // are optional and may be absent.
      const tool = TOOLS.find((t) => t.name === 'repo_up')!;
      const schema = z.object(tool.schema);
      const result = schema.safeParse({ ref: 'app' });
      expect(result.success).toBe(true);
    });
  });

  describe('custom tools', () => {
    it('has exactly 4 custom tools', () => {
      // 5 -> 4: term_exec retired in w2b (repo_exec replaces it as a real leaf).
      expect(CUSTOM_TOOLS.length).toBe(4);
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
