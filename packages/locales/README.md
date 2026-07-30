# @rediacc/locales

The one declaration of the site's locale set.

## Why a package, not a file

Consumers include `eslint.config.js` (runs before any build), eleven `node`-run `.js`
scripts, Astro/Vite, `tsx` scripts, two Cloudflare workers and the bundled CLI. A bare
specifier into a workspace package resolves for every one of them with no build ordering.
`packages/shared` could not host it: its exports resolve through `./dist/`, so eslint would
need a build first. A repo-root file could not either: `rootDir: "./src"` in the shared and
cli tsconfigs makes a relative import out of `src` either fail to compile or emit a path
that breaks at runtime.

## Subsets

Deliberate subsets stay at their own call sites and are built with `subset()`, which throws
on an unknown code. "Which locales have media published to R2" is a fact about a bucket, not
about the site; hoisting it here would make this file lie.

## The Python repos are NOT gated by console CI

`private/generative` and `private/growth` are separate, gitignored repos. They read
`site-locales.json` through a loader that RAISES if the file or a code is missing. Console
CI cannot see them, and no gate here covers them — do not assume otherwise.

Some Python lists are deliberately NOT derived from this file: `engine_qwen.py`'s
`LANGUAGE_LABELS`, `asr.py`'s `language_map` and `tts_bridge.py`'s `ASR_CAPTION_LANGS`
describe what third-party MODELS can voice or align, not what the site ships. Folding those
into a site-locale source is the category error that produced the wrong-language-audio bug.
