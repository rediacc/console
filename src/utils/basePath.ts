/**
 * Detects the application base path at runtime.
 *
 * This function determines the correct base path for React Router
 * based on the current URL, supporting both root and versioned deployments:
 * - Root: https://console.rediacc.com/ -> basename: "/"
 * - Versioned: https://console.rediacc.com/versions/v1.2.3/ -> basename: "/versions/v1.2.3/"
 */
export function getBasePath(): string {
  const pathname = window.location.pathname

  // Check if we're in a versioned deployment (/versions/vX.Y.Z/)
  const versionMatch = pathname.match(/^(\/versions\/v\d+\.\d+\.\d+)/)

  if (versionMatch) {
    // Return the versioned base path with trailing slash
    return versionMatch[1] + '/'
  }

  // Default to root for non-versioned deployments
  return '/'
}
