import { isMachineReadable } from './output-format.js';
import { writeStderr, writeStdout } from './request-context.js';

/** Progress or status text goes to stdout, or to stderr under -o json/yaml/csv so stdout stays the one result document. */
export function writeProgress(text: string): void {
  if (isMachineReadable()) writeStderr(text);
  else writeStdout(text);
}
