"""`rediacc_ci.release.changelog_data`: the data of the www changelog page (PLAN-release-notes D10, D11).

Runs before `astro build` (chained in the www `build` script, since `ignore-scripts=true` also skips npm pre-scripts) and writes `packages/www/.astro/changelog.generated.json`, a gitignored file the page imports. The file lists every version with a GitHub Release, newest first, plus `APP_VERSION` on top when it is a real version not yet published. Each entry carries its groups from `cli/v<V>/release-notes.json` on the releases origin (`null` when the version has no notes file, which the page renders as "No customer notes recorded for this version") and its stable marker from `cli/stable/history.json` (D9): the oldest promoted version at or above it.

A failed fetch fails the build, the rule `downloads.astro` follows: an absent object (HTTP 404) is a state, any other failure is an error. With no `APP_VERSION` (the CI www build) only the published versions are listed.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import typing

from rediacc_ci.well_known import GH_API_BASE, GH_ORIGIN, GH_REPO, RELEASES_ORIGIN

SELF = "rediacc_ci.release.changelog_data"
_ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT_REL = "packages/www/.astro/changelog.generated.json"
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
TIMEOUT = 30

# (status, body): a transport failure raises ChangelogError, an HTTP status is returned as is.
Fetch = typing.Callable[[str], tuple[int, str]]


class ChangelogError(RuntimeError):
    """The page data cannot be built; the message says which fetch or record failed."""


def semver(text: str) -> tuple[int, int, int] | None:
    m = _SEMVER.match(text.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def http_fetch(token: str | None = None) -> Fetch:
    """A `Fetch` over the real `curl`; the GitHub token, when given, goes only to the GitHub API host and over stdin, never on argv."""

    def fetch(url: str) -> tuple[int, str]:
        config = 'header = "Accept: application/json"\n'
        if token and url.startswith(GH_API_BASE):
            config += 'header = "Authorization: Bearer %s"\n' % token
        proc = subprocess.run(
            ["curl", "-sS", "-m", str(TIMEOUT), "-K", "-", "-w", "\n%{http_code}", url],
            input=config,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            msg = "%s: curl rc=%d: %s" % (url, proc.returncode, proc.stderr.strip())
            raise ChangelogError(msg)
        body, _, code = proc.stdout.rpartition("\n")
        return int(code), body

    return fetch


def _json(url: str, status: int, text: str) -> typing.Any:
    if status != 200:
        msg = "%s answered HTTP %d" % (url, status)
        raise ChangelogError(msg)
    try:
        return json.loads(text)
    except ValueError as exc:
        msg = "%s did not return JSON: %s" % (url, exc)
        raise ChangelogError(msg) from exc


def list_releases(repo: str, fetch: Fetch) -> list[dict[str, str]]:
    """`{version, published_at, url}` for every non-draft Release whose tag is `vX.Y.Z`."""
    found: list[dict[str, str]] = []
    page = 1
    while True:
        url = "%s/repos/%s/releases?per_page=100&page=%d" % (GH_API_BASE, repo, page)
        rows = _json(url, *fetch(url))
        if not isinstance(rows, list):
            msg = "%s did not return a list of Releases" % url
            raise ChangelogError(msg)
        for row in rows:
            tag = str(row.get("tag_name", ""))
            if row.get("draft") or semver(tag) is None:
                continue
            fallback = "%s/%s/releases/tag/%s" % (GH_ORIGIN, repo, tag)
            found.append(
                {
                    "version": tag.removeprefix("v"),
                    "published_at": str(row.get("published_at") or ""),
                    "url": str(row.get("html_url") or fallback),
                }
            )
        if len(rows) < 100:
            return found
        page += 1


def stable_history(origin: str, fetch: Fetch) -> list[str]:
    """The promoted versions of `cli/stable/history.json`; no record yet (404) is an empty history."""
    url = origin + "/cli/stable/history.json"
    status, text = fetch(url)
    if status == 404:
        return []
    rows = _json(url, status, text)
    if not isinstance(rows, list):
        msg = "%s is not a list of rows" % url
        raise ChangelogError(msg)
    return [
        str(r["version"]).removeprefix("v")
        for r in rows
        if isinstance(r, dict) and r.get("version")
    ]


def stable_since(version: str, history: list[str]) -> str | None:
    """The oldest promoted version at or above `version` (D9), or None when no promote reached it."""
    own = semver(version)
    if own is None:
        return None
    reached = sorted(
        (s for s in history if (v := semver(s)) is not None and v >= own),
        key=lambda s: semver(s) or (0, 0, 0),
    )
    return reached[0] if reached else None


def notes_for(version: str, origin: str, fetch: Fetch) -> dict[str, list[str]] | None:
    """The groups of `cli/v<V>/release-notes.json`, or None when the version has no notes file."""
    url = "%s/cli/v%s/release-notes.json" % (origin, version)
    status, text = fetch(url)
    if status == 404:
        return None
    doc = _json(url, status, text)
    groups = doc.get("groups") if isinstance(doc, dict) else None
    if not isinstance(groups, dict):
        msg = "%s carries no `groups` object" % url
        raise ChangelogError(msg)
    return {str(k): [str(n) for n in v] for k, v in groups.items() if v}


def build(
    app_version: str | None,
    fetch: Fetch,
    repo: str = GH_REPO,
    origin: str = RELEASES_ORIGIN,
) -> dict[str, typing.Any]:
    """The page document: `{versions: [...]}` newest first, `APP_VERSION` on top when unpublished."""
    releases = {r["version"]: r for r in list_releases(repo, fetch)}
    version_in = (app_version or "").strip().removeprefix("v")
    if version_in and semver(version_in) is not None and version_in not in releases:
        releases[version_in] = {"version": version_in, "published_at": "", "url": ""}
    history = stable_history(origin, fetch)
    entries = []
    for version in sorted(releases, key=lambda v: semver(v) or (0, 0, 0), reverse=True):
        row = releases[version]
        entries.append(
            {
                "version": version,
                "published_at": row["published_at"],
                "url": row["url"],
                "groups": notes_for(version, origin, fetch),
                "stable_since": stable_since(version, history),
            }
        )
    return {"versions": entries}


def write(doc: dict[str, typing.Any], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[0]) if argv else _ROOT / OUT_REL
    token = os.environ.get("GITHUB_TOKEN") or None
    origin = (os.environ.get("RELEASES_ORIGIN") or RELEASES_ORIGIN).rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY") or GH_REPO
    try:
        doc = build(os.environ.get("APP_VERSION"), http_fetch(token), repo, origin)
    except ChangelogError as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return 1
    write(doc, out)
    print("%s: wrote %d version(s) to %s" % (SELF, len(doc["versions"]), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
