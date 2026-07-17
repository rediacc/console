/**
 * CLI-facing wrapper over the shared ref grammar (`@rediacc/shared/ref`).
 *
 * The grammar itself — the RFC-1123 label rules, the `repo[:tag][@place]` split,
 * the reserved `base` tag, and the exact teaching-error texts — lives in the
 * shared module so the console can parse refs identically. This wrapper adds the
 * only CLI-specific behavior: a {@link RefGrammarError} becomes an exit-2
 * `CliExitError` (VALIDATION_ERROR), so a malformed ref exits the process with a
 * message that names the offending character (spec/03 §2.1).
 *
 * Everything else is a straight re-export; call sites and tests are unchanged.
 */

import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import {
  isValidLabel,
  LABEL_MAX_LENGTH,
  parseRef as sharedParseRef,
  type ParsedRef,
  RefGrammarError,
  RESERVED_TAG,
  type SegmentRole,
  validateLabel as sharedValidateLabel,
  validateTag as sharedValidateTag,
} from '@rediacc/shared/ref';

export { isValidLabel, LABEL_MAX_LENGTH, RESERVED_TAG };
export type { ParsedRef, SegmentRole };

/** Run `fn`, converting a shared RefGrammarError into an exit-2 CliExitError. */
function asExit<T>(fn: () => T): T {
  try {
    return fn();
  } catch (error) {
    if (error instanceof RefGrammarError) {
      throw new CliExitError(ERROR_CODES.VALIDATION_ERROR, error.message);
    }
    throw error;
  }
}

/** Validate one label segment, exiting 2 on a grammar violation. */
export function validateLabel(value: string, role: SegmentRole): void {
  asExit(() => sharedValidateLabel(value, role));
}

/** Validate a fork tag (refuses the reserved `base`), exiting 2 on violation. */
export function validateTag(value: string): void {
  asExit(() => sharedValidateTag(value));
}

/** Parse `repo[:tag][@place]`, exiting 2 (VALIDATION_ERROR) on a grammar violation. */
export function parseRef(input: string): ParsedRef {
  return asExit(() => sharedParseRef(input));
}
