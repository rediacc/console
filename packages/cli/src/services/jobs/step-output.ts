import { outputService } from '../core/output.js';
import { setExitCode } from '../core/request-context.js';

/**
 * The output a step asked for with `needsOutput`, or `undefined` after saying the result could not be read and
 * setting exit 1. Blank output is a broken read, not an empty answer: a verb that really has nothing to report
 * still prints a document (`{"entries":[]}`, `{}`, a summary object), so only a step that received no text lands here.
 */
export function requireStepOutput(output: string | undefined, what: string): string | undefined {
  if (output !== undefined && output.trim() !== '') return output;
  outputService.error(`${what}: the result could not be read (no output was returned).`);
  setExitCode(1);
  return undefined;
}
