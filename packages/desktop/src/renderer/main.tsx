/**
 * Desktop renderer entry point
 * This file bootstraps the React application for the Electron renderer process
 */

// Import and re-export the main web application
// This allows electron-vite to properly bundle the app while reusing web code
import '../../../web/src/main';
