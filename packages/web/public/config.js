// Runtime configuration for Rediacc Console
// This file can be overwritten by nginx in production deployments
// For open-source deployments, you can modify this file directly

window.REDIACC_CONFIG = {
  // Instance Information
  instanceName: 'development',

  // API Configuration
  // For production deployments with nginx proxy, use: '/api'
  // For standalone deployments, specify full URL: 'https://your-backend.com/api'
  // Leave as-is for sandbox/development mode (console will auto-detect)
  apiUrl: window.location.origin + '/api',
  domain: 'localhost',
  httpPort: '7322',

  // Build Configuration
  // This is set at build time via REDIACC_BUILD_TYPE environment variable
  // - 'DEBUG': Development mode with sandbox fallback
  // - 'RELEASE': Production mode (uses same-domain /api only)
  buildType: 'DEBUG', // This will be replaced during build

  // Feature Flags
  enableDebug: 'true',
  enableSandboxFallback: 'true', // Only works in DEBUG mode

  // Version Information
  version: 'dev',
  buildTime: new Date().toISOString(),
  environment: 'development',

  // Additional Settings
  defaultLanguage: 'en',

  // Optional: Custom sandbox URL for open-source deployments
  // Uncomment and modify if you want to use a different sandbox
  // sandboxUrl: 'https://sandbox.rediacc.com/api'
};

// Log configuration in development mode
if (window.REDIACC_CONFIG.enableDebug === 'true') {
  console.warn('Rediacc Configuration:', window.REDIACC_CONFIG);
  console.warn('Build Type:', window.REDIACC_CONFIG.buildType || 'Not specified');

  // Warn about sandbox usage in open-source deployments
  if (
    window.REDIACC_CONFIG.buildType === 'DEBUG' &&
    window.REDIACC_CONFIG.enableSandboxFallback === 'true'
  ) {
    console.warn('Note: Console will fallback to sandbox if local backend is unavailable');
  }
}
