// The tutorial player gate's in-page probes: each evaluates one expression in the page and returns plain data. Moved out of test-tutorial-player-release-gate.js to keep that script inside its line budget; `evalInPage` is passed in, so none of them closes over the browser session.

export function currentState(evalInPage) {
  return evalInPage(`(() => {
    const video = document.querySelector('.tvp-root video');
    // The skin's view of playback: its play button carries [data-started] once played, [data-paused] while paused.
    const play = video?.closest('.media-skin')?.querySelector('.media-play-button');
    return {
      paused: video ? video.paused : null,
      ended: video ? video.ended : null,
      currentTime: video ? video.currentTime : null,
      skinPlaying: play ? play.hasAttribute('data-started') && !play.hasAttribute('data-paused') : null,
      sameDocument: window.__tpgDoc === 1,
      players: document.querySelectorAll('.tvp-root video').length
    };
  })()`);
}

/**
 * Whether the media clock moves within the budget. `paused === false` alone is not playback: a
 * play() on a pipeline that never decodes reads paused=false at currentTime 0 for good (seen
 * 2026-10-13 with readyState stuck at 1 and the whole file buffered), and only the clock tells.
 */
export function clockMoves(evalInPage, budgetMs = 10000) {
  return evalInPage(`(() => new Promise((resolve) => {
    const deadline = Date.now() + ${budgetMs};
    const poll = () => {
      const video = document.querySelector('.tvp-root video');
      const moved = Boolean(video) && !video.paused && video.currentTime > 0;
      if (!moved && Date.now() < deadline) return setTimeout(poll, 100);
      resolve({
        moved,
        paused: video ? video.paused : null,
        ended: video ? video.ended : null,
        currentTime: video ? video.currentTime : null,
        readyState: video ? video.readyState : null,
        sameDocument: window.__tpgDoc === 1
      });
    };
    poll();
  }))()`);
}

export function sampledStates(evalInPage, durationMs, tickMs) {
  return evalInPage(`(() => new Promise((resolve) => {
    const rows = [];
    const start = Date.now();
    const collect = () => {
      const video = document.querySelector('.tvp-root video');
      rows.push({
        t: Date.now() - start,
        paused: video ? video.paused : null,
        currentTime: video ? video.currentTime : null,
        // Tell a stalled fetch or a starved decoder (readyState below HAVE_FUTURE_DATA) from a play() race (data present, clock frozen).
        readyState: video ? video.readyState : null,
        networkState: video ? video.networkState : null,
        bufferedEnd: video && video.buffered.length > 0 ? video.buffered.end(video.buffered.length - 1) : null,
        sameDocument: window.__tpgDoc === 1
      });
      if (Date.now() - start >= ${durationMs}) {
        resolve(rows);
      } else {
        setTimeout(collect, ${tickMs});
      }
    };
    collect();
  }))()`);
}
