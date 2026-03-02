/**
 * Contact link interceptor.
 *
 * Uses event delegation to intercept clicks on any link pointing to /contact
 * or /{lang}/contact and opens the contact modal instead. Works with Astro
 * View Transitions since it listens on document (no re-init needed).
 */
(function () {
  const CONTACT_RE = /^\/(?:[a-z]{2}\/)?contact(?:\?|$)/;

  document.addEventListener('click', (e) => {
    if (!window.openContactModal) return;

    let target = e.target;
    while (target && target !== document && target.tagName !== 'A') {
      target = target.parentElement;
    }
    if (target?.tagName !== 'A') return;

    const href = target.getAttribute('href');
    if (!href || !CONTACT_RE.test(href)) return;

    e.preventDefault();

    // Extract ?interest= parameter if present
    let interest;
    try {
      const url = new URL(href, window.location.origin);
      interest = url.searchParams.get('interest');
    } catch {
      // If URL parsing fails, just open without interest
    }

    window.openContactModal(interest ?? undefined);
    window.plausible?.('contact_modal_open', { props: { source: 'interceptor' } });
  });
})();
