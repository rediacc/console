/**
 * Shared finding collector for the gates that gather `problems: string[]` and report them
 * once at the end. A call site names the finding; the list shape stays in one place.
 */
export function recordProblem(problems: string[], text: string): void {
  problems.push(text);
}
