/** The lookup tables and the shell-literal tag every completion renderer shares. */

import type { CompletionModel } from './completion.js';

/** Lookup tables shared by the renderers: key to a word list. */
export interface Tables {
  children: [string, string[]][];
  runnable: string[];
  flags: [string, string[]][];
  valueFlags: [string, string[]][];
  flagValues: [string, string[]][];
  /** `count variadic` per runnable command with positionals. */
  posInfo: [string, string[]][];
  positionals: [string, string[]][];
}

export function tablesOf(model: CompletionModel): Tables {
  const nonEmpty = (rows: [string, string[]][]) => rows.filter(([, words]) => words.length > 0);
  const nodes = model.nodes;
  return {
    children: nonEmpty(nodes.map((n) => [n.key, n.children])),
    runnable: nodes.filter((n) => n.runnable).map((n) => n.key),
    flags: nonEmpty(nodes.map((n) => [n.key, n.flags])),
    valueFlags: nonEmpty(nodes.map((n) => [n.key, n.valueFlags])),
    flagValues: nodes.flatMap((n) =>
      n.flagValues.map(([flag, spec]): [string, string[]] => [`${n.key}|${flag}`, spec])
    ),
    posInfo: nodes
      .filter((n) => n.positionals.length > 0)
      .map((n) => [n.key, [String(n.positionals.length), n.variadic ? '1' : '0']]),
    positionals: nodes.flatMap((n) =>
      n.positionals
        .map((spec, i): [string, string[]] => [`${n.key}|${i}`, spec])
        .filter(([, spec]) => spec.length > 0)
    ),
  };
}

/**
 * A shell source literal: written raw, with `$~{` standing for `${` so a
 * shell parameter expansion is never read as a template placeholder.
 */
export function shell(strings: TemplateStringsArray): string {
  return String.raw({ raw: strings.raw }).replaceAll('$~{', '${');
}
