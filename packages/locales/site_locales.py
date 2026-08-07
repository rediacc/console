"""The site's locale set, for Python consumers.

Companion to `index.js` for the same `site-locales.json`. It lives HERE, beside the JSON,
rather than being copied into each pipeline, because the whole point is that there is one
place to change.

Why this exists: before it, 9 Python lists across 6 pipelines hand-maintained the same 13
codes in 5 different orderings, and nothing could tell a deliberate subset from a stale copy.

## The distinction that matters most

A list of locale codes in this repo is one of two completely different facts:

  (A) **SITE locales** - "the languages the site ships". Derive these from here.
  (B) **MODEL or TOOL capability** - "the languages Qwen3-ASR can align", "the languages
      Qwen3-TTS can voice". These must NOT be derived from here. They are independent facts
      about external software, and coupling them would make adding a 14th site locale
      silently assert TTS/aligner support that does not exist. The house bug in this repo is
      the silent language fallback, and this is exactly how one gets created.

`et` (Estonian) is the discriminator: it is a site locale, but no aligner in the stack
supports it. A 12-code list omitting `et` is almost always category B.

Known category B, deliberately NOT importing from here - do not "fix" these:
  - `tutorial_tts/engine_qwen.py::LANGUAGE_LABELS`
  - `tutorial_tts/asr.py::language_map`
  - `video_pipeline/tts_bridge.py::ASR_CAPTION_LANGS`
  - `tutorial_tts/cli.py::AUDIO_LANGUAGES` - borderline, but its `et` entry is justified by
    MEASUREMENT (samples transcribed back at 0.94/0.86/0.75 despite `et` being absent from
    the model's declared list), not by site membership. Use `assert_covered_by_site()` on it
    if you want a guard; do not derive it.

## Why this module's selftest is NOT in `npm run ci`

Every consumer lives under `private/`, which is gitignored, so CI never checks those trees out
and there is nothing here for CI to protect. Adding `python3 packages/locales/site_locales.py`
to the npm chain would make it the only `python3` in it, on a runner whose workflow sets up no
Python — a new dependency for zero coverage. Run it locally instead:

    python3 packages/locales/site_locales.py

What CI *does* enforce is the part that matters to it: `scripts/check-locale-sources.ts` fails
if `site-locales.json` drifts from `index.js`, in membership or in order. That is the failure
that would make the Python pipelines and the site ship different locale sets.

## Usage

Consumers live in gitignored trees with their own venvs, so there is no installable package
to depend on. Bootstrap by walking up for the marker file:

    import sys
    from pathlib import Path
    for _p in Path(__file__).resolve().parents:
        if (_p / "packages" / "locales" / "site-locales.json").exists():
            sys.path.insert(0, str(_p / "packages" / "locales"))
            break
    from site_locales import SITE_LOCALES, NON_ENGLISH_LOCALES, subset

Walking up for the *marker* rather than for a directory named `console` is deliberate: this
repo uses git worktrees, so the checkout is often not named `console`.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = [
    "DEFAULT_LOCALE",
    "NON_ENGLISH_LOCALES",
    "SITE_LOCALES",
    "assert_covered_by_site",
    "assert_site_locale",
    "is_site_locale",
    "subset",
]

_JSON_PATH = Path(__file__).resolve().parent / "site-locales.json"


def _load() -> tuple[tuple[str, ...], str]:
    with _JSON_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    locales = tuple(data["siteLocales"])
    default = data["defaultLocale"]
    # Fail at import, not at first use: a malformed source of truth should stop the process
    # while the stack trace still says which file is wrong.
    if not locales:
        raise ValueError(f"{_JSON_PATH}: siteLocales is empty")
    if len(set(locales)) != len(locales):
        raise ValueError(f"{_JSON_PATH}: siteLocales contains duplicates: {locales}")
    if default not in locales:
        raise ValueError(f"{_JSON_PATH}: defaultLocale {default!r} is not in siteLocales")
    return locales, default


SITE_LOCALES, DEFAULT_LOCALE = _load()

#: Every site locale except the default. This is the set most pipelines want, because English
#: is the source they translate FROM.
NON_ENGLISH_LOCALES: tuple[str, ...] = tuple(c for c in SITE_LOCALES if c != DEFAULT_LOCALE)


def is_site_locale(code: str) -> bool:
    """Non-raising membership test, for validating untrusted input."""
    return code in SITE_LOCALES


def assert_site_locale(code: str, *, where: str = "") -> str:
    """Return `code`, or raise if it is not a site locale.

    Use this at a boundary where a bad code would otherwise cause a SILENT fallback to
    English rather than a visible failure.
    """
    if code not in SITE_LOCALES:
        ctx = f" in {where}" if where else ""
        raise ValueError(
            f"{code!r} is not a site locale{ctx}. Known: {', '.join(SITE_LOCALES)}. "
            f"If this is a MODEL capability code rather than a site locale, do not route it "
            f"through this module - see the category A/B note in site_locales.py."
        )
    return code


def subset(name: str, codes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """A deliberate, named narrowing of the site set.

    This is the sanctioned way to express "only some locales", because unlike a bare literal
    it FAILS when a code is not a site locale - so a typo or a removed locale is loud. The
    `name` is required and appears in the error, so the reason for the narrowing has a place
    to live.
    """
    out: list[str] = []
    for code in codes:
        assert_site_locale(code, where=f"subset({name!r})")
        if code in out:
            raise ValueError(f"subset({name!r}): duplicate code {code!r}")
        out.append(code)
    return tuple(out)


def assert_covered_by_site(name: str, codes: object) -> None:
    """Assert every code in `codes` is a site locale, WITHOUT deriving it from the site set.

    This is the correct coupling for a category B list, and for an attribute map whose keys
    are per-locale but whose values are independent data. It catches a typo'd key while
    leaving the membership decision where it belongs.
    """
    unknown = sorted(c for c in codes if c not in SITE_LOCALES)  # type: ignore[union-attr]
    if unknown:
        raise ValueError(
            f"{name} contains code(s) that are not site locales: {', '.join(unknown)}. "
            f"Known: {', '.join(SITE_LOCALES)}."
        )


def _selftest() -> int:
    fails = 0

    def chk(label: str, cond: bool) -> None:
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}  {label}")
        if not cond:
            fails += 1

    chk("loads a non-empty site set", len(SITE_LOCALES) > 0)
    chk("default locale is a member", DEFAULT_LOCALE in SITE_LOCALES)
    chk(
        "non-english excludes exactly the default",
        len(NON_ENGLISH_LOCALES) == len(SITE_LOCALES) - 1,
    )
    chk("non-english omits the default", DEFAULT_LOCALE not in NON_ENGLISH_LOCALES)
    chk("order is preserved from the JSON", SITE_LOCALES[0] == "en")
    chk("is_site_locale accepts a member", is_site_locale(SITE_LOCALES[-1]))
    chk("is_site_locale rejects a non-member (control)", not is_site_locale("pt-BR"))

    # subset(): the whole reason it exists is that it FAILS where a literal would not.
    chk("subset returns the requested order", subset("t", ["de", "en"]) == ("de", "en"))
    try:
        subset("t", ["de", "xx"])
        chk("subset raises on an unknown code", False)
    except ValueError as exc:
        chk("subset raises on an unknown code", "xx" in str(exc))
        chk("subset error names the subset", "'t'" in str(exc))
    try:
        subset("t", ["de", "de"])
        chk("subset raises on a duplicate", False)
    except ValueError:
        chk("subset raises on a duplicate", True)

    try:
        assert_site_locale("nope")
        chk("assert_site_locale raises", False)
    except ValueError:
        chk("assert_site_locale raises", True)

    # assert_covered_by_site must accept a real category B list (12 codes, no `et`) and
    # reject a typo. If the first of these ever fails, someone has coupled a capability
    # list to the site set.
    try:
        assert_covered_by_site(
            "capability", ["en", "de", "es", "fr", "ja", "ru", "zh", "ko", "pt", "it", "tr", "ar"]
        )
        chk("a 12-code capability list is accepted, et absent (control)", True)
    except ValueError:
        chk("a 12-code capability list is accepted, et absent (control)", False)
    try:
        assert_covered_by_site("capability", ["en", "jp"])
        chk("assert_covered_by_site catches a typo'd key", False)
    except ValueError as exc:
        chk("assert_covered_by_site catches a typo'd key", "jp" in str(exc))

    if fails:
        print(f"\n{fails} self-test failure(s)")
        return 1
    print("\nsite_locales self-test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
