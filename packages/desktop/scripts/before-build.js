/**
 * electron-builder beforeBuild hook
 *
 * This hook runs before native dependencies are installed/rebuilt.
 * Returning false skips the rebuild step.
 *
 * On Windows, we skip native module rebuild because:
 * - node-pty uses N-API (node-addon-api) which is ABI-stable
 * - The bundled prebuilds work with Electron
 * - Compiling node-pty on Windows CI takes 27+ minutes
 *
 * On Linux/macOS, rebuild completes in seconds, so we allow it.
 */
module.exports = async function beforeBuild(context) {
  if (process.platform === 'win32') {
    console.log('Skipping native module rebuild on Windows (using prebuilds)');
    return false;
  }
  // Allow rebuild on other platforms
  return true;
};
