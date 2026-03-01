/**
 * Scroll reveal — adds .visible to .reveal elements when they enter the viewport.
 * One-shot: once visible, the element stays visible and the observer disconnects.
 */
(function () {
  var elements = document.querySelectorAll('.reveal');
  if (!elements.length) return;

  var remaining = elements.length;
  var observer = new IntersectionObserver(
    function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) {
          entries[i].target.classList.add('visible');
          observer.unobserve(entries[i].target);
          remaining--;
          if (remaining <= 0) observer.disconnect();
        }
      }
    },
    { threshold: 0.1, rootMargin: '0px 0px -50px 0px' }
  );

  for (var i = 0; i < elements.length; i++) observer.observe(elements[i]);
})();
