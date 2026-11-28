/**
 * Diagnostics over the real generated contract (D3 of
 * agent/plans/PLAN-console-command-line.md).
 */
import { describe, expect, it } from 'vitest';
import { CLI_CONTRACT } from '../../cli-contract/index.js';
import { type Diagnostic, diagnose } from '../diagnose.js';
import { parse } from '../parse.js';
import { analyze } from '../state.js';
import { tokenize } from '../tokenize.js';

const env = { contract: CLI_CONTRACT, source: () => [] as string[] };

function problems(line: string): Diagnostic[] {
  return diagnose(analyze(env, line));
}

const codes = (line: string): string[] => problems(line).map((p) => p.code);

describe('parse', () => {
  it('binds the path, positionals and flags the way the form reads them', () => {
    const parsed = parse(
      CLI_CONTRACT,
      tokenize('rdc repo fork shop --tag=t1 --up --checkpoint -o json')
    );
    expect(parsed.command?.pathKey).toBe('repo fork');
    expect(parsed.values).toEqual({ ref: 'shop', tag: 't1', up: 'true', checkpoint: 'true' });
    expect(parsed.flags.find((f) => f.name === '-o')?.spec?.long).toBe('output');
  });

  it('takes the longest command path', () => {
    expect(parse(CLI_CONTRACT, tokenize('rdc repo replicate refresh x')).command?.pathKey).toBe(
      'repo replicate refresh'
    );
    expect(parse(CLI_CONTRACT, tokenize('rdc repo replicate x')).command?.pathKey).toBe(
      'repo replicate'
    );
  });

  it('collects a variadic positional and the words after --', () => {
    const parsed = parse(CLI_CONTRACT, tokenize('rdc repo exec shop -- ls -la /tmp'));
    expect(parsed.command?.pathKey).toBe('repo exec');
    expect(parsed.values.ref).toBe('shop');
    expect(parsed.rest.map((t) => t.text)).toEqual(['ls', '-la', '/tmp']);
  });

  it('marks a value-taking flag at the end of the line as pending', () => {
    const parsed = parse(CLI_CONTRACT, tokenize('rdc repo fork shop --tag'));
    expect(parsed.pending?.name).toBe('--tag');
    expect(parsed.values.tag).toBeUndefined();
  });

  it('leaves the command null and names the first unknown path word', () => {
    const parsed = parse(CLI_CONTRACT, tokenize('rdc repo frok x'));
    expect(parsed.command).toBeNull();
    expect(parsed.unknownPath?.text).toBe('frok');
  });

  it('reads nothing from a line that does not start with rdc', () => {
    const parsed = parse(CLI_CONTRACT, tokenize('ls -la'));
    expect(parsed.hasRdc).toBe(false);
    expect(parsed.command).toBeNull();
  });
});

