/**
 * Protocol module - rediacc:// URL handling
 * Ported from desktop/src/cli/core/protocol_handler.py
 */

export {
  parseProtocolUrl,
  buildCliCommand,
  buildProtocolUrl,
  PROTOCOL_SCHEME,
  VALID_ACTIONS,
} from './parser.js';

export {
  ProtocolHandlerError,
  WindowsProtocolHandler,
  LinuxProtocolHandler,
  MacOSProtocolHandler,
  getProtocolHandler,
  registerProtocol,
  unregisterProtocol,
  getProtocolStatus,
  isProtocolSupported,
  getElectronExecutablePath,
  type ProtocolStatus,
} from './handlers.js';
