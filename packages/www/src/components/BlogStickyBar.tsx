import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import NewsletterSignup from './NewsletterSignup';

interface Props {
  source?: string;
}

const DISMISSED_KEY = 'stickyBarDismissed';

// Dismissal lives in sessionStorage, which the server does not have. Both renders must
// start from the SAME value: reading sessionStorage during render made the server say
// false and the browser say true for a returning reader, and React then discarded the
// whole island rather than reconciling it. useSyncExternalStore is the shape React
// provides for exactly this, with a separate server snapshot, so the stored value is
// applied after hydration instead of during it.
const dismissListeners = new Set<() => void>();

function subscribeDismissed(onStoreChange: () => void): () => void {
  dismissListeners.add(onStoreChange);
  return () => {
    dismissListeners.delete(onStoreChange);
  };
}

function getDismissedSnapshot(): boolean {
  return sessionStorage.getItem(DISMISSED_KEY) !== null;
}

function getDismissedServerSnapshot(): boolean {
  return false;
}

function dismiss(): void {
  sessionStorage.setItem(DISMISSED_KEY, '1');
  for (const listener of dismissListeners) listener();
}

const BlogStickyBar: React.FC<Props> = ({ source = 'blog-sticky' }) => {
  const [visible, setVisible] = useState(false);
  const dismissed = useSyncExternalStore(
    subscribeDismissed,
    getDismissedSnapshot,
    getDismissedServerSnapshot
  );
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // Create a sentinel element at ~30% of viewport height from top
    const sentinel = document.createElement('div');
    sentinel.style.position = 'absolute';
    sentinel.style.top = '60vh';
    sentinel.style.height = '1px';
    sentinel.style.width = '1px';
    sentinel.style.pointerEvents = 'none';
    document.body.appendChild(sentinel);
    sentinelRef.current = sentinel;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          setVisible(true);
        }
      },
      { threshold: 0 }
    );
    observer.observe(sentinel);

    return () => {
      observer.disconnect();
      sentinel.remove();
    };
  }, []);

  if (dismissed || !visible) return null;

  return (
    <div className="blog-sticky-bar-wrapper">
      <button
        className="blog-sticky-bar-close"
        onClick={dismiss}
        aria-label="Dismiss"
        type="button"
        data-track="cta_click"
        data-track-label="blog-sticky-dismiss"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707l-2.646 2.647a.5.5 0 01-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708z" />
        </svg>
      </button>
      <NewsletterSignup variant="sticky-bar" source={source} />
    </div>
  );
};

export default BlogStickyBar;
