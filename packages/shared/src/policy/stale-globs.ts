/**
 * Stale command globs — the one classification system that fails OPEN.
 *
 * A policy rule carries command globs (`schema.ts`), and the two halves fail in
 * opposite directions when a command is renamed out from under them:
 *
 *   allow: ['repo takeover']   CLOSED. The command is refused. Loud, safe; a
 *                              user reports it the first time they hit it.
 *   deny:  ['repo takeover']   OPEN. The moment the leaf becomes `repo promote`,
 *                              the deny SILENTLY STOPS DENYING. The command the
 *                              organization explicitly forbade is now permitted,
 *                              and nothing anywhere says a word.
 *
 * The policy loader (`services/serve/policy.ts`) already refuses a MALFORMED
 * document, and states why: "quietly ignoring them would be the worst possible
 * failure, since it would look like the rules were in force." A document with a
 * stale deny glob is exactly that failure — well-formed, and NOT in force. So it
 * gets the same treatment: a stale deny is a hard refusal, not a warning.
 *
 * A stale ALLOW glob is reported but is not fatal, and the asymmetry is
 * deliberate. An allow glob that matches nothing already fails closed, so
 * refusing to start over one would convert a safe, self-announcing condition
 * into a total executor outage. Denying is where silence is dangerous.
 */
import { matchesGlob } from './evaluate.js';
import type { PolicyDocument, PolicyRule } from './schema.js';

export interface StaleGlobs {
  /** Deny globs matching no live command. Dangerous: they protect nothing. */
  deny: string[];
  /** Allow globs matching no live command. Safe (fail-closed) but still wrong. */
  allow: string[];
}

/**
 * Every rule in the document: the defaults, plus each team's and each user's.
 *
 * A deny buried in a team or user rule fails open exactly like one in the
 * defaults, so none of them may be skipped.
 */
function allRules(doc: PolicyDocument): PolicyRule[] {
  return [doc.defaults, ...Object.values(doc.teams ?? {}), ...Object.values(doc.users ?? {})];
}

/**
 * Command globs in `doc` that match no command in `knownCommands`.
 *
 * `knownCommands` are space-joined contract paths ("repo fork"). Callers pass
 * the LIVE contract, so "stale" means exactly "names no command this binary has".
 */
export function findStaleCommandGlobs(
  doc: PolicyDocument,
  knownCommands: readonly string[]
): StaleGlobs {
  const isStale = (glob: string): boolean =>
    !knownCommands.some((command) => matchesGlob(glob, command));

  const rules = allRules(doc);
  const staleIn = (globsOf: (rule: PolicyRule) => readonly string[] | undefined): string[] => {
    const found = new Set<string>();
    for (const rule of rules) {
      for (const glob of globsOf(rule) ?? []) {
        if (isStale(glob)) found.add(glob);
      }
    }
    return [...found].sort();
  };

  return {
    deny: staleIn((rule) => rule.commands?.deny),
    allow: staleIn((rule) => rule.commands?.allow),
  };
}

/**
 * The refusal text for a document whose deny globs protect nothing.
 *
 * Names every stale glob, because the author has to know WHICH rule stopped
 * being a rule — and because the likeliest cause is that the command was
 * renamed, in which case the fix is a re-key, not a deletion.
 */
export function staleDenyRefusal(staleDeny: readonly string[]): string {
  const globs = staleDeny.map((glob) => `"${glob}"`).join(', ');
  const plural = staleDeny.length === 1 ? 'a command that does not' : 'commands that do not';

  return (
    `The policy document denies ${globs} — ${plural} exist, so ${
      staleDeny.length === 1 ? 'that rule denies' : 'those rules deny'
    } nothing. ` +
    'A deny rule that matches no command is not a safe no-op: it reads as protection that is not ' +
    'there. Most often the command was renamed and the rule was left behind, which means it is ' +
    'now permitted. Re-key the rule to the current command name (or remove it deliberately) in ' +
    'the console under Permissions. No command can be authorized until it is resolved.'
  );
}