describe('diagnose', () => {
  it('control: a complete, valid line has no problem, and neither does an empty line', () => {
    expect(problems('rdc repo fork shop --tag t1')).toEqual([]);
    expect(problems('rdc backup strategy set s --mode hot --dry-run')).toEqual([]);
    expect(problems('')).toEqual([]);
    expect(problems('rdc ')).toEqual([]);
    expect(problems('rdc repo ')).toEqual([]);
  });

  it('suggests the nearest flag for a typo, with the flag token span', () => {
    const line = 'rdc backup repair shop --dyr-run';
    const [problem] = problems(line);
    expect(problem).toMatchObject({
      code: 'unknown-flag',
      suggestion: '--dry-run',
      messageKey: 'commandLine.diagnostic.unknown-flag',
    });
    expect(line.slice(problem.start, problem.end)).toBe('--dyr-run');
    expect(problem.message).toContain('--dry-run');
  });

  it('gives no suggestion for a flag nothing resembles', () => {
    const [problem] = problems('rdc repo fork shop --tag t --zzzzzz');
    expect(problem.code).toBe('unknown-flag');
    expect(problem.suggestion).toBeUndefined();
  });

  it('suggests the nearest subcommand and domain, anchored on the word', () => {
    const line = 'rdc repo frok shop';
    const [sub] = problems(line);
    expect(sub).toMatchObject({ code: 'unknown-command', suggestion: 'fork' });
    expect(line.slice(sub.start, sub.end)).toBe('frok');
    expect(problems('rdc rpeo list')[0]).toMatchObject({
      code: 'unknown-command',
      suggestion: 'repo',
    });
  });

  it('does not suggest a short word that merely sits within two edits', () => {
    const [problem] = problems('rdc qq');
    expect(problem.code).toBe('unknown-command');
    expect(problem.suggestion).toBeUndefined();
  });

  it('reports a missing required positional, zero-width at the end of the line', () => {
    const line = 'rdc repo fork --tag t1';
    expect(problems(line)).toEqual([
      expect.objectContaining({
        code: 'missing-positional',
        params: { name: 'ref' },
        start: line.length,
        end: line.length,
      }),
    ]);
  });

  it('reports a missing mandatory flag', () => {
    const line = 'rdc backup schedule';
    expect(problems(line)).toEqual([
      expect.objectContaining({ code: 'missing-flag', start: line.length, end: line.length }),
    ]);
    expect(codes('rdc backup schedule --machine m1')).toEqual([]);
  });

  it('reports a flag with no value, with its span at the end of the line', () => {
    const line = 'rdc repo fork shop --tag';
    const found = problems(line);
    expect(found).toEqual([
      expect.objectContaining({ code: 'missing-value', start: line.length, end: line.length }),
    ]);
    expect(found.some((p) => p.code === 'missing-flag')).toBe(false);
    expect(found[0].message).toContain('--tag');
  });

  it('reports a value outside choices, spanning the value', () => {
    const line = 'rdc backup strategy set s --mode warm';
    const [problem] = problems(line);
    expect(problem).toMatchObject({ code: 'invalid-choice', params: { choices: 'hot, cold' } });
    expect(line.slice(problem.start, problem.end)).toBe('warm');
    const inline = 'rdc backup strategy set s --mode=warm';
    const [second] = problems(inline);
    expect(inline.slice(second.start, second.end)).toBe('warm');
  });

  it('reports a flag given twice, on the second use, but not a variadic one', () => {
    const line = 'rdc repo fork shop --tag a --tag b';
    const [problem] = problems(line);
    expect(problem.code).toBe('duplicate-flag');
    expect(line.slice(problem.start, problem.end)).toBe('--tag');
    expect(problem.start).toBe(line.lastIndexOf('--tag'));
    const variadic = CLI_CONTRACT.commands
      .flatMap((c) =>
        c.options.filter((o) => o.variadic && o.valueTaking).map((o) => [c, o] as const)
      )
      .at(0);
    if (!variadic) throw new Error('contract has no variadic value-taking option');
    const [cmd, opt] = variadic;
    const required = cmd.positionals.filter((p) => p.required).map(() => 'x');
    const mandatory = cmd.options.filter((o) => o.mandatory && o.long !== opt.long);
    const base = [
      'rdc',
      ...cmd.path,
      ...required,
      ...mandatory.flatMap((o) => [`--${o.long}`, 'x']),
    ];
    expect(codes([...base, `--${opt.long}`, 'a', `--${opt.long}`, 'b'].join(' '))).not.toContain(
      'duplicate-flag'
    );
  });

  it('reports a value on a switch and an extra positional', () => {
    expect(codes('rdc backup strategy set s --dry-run=yes')).toEqual(['unexpected-value']);
    const [extra] = problems('rdc repo fork shop extra --tag t1');
    expect(extra.code).toBe('too-many-positionals');
  });

  it('reports a line that does not start with rdc and an unclosed quote', () => {
    expect(problems('ls -la')).toEqual([
      expect.objectContaining({ code: 'not-rdc', start: 0, end: 2 }),
    ]);
    const line = 'rdc repo fork "shop';
    const open = problems(line).find((p) => p.code === 'unclosed-quote');
    expect(open).toMatchObject({ start: 14, end: line.length });
  });

  it('accepts root options before and after the command words, and a short alias', () => {
    expect(problems('rdc repo fork shop --tag t1 -o json --yes')).toEqual([]);
  });

  it('returns problems in line order', () => {
    const found = problems('rdc repo fork --bogus');
    const starts = found.map((p) => p.start);
    expect(starts).toEqual([...starts].sort((a, b) => a - b));
    expect(found.map((p) => p.code)).toEqual([
      'unknown-flag',
      'missing-positional',
      'missing-flag',
    ]);
  });
});
