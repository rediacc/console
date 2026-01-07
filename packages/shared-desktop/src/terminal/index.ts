/**
 * Terminal module - Terminal detection and launching
 * Ported from desktop/src/cli/core/config.py (TerminalDetector class)
 */

export { TerminalDetector, findMSYS2Installation } from './detector.js';

export {
  launchTerminal,
  launchInline,
  getDefaultTerminalType,
  type LaunchResult,
} from './launchers.js';
