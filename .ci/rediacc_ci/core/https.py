"""The one place `.ci` opens a URL with urllib, and the scheme check that makes that safe.

`urllib.request.urlopen` and `urllib.request.Request` accept `file:`, `ftp:` and custom schemes, so ruff's S310 reports every call whose URL is not a literal. Call sites carried a per-line marker saying "this one is a constant URL"; each is now a call to `build_request` or `urlopen` here, which REFUSES any other scheme, so the claim is checked at run time instead of asserted in a comment. S310 is per-file-ignored for this module only (pyproject.toml), where both urllib calls live.

`http` says what plain `http://` may reach. `"never"` (the default) refuses it. `"loopback"` admits `127.0.0.1`, `localhost` and `::1`, for a fixture server the caller started itself. `"any"` admits any host, for the dev drills, whose gateway answers on a bridge address with no certificate. No setting admits `file:`, `ftp:` or a custom scheme, which is what S310 exists to stop.

A refusal is `urllib.error.URLError`, an `OSError`, so a caller that already handles a failed fetch handles a refused one the same way.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    import http.client
    from collections.abc import Mapping

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def check_url(url: str, *, http: str = "never") -> str:
    """`url` unchanged when its scheme is allowed (see the module docstring); URLError otherwise."""
    parts = urllib.parse.urlsplit(url)
    if parts.hostname:
        if parts.scheme == "https":
            return url
        if parts.scheme == "http" and (
            http == "any" or (http == "loopback" and parts.hostname in LOOPBACK_HOSTS)
        ):
            return url
    raise urllib.error.URLError("refusing a URL this call may not open: %s" % url[:80])


def build_request(
    url: str,
    *,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    method: str | None = None,
    http: str = "never",
) -> urllib.request.Request:
    """A `Request` for `url` after the scheme check."""
    return urllib.request.Request(
        check_url(url, http=http),
        data=data,
        headers=dict(headers or {}),
        method=method,
    )


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """Follows a 3xx only to a URL `check_url` admits under the same `http` setting (review 1bf85a71.1): the default handler follows an https URL's redirect to `http://` or `ftp://`, which would reopen the hole the first check closes."""

    def __init__(self, http: str) -> None:
        super().__init__()
        self._http = http

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        check_url(newurl, http=self._http)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(
    *handlers: urllib.request.BaseHandler, http: str = "never"
) -> urllib.request.OpenerDirector:
    """`urllib.request.build_opener(*handlers)` whose redirects pass `check_url` under the same `http` setting (review 1bf85a71.2): a caller that needs cookies or another handler gets the redirect check too."""
    return urllib.request.build_opener(*handlers, _CheckedRedirect(http))


def urlopen(target: str | urllib.request.Request, *, timeout: float, http: str = "never") -> Any:
    """`urllib.request.urlopen(target, timeout=...)` after the scheme check, through an opener whose redirects pass the same check; the response is a context manager."""
    url = target if isinstance(target, str) else target.full_url
    check_url(url, http=http)
    return build_opener(http=http).open(target, timeout=timeout)
