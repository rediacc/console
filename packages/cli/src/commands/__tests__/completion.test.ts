/**
 * `rdc completion <shell>` and `rdc __complete` (D9 of PLAN-console-command-line).
 *
 * The bash script is sourced and driven for real: static words, a name lookup
 * through a stub `rdc` on PATH, the per-session cache keyed on the config
 * file's mtime, and the latency of a static completion. zsh, fish and pwsh get
 * their parser's syntax check where the binary is installed.
 */

import { execFileSync, spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, resolve } from 'node:path';
import { CLI_CONTRACT, type CliContract } from '@rediacc/shared/cli-contract';
import { describe, expect, it } from 'vitest';
import {
  buildCompletionModel,
  COMPLETE_COMMAND,
  COMPLETION_SHELLS,
  completeNames,
  isCompleteInvocation,
  renderCompletionScript,
} from '../completion.js';

const CLI_ROOT = resolve(import.meta.dirname, '../../..');
const work = mkdtempSync(join(tmpdir(), 'rdc-completion-'));

function hasBinary(name: string): boolean {
  return spawnSync('sh', ['-c', `command -v ${name}`], { stdio: 'ignore' }).status === 0;
}

function writeScript(shell: string): string {
  const file = join(work, `rdc.${shell}`);
  writeFileSync(file, renderCompletionScript(shell as never, CLI_CONTRACT));
  return file;
}

const FIXTURE_CONFIG = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-000000000001',
  version: 1,
  resources: {
    machines: { 'server-1': {}, 'server-2': {} },
    repositories: {
      shop: { grand: 'base', tags: { base: {}, test: {} } },
      mail: { grand: 'base', tags: { base: {} } },
    },
  },
};

function configDir(): string {
  const dir = join(process.env.XDG_CONFIG_HOME as string, 'rediacc');
  mkdirSync(dir, { recursive: true });
  return dir;
}

function writeConfig(name: string, body: unknown): string {
  const file = join(configDir(), `${name}.json`);
  writeFileSync(file, JSON.stringify(body));
  return file;
}

interface Drive {
  env?: NodeJS.ProcessEnv;
  /** The word bash itself hands over as COMP_WORDS[COMP_CWORD], when COMP_WORDBREAKS splits it. */
  bashWord?: string;
  /** Shell code run between the two Tabs of one session. */
  between?: string;
}

/**
 * Press Tab twice in one bash session on `line` (cursor at the end) and return
 * the second answer, one candidate per element.
 */
function bashComplete(script: string, line: string, drive: Drive = {}) {
  const driver = [
    'source "$1"',
    'COMP_LINE="$2"; COMP_POINT=${#COMP_LINE}',
    'read -ra COMP_WORDS <<< "$COMP_LINE"',
    'case $COMP_LINE in *" ") COMP_WORDS+=("") ;; esac',
    'COMP_CWORD=$((${#COMP_WORDS[@]} - 1))',
    '[ -z "$3" ] || COMP_WORDS[COMP_CWORD]="$3"',
    '_rdc_bash',
    'eval "$4"',
    '_rdc_bash',
    'printf "%s\\n" "${COMPREPLY[@]}"',
  ].join('\n');
  const args = ['-c', driver, 'bash', script, line, drive.bashWord ?? '', drive.between ?? ''];
  const out = execFileSync('bash', args, { env: drive.env ?? process.env, encoding: 'utf-8' });
  return out.split('\n').filter(Boolean);
}

