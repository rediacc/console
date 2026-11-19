"""The solution home page's video carries a Downloads link (review 11e5072e.1): the href, the translation key and the route it points at are pinned, so a change to any of the three fails here instead of shipping a dead link."""

from __future__ import annotations

import json

from rediacc_ci import paths

WWW = paths.repo_root() / "packages" / "www" / "src"
COMPONENT = WWW / "components" / "solution-pages" / "SPHomeVideo.astro"
ROUTE = WWW / "pages" / "[lang]" / "downloads.astro"
EN = WWW / "i18n" / "translations" / "en.json"
KEY = "pages.install.hero.downloadsLink"


def _has_key(doc: object, dotted: str) -> bool:
    """True when `dotted` resolves in the translation tree, flat or nested."""
    if isinstance(doc, dict) and dotted in doc:
        return True
    node = doc
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def test_the_home_video_links_to_the_downloads_route_with_an_existing_key() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    assert "href={`/${lang}/downloads`}" in source
    assert "t('%s')" % KEY in source
    assert ROUTE.is_file(), "the link points at a route that does not exist"
    assert _has_key(json.loads(EN.read_text(encoding="utf-8")), KEY)


def test_the_key_check_refuses_a_missing_key() -> None:
    """Control: a key absent from the tree, flat or nested, is not found."""
    assert not _has_key({"pages": {"install": {"hero": {}}}}, KEY)
    assert not _has_key({}, KEY)
    assert _has_key({KEY: "Downloads"}, KEY)
    assert _has_key({"pages": {"install": {"hero": {"downloadsLink": "Downloads"}}}}, KEY)
