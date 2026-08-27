# The render image: Remotion + headless Chrome + ffmpeg + EVERY font the renderers name.
#
# WHY THIS IMAGE EXISTS AT ALL, and why it is the FIRST of the three.
# On 2026-08-27 a rebuilt host had four of the five font families the renderers name
# absent: Inter, JetBrains Mono, WenQuanYi Zen Hei, Noto Sans Arabic. The tutorial-card
# path fails closed on that (assertCardFontsUsable reads the font's own cmap), but the
# SOLUTION VIDEO path does not: remotion/src/fonts.ts wraps only the Arabic face in
# delayRender/cancelRender, while DEFAULT_FONT_STACK names 'Inter' with no assertion
# behind it. Chrome substitutes silently, so a render on that host would have shipped all
# 12 non-Arabic locales in the wrong typeface, with a zero exit code the whole way.
#
# Baking the fonts here fixes the containerised path. It does NOT fix a bare-metal render,
# which is why the fonts are also vendored into the repo and why fonts.ts still needs a
# Latin assertion. This image is one of the two halves, not the whole answer.
#
# NO CUDA AND NO MODEL WEIGHTS LIVE HERE, deliberately. Encoding is 0.39% of render time
# by this repo's own profile, and rasterisation is pinned to Skia's CPU backend precisely
# to stay OFF the card that narration needs. Keeping this image GPU-free keeps it small
# and keeps `--gpus all` to the one image that earns it.
FROM node:22-bookworm-slim

# Chrome's shared libraries. Remotion downloads its own chrome-headless-shell, but the
# system libs it links against are not in a slim base.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      ca-certificates \
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
      libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
      libgbm1 libasound2 libpango-1.0-0 libcairo2 \
      fontconfig \
    && rm -rf /var/lib/apt/lists/*

# THE FIVE FAMILIES, by their exact family names as card-fonts.ts and fonts.ts name them.
# fonts-noto-core carries Noto Sans Arabic; fonts-wqy-zenhei carries WenQuanYi Zen Hei,
# which was chosen over Droid Sans Fallback because that face has no Hangul and `ko` fell
# through to Unifont.
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-inter fonts-jetbrains-mono fonts-wqy-zenhei fonts-noto-core fonts-dejavu-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Fail the BUILD if a family is missing, rather than discovering it in a shipped video.
# An empty fc-list result must fail, not pass: that is the vacuity direction this repo
# keeps paying for.
RUN set -eu; \
    for f in "Inter" "JetBrains Mono" "WenQuanYi Zen Hei" "DejaVu Sans" "Noto Sans Arabic"; do \
      n="$(fc-list : family | tr ',' '\n' | grep -ixc "$f" || true)"; \
      [ "$n" -gt 0 ] || { echo "FATAL: font family '$f' absent from this image"; exit 1; }; \
      echo "ok  $f"; \
    done

WORKDIR /work
