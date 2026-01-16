/**
 * Global keyboard shortcut handler for search
 * Listens for Cmd+K (Mac) or Ctrl+K (Windows/Linux)
 */

(function () {
  // Create custom event for search hotkey
  const SEARCH_HOTKEY_EVENT = 'search:open';

  // Listen for keyboard events
  document.addEventListener('keydown', (event) => {
    // Check for Cmd+K (Mac) or Ctrl+K (Windows/Linux)
    const isMac = (() => {
      if (navigator.userAgentData?.platform) {
        return navigator.userAgentData.platform === 'macOS';
      }
      // Fallback for browsers without userAgentData
      return /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
    })();
    const isSearchShortcut = isMac
      ? event.metaKey && event.key === 'k'
      : event.ctrlKey && event.key === 'k';

    if (isSearchShortcut) {
      event.preventDefault();
      // Dispatch custom event that React component can listen to
      document.dispatchEvent(new CustomEvent(SEARCH_HOTKEY_EVENT));
    }
  });

  // Make event name available globally for React components
  window.SEARCH_HOTKEY_EVENT = SEARCH_HOTKEY_EVENT;
})();
