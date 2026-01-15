/**
 * Protocol module - rediacc:// URL handling
 * Ported from desktop/src/cli/core/protocol_handler.py
 */

export {
  getElectronExecutablePath,
  getProtocolHandler,
  getProtocolStatus,
  isProtocolSupported,
  LinuxProtocolHandler,
  MacOSProtocolHandler,
  ProtocolHandlerError,
  type ProtocolStatus,
  registerProtocol,
  unregisterProtocol,
  WindowsProtocolHandler,
} from './handlers.js';
export {
  buildCliCommand,
  buildProtocolUrl,
  PROTOCOL_SCHEME,
  parseProtocolUrl,
  VALID_ACTIONS,
} from './parser.js';
