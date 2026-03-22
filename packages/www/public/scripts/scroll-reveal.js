/**
 * Scroll reveal — adds .visible to .reveal elements when they enter the viewport.
 * One-shot: once visible, the element stays visible and the observer disconnects.
 */
(function () {
  const elements = document.querySelectorAll('.reveal');
  if (!elements.length) return;

  let remaining = elements.length;
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
          remaining--;
          if (remaining <= 0) observer.disconnect();
        }
      }
    },
    { threshold: 0.1, rootMargin: '0px 0px -50px 0px' }
  );

  for (const el of elements) observer.observe(el);
})();
