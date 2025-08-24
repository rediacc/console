// Development placeholder for runtime configuration
// This file will be overwritten by nginx in production
window.REDIACC_CONFIG = {
  // Instance Information
  instanceName: 'development',
  
  // API Configuration - these will be replaced in production
  apiUrl: window.location.origin + '/api',
  domain: 'localhost',
  httpPort: '7322',
  
  // Feature Flags
  enableDebug: 'true',
  
  // Version Information
  version: 'dev',
  buildTime: new Date().toISOString(),
  environment: 'development',
  
  // Additional Settings
  defaultLanguage: 'en'
};

// Log configuration in development mode
if (window.REDIACC_CONFIG.enableDebug === 'true') {
  console.log('Rediacc Development Configuration Loaded:', window.REDIACC_CONFIG);
}