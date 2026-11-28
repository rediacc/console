import { describe, expect, it } from 'vitest';
import { CLI_CONTRACT } from '../../cli-contract/index.js';
import { fillVariables, type ParsedRecipe, parseRecipe, renderStep } from '../recipe.js';
import { analyze } from '../state.js';

const parse = (text: string): ParsedRecipe => parseRecipe(text, CLI_CONTRACT);
const codes = (text: string): string[] => parse(text).problems.map((p) => p.code);

const GOOD = [
  '# Fork a repo for testing',
  '# then bring the fork up',
  '$repo = required "Which repo?"',
  '$tag = "t1"',
  '',
  'rdc repo fork $repo --tag $tag',
  'rdc repo up $repo:$tag',
].join('\n');

describe('parseRecipe', () => {
  it('control: a well-formed recipe has variables, steps and no problem', () => {
    const recipe = parse(GOOD);
    expect(recipe.problems).toEqual([]);
    expect(recipe.description).toBe('Fork a repo for testing\nthen bring the fork up');
    expect(recipe.variables).toEqual([
      expect.objectContaining({
        name: 'repo',
        required: true,
        prompt: 'Which repo?',
        default: null,
      }),
      expect.objectContaining({ name: 'tag', required: false, prompt: null, default: 't1' }),
    ]);
    expect(recipe.steps.map((s) => [s.command?.pathKey, s.variables, s.destructive])).toEqual([
      ['repo fork', ['repo', 'tag'], false],
      ['repo up', ['repo', 'tag'], false],
    ]);
  });

  it('anchors steps and declarations at body offsets', () => {
    const recipe = parse(GOOD);
    for (const step of recipe.steps) expect(GOOD.slice(step.start, step.end)).toBe(step.text);
    const decl = recipe.variables[0];
    expect(GOOD.slice(decl.start, decl.end)).toBe('$repo = required "Which repo?"');
  });

  it('flags an undeclared variable on its token', () => {
    const text = '$a = "x"\nrdc repo fork $a --tag $missing';
    const [problem] = parse(text).problems;
    expect(problem.code).toBe('undeclared-variable');
    expect(text.slice(problem.start, problem.end)).toBe('$missing');
    expect(problem.line).toBe(1);
  });

  it('does not substitute inside single quotes', () => {
    expect(codes(`rdc repo fork shop --tag '$literal'`)).toEqual([]);
  });

  it('flags a term step as not proxy-capable on the command words', () => {
    const text = 'rdc term connect shop';
    const found = parse(text).problems.find((p) => p.code === 'not-proxy-capable');
    expect(found).toBeDefined();
    expect(text.slice(found?.start, found?.end)).toBe('term connect');
    expect(found?.message).toContain('cannot run in the console');
  });

  it('control: a proxy-capable step has no such problem', () => {
    expect(codes('rdc repo up shop')).toEqual([]);
  });

  it('marks a destructive step', () => {
    const [step] = parse('rdc repo delete shop').steps;
    expect(step.destructive).toBe(true);
  });

  it('reports command diagnostics on the step with body offsets', () => {
    const text = '$t = "a"\nrdc repo frok shop';
    const found = parse(text).problems.find((p) => p.code === 'unknown-command');
    expect(text.slice(found?.start, found?.end)).toBe('frok');
    expect(found?.line).toBe(1);
  });

  it('ignores a $variable where a choice is required but flags a real bad choice', () => {
    expect(codes('$m = "ours"\nrdc repo merge shop --from t1 --resolve $m')).toEqual([]);
    expect(codes('rdc repo merge shop --from t1 --resolve mine')).toEqual(['invalid-choice']);
  });

  it('flags a line that is not an rdc step', () => {
    expect(codes('echo hi')).toContain('not-rdc');
  });

  it('flags bad, duplicate and late declarations', () => {
    expect(codes('$x = required\nrdc repo up shop')).toEqual(['bad-declaration']);
    expect(codes('$x = hello\nrdc repo up shop')).toEqual(['bad-declaration']);
    expect(codes('$x\nrdc repo up shop')).toEqual(['bad-declaration']);
    expect(codes('$x = "a"\n$x = "b"\nrdc repo up shop')).toEqual(['duplicate-variable']);
    expect(codes('rdc repo up shop\n$x = "a"')).toEqual(['late-declaration']);
    expect(codes('$x = "unclosed\nrdc repo up shop')).toEqual(['bad-declaration']);
  });

  it('accepts an empty default', () => {
    const recipe = parse('$x = ""\nrdc repo up shop');
    expect(recipe.problems).toEqual([]);
    expect(recipe.variables[0].default).toBe('');
  });

  it('flags a recipe without a step, and an empty body', () => {
    expect(codes('# only a note')).toEqual(['no-steps']);
    expect(codes('')).toEqual(['no-steps']);
  });

  it('returns problems in body order', () => {
    const found = parse('echo hi\nrdc term connect shop\n$x = "late"').problems;
    const starts = found.map((p) => p.start);
    expect(starts).toEqual([...starts].sort((a, b) => a - b));
  });

  it('keeps Arabic text in a default and a quoted step argument', () => {
    const recipe = parse('$note = "مرحبا بالعالم"\nrdc repo fork shop --tag "$note"');
    expect(recipe.problems).toEqual([]);
    expect(recipe.variables[0].default).toBe('مرحبا بالعالم');
  });
});

