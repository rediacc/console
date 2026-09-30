/**
 * The two pieces every dialog on this site needs, and neither of which may be
 * written twice.
 *
 * They lived inside `components/Overlay.tsx` until the video theater needed
 * them too. The theater is driven from a plain script (`scripts/video-theater.ts`)
 * because the Plyr player it hosts cannot be server-rendered and therefore
 * cannot live inside a React island, so importing the component to reach its
 * private helpers was not an option -- and copying them would have made the
 * theater the sixth hand-rolled scroll lock, which is the exact duplication
 * `Overlay.tsx`'s own header says it was written to end.
 *
 * Nothing here imports React, so an eager, non-React script pays only these
 * few lines for them.
 */

/**
 * What counts as focusable for a focus trap. Deliberately broader than the
 * selector in `public/scripts/image-modal.js`, which omits inputs and selects.
 */
export const FOCUSABLE = [
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

export function lockScroll(): () => void {
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