describe('rdc completion: static words', () => {
  const model = buildCompletionModel(CLI_CONTRACT);
  const nodes = new Map(model.nodes.map((n) => [n.key, n]));

  it('offers every top-level domain of the contract at the root', () => {
    const domains = [...new Set(CLI_CONTRACT.commands.map((c) => c.path[0]))];
    expect(nodes.get('rdc')?.children).toEqual(domains);
    expect(domains).toContain('completion');
  });

  it('carries every command of the contract with its own flags and positionals', () => {
    for (const command of CLI_CONTRACT.commands) {
      const node = nodes.get(`rdc ${command.pathKey}`);
      expect(node?.runnable, command.pathKey).toBe(true);
      expect(node?.flags).toEqual(command.options.map((o) => `--${o.long}`));
      expect(node?.positionals).toHaveLength(command.positionals.length);
    }
  });

  it('binds config kinds and choices to their value slots', () => {
    const fork = nodes.get('rdc repo fork');
    expect(fork?.positionals).toEqual([['@repo']]);
    const withChoices = CLI_CONTRACT.commands.find((c) =>
      c.options.some((o) => (o.choices?.length ?? 0) > 0)
    );
    const option = withChoices?.options.find((o) => (o.choices?.length ?? 0) > 0);
    const spec = nodes
      .get(`rdc ${withChoices?.pathKey}`)
      ?.flagValues.find(([flag]) => flag === `--${option?.long}`)?.[1];
    expect(spec?.slice(0, option?.choices?.length)).toEqual(option?.choices);
  });

  it('keeps the hidden __complete out of the contract', () => {
    expect(CLI_CONTRACT.commands.some((c) => c.path[0] === COMPLETE_COMMAND)).toBe(false);
  });

  it('refuses a contract word that is not safe to print into a shell script', () => {
    const command = structuredClone(CLI_CONTRACT.commands.find((c) => c.pathKey === 'repo fork'));
    if (!command) throw new Error('repo fork is missing from the contract');
    command.options[0] = { ...command.options[0], choices: ["a'b"] };
    const contract: CliContract = { ...CLI_CONTRACT, commands: [command] };
    expect(() => buildCompletionModel(contract)).toThrow(/a'b/);
  });
});

describe('rdc completion: shell syntax', () => {
  it('bash -n accepts the bash script', () => {
    expect(spawnSync('bash', ['-n', writeScript('bash')]).status).toBe(0);
  });

  const checks: [string, string, string[]][] = [
    ['zsh', 'zsh', ['-n']],
    ['fish', 'fish', ['--no-execute']],
  ];
  for (const [shell, binary, args] of checks) {
    const present = hasBinary(binary);
    const title = present
      ? `${binary} ${args.join(' ')} accepts the ${shell} script`
      : `${binary} ${args.join(' ')} accepts the ${shell} script (skipped: ${binary} is not installed)`;
    it.skipIf(!present)(title, () => {
      const result = spawnSync(binary, [...args, writeScript(shell)], { encoding: 'utf-8' });
      expect(result.stderr).toBe('');
      expect(result.status).toBe(0);
    });
  }

  const pwsh = hasBinary('pwsh');
  it.skipIf(!pwsh)(
    pwsh
      ? 'pwsh parses the PowerShell script'
      : 'pwsh parses the PowerShell script (skipped: pwsh is not installed)',
    () => {
      const file = writeScript('pwsh');
      const command = `$e=$null; [System.Management.Automation.Language.Parser]::ParseFile('${file}', [ref]$null, [ref]$e) | Out-Null; if ($e.Count) { $e; exit 1 }`;
      expect(spawnSync('pwsh', ['-NoProfile', '-Command', command]).status).toBe(0);
    }
  );

  // The parser checks above are skipped on a host without the shell. This structural
  // check always runs, so a broken quote or bracket in the zsh, fish or pwsh script
  // still fails there, though it is no replacement for the parser.
  for (const shell of ['zsh', 'fish', 'pwsh']) {
    it(`${shell} script has balanced quotes and brackets (runs without the ${shell} binary)`, () => {
      const code = readFileSync(writeScript(shell), 'utf-8')
        .split('\n')
        .filter((line) => !/^\s*#/.test(line))
        .join('\n');
      expect((code.match(/'/g) ?? []).length % 2, 'single quotes').toBe(0);
      // zsh `case` arms (`*)`) carry unmatched parentheses by design.
      const pairs = [['{', '}'], ['[', ']'], ...(shell === 'zsh' ? [] : [['(', ')']])];
      for (const [open, close] of pairs) {
        expect(code.split(open).length, `${open}${close}`).toBe(code.split(close).length);
      }
    });
  }

  it('renders a script for every supported shell', () => {
    for (const shell of COMPLETION_SHELLS) {
      expect(renderCompletionScript(shell, CLI_CONTRACT)).toContain("'rdc repo fork'");
    }
  });
});

describe('rdc completion bash: driven for real', () => {
  const script = writeScript('bash');

  it('completes domains, subcommands and flags from the static words', () => {
    expect(bashComplete(script, 'rdc rep')).toEqual(['repo']);
    expect(bashComplete(script, 'rdc repo f')).toContain('fork');
    expect(bashComplete(script, 'rdc repo fork --t')).toEqual(['--tag']);
    expect(bashComplete(script, 'rdc -o json repo fo')).toEqual(['fork']);
  });

  it('asks rdc __complete for names once per config mtime, honouring --config', () => {
    const bin = join(work, 'bin');
    const log = join(work, 'stub.log');
    mkdirSync(bin, { recursive: true });
    writeFileSync(log, '');
    const stub = join(bin, 'rdc');
    writeFileSync(stub, `#!/bin/sh\necho "$*" >> '${log}'\nprintf 'shop\\nshop:test\\nmail\\n'\n`, {
      mode: 0o755,
    });
    const file = writeConfig('stubbed', FIXTURE_CONFIG);
    const env = { ...process.env, PATH: `${bin}:${process.env.PATH}` };

    const asked = () => readFileSync(log, 'utf-8').trim().split('\n').filter(Boolean);

    // Two Tabs in one shell: the second is served from the session cache.
    expect(bashComplete(script, 'rdc --config stubbed repo fork sh', { env })).toEqual([
      'shop',
      'shop:test',
    ]);
    expect(asked()).toEqual(['__complete --kind repo --config stubbed']);

    // A changed mtime between the Tabs is a miss. Bash split `shop:` at the colon,
    // so only the part after it is handed back.
    writeFileSync(log, '');
    const touch = `touch -d '@${Math.floor(Date.now() / 1000) + 60}' '${file}'`;
    expect(
      bashComplete(script, 'rdc --config=stubbed repo fork shop:', {
        env,
        bashWord: ':',
        between: touch,
      })
    ).toEqual([':test']);
    expect(asked()).toEqual([
      '__complete --kind repo --config stubbed',
      '__complete --kind repo --config stubbed',
    ]);
  });

  it('does not cache a failed lookup: the next Tab asks again', () => {
    const bin = join(work, 'bin-failing');
    const log = join(work, 'failing.log');
    mkdirSync(bin, { recursive: true });
    writeFileSync(log, '');
    writeFileSync(
      join(bin, 'rdc'),
      `#!/bin/sh\necho "$*" >> '${log}'\nprintf 'half\\n'\nexit 1\n`,
      {
        mode: 0o755,
      }
    );
    writeConfig('failing', FIXTURE_CONFIG);
    const env = { ...process.env, PATH: `${bin}:${process.env.PATH}` };
    expect(bashComplete(script, 'rdc --config failing repo fork ', { env })).toEqual([]);
    expect(readFileSync(log, 'utf-8').trim().split('\n')).toEqual([
      '__complete --kind repo --config failing',
      '__complete --kind repo --config failing',
    ]);
  });

  it('asks nothing when the config file does not exist', () => {
    const bin = join(work, 'bin-missing');
    const log = join(work, 'missing.log');
    mkdirSync(bin, { recursive: true });
    writeFileSync(log, '');
    writeFileSync(join(bin, 'rdc'), `#!/bin/sh\necho "$*" >> '${log}'\n`, { mode: 0o755 });
    const env = { ...process.env, PATH: `${bin}:${process.env.PATH}` };
    expect(bashComplete(script, 'rdc --config absent repo fork ', { env })).toEqual([]);
    expect(readFileSync(log, 'utf-8')).toBe('');
  });

  it('completes `rdc repo f` under 100 ms p50 over 20 runs', () => {
    const samples: number[] = [];
    for (let i = 0; i < 20; i++) {
      const start = performance.now();
      const words = bashComplete(script, 'rdc repo f');
      samples.push(performance.now() - start);
      expect(words).toContain('fork');
    }
    samples.sort((a, b) => a - b);
    const p50 = (samples[9] + samples[10]) / 2;
    expect(p50).toBeLessThan(100);
  });
});

describe('rdc __complete', () => {
  it('prints the repository refs of a config: the grand tag bare, a fork as name:tag', () => {
    writeConfig('fixture', FIXTURE_CONFIG);
    expect(completeNames({ kind: 'repo', config: 'fixture' })).toEqual([
      'shop',
      'shop:test',
      'mail',
    ]);
    expect(completeNames({ kind: 'machine', config: 'fixture' })).toEqual(['server-1', 'server-2']);
    expect(completeNames({ kind: 'cluster', config: 'fixture' })).toEqual([]);
  });

  it('reads REDIACC_CONFIG when no --config is given', () => {
    writeConfig('from-env', FIXTURE_CONFIG);
    process.env.REDIACC_CONFIG = 'from-env';
    try {
      expect(completeNames({ kind: 'machine' })).toEqual(['server-1', 'server-2']);
    } finally {
      delete process.env.REDIACC_CONFIG;
    }
  });

  it('refuses a kind the config file cannot answer, a missing file and a remote pointer', () => {
    writeConfig('fixture', FIXTURE_CONFIG);
    expect(() => completeNames({ kind: 'container', config: 'fixture' })).toThrow(/container/);
    expect(() => completeNames({ kind: 'repo', config: 'nowhere' })).toThrow(/nowhere\.json/);
    writeConfig('remote', { ...FIXTURE_CONFIG, resources: undefined, remote: { apiUrl: 'x' } });
    expect(() => completeNames({ kind: 'repo', config: 'remote' })).toThrow(/remote/);
    writeConfig('broken', { ...FIXTURE_CONFIG, resources: { repositories: { shop: 1 } } });
    expect(() => completeNames({ kind: 'repo', config: 'broken' })).toThrow(/broken\.json/);
  });

  it('keeps the parser text of a malformed config out of the error', () => {
    const file = join(configDir(), 'secretive.json');
    writeFileSync(file, 's3cr3t-value');
    let message = '';
    try {
      completeNames({ kind: 'repo', config: 'secretive' });
    } catch (error) {
      message = String(error);
    }
    expect(message).toMatch(/secretive\.json/);
    expect(message).not.toContain('s3cr3t-value');
  });

  it('reads only a plain config name from the config dir', () => {
    writeFileSync(join(work, 'outside.json'), JSON.stringify(FIXTURE_CONFIG));
    const escape = relative(configDir(), join(work, 'outside'));
    expect(() => completeNames({ kind: 'repo', config: escape })).toThrow(/plain config name/);
    expect(() => completeNames({ kind: 'repo', config: '..' })).toThrow(/plain config name/);
    writeConfig('plain-name_1', FIXTURE_CONFIG);
    expect(completeNames({ kind: 'machine', config: 'plain-name_1' })).toEqual([
      'server-1',
      'server-2',
    ]);
  });

  it('is answered by the CLI entry without the full command tree', () => {
    expect(isCompleteInvocation(['node', 'rdc', COMPLETE_COMMAND])).toBe(true);
    expect(isCompleteInvocation(['node', 'rdc', 'repo', COMPLETE_COMMAND])).toBe(false);
    writeConfig('spawned', FIXTURE_CONFIG);
    const result = spawnSync(
      'npx',
      ['tsx', 'src/index.ts', COMPLETE_COMMAND, '--kind', 'repo', '--config', 'spawned'],
      { cwd: CLI_ROOT, encoding: 'utf-8', env: process.env, timeout: 120_000 }
    );
    expect(result.stderr).toBe('');
    expect(result.stdout).toBe('shop\nshop:test\nmail\n');
    expect(result.status).toBe(0);
  }, 120_000);
});
