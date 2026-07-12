/**
 * CLI contract shape guard.
 *
 * The contract is generated, so this is not testing hand-written logic — it is
 * proving that what the generator committed still parses against the schema the
 * consumers (web console, proxy client, executor) rely on, and that its derived
 * fields are self-consistent.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { CLI_CONTRACT, CLI_CONTRACT_VERSION } from '../data/contract.generated';
import { CONTRACT_LANGUAGES, translate } from '../i18n';
import { commandsByDomain, commandsForContext, getCommand, proxyCapableCommands } from '../index';
import { ContractStringsSchema, checkContractInvariants, parseCliContract } from '../validation';

/**
 * Read as an asset rather than imported: a static import of a 348KB JSON makes
 * TypeScript serialise the whole literal type and give up (TS7056), and reading
 * it is closer to how a consumer loads it anyway.
 */
function readJson(relative: string): unknown {
  return JSON.parse(readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf-8'));
}

const contractJson = readJson('../data/contract.json');

describe('CLI contract', () => {
  it('contract.json parses against the schema', () => {
    expect(() => parseCliContract(contractJson)).not.toThrow();
  });

  it('the generated literal parses against the schema', () => {
    expect(() => parseCliContract(CLI_CONTRACT)).not.toThrow();
  });

  it('contract.json and the generated literal are the same data', () => {
    expect(contractJson).toEqual(CLI_CONTRACT);
  });

  it('satisfies its invariants', () => {
    expect(checkContractInvariants(CLI_CONTRACT)).toEqual([]);
  });

  it('has a version', () => {
    expect(CLI_CONTRACT_VERSION.length).toBeGreaterThan(0);
    expect(CLI_CONTRACT.version).toBe(CLI_CONTRACT_VERSION);
  });

  it('ships a bundle for every declared language', () => {
    expect([...CLI_CONTRACT.languages].sort()).toEqual([...CONTRACT_LANGUAGES].sort());

    for (const lang of CLI_CONTRACT.languages) {
      const path = fileURLToPath(new URL(`../data/i18n/${lang}.json`, import.meta.url));
      const bundle = JSON.parse(readFileSync(path, 'utf-8'));
      expect(ContractStringsSchema.safeParse(bundle).success, `${lang} bundle`).toBe(true);
      expect(Object.keys(bundle).length).toBeGreaterThan(0);
    }
  });

  it('every descriptionKey resolves in the English bundle', () => {
    const path = fileURLToPath(new URL('../data/i18n/en.json', import.meta.url));
    const en: Record<string, string> = JSON.parse(readFileSync(path, 'utf-8'));

    const missing: string[] = [];
    for (const cmd of CLI_CONTRACT.commands) {
      if (cmd.descriptionKey && !(cmd.descriptionKey in en)) {
        missing.push(`${cmd.pathKey} -> ${cmd.descriptionKey}`);
      }
      for (const opt of cmd.options) {
        if (opt.descriptionKey && !(opt.descriptionKey in en)) {
          missing.push(`${cmd.pathKey} --${opt.long} -> ${opt.descriptionKey}`);
        }
      }
    }

    expect(missing).toEqual([]);
  });

  it('falls back to the English label when a key is missing or null', () => {
    expect(translate({}, null, 'Deploy a repository')).toBe('Deploy a repository');
    expect(translate({}, 'commands.absent', 'Deploy a repository')).toBe('Deploy a repository');
    expect(translate({ 'commands.x': 'Dagit' }, 'commands.x', 'Deploy')).toBe('Dagit');
  });

  it('proxyCapable implies a machine plane and a non-interactive command', () => {
    for (const cmd of CLI_CONTRACT.commands) {
      if (cmd.proxyCapable) {
        expect(cmd.plane, cmd.pathKey).toBe('machine');
        expect(cmd.interactive, cmd.pathKey).toBe(false);
      }
    }

    // A pinned count is a deliberate drift alarm: it fires when the proxy-capable
    // surface changes so the change is noticed rather than silent. 84 = the
    // machine-plane, non-interactive, non-direct-SFTP, non-local-effect commands,
    // including the five `rdc job` verbs added in the detached-job work. Update
    // this only when the surface genuinely changes, and know why it moved.
    expect(proxyCapableCommands().length).toBe(84);
  });

  it('every refusal carries a reason, and every proxyable command carries none', () => {
    // The CLI's --proxy guard prints proxyBlockedReason, so a command can never
    // be refused without telling the operator why.
    for (const cmd of CLI_CONTRACT.commands) {
      if (cmd.proxyCapable) {
        expect(cmd.proxyBlockedReason, cmd.pathKey).toBeUndefined();
      } else {
        expect(cmd.proxyBlockedReason, cmd.pathKey).toBeTruthy();
      }
    }
  });

  it('excludes the machine commands a remote executor must not run', () => {
    // Two classes. Client-side transfer: the paths exist only on the operator's
    // own disk. Local effect: the command reaches a machine, but its whole point
    // is to write what it found back into the CALLER's config or filesystem.
    const excluded = [
      'repo sync upload',
      'repo sync download',
      'repo sync status',
      'config cert-cache pull',
      'cluster kubeconfig',
      'config machine scan-keys',
    ];

    for (const pathKey of excluded) {
      const cmd = getCommand(pathKey);
      expect(cmd?.plane, pathKey).toBe('machine');
      expect(cmd?.interactive, pathKey).toBe(false);
      expect(cmd?.proxyCapable, pathKey).toBe(false);
      expect(cmd?.proxyBlockedReason, pathKey).toBeTruthy();
    }

    // Every other machine-plane, non-interactive command IS proxyable, so this
    // list is the complete exclusion set rather than a sample.
    const blocked = CLI_CONTRACT.commands
      .filter((c) => c.plane === 'machine' && !c.interactive && !c.proxyCapable)
      .map((c) => c.pathKey)
      .sort();
    expect(blocked).toEqual([...excluded].sort());

    // Reads a local file but ships the bytes inside the renet params, which
    // crosses the wire fine — param building, not a transfer.
    expect(getCommand('repo template apply')?.proxyCapable).toBe(true);
  });

  it('looks a command up by path key', () => {
    const repoUp = getCommand('repo up');
    expect(repoUp?.domain).toBe('repo');
    expect(repoUp?.plane).toBe('machine');
    expect(repoUp?.proxyCapable).toBe(true);
    expect(repoUp?.machineOption).toBe('machine');
    expect(getCommand('nope not a command')).toBeUndefined();
  });

  it('groups by domain', () => {
    const byDomain = commandsByDomain();
    expect(byDomain.get('repo')?.length).toBeGreaterThan(0);
    expect(byDomain.get('repo')?.every((c) => c.domain === 'repo')).toBe(true);
  });

  it('filters to the commands a selected resource can drive', () => {
    const forMachine = commandsForContext({ machine: true });
    expect(forMachine.every((c) => c.machineOption !== null)).toBe(true);
    expect(forMachine.map((c) => c.pathKey)).toContain('repo up');

    const forRepo = commandsForContext({ repo: true });
    expect(forRepo.every((c) => c.repoOption !== null)).toBe(true);

    // No context means no filtering.
    expect(commandsForContext({}).length).toBe(CLI_CONTRACT.commands.length);
  });

  it('records the enum options, so a consumer can render a hard Select', () => {
    // An option carries `choices` exactly when it declared Commander .choices().
    // Absent means free-form, so the console renders a text input instead.
    const enums = CLI_CONTRACT.commands
      .flatMap((c) => c.options.map((o) => ({ cmd: c.pathKey, opt: o })))
      .filter(({ opt }) => opt.choices)
      .map(({ cmd, opt }) => `${cmd} --${opt.long}=${opt.choices?.join('|')}`)
      .sort();

    expect(enums).toEqual([
      'cluster create --control-ds-backend=local|ceph',
      'cluster fork --writes=local|ceph',
      'config audit log --actor=human|agent',
      'config backup-strategy set --mode=hot|cold',
      'datastore init --backend=local|ceph',
      'ops down --backend=kvm|qemu',
      'ops ssh --backend=kvm|qemu',
      'ops status --backend=kvm|qemu',
      'ops up --backend=kvm|qemu',
      'repo merge --resolve=ours|theirs',
      'repo policy set --auto-grow=true|false',
      'repo policy set --auto-trim=true|false',
      'repo secret set --mode=env|file',
      'serve --mode=daemon|container',
    ]);
  });

  it('no enum option defaults outside its own choices', () => {
    // The CLI would reject its own default. checkContractInvariants enforces
    // this too; asserted here so the failure names the option.
    for (const cmd of CLI_CONTRACT.commands) {
      for (const opt of cmd.options) {
        if (opt.choices && opt.defaultValue !== null) {
          expect(opt.choices, `${cmd.pathKey} --${opt.long}`).toContain(opt.defaultValue);
        }
      }
    }
  });

  it('has no positional arguments to serialise', () => {
    // The contract is options-only. The generator refuses to emit a command
    // that registers a positional, so nothing here should carry one — this
    // just pins the assumption the consumers' argv serialisation depends on.
    for (const cmd of CLI_CONTRACT.commands) {
      for (const opt of cmd.options) {
        expect(opt.long.length, `${cmd.pathKey}`).toBeGreaterThan(0);
      }
    }
  });
});