describe('fillVariables', () => {
  const recipe = parse(GOOD);

  it('a default fills when no answer is given', () => {
    expect(fillVariables(recipe, { repo: 'shop' })).toEqual({
      values: { repo: 'shop', tag: 't1' },
      missing: [],
    });
  });

  it('an answer beats the default', () => {
    expect(fillVariables(recipe, { repo: 'shop', tag: 'x' }).values.tag).toBe('x');
  });

  it('a blank answer falls back to the default, and a required one is missing', () => {
    expect(fillVariables(recipe, { repo: '  ', tag: '' })).toEqual({
      values: { tag: 't1' },
      missing: ['repo'],
    });
  });
});

describe('renderStep', () => {
  const recipe = parse(GOOD);

  it('substitutes values and the result parses as the same command', () => {
    const line = renderStep(recipe.steps[0], { repo: 'shop', tag: 't1' });
    expect(line).toBe('rdc repo fork shop --tag t1');
    const state = analyze({ contract: CLI_CONTRACT, source: () => [] }, line);
    expect(state.parsed.values).toEqual({ ref: 'shop', tag: 't1' });
  });

  it('quotes a value with spaces and keeps a flag token a flag', () => {
    const line = renderStep(recipe.steps[0], { repo: 'my shop', tag: 'a b' });
    expect(line).toBe(`rdc repo fork 'my shop' --tag 'a b'`);
    const eq = parse('$t = "x"\nrdc repo fork shop --tag=$t').steps[0];
    const rendered = renderStep(eq, { t: 'a b' });
    expect(rendered).toBe(`rdc repo fork shop --tag='a b'`);
    const state = analyze({ contract: CLI_CONTRACT, source: () => [] }, rendered);
    expect(state.parsed.values.tag).toBe('a b');
  });

  it('quotes a substituted value that starts with a dash so it cannot read as a flag', () => {
    const line = renderStep(recipe.steps[0], { repo: '-x', tag: 't' });
    expect(line).toBe(`rdc repo fork '-x' --tag t`);
    const state = analyze({ contract: CLI_CONTRACT, source: () => [] }, line);
    expect(state.parsed.values.ref).toBe('-x');
    expect(state.parsed.flags.map((f) => f.name)).toEqual(['--tag']);
  });

  it('leaves a single-quoted word literal and an undeclared variable as written', () => {
    const step = parse(`rdc repo fork shop --tag '$tag'`).steps[0];
    expect(renderStep(step, { tag: 'x' })).toBe(`rdc repo fork shop --tag '$tag'`);
    const open = parse('rdc repo fork $nope --tag t').steps[0];
    expect(renderStep(open, {})).toBe(`rdc repo fork '$nope' --tag t`);
  });
});
