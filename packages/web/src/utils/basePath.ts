/**
 * Detects the application base path at runtime.
 *
 * This function determines the correct base path for React Router
 * based on the current URL, supporting:
 * - Local dev: http://localhost:7322/console/ -> basename: "/console/"
 * - Production root: https://console.rediacc.com/ -> basename: "/"
 * - Versioned: https://console.rediacc.com/versions/v1.2.3/ -> basename: "/versions/v1.2.3/"
 */
export function getBasePath(): string {
  const pathname = window.location.pathname;

  // Check if we're in a versioned deployment (/versions/vX.Y.Z/)
  const versionMatch = /^(\/versions\/v\d+\.\d+\.\d+)/.exec(pathname);

  if (versionMatch) {
    // Return the versioned base path with trailing slash
    return `${versionMatch[1]}/`;
  }

  // Check if the build-time base URL is set and matches the current path
  // This handles local development where base is /console/
  const buildBase = import.meta.env.BASE_URL;
  if (buildBase && buildBase !== '/' && pathname.startsWith(buildBase)) {
    return buildBase;
  }

  // Default to root for production deployments
  return '/';
}
