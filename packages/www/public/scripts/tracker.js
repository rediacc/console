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
  var p = window.plausible;
  if (!p) return;

  var path = function () { return location.pathname; };

  // ── 1. Scroll Depth ──────────────────────────────────────────────
  var scrollFired = {};
  var scrollObserver = null;
  var sentinels = [];

  function initScrollDepth() {
    // Clean up previous sentinels
    for (var i = 0; i < sentinels.length; i++) sentinels[i].remove();
    sentinels = [];
    scrollFired = {};
    if (scrollObserver) scrollObserver.disconnect();

    var main = document.querySelector('main');
    if (!main) return;

    var depths = [25, 50, 75, 100];
    scrollObserver = new IntersectionObserver(function (entries) {
      for (var j = 0; j < entries.length; j++) {
        var entry = entries[j];
        if (!entry.isIntersecting) continue;
        var depth = entry.target.dataset.depth;
        if (depth && !scrollFired[depth]) {
          scrollFired[depth] = true;
          p('scroll_depth', { props: { depth: depth, path: path() } });
          scrollObserver.unobserve(entry.target);
        }
      }
    }, { threshold: 0 });

    for (var k = 0; k < depths.length; k++) {
      var el = document.createElement('div');
      el.dataset.depth = String(depths[k]);
      el.style.cssText = 'position:absolute;left:0;width:1px;height:1px;pointer-events:none;';
      el.style.top = depths[k] + '%';
      main.style.position = main.style.position || 'relative';
      main.appendChild(el);
      sentinels.push(el);
      scrollObserver.observe(el);
    }
  }

  // ── 2. Section Visibility ────────────────────────────────────────
  var sectionObserver = null;

  function initSectionVisibility() {
    if (sectionObserver) sectionObserver.disconnect();

    var sections = document.querySelectorAll('section[id]');
    if (!sections.length) return;

    sectionObserver = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        var entry = entries[i];
        if (entry.isIntersecting) {
          p('section_view', { props: { section: entry.target.id, path: path() } });
          sectionObserver.unobserve(entry.target);
        }
      }
    }, { threshold: 0.3 });

    for (var j = 0; j < sections.length; j++) sectionObserver.observe(sections[j]);
  }

  // ── 3. Time on Page ─────────────────────────────────────────────
  var timeBuckets = [15, 30, 60, 120, 300];
  var timeFired = {};
  var timeStart = 0;
  var timeElapsed = 0;
  var timeTimer = null;
  var timeHidden = false;

  function tickTime() {
    if (timeHidden) return;
    timeElapsed = Math.floor((Date.now() - timeStart) / 1000);
    for (var i = 0; i < timeBuckets.length; i++) {
      var bucket = timeBuckets[i];
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

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      timeHidden = true;
    } else {
      timeHidden = false;
      // Adjust start to account for hidden time
      timeStart = Date.now() - timeElapsed * 1000;
    }
  });

  // ── 4. Delegated Click Tracking ─────────────────────────────────
  document.addEventListener('click', function (e) {
    var target = e.target;
    while (target && target !== document) {
      if (target.dataset && target.dataset.track) {
        var eventName = target.dataset.track;
        var props = {};
        var attrs = target.attributes;
        for (var i = 0; i < attrs.length; i++) {
          var name = attrs[i].name;
          if (name.indexOf('data-track-') === 0 && name !== 'data-track') {
            props[name.slice(11)] = attrs[i].value;
          }
        }
        p(eventName, { props: props });
        return;
      }
      target = target.parentElement;
    }
  });

  // ── 5. UTM Capture & Session Persistence ───────────────────────
  function initUtm() {
    // Parse UTM params (first-touch only)
    if (!sessionStorage.getItem('__pa_utm')) {
      var params = new URLSearchParams(location.search);
      var keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
      var utm = {};
      var hasAny = false;
      for (var i = 0; i < keys.length; i++) {
        var val = params.get(keys[i]);
        if (val) { utm[keys[i]] = val; hasAny = true; }
      }
      if (hasAny) sessionStorage.setItem('__pa_utm', JSON.stringify(utm));
    }

    // Store referrer (first-touch only)
    if (!sessionStorage.getItem('__pa_referrer') && document.referrer) {
      try {
        var ref = new URL(document.referrer);
        if (ref.hostname !== location.hostname) {
          sessionStorage.setItem('__pa_referrer', document.referrer);
        }
      } catch (_) { /* invalid referrer */ }
    }

    // Track last solution page
    var match = location.pathname.match(/^\/[a-z]{2}\/solutions\/([^/]+)/);
    if (match && match[1]) {
      sessionStorage.setItem('__pa_last_solution', match[1]);
    }
  }

  // Expose UTM getter for conversion events
  window.__pa_get_utm = function () {
    try { return JSON.parse(sessionStorage.getItem('__pa_utm') || '{}'); }
    catch (_) { return {}; }
  };
  window.__pa_get_referrer = function () {
    return sessionStorage.getItem('__pa_referrer') || '';
  };

  // ── 6. Rage Click Detection ───────────────────────────────────
  var rageClicks = [];

  function initRageClickDetection() {
    document.addEventListener('click', function (e) {
      var target = e.target;
      var now = Date.now();
      rageClicks.push({ t: now, el: target });
      // Keep last 5
      if (rageClicks.length > 5) rageClicks.shift();

      // Check for 3+ clicks on same element within 1.5s
      if (rageClicks.length >= 3) {
        var recent = rageClicks.filter(function (c) {
          return c.el === target && now - c.t < 1500;
        });
        if (recent.length >= 3) {
          var tag = target.tagName || 'unknown';
          var label = target.dataset ? target.dataset.trackLabel || '' : '';
          p('rage_click', {
            props: { element: tag, path: path(), label: label },
            interactive: false
          });
          rageClicks = []; // reset after firing
        }
      }
    });
  }

  // ── 7. Engagement Scoring ─────────────────────────────────────
  var engagementScore = 0;
  var engagementQualified = false;
  var scoreMap = {
    section_view: 10,
    scroll_depth: 15,
    time_on_page: 10,
    cta_click: 5
  };

  // Wrap plausible to intercept our own events for scoring
  var origP = p;
  p = function (eventName, opts) {
    origP(eventName, opts);
    if (!engagementQualified && scoreMap[eventName]) {
      engagementScore += scoreMap[eventName];
      if (engagementScore >= 50) {
        engagementQualified = true;
        origP('engagement_qualified', {
          props: { score: String(engagementScore), path: path() },
          interactive: false
        });
      }
    }
  };

  // ── 8. 404 Page Detection ─────────────────────────────────────
  function init404Detection() {
    if (document.querySelector('.error-page')) {
      p('404', {
        props: { path: path(), referrer: document.referrer || '(direct)' },
        interactive: false
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
  document.addEventListener('astro:before-swap', function () {
    if (timeTimer) clearInterval(timeTimer);
  });
})();
