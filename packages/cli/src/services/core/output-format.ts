/** The result format the running command prints in (`-o`). Its only import is type-only and erased at runtime, so `utils/errors.ts` (which sets it) and `output.ts` (which reads it) share it without an import cycle. */

import type { OutputFormat } from '../../types/index.js';

let current: OutputFormat = 'table';

export function setCurrentOutputFormat(format: OutputFormat): void {
  current = format;
}

export function currentOutputFormat(): OutputFormat {
  return current;
}

/** json, yaml and csv put only data on stdout. */
export function isMachineReadable(format: OutputFormat = current): boolean {
  return format === 'json' || format === 'yaml' || format === 'csv';
}
