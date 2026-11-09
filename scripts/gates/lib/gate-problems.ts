/**
 * Shared finding collector for the gates that gather `problems: string[]` and report them
 * once at the end. The gates add a finding through this one verb, so a later change to how a
 * finding is recorded (a dedupe, a severity) lands here instead of at each call site.
 */
export function recordProblem(problems: string[], text: string): void {
  problems.push(text);
}
