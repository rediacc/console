/**
 * Formats the build-time VITE_APP_VERSION string for display.
 * - Returns 'Development' for dev placeholders.
 * - Returns 'v{hash}' abbreviated for 40-char commit hashes.
 * - Otherwise prefixes 'v' if missing.
 */
export function formatAppVersion(version: string | undefined): string {
  if (
    !version ||
    version === '0.0.0-dev' ||
    version === 'dev' ||
    version === 'development' ||
    version === 'unknown'
  ) {
    return 'Development';
  }
  if (version.length === 40 && /^[0-9a-f]+$/i.test(version)) {
    return `v${version.substring(0, 7)}`;
  }
  return version.startsWith('v') ? version : `v${version}`;
}
