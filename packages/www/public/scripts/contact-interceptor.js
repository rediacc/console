/**
 * Contact link interceptor.
 *
 * Uses event delegation to intercept clicks on any link pointing to /contact
 * or /{lang}/contact and opens the contact modal instead. Works with Astro
 * View Transitions since it listens on document (no re-init needed).
 */
(function () {
  var CONTACT_RE = /^\/(?:[a-z]{2}\/)?contact(?:\?|$)/;

  document.addEventListener('click', function (e) {
    if (!window.openContactModal) return;

    var target = e.target;
    while (target && target !== document && target.tagName !== 'A') {
      target = target.parentElement;
    }
    if (!target || target.tagName !== 'A') return;

    var href = target.getAttribute('href');
    if (!href || !CONTACT_RE.test(href)) return;

    e.preventDefault();

    // Extract ?interest= parameter if present
    var interest;
    try {
      var url = new URL(href, window.location.origin);
      interest = url.searchParams.get('interest');
    } catch (_) {
      // If URL parsing fails, just open without interest
    }

    window.openContactModal(interest || undefined);
    if (window.plausible) window.plausible('contact_modal_open', { props: { source: 'interceptor' } });
  });
})();
