import React, { useCallback, useEffect, useRef } from 'react';

/**
 * The one overlay.
 *
 * Before 2026-08-18 there were six, with no shared code between them:
 * `handleFocusTrap` was byte-identical in ContactModal, LeadMagnetModal and
 * RegionPickerModal, SearchModal reimplemented the same logic inline,
 * NewsletterReturnPopup had no focus trap at all, and
 * `document.body.style.overflow = 'hidden'` was written five times. Their
 * backdrops sat at four different opacities and their panels at four
 * different radii.
 *
 * Everything a dialog owes the user lives here: backdrop, panel, Escape,
 * focus trap, focus restore, scroll lock and the ARIA contract. A consumer
 * supplies content and nothing else.
 */

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

/**
 * Scroll lock is REFERENCE COUNTED. Five separate implementations each wrote
 * `overflow: hidden` on open and `''` on close, so the newsletter popup
 * closing behind an open contact modal unlocked the page underneath a live
 * dialog. Counting means the last one out restores it, and it restores what
 * was actually there rather than the empty string.
 */
let lockCount = 0;
let lockedOverflow = '';

function lockScroll(): () => void {
  if (lockCount === 0) {
    lockedOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  lockCount += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    lockCount -= 1;
    if (lockCount === 0) document.body.style.overflow = lockedOverflow;
  };
}

interface OverlayProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name for the dialog. */
  label: string;
  /** Visible heading. Omit when the content supplies its own. */
  title?: React.ReactNode;
  description?: React.ReactNode;
  /** Accessible name for the close button. Omit to render no close button. */
  closeLabel?: string;
  align?: 'top' | 'center';
  width?: 'default' | 'wide';
  /** Focused on open. Falls back to the first focusable element in the panel. */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  panelClassName?: string;
  /** data-track-label for the close button, so analytics keeps its names. */
  closeTrackLabel?: string;
  /** Called instead of onClose when the backdrop is clicked. */
  onBackdropClose?: () => void;
  children: React.ReactNode;
}

const Overlay: React.FC<OverlayProps> = ({
  open,
  onClose,
  label,
  title,
  description,
  closeLabel,
  align = 'top',
  width = 'default',
  initialFocusRef,
  panelClassName,
  closeTrackLabel,
  onBackdropClose,
  children,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const dismiss = useCallback(() => {
    (onBackdropClose ?? onClose)();
  }, [onBackdropClose, onClose]);

  useEffect(() => {
    if (!open) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const releaseScroll = lockScroll();

    const raf = requestAnimationFrame(() => {
      const target =
        initialFocusRef?.current ?? panelRef.current?.querySelector<HTMLElement>(FOCUSABLE);
      target?.focus();
    });

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        dismiss();
        return;
      }
      if (e.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusable = panel.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('keydown', onKeyDown);
      releaseScroll();
      previousFocusRef.current?.focus();
    };
  }, [open, dismiss, initialFocusRef]);

  if (!open) return null;

  return (
    <div
      className={`overlay-backdrop${align === 'center' ? ' overlay-backdrop--center' : ''}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) dismiss();
      }}
    >
      <div
        ref={panelRef}
        className={`overlay-panel${width === 'wide' ? ' overlay-panel--wide' : ''}${
          panelClassName ? ` ${panelClassName}` : ''
        }`}
        role="dialog"
        aria-modal="true"
        aria-label={label}
      >
        {/* Truthiness, not nullishness: an empty title must not open the header. */}
        {(Boolean(title) || Boolean(closeLabel)) && (
          <div className="overlay-header">
            <div>
              {title && <h2 className="overlay-title">{title}</h2>}
              {description && <p className="overlay-description">{description}</p>}
            </div>
            {closeLabel && (
              <button
                type="button"
                className="btn--icon overlay-close"
                onClick={onClose}
                aria-label={closeLabel}
                data-track="cta_click"
                data-track-label={closeTrackLabel}
              >
                <svg
                  className="icon"
                  width="20"
                  height="20"
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  strokeLinecap="round"
                  aria-hidden="true"
                >
                  <path d="M5 5l10 10M15 5L5 15" />
                </svg>
              </button>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  );
};

export default Overlay;
