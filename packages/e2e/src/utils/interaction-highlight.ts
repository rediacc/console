/**
 * Browser-side interaction highlighting for E2E video recordings.
 *
 * Injects DOM overlays that visualize clicks (red rectangle) and text input
 * focus/keystrokes (blue outline + pulse). Designed to be injected via
 * `context.addInitScript()` so overlays appear in recorded .webm videos.
 *
 * The script is exported as a plain JavaScript string to avoid function
 * serialization issues with addInitScript — Playwright's .toString() on
 * compiled TypeScript functions can produce invalid browser-context code.
 */
export const INTERACTION_HIGHLIGHT_SCRIPT = `
(function() {
  // Guard against double initialization (addInitScript re-runs on navigation)
  if (window.__e2eHighlightInit) return;
  window.__e2eHighlightInit = true;

  // -- State -------------------------------------------------------------------
  var focusOverlays = new WeakMap();
  var activeFocusTarget = null;
  var focusRafId = null;
  var PAD = 3;
  var stylesInjected = false;

  // -- Lazy style injection ----------------------------------------------------
  // addInitScript runs before the DOM is parsed, so document.head may not exist
  // yet. Defer style injection to when the first overlay is created.
  function ensureStyles() {
    if (stylesInjected) return;
    var head = document.head || document.documentElement;
    if (!head) return;
    stylesInjected = true;
    var style = document.createElement('style');
    style.id = 'e2e-highlight-styles';
    style.textContent =
      '@keyframes e2e-keystroke-pulse {' +
      '  0%   { box-shadow: 0 0 8px rgba(33,150,243,0.4); }' +
      '  50%  { box-shadow: 0 0 14px rgba(33,150,243,0.7); }' +
      '  100% { box-shadow: 0 0 8px rgba(33,150,243,0.4); }' +
      '}';
    head.appendChild(style);
  }

  // -- Helpers -----------------------------------------------------------------

  function createOverlay(rect, border, background, boxShadow, dataAttr) {
    ensureStyles();
    var parent = document.body || document.documentElement;
    if (!parent) return null;
    var div = document.createElement('div');
    div.setAttribute(dataAttr, '');
    div.style.position = 'fixed';
    div.style.left = (rect.left - PAD) + 'px';
    div.style.top = (rect.top - PAD) + 'px';
    div.style.width = (rect.width + PAD * 2) + 'px';
    div.style.height = (rect.height + PAD * 2) + 'px';
    div.style.border = border;
    div.style.borderRadius = '4px';
    div.style.background = background;
    div.style.boxShadow = boxShadow || 'none';
    div.style.pointerEvents = 'none';
    div.style.zIndex = '2147483647';
    div.style.boxSizing = 'border-box';
    div.style.transition = 'opacity 0.3s ease-out';
    div.style.opacity = '1';
    parent.appendChild(div);
    return div;
  }

  function isTextInput(el) {
    var tag = el.tagName.toLowerCase();
    if (tag === 'textarea') return true;
    if (el.contentEditable === 'true') return true;
    if (tag === 'input') {
      var type = (el.type || '').toLowerCase();
      return ['text','email','password','search','url','tel','number',''].indexOf(type) !== -1;
    }
    return false;
  }

  // -- Click highlight ---------------------------------------------------------

  function handleMouseDown(e) {
    var target = (e.composedPath && e.composedPath()[0]) || e.target;
    if (!target || !(target instanceof Element)) return;
    if (target.hasAttribute('data-e2e-click-hl')) return;

    var rect = target.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return;

    var overlay = createOverlay(
      rect,
      '3px solid rgba(255, 0, 0, 0.85)',
      'rgba(255, 0, 0, 0.08)',
      null,
      'data-e2e-click-hl'
    );
    if (!overlay) return;

    setTimeout(function() { overlay.style.opacity = '0'; }, 600);
    setTimeout(function() { overlay.remove(); }, 900);
  }

  // -- Focus highlight ---------------------------------------------------------

  function handleFocusIn(e) {
    var target = e.target;
    if (!target || !(target instanceof Element)) return;
    if (!isTextInput(target)) return;
    if (focusOverlays.has(target)) return;

    var rect = target.getBoundingClientRect();
    var overlay = createOverlay(
      rect,
      '2px solid rgba(33, 150, 243, 0.85)',
      'rgba(33, 150, 243, 0.05)',
      '0 0 8px rgba(33, 150, 243, 0.4)',
      'data-e2e-focus-hl'
    );
    if (!overlay) return;
    focusOverlays.set(target, overlay);
    activeFocusTarget = target;
    startFocusTracking();
  }

  function handleFocusOut(e) {
    var target = e.target;
    if (!target) return;
    var overlay = focusOverlays.get(target);
    if (!overlay) return;

    overlay.style.opacity = '0';
    setTimeout(function() { overlay.remove(); }, 300);
    focusOverlays.delete(target);

    if (activeFocusTarget === target) {
      activeFocusTarget = null;
      stopFocusTracking();
    }
  }

  // -- Keystroke pulse ---------------------------------------------------------

  function handleInput(e) {
    var target = e.target;
    if (!target) return;
    var overlay = focusOverlays.get(target);
    if (!overlay) return;

    overlay.style.animation = 'none';
    void overlay.offsetHeight; // force reflow
    overlay.style.animation = 'e2e-keystroke-pulse 0.2s ease-in-out';
  }

  // -- Focus position tracking (scroll / resize) --------------------------------

  function startFocusTracking() {
    if (focusRafId !== null) return;

    function update() {
      if (!activeFocusTarget) { focusRafId = null; return; }
      var overlay = focusOverlays.get(activeFocusTarget);
      if (overlay) {
        var rect = activeFocusTarget.getBoundingClientRect();
        overlay.style.left = (rect.left - PAD) + 'px';
        overlay.style.top = (rect.top - PAD) + 'px';
        overlay.style.width = (rect.width + PAD * 2) + 'px';
        overlay.style.height = (rect.height + PAD * 2) + 'px';
      }
      focusRafId = requestAnimationFrame(update);
    }
    focusRafId = requestAnimationFrame(update);
  }

  function stopFocusTracking() {
    if (focusRafId !== null) {
      cancelAnimationFrame(focusRafId);
      focusRafId = null;
    }
  }

  // -- Register event listeners ------------------------------------------------

  document.addEventListener('mousedown', handleMouseDown, true);
  document.addEventListener('focusin', handleFocusIn);
  document.addEventListener('focusout', handleFocusOut);
  document.addEventListener('input', handleInput);
})();
`;
