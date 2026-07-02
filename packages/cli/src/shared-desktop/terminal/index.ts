/**
 * Terminal module - Terminal detection and launching
 * Ported from desktop/src/cli/core/config.py (TerminalDetector class)
 */

export { findMSYS2Installation, TerminalDetector } from './detector.js';

export {
  getDefaultTerminalType,
  type LaunchResult,
  launchInline,
  launchTerminal,
} from './launchers.js';
