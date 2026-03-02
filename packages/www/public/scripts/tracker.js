/**
 * Behavioral tracking via Plausible custom events.
 *
 * Modules:
 * 1. Scroll depth — sentinels at 25/50/75/100%
 * 2. Section visibility — IntersectionObserver on section[id]
 * 3. Time on page — buckets at 15/30/60/120/300s
 * 4. Delegated click tracking — data-track attributes
 * 5. UTM capture & session persistence
 * 6. Rage click detection
 * 7. Engagement scoring
 * 8. 404 page detection
 *
 * Survives Astro View Transitions via astro:page-load re-init.
 */
(function () {
  let p = window.plausible;
  if (!p) return;

  const path = function () {
    return location.pathname;
  };

  // ── 1. Scroll Depth ──────────────────────────────────────────────
  let scrollFired = {};
  let scrollObserver = null;
  let sentinels = [];

  function initScrollDepth() {
    // Clean up previous sentinels
    for (const sentinel of sentinels) sentinel.remove();
    sentinels = [];
    scrollFired = {};
    if (scrollObserver) scrollObserver.disconnect();

    const main = document.querySelector('main');
    if (!main) return;

    const depths = [25, 50, 75, 100];
    scrollObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const depth = entry.target.dataset.depth;
          if (depth && !scrollFired[depth]) {
            scrollFired[depth] = true;
            p('scroll_depth', { props: { depth, path: path() } });
            scrollObserver.unobserve(entry.target);
          }
        }
      },
      { threshold: 0 }
    );

    for (const d of depths) {
      const el = document.createElement('div');
      el.dataset.depth = String(d);
      el.style.cssText = 'position:absolute;left:0;width:1px;height:1px;pointer-events:none;';
      el.style.top = `${d}%`;
      main.style.position = main.style.position || 'relative';
      main.appendChild(el);
      sentinels.push(el);
      scrollObserver.observe(el);
    }
  }

  // ── 2. Section Visibility ────────────────────────────────────────
  let sectionObserver = null;

  function initSectionVisibility() {
    if (sectionObserver) sectionObserver.disconnect();

    const sections = document.querySelectorAll('section[id]');
    if (!sections.length) return;

    sectionObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            p('section_view', { props: { section: entry.target.id, path: path() } });
            sectionObserver.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.3 }
    );

    for (const section of sections) sectionObserver.observe(section);
  }

  // ── 3. Time on Page ─────────────────────────────────────────────
  const timeBuckets = [15, 30, 60, 120, 300];
  let timeFired = {};
  let timeStart = 0;
  let timeElapsed = 0;
  let timeTimer = null;
  let timeHidden = false;

  function tickTime() {
    if (timeHidden) return;
    timeElapsed = Math.floor((Date.now() - timeStart) / 1000);
    for (const bucket of timeBuckets) {
      if (timeElapsed >= bucket && !timeFired[bucket]) {
        timeFired[bucket] = true;
        p('time_on_page', { props: { seconds: String(bucket), path: path() } });
      }
    }
    // Stop after last bucket
    if (timeElapsed >= timeBuckets[timeBuckets.length - 1]) {
      clearInterval(timeTimer);
      timeTimer = null;
    }
  }

  function initTimeOnPage() {
    if (timeTimer) clearInterval(timeTimer);
    timeFired = {};
    timeElapsed = 0;
    timeHidden = false;
    timeStart = Date.now();
    timeTimer = setInterval(tickTime, 5000);
  }

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      timeHidden = true;
    } else {
      timeHidden = false;
      // Adjust start to account for hidden time
      timeStart = Date.now() - timeElapsed * 1000;
    }
  });

  // ── 4. Delegated Click Tracking ─────────────────────────────────
  function collectTrackProps(el) {
    const props = {};
    for (const attr of el.attributes) {
      if (attr.name.startsWith('data-track-') && attr.name !== 'data-track') {
        props[attr.name.slice(11)] = attr.value;
      }
    }
    return props;
  }

  document.addEventListener('click', (e) => {
    let target = e.target;
    while (target && target !== document) {
      if (target.dataset?.track) {
        p(target.dataset.track, { props: collectTrackProps(target) });
        return;
      }
      target = target.parentElement;
    }
  });

  // ── 5. UTM Capture & Session Persistence ───────────────────────
  function captureUtmParams() {
    if (sessionStorage.getItem('__pa_utm')) return;
    const params = new URLSearchParams(location.search);
    const keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
    const utm = {};
    let hasAny = false;
    for (const key of keys) {
      const val = params.get(key);
      if (val) {
        utm[key] = val;
        hasAny = true;
      }
    }
    if (hasAny) sessionStorage.setItem('__pa_utm', JSON.stringify(utm));
  }

  function captureReferrer() {
    if (sessionStorage.getItem('__pa_referrer') || !document.referrer) return;
    try {
      const ref = new URL(document.referrer);
      if (ref.hostname !== location.hostname) {
        sessionStorage.setItem('__pa_referrer', document.referrer);
      }
    } catch {
      /* invalid referrer */
    }
  }

  function initUtm() {
    captureUtmParams();
    captureReferrer();

    // Track last solution page
    const match = /^\/[a-z]{2}\/solutions\/([^/]+)/.exec(location.pathname);
    if (match?.[1]) {
      sessionStorage.setItem('__pa_last_solution', match[1]);
    }
  }

  // Expose UTM getter for conversion events
  window.__pa_get_utm = function () {
    try {
      return JSON.parse(sessionStorage.getItem('__pa_utm') ?? '{}');
    } catch {
      return {};
    }
  };
  window.__pa_get_referrer = function () {
    return sessionStorage.getItem('__pa_referrer') ?? '';
  };

  // ── 6. Rage Click Detection ───────────────────────────────────
  let rageClicks = [];

  function initRageClickDetection() {
    document.addEventListener('click', (e) => {
      const target = e.target;
      const now = Date.now();
      rageClicks.push({ t: now, el: target });
      // Keep last 5
      if (rageClicks.length > 5) rageClicks.shift();

      // Check for 3+ clicks on same element within 1.5s
      if (rageClicks.length >= 3) {
        const recent = rageClicks.filter((c) => {
          return c.el === target && now - c.t < 1500;
        });
        if (recent.length >= 3) {
          const tag = target.tagName;
          const label = target.dataset?.trackLabel ?? '';
          p('rage_click', {
            props: { element: tag, path: path(), label },
            interactive: false,
          });
          rageClicks = []; // reset after firing
        }
      }
    });
  }

  // ── 7. Engagement Scoring ─────────────────────────────────────
  let engagementScore = 0;
  let engagementQualified = false;
  const scoreMap = {
    section_view: 10,
    scroll_depth: 15,
    time_on_page: 10,
    cta_click: 5,
  };

  // Wrap plausible to intercept our own events for scoring
  const origP = p;
  p = function (eventName, opts) {
    origP(eventName, opts);
    if (!engagementQualified && scoreMap[eventName]) {
      engagementScore += scoreMap[eventName];
      if (engagementScore >= 50) {
        engagementQualified = true;
        origP('engagement_qualified', {
          props: { score: String(engagementScore), path: path() },
          interactive: false,
        });
      }
    }
  };

  // ── 8. 404 Page Detection ─────────────────────────────────────
  function init404Detection() {
    if (document.querySelector('.error-page')) {
      p('404', {
        props: { path: path(), referrer: document.referrer || '(direct)' },
        interactive: false,
      });
    }
  }

  // ── Init on first load + View Transitions ───────────────────────
  function init() {
    initScrollDepth();
    initSectionVisibility();
    initTimeOnPage();
    initUtm();
    init404Detection();
    engagementScore = 0;
    engagementQualified = false;
  }

  init();
  initRageClickDetection(); // once — delegated, no re-init needed

  // Re-init on Astro View Transition
  document.addEventListener('astro:page-load', init);

  // Reset time tracker before swap
  document.addEventListener('astro:before-swap', () => {
    if (timeTimer) clearInterval(timeTimer);
  });
})();
