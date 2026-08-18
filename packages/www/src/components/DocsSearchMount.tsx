import React, { useCallback, useEffect, useState } from 'react';
import SearchModal from './SearchModal';

interface DocsSearchMountProps {
  /**
   * `category` values from the generated search index that this surface is
   * allowed to return. Passed straight through to SearchModal.
   */
  categories?: readonly string[];
  /** Distinguishes this surface from the site-wide modal in analytics. */
  scope?: string;
}

/**
 * Headless island: it owns open/closed state for the docs-scoped search modal
 * and renders no chrome of its own. The button the reader clicks is server
 * rendered by DocsLayout, so it is in the HTML before any JavaScript arrives
 * and there is nothing to shift when this hydrates.
 *
 * The two surfaces are wired so they can never be open at the same time. This
 * one closes itself when the site-wide modal opens, which is cheaper and more
 * reliable than a shared coordinator: neither modal has to know whether the
 * other is mounted on this page.
 */
const DocsSearchMount: React.FC<DocsSearchMountProps> = ({ categories, scope = 'docs' }) => {
  const [isOpen, setIsOpen] = useState(false);
  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    const open = () => setIsOpen(true);
    // Delegated on `document`, so an Astro view transition swapping the header
    // out does not need this island to rebind anything.
    document.addEventListener('docs-search:open', open);
    return () => document.removeEventListener('docs-search:open', open);
  }, []);

  useEffect(() => {
    // Cmd/Ctrl+K, or any other dispatcher of the site-wide modal's open event,
    // closes this one. Mirrors the name resolution Navigation.tsx uses.
    const globalEvent =
      (window as unknown as { SEARCH_HOTKEY_EVENT?: string }).SEARCH_HOTKEY_EVENT ?? 'search:open';
    const closeForGlobal = () => setIsOpen(false);
    document.addEventListener(globalEvent, closeForGlobal);
    return () => document.removeEventListener(globalEvent, closeForGlobal);
  }, []);

  return <SearchModal isOpen={isOpen} onClose={close} categories={categories} scope={scope} />;
};

export default DocsSearchMount;
