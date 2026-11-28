/**
 * The recovery kit (agent/programs/remote-mcp/02-decisions.md D43): what every enrollment shows the
 * user before it completes, and the check that the kit was saved.
 *
 * The kit carries the recovery code of the user's recovery slot (slots.ts `generateRecoveryCode`).
 * This module renders the CONTENT only (the fields, the code in groups, the QR payload and the
 * instructions); the web turns it into a PDF and a print page, the CLI into a text file and a
 * terminal QR. The code never leaves the client unwrapped: the server stores only the recovery
 * slot. Regenerating a kit replaces the recovery slot, so an older printout stops working.
 *
 * The save check asks for the last 4 characters of the code, or the code scanned back from the QR.
 * A wrong answer re-shows the kit; there is no skip.
 */

import { parseRecoveryCode } from './slots.js';

/** Number of trailing code characters the save check asks for. */
export const KIT_CHECK_LENGTH = 4;

export interface RecoveryKitInput {
  /** The store's display name. */
  storeName: string;
  /** The user the recovery slot belongs to. */
  userEmail: string;
  /** When the kit (and its recovery slot) was created. */
  createdAt: Date;
  /** The recovery code, in any accepted spelling; the kit shows the canonical form. */
  recoveryCode: string;
}

export interface RecoveryKit {
  storeName: string;
  userEmail: string;
  /** ISO 8601 date (YYYY-MM-DD, UTC) of creation. */
  createdOn: string;
  /** The canonical code, `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX`. */
  code: string;
  /** The code's four 8-character groups, for large, spaced display. */
  codeGroups: string[];
  /** The string a QR of the code encodes: the canonical code, so scanning it back answers the save check. */
  qrPayload: string;
  /** The recovery instructions, one step per entry, in order. */
  instructions: string[];
  /** The responsibility notice shown at the save step. */
  keepNotice: string;
}

/**
 * Build the kit content for one recovery code.
 *
 * @throws when `recoveryCode` is not a valid recovery code.
 */
export function buildRecoveryKit(input: RecoveryKitInput): RecoveryKit {
  const code = parseRecoveryCode(input.recoveryCode);
  return {
    storeName: input.storeName,
    userEmail: input.userEmail,
    createdOn: input.createdAt.toISOString().slice(0, 10),
    code,
    codeGroups: code.split('-').slice(1),
    qrPayload: code,
    instructions: [
      `This kit unlocks the config store "${input.storeName}" for ${input.userEmail} when no passkey is available.`,
      'Open the config store in the Rediacc portal and choose "Unlock with recovery code".',
      'Type the code below, or scan its QR code. Dashes, spaces and letter case do not matter.',
      'After unlocking, enroll a new passkey and generate a new kit; generating a new kit makes this one stop working.',
    ],
    keepNotice:
      'Keeping this kit is the responsibility of its holder: Rediacc cannot recover the code or the store without it. Store it offline, away from the devices that hold the passkey.',
  };
}

/**
 * The save check: does `answer` prove the user holds the kit for `recoveryCode`? Accepts the last
 * {@link KIT_CHECK_LENGTH} characters of the code (letter case and Crockford aliases forgiven), or
 * the whole code (the QR scanned back, or typed out). Anything else, empty input included, fails.
 */
export function checkRecoveryKitSaved(recoveryCode: string, answer: string): boolean {
  const code = parseRecoveryCode(recoveryCode);
  const compact = code.slice('RC1-'.length).replaceAll('-', '');
  let folded = answer
    .toUpperCase()
    .replaceAll(/[\s-]/g, '')
    .replaceAll('O', '0')
    .replaceAll(/[IL]/g, '1');
  // A scanned or typed whole code may carry its prefix (folding turns its letters into RC1).
  if (folded.length === compact.length + 3 && folded.startsWith('RC1')) folded = folded.slice(3);
  if (folded.length === compact.length) return folded === compact;
  return folded.length === KIT_CHECK_LENGTH && compact.endsWith(folded);
}
