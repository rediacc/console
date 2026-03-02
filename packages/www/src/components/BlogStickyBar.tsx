import React, { useState, useEffect, useRef } from 'react';
import NewsletterSignup from './NewsletterSignup';

interface Props {
  source?: string;
}

const DISMISSED_KEY = 'stickyBarDismissed';

const BlogStickyBar: React.FC<Props> = ({ source = 'blog-sticky' }) => {
  const [visible, setVisible] = useState(false);
  const [dismissed, setDismissed] = useState(
    () => typeof window !== 'undefined' && sessionStorage.getItem(DISMISSED_KEY) !== null
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

  const handleDismiss = () => {
    setDismissed(true);
    sessionStorage.setItem(DISMISSED_KEY, '1');
  };

  if (dismissed || !visible) return null;

  return (
    <div className="blog-sticky-bar-wrapper">
      <button
        className="blog-sticky-bar-close"
        onClick={handleDismiss}
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
